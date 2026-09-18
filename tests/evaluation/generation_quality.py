# -*- coding: utf-8 -*-
"""生成质量评测脚本：忠实度（faithfulness）+ 答案正确性（correctness）。

评测流程（端到端）：
1. 对测试集每道题执行混合检索得到参考上下文（复用 evaluator_utils.retrieve_top_k）
2. 用 ANSWER_PROMPT 让大模型基于参考上下文生成答案
3. 大模型裁判（LLM-as-judge）分别打分：
   - 忠实度 faithfulness（1-5）：答案是否由参考上下文支撑、有无编造
   - 正确性 correctness（1-5）：答案与参考答案语义是否一致、是否覆盖关键事实点
4. 规则性检查：答案非空、长度合理性

输出分类型汇总、平均分与 Markdown 报告。

用法示例：
    python tests/evaluation/generation_quality.py --k 5
    python tests/evaluation/generation_quality.py --k 5 --output reports/quality.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from evaluator_utils import load_datasets, retrieve_top_k
from langchain_core.messages import HumanMessage

# 复用线上答案生成提示词
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from knowledge_base.query_process.prompt import ANSWER_PROMPT  # noqa: E402
from knowledge_base.utils.llm_utils import get_llm_client  # noqa: E402

DEFAULT_DATASET_DIR = str(Path(__file__).resolve().parent / "dataset")

MAX_CONTEXT_CHARS = 12000

FAITHFULNESS_JUDGE_PROMPT = """你是一名严格的评测裁判。请判断【助手回答】是否忠实于【参考上下文】，即回答中的关键事实是否都能从参考上下文中找到依据，是否存在编造、夸大或无中生有的内容。

【问题】
{question}

【参考上下文】
{context}

【助手回答】
{answer}

评分标准（1-5分）：
- 5分：回答完全由参考上下文支撑，无任何编造
- 4分：回答绝大部分有依据，仅极少量轻微细节不完全贴合
- 3分：回答大体有依据，但存在个别无依据的表述
- 2分：回答有较多无依据或与上下文冲突的内容
- 1分：回答基本脱离上下文或大量编造

请直接返回JSON，格式如下：
{{"score": 5, "reason": "一句话说明理由"}}"""

CORRECTNESS_JUDGE_PROMPT = """你是一名严格的评测裁判。请判断【助手回答】与【参考答案】是否语义一致、是否覆盖了关键事实点。

【问题】
{question}

【参考答案】
{reference_answer}

【助手回答】
{answer}

评分标准（1-5分）：
- 5分：关键事实点全部覆盖且准确
- 4分：覆盖了大部分关键事实点，无明显错误
- 3分：覆盖部分关键事实点，有少量遗漏或轻微偏差
- 2分：遗漏较多关键事实点或存在明显错误
- 1分：基本未覆盖关键事实点或结论错误

请直接返回JSON，格式如下：
{{"score": 5, "reason": "一句话说明理由"}}"""


def _format_context(chunks: list[dict]) -> str:
    """将检索切片格式化为参考上下文，控制总长度。"""
    parts = []
    used = 0
    for i, c in enumerate(chunks, start=1):
        title = c.get("file_title") or c.get("title") or ""
        content = c.get("content") or ""
        block = f"[{i}][来源:{title}]\n{content}"
        if used + len(block) > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - used
            if remaining > 200:
                block = block[:remaining]
            else:
                break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _generate_answer(question: str, context: str, model: str | None) -> str:
    """基于参考上下文生成答案（非流式）。"""
    prompt = ANSWER_PROMPT.format(context=context, history="", item_names="", question=question)
    llm = get_llm_client(model=model, json_mode=False)
    resp = llm.invoke([HumanMessage(content=prompt)])
    return (resp.content or "").strip()


def _judge(prompt: str, model: str | None) -> tuple[int, str]:
    """调用裁判模型返回 (score, reason)。"""
    llm = get_llm_client(model=model, json_mode=True)
    resp = llm.invoke([HumanMessage(content=prompt)])
    text = (resp.content or "").strip()
    # 兼容可能被包裹的 markdown 代码块
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    data = None
    try:
        data = json.loads(text)
        score = int(data.get("score", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        # 兜底：尝试从文本中抽取数字
        match = re.search(r"([1-5])", text)
        score = int(match.group(1)) if match else 0
    reason = data.get("reason", "") if isinstance(data, dict) else ""
    return score, reason


def _rule_checks(answer: str) -> list[str]:
    """规则性检查，返回异常提示列表（空列表表示通过）。"""
    problems = []
    if not answer:
        problems.append("答案为空")
    elif len(answer) < 10:
        problems.append(f"答案过短({len(answer)}字)")
    elif len(answer) > 3000:
        problems.append(f"答案过长({len(answer)}字)")
    return problems


def run(dataset_dir: str, k: int, candidate_limit: int,
        departments: list[str] | None, clearance_level: int | None,
        gen_model: str | None, judge_model: str | None,
        limit: int | None) -> tuple[dict, list]:
    """执行生成质量评测，返回 (汇总统计, 逐条明细)。"""
    items = load_datasets(dataset_dir)
    if not items:
        raise RuntimeError(f"未在 {dataset_dir} 找到任何评测条目")
    if limit:
        items = items[:limit]

    by_category = defaultdict(lambda: {"total": 0, "faith_sum": 0, "corr_sum": 0})
    details = []
    faith_scores = []
    corr_scores = []

    for idx, item in enumerate(items, start=1):
        question = item["question"]
        reference = item.get("reference_answer") or ""
        category = item.get("category", "未知")
        perm = item.get("permission") or {}
        depts = departments if departments is not None else perm.get("departments")
        level = clearance_level if clearance_level is not None else perm.get("clearance_level")

        print(f"[{idx}/{len(items)}] 评测 {item['id']} ({category}) ...", file=sys.stderr)

        try:
            chunks = retrieve_top_k(question, k=k, departments=depts,
                                    clearance_level=level, candidate_limit=candidate_limit)
            context = _format_context(chunks)
            answer = _generate_answer(question, context, gen_model)
        except Exception as exc:
            details.append({
                "id": item["id"], "category": category, "question": question,
                "answer_len": 0, "faithfulness": None, "correctness": None,
                "rules_ok": False, "error": str(exc),
            })
            by_category[category]["total"] += 1
            continue

        problems = _rule_checks(answer)
        rules_ok = not problems

        faith = corr = None
        try:
            faith, faith_reason = _judge(
                FAITHFULNESS_JUDGE_PROMPT.format(question=question, context=context, answer=answer),
                judge_model,
            )
        except Exception:
            faith, faith_reason = None, "裁判调用失败"
        try:
            corr, corr_reason = _judge(
                CORRECTNESS_JUDGE_PROMPT.format(question=question, reference_answer=reference, answer=answer),
                judge_model,
            )
        except Exception:
            corr, corr_reason = None, "裁判调用失败"

        if faith is not None:
            faith_scores.append(faith)
            by_category[category]["faith_sum"] += faith
        if corr is not None:
            corr_scores.append(corr)
            by_category[category]["corr_sum"] += corr
        by_category[category]["total"] += 1

        details.append({
            "id": item["id"], "category": category, "question": question,
            "reference": reference, "answer": answer, "answer_len": len(answer),
            "faithfulness": faith, "correctness": corr,
            "rules_ok": rules_ok, "problems": problems,
        })

    summary = {
        "total": len(items),
        "k": k,
        "avg_faithfulness": round(sum(faith_scores) / len(faith_scores), 2) if faith_scores else None,
        "avg_correctness": round(sum(corr_scores) / len(corr_scores), 2) if corr_scores else None,
        "rule_pass": sum(1 for d in details if d.get("rules_ok")),
        "by_category": dict(by_category),
    }
    return summary, details


def _avg(cat_sum: int, total: int) -> str:
    if total == 0:
        return "-"
    return f"{cat_sum / total:.2f}"


def _print_report(summary: dict) -> None:
    print("=" * 72)
    print(f"生成质量评测结果  (Top-K = {summary['k']})")
    print("=" * 72)
    print(f"总条目数         : {summary['total']}")
    print(f"平均忠实度       : {summary['avg_faithfulness']}")
    print(f"平均正确性       : {summary['avg_correctness']}")
    print(f"规则检查通过率   : {summary['rule_pass']}/{summary['total']}")
    print("-" * 72)
    print(f"{'类别':<14}{'条数':>4}{'平均忠实度':>10}{'平均正确性':>10}")
    for cat, stat in sorted(summary["by_category"].items()):
        print(f"{cat:<14}{stat['total']:>4}"
              f"{_avg(stat['faith_sum'], stat['total']):>10}"
              f"{_avg(stat['corr_sum'], stat['total']):>10}")
    print("=" * 72)


def _write_markdown(summary: dict, details: list, output: str) -> None:
    lines = []
    lines.append("# 生成质量评测报告")
    lines.append("")
    lines.append(f"- 总条目数：{summary['total']}")
    lines.append(f"- Top-K：{summary['k']}")
    lines.append(f"- 平均忠实度：{summary['avg_faithfulness']}")
    lines.append(f"- 平均正确性：{summary['avg_correctness']}")
    lines.append(f"- 规则检查通过率：{summary['rule_pass']}/{summary['total']}")
    lines.append("")
    lines.append("## 分类型统计")
    lines.append("")
    lines.append("| 类别 | 条数 | 平均忠实度 | 平均正确性 |")
    lines.append("| --- | ---: | ---: | ---: |")
    for cat, stat in sorted(summary["by_category"].items()):
        lines.append(f"| {cat} | {stat['total']} | "
                     f"{_avg(stat['faith_sum'], stat['total'])} | "
                     f"{_avg(stat['corr_sum'], stat['total'])} |")
    lines.append("")
    lines.append("## 逐条明细")
    lines.append("")
    lines.append("| ID | 类别 | 问题 | 忠实度 | 正确性 | 规则通过 |")
    lines.append("| --- | --- | --- | ---: | ---: | --- |")
    for d in details:
        if d.get("error"):
            lines.append(f"| {d['id']} | {d['category']} | {d['question']} | - | - | 错误:{d['error']} |")
            continue
        problems = "；".join(d.get("problems") or []) or "✔"
        lines.append(f"| {d['id']} | {d['category']} | {d['question']} | "
                     f"{d['faithfulness']} | {d['correctness']} | {problems} |")
    lines.append("")

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入：{out_path.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成质量评测（忠实度 + 正确性）")
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR, help="测试集目录")
    parser.add_argument("--k", type=int, default=5, help="检索 Top-K 值")
    parser.add_argument("--candidate-limit", type=int, default=20, help="ANN 候选池大小")
    parser.add_argument("--output", default=None, help="Markdown 报告输出路径（可选）")
    parser.add_argument("--departments", default=None, help="覆盖用户部门，逗号分隔（可选）")
    parser.add_argument("--clearance-level", type=int, default=None, help="覆盖用户密级（可选）")
    parser.add_argument("--gen-model", default=None, help="生成模型名称（可选，默认取配置）")
    parser.add_argument("--judge-model", default=None, help="裁判模型名称（可选，默认取配置）")
    parser.add_argument("--limit", type=int, default=None, help="仅评测前 N 条（调试用）")
    args = parser.parse_args()

    departments = [d.strip() for d in args.departments.split(",") if d.strip()] if args.departments else None

    try:
        summary, details = run(
            args.dataset_dir, args.k, args.candidate_limit,
            departments, args.clearance_level,
            args.gen_model, args.judge_model, args.limit,
        )
    except RuntimeError as exc:
        print(f"评测失败：{exc}", file=sys.stderr)
        return 1

    _print_report(summary)
    if args.output:
        _write_markdown(summary, details, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""检索召回率（Recall@K / Hit Rate@K）评测脚本。

对测试集中每道题执行一次混合向量检索（与线上 node_search_embedding 一致），
统计：
- 文档命中率（Recall@K）：Top-K 中是否命中期望源文档（file_title 精确匹配）
- 关键词命中率：Top-K 正文是否命中期望关键词（去空白子串匹配）
- 无结果率：Top-K 为空的条目占比
- 权限过滤正确率：expect_hit=false 的负例条目，Top-K 中不应命中期望文档

用法示例：
    python tests/evaluation/recall_at_k.py --k 5
    python tests/evaluation/recall_at_k.py --k 10 --output reports/recall.md
    python tests/evaluation/recall_at_k.py --departments 售后部 --clearance-level 3
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from evaluator_utils import (
    check_doc_hit,
    check_keyword_hit,
    load_datasets,
    retrieve_top_k,
)

DEFAULT_DATASET_DIR = str(Path(__file__).resolve().parent / "dataset")


def _fmt_rate(hit: int, total: int) -> str:
    if total == 0:
        return "-"
    return f"{hit}/{total} ({hit / total * 100:.1f}%)"


def run(dataset_dir: str, k: int, candidate_limit: int,
        departments: list[str] | None, clearance_level: int | None) -> tuple[dict, list]:
    """执行评测，返回 (汇总统计字典, 逐条明细列表)。"""
    items = load_datasets(dataset_dir)
    if not items:
        raise RuntimeError(f"未在 {dataset_dir} 找到任何评测条目")

    total = 0
    doc_hits = keyword_hits = no_results = 0
    # 负例（expect_hit=false）权限过滤正确率统计
    neg_total = neg_correct = 0

    by_category = defaultdict(lambda: {"total": 0, "doc_hit": 0, "keyword_hit": 0, "no_result": 0})
    details = []

    for item in items:
        category = item.get("category", "未知")
        question = item["question"]
        expected_titles = item.get("expected_doc_titles") or []
        expected_keywords = item.get("expected_hit_keywords") or []
        expect_hit = item.get("expect_hit", True)
        perm = item.get("permission") or {}
        depts = departments if departments is not None else perm.get("departments")
        level = clearance_level if clearance_level is not None else perm.get("clearance_level")

        try:
            chunks = retrieve_top_k(question, k=k, departments=depts,
                                    clearance_level=level, candidate_limit=candidate_limit)
        except Exception as exc:  # 单条失败不中断整体评测
            details.append({
                "id": item["id"], "category": category, "question": question,
                "retrieved": 0, "doc_hit": None, "keyword_hit": None,
                "expect_hit": expect_hit, "error": str(exc),
            })
            if expect_hit:
                by_category[category]["total"] += 1
                total += 1
            continue

        doc_hit = check_doc_hit(chunks, expected_titles)
        keyword_hit = check_keyword_hit(chunks, expected_keywords)
        is_empty = len(chunks) == 0

        # 负例：只统计权限过滤正确率，不进入正例召回统计
        if not expect_hit:
            neg_total += 1
            if not doc_hit:
                neg_correct += 1
            details.append({
                "id": item["id"], "category": category, "question": question,
                "retrieved": len(chunks),
                "doc_hit": doc_hit, "keyword_hit": keyword_hit,
                "expect_hit": expect_hit,
                "top_titles": [c.get("file_title", "") for c in chunks[:k]],
            })
            continue

        total += 1
        by_category[category]["total"] += 1
        if is_empty:
            no_results += 1
            by_category[category]["no_result"] += 1
        if doc_hit:
            doc_hits += 1
            by_category[category]["doc_hit"] += 1
        if keyword_hit:
            keyword_hits += 1
            by_category[category]["keyword_hit"] += 1

        details.append({
            "id": item["id"], "category": category, "question": question,
            "retrieved": len(chunks),
            "doc_hit": doc_hit, "keyword_hit": keyword_hit,
            "expect_hit": expect_hit,
            "top_titles": [c.get("file_title", "") for c in chunks[:k]],
        })

    summary = {
        "total": total,
        "k": k,
        "doc_hit": doc_hits,
        "keyword_hit": keyword_hits,
        "no_result": no_results,
        "neg_total": neg_total,
        "neg_correct": neg_correct,
        "by_category": dict(by_category),
    }
    return summary, details


def _print_report(summary: dict, details: list) -> None:
    total = summary["total"]
    print("=" * 72)
    print(f"检索召回率评测结果  (Top-K = {summary['k']})")
    print("=" * 72)
    print(f"总条目数         : {total}")
    print(f"文档命中率@K     : {_fmt_rate(summary['doc_hit'], total)}")
    print(f"关键词命中率@K   : {_fmt_rate(summary['keyword_hit'], total)}")
    print(f"无结果率         : {_fmt_rate(summary['no_result'], total)}")
    if summary["neg_total"]:
        print(f"权限过滤正确率   : {_fmt_rate(summary['neg_correct'], summary['neg_total'])}  (负例 {summary['neg_total']} 条)")
    print("-" * 72)

    print(f"{'类别':<14}{'条数':>4}{'文档命中':>12}{'关键词命中':>12}{'无结果':>8}")
    for cat, stat in sorted(summary["by_category"].items()):
        print(f"{cat:<14}{stat['total']:>4}"
              f"{_fmt_rate(stat['doc_hit'], stat['total']):>12}"
              f"{_fmt_rate(stat['keyword_hit'], stat['total']):>12}"
              f"{stat['no_result']:>8}")
    print("-" * 72)

    # 未命中的正例明细
    misses = [d for d in details if d.get("doc_hit") is False and d.get("expect_hit") is True]
    if misses:
        print("未命中正例明细：")
        for d in misses:
            print(f"  - [{d['id']}] ({d['category']}) {d['question']}")
    print("=" * 72)


def _write_markdown(summary: dict, details: list, output: str) -> None:
    lines = []
    total = summary["total"]
    lines.append("# 检索召回率评测报告")
    lines.append("")
    lines.append(f"- 总条目数：{total}")
    lines.append(f"- Top-K：{summary['k']}")
    lines.append(f"- 文档命中率@K：{_fmt_rate(summary['doc_hit'], total)}")
    lines.append(f"- 关键词命中率@K：{_fmt_rate(summary['keyword_hit'], total)}")
    lines.append(f"- 无结果率：{_fmt_rate(summary['no_result'], total)}")
    if summary["neg_total"]:
        lines.append(f"- 权限过滤正确率：{_fmt_rate(summary['neg_correct'], summary['neg_total'])}（负例 {summary['neg_total']} 条）")
    lines.append("")
    lines.append("## 分类型统计")
    lines.append("")
    lines.append("| 类别 | 条数 | 文档命中 | 关键词命中 | 无结果 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for cat, stat in sorted(summary["by_category"].items()):
        lines.append(f"| {cat} | {stat['total']} | "
                     f"{_fmt_rate(stat['doc_hit'], stat['total'])} | "
                     f"{_fmt_rate(stat['keyword_hit'], stat['total'])} | "
                     f"{stat['no_result']} |")
    lines.append("")
    lines.append("## 逐条明细")
    lines.append("")
    lines.append("| ID | 类别 | 问题 | 返回数 | 文档命中 | 关键词命中 | 期望命中 | 命中标题 |")
    lines.append("| --- | --- | --- | ---: | --- | --- | --- | --- |")
    for d in details:
        hit_mark = {True: "✔", False: "✘", None: "-"}[d.get("doc_hit")]
        kw_mark = {True: "✔", False: "✘", None: "-"}[d.get("keyword_hit")]
        titles = "；".join(d.get("top_titles") or []) or "（无结果）"
        err = f"<br/>错误：{d.get('error')}" if d.get("error") else ""
        lines.append(f"| {d['id']} | {d['category']} | {d['question']} | "
                     f"{d['retrieved']} | {hit_mark} | {kw_mark} | {d.get('expect_hit', True)} | {titles}{err} |")
    lines.append("")

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入：{out_path.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="检索召回率（Recall@K）评测")
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR, help="测试集目录")
    parser.add_argument("--k", type=int, default=5, help="Top-K 值")
    parser.add_argument("--candidate-limit", type=int, default=20, help="ANN 候选池大小")
    parser.add_argument("--output", default=None, help="Markdown 报告输出路径（可选）")
    parser.add_argument("--departments", default=None, help="覆盖用户部门，逗号分隔（可选）")
    parser.add_argument("--clearance-level", type=int, default=None, help="覆盖用户密级（可选）")
    args = parser.parse_args()

    departments = [d.strip() for d in args.departments.split(",") if d.strip()] if args.departments else None

    try:
        summary, details = run(args.dataset_dir, args.k, args.candidate_limit,
                               departments, args.clearance_level)
    except RuntimeError as exc:
        print(f"评测失败：{exc}", file=sys.stderr)
        return 1

    _print_report(summary, details)
    if args.output:
        _write_markdown(summary, details, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

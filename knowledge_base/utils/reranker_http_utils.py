# knowledge_base/utils/reranker_http_utils.py
"""LLM-as-reranker：通过 OpenAI 兼容接口调用 LLM 对候选文档打分重排。

原实现依赖阿里云 DashScope 的 TextReRank 专有接口（qwen3-rerank），
要求使用 DashScope 的 API Key。为兼容通用 OpenAI 兼容 LLM（如 DeepSeek），
改为「LLM 打分」方式：一次性把候选文档列表发给 LLM，让其输出每篇文档与
查询的相关性分数（0~1），再按分数重排。

若 LLM 打分失败，返回 0 分（不阻断主流程），由上层按 RRF 分数兜底排序。
"""

import json
import logging
from typing import List

from knowledge_base.config.config import lm_config, reranker_http_config
from knowledge_base.utils.llm_utils import get_llm_client

logger = logging.getLogger(__name__)

# 每批最多送多少篇文档给 LLM 打分（避免超长上下文）
_BATCH_SIZE = 20

# 单篇文档截断长度（字符），防止超长 chunk 撑爆上下文
_DOC_SNIPPET_MAX = 800

_RERANK_SYSTEM_PROMPT = (
    "你是信息检索相关性评估助手。请根据用户查询，评估每个候选文档与查询的相关程度，"
    "为每篇文档打 0~1 的相关性分数（1 表示高度相关，0 表示完全不相关）。"
    "只输出 JSON，不要输出任何其它文字或解释。"
)


def _build_user_prompt(query: str, documents: List[str]) -> str:
    lines = [f"用户查询：{query}", "", "候选文档："]
    for i, doc in enumerate(documents):
        snippet = doc if len(doc) <= _DOC_SNIPPET_MAX else doc[:_DOC_SNIPPET_MAX]
        lines.append(f"[{i}] {snippet}")
    lines.append("")
    lines.append(
        f'请输出 JSON：{{"scores": [分数0, 分数1, ...]}}，数组长度必须为 {len(documents)}，'
        "每个分数为 0~1 的小数（可保留两位）。"
    )
    return "\n".join(lines)


def rerank_documents(query: str, documents: list) -> List[float]:
    if not documents:
        return []

    # 重排模型：优先用 TEXT_RERANK_MODEL，缺省回退到主 LLM 模型
    model = reranker_http_config.model or lm_config.llm_model
    llm = get_llm_client(model=model, json_mode=True)

    scores: List[float] = [0.0] * len(documents)
    for start in range(0, len(documents), _BATCH_SIZE):
        batch = documents[start : start + _BATCH_SIZE]
        user_prompt = _build_user_prompt(query, batch)
        try:
            resp = llm.invoke([("system", _RERANK_SYSTEM_PROMPT), ("user", user_prompt)])
            content = resp.content if hasattr(resp, "content") else str(resp)
            # 兼容部分模型在 JSON 外包裹代码块 ```json ... ```
            content = content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
            batch_scores = data.get("scores", []) if isinstance(data, dict) else data
            for i, s in enumerate(batch_scores[: len(batch)]):
                try:
                    scores[start + i] = float(s)
                except (TypeError, ValueError):
                    scores[start + i] = 0.0
        except Exception as e:
            logger.warning(f"reranker LLM 打分失败，返回 0 分兜底: {e}")
            for i in range(len(batch)):
                scores[start + i] = 0.0
    return scores


if __name__ == "__main__":
    query = "什么是重排序模型"
    documents = [
        "重排序模型广泛应用于搜索引擎和推荐系统，按相关性对候选文本进行排序。",
        "量子计算是计算科学的前沿领域。",
        "预训练语言模型的发展为重排序模型带来了新的进展。",
    ]
    print(rerank_documents(query, documents))

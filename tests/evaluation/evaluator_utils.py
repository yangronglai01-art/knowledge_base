# -*- coding: utf-8 -*-
"""评测公共工具：测试集加载、向量检索、命中判定。

供 recall_at_k.py 与 generation_quality.py 复用。直接调用 knowledge_base 内部
的 embedding / milvus / permission 工具，确保与线上查询链路（node_search_embedding）
保持一致的检索行为（混合检索权重 0.8/0.2、norm_score=True）。

运行前置条件：
- 已配置 .env（MILVUS_URL、CHUNKS_COLLECTION、BGE_M3*、LLM_* 等）
- Milvus 中已导入 data/documents 对应的知识库切片
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 将项目根目录加入 sys.path，保证脚本以任意目录方式运行时均可 import knowledge_base
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_base.config.config import milvus_config, permission_config  # noqa: E402
from knowledge_base.utils.embedding_utils import generate_embeddings  # noqa: E402
from knowledge_base.utils.milvus_utils import (  # noqa: E402
    create_hybrid_search_request,
    hybrid_search,
)
from knowledge_base.utils.permission_utils import build_permission_filter  # noqa: E402

# 检索时回读的切片字段（与 node_search_embedding 一致，额外回读标题类字段用于命中判定）
OUTPUT_FIELDS = [
    "chunk_id",
    "content",
    "title",
    "file_title",
    "parent_title",
    "item_name",
    "dept",
    "clearance_level",
]

# 混合检索权重与归一化，与线上 node_search_embedding 保持一致
RANKER_WEIGHTS = (0.8, 0.2)
NORM_SCORE = True


def load_datasets(dataset_dir: str) -> List[Dict[str, Any]]:
    """加载 dataset 目录下所有 JSON 测试集，返回展平后的条目列表。

    每个条目自动附加 category 字段；未声明 expect_hit 时默认 True（期望命中）。
    """
    dataset_dir = Path(dataset_dir)
    items: List[Dict[str, Any]] = []
    for path in sorted(dataset_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        category = data.get("category", path.stem)
        for it in data.get("items", []):
            item = dict(it)
            item.setdefault("category", category)
            item.setdefault("expect_hit", True)
            items.append(item)
    return items


def _normalize(text: Any) -> str:
    """去掉所有空白字符，用于容错的关键词/正文子串匹配。"""
    if text is None:
        return ""
    return "".join(str(text).split())


def _get_entity(hit: Any) -> Dict[str, Any]:
    """从混合搜索命中中提取 output_fields 实体字典，兼容 dict 与对象两种返回形式。"""
    if isinstance(hit, dict):
        return hit.get("entity") or {}
    entity = getattr(hit, "entity", None)
    return entity or {}


def _get_score(hit: Any) -> Optional[float]:
    """提取检索得分（hybrid_search 命中对象上的 distance/score）。"""
    if isinstance(hit, dict):
        for key in ("distance", "score"):
            if hit.get(key) is not None:
                return float(hit[key])
    for attr in ("distance", "score"):
        value = getattr(hit, attr, None)
        if value is not None:
            return float(value)
    return None


def retrieve_top_k(
    question: str,
    k: int = 5,
    departments: Optional[List[str]] = None,
    clearance_level: Optional[int] = None,
    candidate_limit: int = 20,
) -> List[Dict[str, Any]]:
    """对单个问题执行混合向量检索，返回 Top-K 切片（每项为字段字典，含 _score）。

    :param question: 查询文本
    :param k: 返回 Top-K 数量
    :param departments: 用户部门列表（用于权限过滤，可空）
    :param clearance_level: 用户密级（用于权限过滤，可空）
    :param candidate_limit: 每个 ANN 分支的候选池大小（需 >= k）
    """
    embeddings = generate_embeddings([question])
    dense_vector = embeddings.get("dense")[0]
    sparse_vector = embeddings.get("sparse")[0]

    # 权限过滤（沿用线上权限模型）
    expr = None
    if permission_config.filter_enabled and (departments or clearance_level is not None):
        expr = build_permission_filter(departments, clearance_level)

    req_limit = max(candidate_limit, k)
    reqs = create_hybrid_search_request(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        expr=expr,
        limit=req_limit,
    )
    res = hybrid_search(
        collection_name=milvus_config.chunks_collection,
        reqs=reqs,
        ranker_weights=RANKER_WEIGHTS,
        norm_score=NORM_SCORE,
        limit=k,
        output_fields=OUTPUT_FIELDS,
    )

    hits = res[0] if res else []
    chunks: List[Dict[str, Any]] = []
    for hit in hits:
        entity = _get_entity(hit)
        if not entity:
            continue
        record = dict(entity)
        record["_score"] = _get_score(hit)
        chunks.append(record)
    return chunks


def check_doc_hit(chunks: List[Dict[str, Any]], expected_doc_titles: List[str]) -> bool:
    """判断 Top-K 结果中是否命中任意一篇期望文档（按 file_title 精确匹配）。"""
    if not expected_doc_titles:
        return False
    titles = {str(c.get("file_title", "")) for c in chunks}
    return any(str(t) in titles for t in expected_doc_titles)


def check_keyword_hit(chunks: List[Dict[str, Any]], expected_keywords: List[str]) -> bool:
    """判断 Top-K 结果正文是否命中任意一个期望关键词（去空白后子串匹配）。"""
    if not expected_keywords:
        return False
    normalized_content = _normalize(" ".join(str(c.get("content", "")) for c in chunks))
    for kw in expected_keywords:
        if _normalize(kw) in normalized_content:
            return True
    return False

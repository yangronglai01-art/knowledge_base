# -*- coding: utf-8 -*-
"""查询监控指标工具 + 轻量告警规则。

查询链路各节点按 task_id 幂等 upsert 指标字段到 MongoDB 的 query_metrics 集合，
最终形成一条完整的查询监控记录，字段包括：
- session_id / task_id / question / status
- retrieval_latency_ms：检索延迟（node_search_embedding）
- generation_latency_ms：答案生成延迟（node_answer_output）
- total_latency_ms：整条查询总延迟（query_service）
- retrieval_count：检索召回切片数
- rerank_count：重排序后保留切片数
- answer_length / no_result：答案长度 / 是否无结果
- error：失败原因

并提供聚合统计与轻量告警规则（阈值触发即记录告警日志）：
- 无结果率 > 30%
- 失败率 > 20%
- 平均检索延迟 > 3s
- 平均生成延迟 > 30s
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient, DESCENDING

from knowledge_base.config.config import mongo_config
from knowledge_base.tool.logger import logger

# 轻量告警阈值（可按需调整）
NO_RESULT_RATE_THRESHOLD = 0.30        # 无结果率阈值
ERROR_RATE_THRESHOLD = 0.20            # 失败率阈值
AVG_RETRIEVAL_LATENCY_MS = 3000.0      # 平均检索延迟阈值（毫秒）
AVG_GENERATION_LATENCY_MS = 30000.0    # 平均生成延迟阈值（毫秒）


class MetricsMongoTool:
    """查询指标 MongoDB 访问器（懒加载）。"""

    def __init__(self):
        try:
            self.client = MongoClient(mongo_config.mongo_url)
            self.db = self.client[mongo_config.mongo_db_name]
            self.collection = self.db["query_metrics"]
            self.collection.create_index([("task_id", 1)], unique=True)
            self.collection.create_index([("created_at", -1)])
            logger.info("指标MongoDB连接成功")
        except Exception as e:
            logger.exception(f"指标MongoDB连接失败: {e}")
            raise


_metrics_tool: Optional[MetricsMongoTool] = None


def get_metrics_tool() -> MetricsMongoTool:
    global _metrics_tool
    if _metrics_tool is None:
        _metrics_tool = MetricsMongoTool()
    return _metrics_tool


def record_query_metric(task_id: str, **fields: Any) -> None:
    """按 task_id 幂等 upsert 一条查询指标（多节点分次写入累加字段）。

    任何异常都会被吞掉并记录告警日志，绝不阻断查询主流程。
    """
    if not task_id:
        return
    try:
        tool = get_metrics_tool()
        now = datetime.now().timestamp()
        tool.collection.update_one(
            {"task_id": task_id},
            {
                "$set": {**fields, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"记录查询指标失败: {e}")


def get_recent_metrics(window_seconds: int = 300, limit: int = 200) -> List[Dict[str, Any]]:
    """获取最近时间窗口内的查询指标（时间倒序）。"""
    try:
        tool = get_metrics_tool()
        cutoff = datetime.now().timestamp() - window_seconds
        cursor = (
            tool.collection.find({"created_at": {"$gte": cutoff}})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        return list(cursor)
    except Exception as e:
        logger.error(f"查询指标失败: {e}")
        return []


def aggregate_metrics(metrics: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """聚合一批查询指标，返回汇总统计。无数据返回 None。"""
    if not metrics:
        return None
    total = len(metrics)
    no_result_count = sum(1 for m in metrics if m.get("no_result"))
    failed_count = sum(1 for m in metrics if m.get("status") == "failed")
    ret_lat = [m["retrieval_latency_ms"] for m in metrics
               if m.get("retrieval_latency_ms") is not None]
    gen_lat = [m["generation_latency_ms"] for m in metrics
               if m.get("generation_latency_ms") is not None]
    return {
        "total": total,
        "no_result_count": no_result_count,
        "no_result_rate": round(no_result_count / total, 4),
        "failed_count": failed_count,
        "error_rate": round(failed_count / total, 4),
        "avg_retrieval_latency_ms": round(sum(ret_lat) / len(ret_lat), 2) if ret_lat else None,
        "avg_generation_latency_ms": round(sum(gen_lat) / len(gen_lat), 2) if gen_lat else None,
    }


def _make_alert(rule: str, level: str, message: str, value: Any, threshold: Any) -> Dict[str, Any]:
    return {
        "rule": rule,
        "level": level,
        "message": message,
        "value": value,
        "threshold": threshold,
        "ts": datetime.now().timestamp(),
    }


def evaluate_alerts(aggregate: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """基于聚合指标评估告警规则，返回触发的告警列表。"""
    if not aggregate:
        return []
    alerts: List[Dict[str, Any]] = []

    if (aggregate.get("no_result_rate") or 0) > NO_RESULT_RATE_THRESHOLD:
        alerts.append(_make_alert(
            "high_no_result_rate", "warning",
            "无结果率过高，疑似检索质量下降或知识覆盖不足",
            aggregate["no_result_rate"], NO_RESULT_RATE_THRESHOLD,
        ))
    if (aggregate.get("error_rate") or 0) > ERROR_RATE_THRESHOLD:
        alerts.append(_make_alert(
            "high_error_rate", "critical",
            "查询失败率过高，疑似服务异常",
            aggregate["error_rate"], ERROR_RATE_THRESHOLD,
        ))
    if aggregate.get("avg_retrieval_latency_ms") is not None \
            and aggregate["avg_retrieval_latency_ms"] > AVG_RETRIEVAL_LATENCY_MS:
        alerts.append(_make_alert(
            "high_retrieval_latency", "warning",
            "平均检索延迟过高，疑似向量库性能下降",
            aggregate["avg_retrieval_latency_ms"], AVG_RETRIEVAL_LATENCY_MS,
        ))
    if aggregate.get("avg_generation_latency_ms") is not None \
            and aggregate["avg_generation_latency_ms"] > AVG_GENERATION_LATENCY_MS:
        alerts.append(_make_alert(
            "high_generation_latency", "warning",
            "平均生成延迟过高，疑似大模型服务响应变慢",
            aggregate["avg_generation_latency_ms"], AVG_GENERATION_LATENCY_MS,
        ))
    return alerts


def check_alerts(window_seconds: int = 300, limit: int = 200) -> Dict[str, Any]:
    """拉取最近窗口指标 → 聚合 → 评估告警 → 记录告警日志，返回结果字典。"""
    metrics = get_recent_metrics(window_seconds, limit)
    aggregate = aggregate_metrics(metrics)
    alerts = evaluate_alerts(aggregate)
    for alert in alerts:
        logger.warning(f"[告警] {alert['level']}: {alert['message']} "
                       f"(当前={alert['value']}, 阈值={alert['threshold']})")
    return {"window_seconds": window_seconds, "aggregate": aggregate, "alerts": alerts}

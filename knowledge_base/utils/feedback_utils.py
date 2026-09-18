# -*- coding: utf-8 -*-
"""用户反馈存储工具：点赞/点踩/纠错沉淀，形成知识运营闭环。

反馈数据写入 MongoDB 的 chat_feedback 集合，作为知识内容优化的依据：
- like：答案正确有用
- dislike：答案不准确/无帮助
- correction：用户给出正确答案（可回填到知识库）

对外接口：
- save_feedback(...)        新增一条反馈
- get_feedback_by_message(...) 按消息ID查询反馈
- get_feedback_stats(...)   反馈聚合统计（点赞/点踩/纠错计数）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient, DESCENDING

from knowledge_base.config.config import mongo_config
from knowledge_base.tool.logger import logger

# 反馈类型常量
FEEDBACK_LIKE = "like"              # 点赞（答案正确有用）
FEEDBACK_DISLIKE = "dislike"        # 点踩（答案不准确/无帮助）
FEEDBACK_CORRECTION = "correction"  # 纠错（用户给出正确答案）
FEEDBACK_TYPES = (FEEDBACK_LIKE, FEEDBACK_DISLIKE, FEEDBACK_CORRECTION)


class FeedbackMongoTool:
    """反馈数据 MongoDB 访问器（懒加载）。"""

    def __init__(self):
        try:
            self.client = MongoClient(mongo_config.mongo_url)
            self.db = self.client[mongo_config.mongo_db_name]
            self.collection = self.db["chat_feedback"]
            # 索引：按消息ID查询、按时间倒序聚合（幂等）
            self.collection.create_index([("message_id", 1)])
            self.collection.create_index([("ts", -1)])
            logger.info("反馈MongoDB连接成功")
        except Exception as e:
            logger.exception(f"反馈MongoDB连接失败: {e}")
            raise


_feedback_tool: Optional[FeedbackMongoTool] = None


def get_feedback_tool() -> FeedbackMongoTool:
    global _feedback_tool
    if _feedback_tool is None:
        _feedback_tool = FeedbackMongoTool()
    return _feedback_tool


def save_feedback(
    session_id: str,
    feedback_type: str,
    message_id: Optional[str] = None,
    question: str = "",
    answer: str = "",
    correction: str = "",
    user_id: str = "",
) -> str:
    """新增一条用户反馈。

    :param session_id: 会话ID
    :param feedback_type: 反馈类型（like/dislike/correction）
    :param message_id: 被评价的助手消息ID（可空）
    :param question: 对应问题
    :param answer: 助手回答原文
    :param correction: 纠错内容（feedback_type=correction 时）
    :param user_id: 反馈用户标识
    :return: 反馈记录ID
    """
    if feedback_type not in FEEDBACK_TYPES:
        raise ValueError(f"非法反馈类型: {feedback_type}，可选值 {FEEDBACK_TYPES}")

    document = {
        "session_id": session_id,
        "message_id": message_id,
        "feedback_type": feedback_type,
        "question": question,
        "answer": answer,
        "correction": correction,
        "user_id": user_id,
        "ts": datetime.now().timestamp(),
    }
    try:
        tool = get_feedback_tool()
        result = tool.collection.insert_one(document)
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"保存反馈失败: {e}")
        raise RuntimeError(f"保存反馈失败: {e}")


def get_feedback_by_message(message_id: str) -> List[Dict[str, Any]]:
    """按消息ID查询反馈列表（时间倒序）。"""
    try:
        tool = get_feedback_tool()
        cursor = tool.collection.find({"message_id": message_id}).sort("ts", DESCENDING)
        return list(cursor)
    except Exception as e:
        logger.error(f"查询反馈失败: {e}")
        return []


def get_feedback_stats(session_id: Optional[str] = None) -> Dict[str, Any]:
    """反馈聚合统计：各类型计数 + 最近反馈数。

    :param session_id: 可选，仅统计指定会话
    :return: {like, dislike, correction, total}
    """
    try:
        tool = get_feedback_tool()
        query = {"session_id": session_id} if session_id else {}
        counts = {t: tool.collection.count_documents({**query, "feedback_type": t})
                  for t in FEEDBACK_TYPES}
        counts["total"] = tool.collection.count_documents(query)
        return counts
    except Exception as e:
        logger.error(f"统计反馈失败: {e}")
        return {t: 0 for t in FEEDBACK_TYPES} | {"total": 0}


def _to_str(obj: Any) -> str:
    if isinstance(obj, ObjectId):
        return str(obj)
    return str(obj)

# -*- coding: utf-8 -*-
"""知识版本化工具：记录每次导入的文档版本，支撑知识运营回滚与审计。

文档每次成功导入，都会在 MongoDB 的 document_versions 集合中记录一条版本：
- file_title：源文档标题（对应切片 file_title）
- version：自增版本号（同一 file_title 每次导入 +1）
- content_hash：内容指纹（切片正文拼接的 MD5），用于识别内容是否变化
- chunk_count：切片数量
- dept / clearance_level：导入时的权限元数据
- imported_at：导入时间戳

对外接口：
- save_document_version(...)  新增一条版本记录，返回版本号
- get_latest_version(...)     查询某文档最新版本
- list_versions(...)          查询某文档全部版本历史
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient, DESCENDING

from knowledge_base.config.config import mongo_config
from knowledge_base.tool.logger import logger


class VersionMongoTool:
    """文档版本 MongoDB 访问器（懒加载）。"""

    def __init__(self):
        try:
            self.client = MongoClient(mongo_config.mongo_url)
            self.db = self.client[mongo_config.mongo_db_name]
            self.collection = self.db["document_versions"]
            self.collection.create_index([("file_title", 1), ("version", -1)])
            logger.info("版本MongoDB连接成功")
        except Exception as e:
            logger.exception(f"版本MongoDB连接失败: {e}")
            raise


_version_tool: Optional[VersionMongoTool] = None


def get_version_tool() -> VersionMongoTool:
    global _version_tool
    if _version_tool is None:
        _version_tool = VersionMongoTool()
    return _version_tool


def compute_content_hash(chunk_contents: List[str]) -> str:
    """由切片正文列表计算内容指纹（MD5），用于识别内容变化。"""
    normalized = "\n".join(sorted(c or "" for c in chunk_contents))
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def save_document_version(
    file_title: str,
    chunk_count: int,
    dept: str = "*",
    clearance_level: int = 1,
    content_hash: str = "",
    source_path: str = "",
) -> int:
    """新增一条文档版本记录并返回自增版本号。"""
    try:
        tool = get_version_tool()
        latest = get_latest_version(file_title)
        next_version = (latest.get("version") or 0) + 1 if latest else 1
        document = {
            "file_title": file_title,
            "version": next_version,
            "content_hash": content_hash,
            "chunk_count": chunk_count,
            "dept": dept,
            "clearance_level": clearance_level,
            "source_path": source_path,
            "imported_at": datetime.now().timestamp(),
        }
        tool.collection.insert_one(document)
        logger.info(f"文档版本已记录: {file_title} v{next_version} (chunks={chunk_count})")
        return next_version
    except Exception as e:
        logger.error(f"记录文档版本失败: {e}")
        # 版本记录失败不应阻断导入主流程
        return -1


def get_latest_version(file_title: str) -> Optional[Dict[str, Any]]:
    """查询某文档最新版本记录，无记录返回 None。"""
    try:
        tool = get_version_tool()
        return tool.collection.find_one(
            {"file_title": file_title}, sort=[("version", DESCENDING)]
        )
    except Exception as e:
        logger.error(f"查询最新版本失败: {e}")
        return None


def list_versions(file_title: str) -> List[Dict[str, Any]]:
    """查询某文档全部版本历史（版本号倒序）。"""
    try:
        tool = get_version_tool()
        cursor = tool.collection.find({"file_title": file_title}).sort("version", DESCENDING)
        return list(cursor)
    except Exception as e:
        logger.error(f"查询版本历史失败: {e}")
        return []

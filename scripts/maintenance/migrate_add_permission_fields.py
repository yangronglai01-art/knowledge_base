# scripts/maintenance/migrate_add_permission_fields.py
"""Milvus chunks 集合迁移脚本：为已有集合补充权限字段。

背景：文档权限过滤功能为 chunks 集合新增了 dept / clearance_level 两个标量字段。
Milvus 已存在的集合无法直接改动主键结构，本脚本采用最简单可靠的方式：删除旧集合，
下次导入文档时由 node_import_milvus 按新 schema（含权限字段）自动重建。

注意：此方式会丢失旧集合中的已导入数据，删除后需重新导入文档。
适用于当前开发阶段（集合中仅测试数据）的场景。

用法：
    python scripts/maintenance/migrate_add_permission_fields.py
"""
import sys

from knowledge_base.config.config import milvus_config
from knowledge_base.tool.logger import logger
from knowledge_base.utils.milvus_utils import get_milvus_client


def drop_chunks_collection():
    """删除旧 chunks 集合，使其按新 schema 重建。"""
    client = get_milvus_client()
    collection_name = milvus_config.chunks_collection
    if client.has_collection(collection_name):
        client.drop_collection(collection_name)
        logger.info(f"已删除旧集合：{collection_name}（下次导入将按新 schema 自动重建）")
    else:
        logger.info(f"集合 {collection_name} 不存在，无需删除")


def main():
    print("警告：此操作会删除现有 chunks 集合及其全部数据，删除后需重新导入文档。")
    confirm = input("确认删除？输入 y 继续：")
    if confirm.strip().lower() != "y":
        print("已取消")
        sys.exit(0)

    drop_chunks_collection()
    print("迁移完成：旧集合已删除，下次导入将按新 schema（含 dept/clearance_level）重建。")


if __name__ == "__main__":
    main()

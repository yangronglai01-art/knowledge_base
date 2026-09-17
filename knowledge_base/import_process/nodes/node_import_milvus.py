# knowledge_base/import_process/nodes/node_import_milvus.py
import json
from typing import Dict, Any

import logger
from pymilvus import DataType

from knowledge_base.config.config import milvus_config, permission_config
from knowledge_base.import_process.base import NodeBase
from knowledge_base.import_process.state import ImportGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.milvus_utils import get_milvus_client, escape_milvus_string


class NodeImportMilvus(NodeBase):
    """
    导入向量库节点：数据持久化
    """

    name = "node_import_milvus"

    def process(self, state: ImportGraphState):

        """Milvus切片数据入"""

        # 步骤1：输入数据有效性校验
        file_title, chunks_json_data, vector_dimension = self._step1_check_input(state)

        # 步骤2：集合准备
        self._step2_prepare_collection(vector_dimension)

        # 步骤3：幂等性处理 - 清理同file_title旧数据
        self._step3_clean_old_data(file_title)

        # 步骤4：批量插入数据+主键chunk_id回填（附带文档权限元数据）
        updated_chunks = self._step4_insert_data(
            chunks_json_data,
            dept=state.get("dept"),
            clearance_level=state.get("clearance_level")
        )

        # 步骤5：更新全局状态，将回填后的切片回传下游
        return {
            "chunks": updated_chunks
        }

    def _step1_check_input(self, state: Dict[str, Any]) -> tuple:
        """ Step 1：输入数据有效性校验"""

        # 校验1：file_title非空
        file_title = state.get("file_title")
        if not file_title:
            raise ValueError("file_title不能为空")

        # 校验1：chunks非空
        chunks = state.get("chunks")
        if not chunks:
            raise ValueError("chunks不能为空")

        if not isinstance(chunks, list):
            raise ValueError("chunks数据类型不正确")

        # 校验2：切片包含dense_vector字段
        first_chunk = chunks[0]
        if 'dense_vector' not in first_chunk:
            raise ValueError("错误: 数据中缺失dense_vector字段")

        # 校验3：切片包含 sparse_vector 字段
        if 'sparse_vector' not in first_chunk:
            raise ValueError("错误: 数据中缺失sparse_vector字段")

        # 提取向量维度
        vector_dimension = len(first_chunk['dense_vector'])

        return file_title, chunks, vector_dimension

    def _step2_prepare_collection(self, vector_dimension: int):
        """
        Step2：Milvus客户端连接+集合准备
        1. 获取Milvus单例客户端
        2. 集合不存在则自动创建（Schema+索引），存在则直接复用
        """

        # 1. 获取milvus客户端对象
        milvus_client = get_milvus_client()

        # 2. 集合不存在则创建
        collections_name = milvus_config.chunks_collection
        if not milvus_client.has_collection(collections_name):
            self._create_chunks_collection(collections_name, milvus_client, vector_dimension)

    def _create_chunks_collection(self, collections_name, milvus_client, vector_dimension):

        # 1. 创建schem
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        # 2. 创建列
        schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)  # 切片内容
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=100)  # 切片标题
        schema.add_field(field_name="parent_title", datatype=DataType.VARCHAR, max_length=100)  # 父标题
        schema.add_field(field_name="part", datatype=DataType.INT8)  # 分片编号
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=100)  # 源文件标题
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=100)  # 商品名称（幂等性依据）
        schema.add_field(field_name="dept", datatype=DataType.VARCHAR, max_length=64)  # 文档所属部门（* 表示全员可访问）
        schema.add_field(field_name="clearance_level", datatype=DataType.INT8)  # 文档密级 1-5，越大越机密
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)  # 稀疏向量
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=vector_dimension)  # 稠密向量

        # 3. 创建索引
        index_params = milvus_client.prepare_index_params()
        # 稠密向量索引：AUTOINDEX自动选最优索引类型+余弦相似度（语义检索常用）
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",
            metric_type="COSINE"
        )
        # 稀疏向量索引：专用SPARSE_INVERTED_INDEX+内积（IP），适配稀疏向量检索
        index_params.add_index(
            field_name="sparse_vector",
            index_name="sparse_inverted_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            params={"inverted_index_algo": "DAAT_MAXSCORE", "normalize": True, "quantization": "none"}
        )

        # 创建集合
        milvus_client.create_collection(
            collection_name=collections_name,
            schema=schema,
            index_params=index_params
        )


    def _step3_clean_old_data(self, file_title):
        """
        Step3: 幂等清理 基于每个片段的file_title进行旧数据的清理
        """
        # 1. 转义商品名称（防止特殊字符导致filter解析失败）
        safe_file_title = escape_milvus_string(file_title)

        # 2. 构建过滤表达式：item_name等于目标值
        filter_expr = f'file_title=="{safe_file_title}"'

        # 3. 删除符合条件的数据
        milvus_client = get_milvus_client()
        collection_name = milvus_config.chunks_collection
        milvus_client.delete(collection_name=collection_name, filter=filter_expr)

    def _step4_insert_data(self, chunks_json_data, dept=None, clearance_level=None):
        """ Step4：批量插入切片数据到Milvus+主键回填（写入文档权限元数据）"""

        # 0. 为每个切片写入文档权限元数据（文档级权限，默认取配置项默认值）
        dept = dept or permission_config.default_dept
        clearance_level = clearance_level if clearance_level is not None else permission_config.default_clearance_level
        for item in chunks_json_data:
            item["dept"] = dept
            item["clearance_level"] = int(clearance_level)

        # 1. 批量插入数据
        milvus_client = get_milvus_client()
        result = milvus_client.insert(
            collection_name=milvus_config.chunks_collection,
            data=chunks_json_data
        )

        # 2. 回填chunk_id
        inserted_ids = result.get("ids")
        for idx, item in enumerate(chunks_json_data):
            item["chunk_id"] = inserted_ids[idx]

        return chunks_json_data



if __name__ == "__main__":

    # state_vector.json: 可以手动从上一个步骤的结果中复制粘贴过来
    json_path = "data/examples/state_vector.json"
    with open(json_path, "r", encoding="utf-8") as f:
        state_json = f.read()

    state = json.loads(state_json)

    init_state = {
        "chunks": state.get("chunks"),
        "file_title": "hak180产品安全手册"  # node_entry节点返回
    }

    # 执行核心处理流程
    node_import_milvus = NodeImportMilvus()
    result = node_import_milvus(init_state)

    logger.info(json.dumps(result, ensure_ascii=False, indent=4))

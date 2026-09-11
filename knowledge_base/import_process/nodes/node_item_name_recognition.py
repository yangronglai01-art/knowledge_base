# knowledge_base/import_process/nodes/node_item_name_recognition.py
import json
from enum import auto
from typing import Tuple, List, Dict
from langchain_core.messages import SystemMessage, HumanMessage
from pymilvus import DataType

from knowledge_base.config.config import lm_config, milvus_config
from knowledge_base.import_process.base import NodeBase
from knowledge_base.import_process.prompt import NAME_RECOGNITION
from knowledge_base.import_process.state import ImportGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.embedding_utils import generate_embeddings
from knowledge_base.utils.llm_utils import get_llm_client
from knowledge_base.utils.milvus_utils import get_milvus_client, escape_milvus_string


class NodeItemNameRecognition(NodeBase):
    """
    主体识别节点：主体识别与标签提取
    """

    name = "node_item_name_recognition"

    # --- 配置参数 (Configuration) ---
    # 取前5个切片作为上下文，用于大模型识别商品名称（避免切片过多导致上下文过长）
    DEFAULT_ITEM_NAME_CHUNK_K = 5
    # 总上下文字符限制
    MAX_CHARS = 2500

    def process(self, state: ImportGraphState):
        """
        主体识别节点：主体识别与标签提取
        流程总览：
            1. 提取输入
            2. 构建大模型上下文
            3. 调用大模型识别商品名称
            4. 回填商品名称到状态和切片
            5. 生成商品名称的稠密/稀疏向量
            6. 将数据存入Milvus向量数据库
        """

        # 步骤1：提取并校验输入
        file_title, chunks = self._step1_get_inputs(state)

        # 步骤2：构建大模型识别的上下文
        context = self._step2_build_context(chunks)

        # 步骤3：调用大模型识别商品名称
        item_name = self._step3_call_llm(file_title, context)

        # # 步骤4：回填商品名称到切片
        chunks = self._step4_update_chunks(chunks, item_name)

        # 步骤5：为商品名称生成稠密/稀疏向量
        dense_vector, sparse_vector = self._step5_generate_vectors(item_name)

        # 步骤6：将数据存入Milvus向量数据库
        self._step6_save_to_milvus(file_title, item_name, dense_vector, sparse_vector)

        # 打印识别结果
        logger.info(f"主体名称识别完成: {item_name}")

        return {
            "chunks": chunks,
            "item_name": item_name,
        }

    def _step1_get_inputs(self, state: ImportGraphState) -> Tuple[str, List[Dict]]:
        """
        Step1: 接收并校验流程输入
        从流程状态中提取文件标题、文本切片核心数据
        """

        # 1. file_title 参数校验
        file_title = state.get("file_title")
        if not file_title:
            raise ValueError("标题不能为空")

        # 2. chunks 参数校验
        chunks = state.get("chunks")
        if not chunks:
            raise ValueError("文本片段不能为空")

        if not isinstance(chunks, list):
            raise ValueError("文本片段必须是列表")

        return file_title, chunks

    def _step2_build_context(self, chunks: List[Dict]) -> str:
        """
        Step2: 构造大模型商品名称识别的标准化上下文
        作用：
            1. 限制切片数量：仅取前k个切片，避免上下文过长
            2. 限制字符长度：总上下文字符限制，适配大模型输入上限
            3. 格式化内容：带序号的结构化格式，提升大模型识别精度
        返回值：str 格式化后的上下文字符串
        """

        # 总字符数，默认为0
        total_chars = 0
        # 取前k个切片
        parts: List[str] = []
        for idx, chunk in enumerate(chunks[:self.DEFAULT_ITEM_NAME_CHUNK_K], start=1):
            print(f"第{idx}个切片")

            # 1. 提取前k的切片
            chunk_title = chunk.get("title")
            chunk_content = chunk.get("content")

            # 2. 格式化切切片
            piece = f"【切片{idx}】\n标题：{chunk_title}\n内容：{chunk_content}"
            parts.append(piece)

            # 3. 累计字符数
            total_chars += len(piece)

            # 4. 判断字符数是否超过限制
            if total_chars > self.MAX_CHARS:
                logger.warning(f"总字符数超过限制，已截断，请检查")
                break

        context = "\n\n".join(parts).strip()
        final_context = context[:self.MAX_CHARS]

        return final_context

    def _step3_call_llm(self, file_title: str, context: str) -> str:
        """
        调用大模型实现主体的识别（品牌、型号、名称）
        """
        try:
            # 1. 加载提示词模板
            prompt = NAME_RECOGNITION.format(
                file_title=file_title,
                context=context
            )

            # 2. 获取模型客户端对象
            llm = get_llm_client(model=lm_config.item_model)

            # 3. 组装会话消息
            messages = [
                SystemMessage(content="你是商品识别专家，只输出识别到的字符串即可"),
                HumanMessage(content=prompt)
            ]

            # 4. 调用大模型
            response = llm.invoke(messages)

            # 5. 获取返回结果
            item_name = response.content.strip()
            # ExampleCorp X100工业设备
            item_name = item_name.replace("\n", "").replace("\r", "").replace("\t", "").replace(" ", "")

            # 6. 兜底判断
            if not item_name:
                return file_title

            # 7. 返回结果
            return item_name

        except Exception as e:
            # logger.error(f"大模型调用失败：{e}")
            logger.exception(f"大模型调用失败：{e}")

            # 返回文件名作为兜底处理的方案
            return file_title

    def _step4_update_chunks(self, chunks: List[Dict], item_name: str) -> List[Dict]:

        for chunk in chunks:
            chunk["item_name"] = item_name

        return chunks

    def _step5_generate_vectors(self, item_name: str) -> Tuple:
        """
        为商品名称生成双向量：稠密、稀疏
        """
        vectors = generate_embeddings([item_name])
        return vectors["dense"][0], vectors["sparse"][0]

    def _step6_save_to_milvus(self, file_title, item_name, dense_vector, sparse_vector):
        """
        Step6: 将商品名称、文件标题、双向量持久化到 Milvus 向量数据库
        核心逻辑：
           1. 配置校验：检查 Milvus 连接地址和集合名配置，缺失则跳过
           2. 客户端获取：获取单例 Milvus 客户端，连接失败则跳过
           3. 集合初始化：无集合则创建（定义 Schema+索引），有集合则直接使用
           4. 幂等性处理：删除同名商品数据，避免重复存储
           5. 数据插入：构造符合 Schema 的数据，非空向量才添加
           6. 集合加载：插入后强制加载集合，确保数据立即可查/Attu 可见
        """
        try:
            # 1. 获取Milvus客户端连接对象
            milvus_client = get_milvus_client()

            # 2. 创建集合（如果不存在）
            collection_name = milvus_config.item_name_collection
            if not milvus_client.has_collection(collection_name):
                self._create_item_name_collection(collection_name, milvus_client)

            file_title_safe = escape_milvus_string(file_title)
            # 3. 幂等删除
            milvus_client.delete(collection_name=collection_name, filter=f"file_title=='{file_title_safe}'")

            # 4. 准备数据
            data = {
                "file_title": file_title,
                "item_name": item_name,
                "dense_vector": dense_vector,
                "sparse_vector": sparse_vector
            }
            # 5 插入数据
            milvus_client.insert(collection_name=collection_name, data=[data])


        except Exception as e:
            logger.error(f"持久化数据失败：文件名：{file_title}，错误信息：{e}", exc_info= True)

    def _create_item_name_collection(self, collection_name, milvus_client):

        # 1. 创建集合schema
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)

        # 添加主键字段（INT64类型，自增）
        schema.add_field(
            field_name="pk",
            datatype=DataType.INT64,
            is_primary=True,
            auto_id=True
        )

        # 添加文件标题字段（VARCHAR类型，最大长度65535）
        schema.add_field(
            field_name="file_title",
            datatype=DataType.VARCHAR,
            max_length=100
        )

        # 添加商品名称字段（VARCHAR类型，最大长度65535）
        schema.add_field(
            field_name="item_name",
            datatype=DataType.VARCHAR,
            max_length=100
        )

        # 添加稠密向量字段（FLOAT_VECTOR类型，1024维，BGE-M3模型固定维度）
        schema.add_field(
            field_name="dense_vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024
        )
        # 添加稀疏向量字段（SPARSE_FLOAT_VECTOR类型，变长，适配BGE-M3的稀疏向量）
        schema.add_field(
            field_name="sparse_vector",
            datatype=DataType.SPARSE_FLOAT_VECTOR
        )

        # 构建索引参数（提升向量检索性能）
        index_params = milvus_client.prepare_index_params()

        # 为稠密向量创建索引（IVF_FLAT：兼容性好，适合小数据量）
        # 核心是 “先聚类分桶、再桶内暴力精确检索”。
        index_params.add_index(
            field_name="dense_vector",  # 字段名
            index_name="dense_vector_index",  # 索引名
            index_type="IVF_FLAT",  # 索引类型（兼容所有Milvus版本）
            metric_type="COSINE",  # 相似度计算方式（余弦相似度）
            params={"nlist": 128}  # 聚类数（影响检索精度/速度）
        )

        # 为稀疏向量创建索引（SPARSE_INVERTED_INDEX：稀疏向量专用索引）
        index_params.add_index(
            field_name="sparse_vector",  # 字段名
            index_name="sparse_vector_index",  # 索引名
            index_type="SPARSE_INVERTED_INDEX",  # 索引类型
            metric_type="IP",  # 相似度计算方式（内积）
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                # 高效的稀疏检索算法

                "normalize": True,
                # ↑ L2 归一化，让内积 (IP) 等价于余弦相似度

                "quantization": "none"
                # ↑ 关闭量化，保持原始精度：模型生成的向量已经压缩的一半的精度了（BGE_FP16=1），这里就不再压缩了
                # "quantization": "none" → 存储原始向量，不压缩
                # "quantization": "sq8" → 存储压缩后的向量（8-bit 量化
            })

        # 4. 创建集合（Schema + 索引）
        milvus_client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params
        )



if __name__ == "__main__":

    md_path = "data/examples/chunks.json"
    with open(md_path, "r", encoding="utf-8") as f:
        chunks_json = f.read()

    chunks = json.loads(chunks_json)
    init_state = {
        "chunks": chunks,
        "file_title": "hak180产品安全手册"
    }

    # 执行核心处理流程
    node_item_name_recognition = NodeItemNameRecognition()
    result = node_item_name_recognition(init_state)


    logger.info(json.dumps(result, ensure_ascii=False, indent=4))

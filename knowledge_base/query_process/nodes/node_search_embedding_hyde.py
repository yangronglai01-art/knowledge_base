# knowledge_base/query_process/nodes/node_search_embedding_hyde.py
from typing import Tuple

from knowledge_base.config.config import milvus_config
from knowledge_base.query_process.base import NodeBase
from knowledge_base.query_process.prompt import HYDE_PROMPT
from knowledge_base.query_process.state import QueryGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.embedding_utils import generate_embeddings
from knowledge_base.utils.llm_utils import get_llm_client
from knowledge_base.utils.milvus_utils import escape_milvus_string, create_hybrid_search_request, hybrid_search
from knowledge_base.utils.permission_utils import build_permission_filter, combine_filter
from knowledge_base.utils.mongo_history_utils import format_json


class NodeSearchEmbeddingHyde(NodeBase):
    """
    节点功能：HyDE (Hypothetical Document Embedding)
    先让 LLM 生成假设性答案，再对答案进行向量检索，提高召回率。
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_search_embedding_hyde"

    def process(self, state: QueryGraphState) -> QueryGraphState:

        try:
            # 1. 参数校验
            rewritten_query, item_names = self._step1_validate_param(state)

            # 2、生成假设性文档
            hyde_doc = self._step2_create_hyde_doc(rewritten_query)

            # 3、用“重写问题 + 假设文档”检索切片（附带权限过滤）
            res = self._step3_search_embedding_hyde(
                rewritten_query=rewritten_query,
                hyde_doc=hyde_doc,
                item_names=item_names,
                departments=state.get("departments"),
                clearance_level=state.get("clearance_level")
            )

            # 4、结果封装
            return {"hyde_embedding_chunks": res}

        except Exception as e:
            logger.exception(f"假设性文档向量搜索失败: {e}")
            return {"hyde_embedding_chunks": []}


    def _step1_validate_param(self, state: QueryGraphState) -> Tuple:

        query = state.get("rewritten_query")
        if not query:
            raise ValueError("未指定用户问题")

        item_names = state.get("item_names")
        if not item_names:
            raise ValueError("未指定商品名")

        return query, item_names

    def _step2_create_hyde_doc(self, rewritten_query):

        try:

            llm = get_llm_client()
            hyde_prompt = HYDE_PROMPT.format(rewritten_query=rewritten_query)
            response = llm.invoke(hyde_prompt)
            hyde_doc = response.content
            return hyde_doc

        except Exception as e:
            logger.exception(f"假设性文档生成失败: {e}")
            raise

    def _step3_search_embedding_hyde(self, rewritten_query, hyde_doc, item_names, departments=None, clearance_level=None):

        try:

            # 1. 对改写后的用户提问做向量转换
            embeddings = generate_embeddings([rewritten_query + "\n" + hyde_doc])
            dense_vector = embeddings.get("dense")[0]
            sparse_vector = embeddings.get("sparse")[0]

            # 2. 组织标量过滤条件（业务条件 + 权限条件）
            item_expr = None
            if item_names:
                # 2.1 组织标量条件表达式
                escaped = ', '.join(f'"{escape_milvus_string(name)}"' for name in item_names)
                item_expr = f"item_name in [{escaped}]"
            else:
                # 2.1 不组织标量条件表达式
                logger.info("未指定商品名，将进行全库搜索")

            # 2.2 组织权限过滤条件
            permission_expr = build_permission_filter(departments, clearance_level)
            expr = combine_filter(item_expr, permission_expr)

            # 3. 向量检索的请求对象
            reqs = create_hybrid_search_request(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                expr=expr,
                limit=10
            )

            # 4. 执行向量检索
            res = hybrid_search(
                collection_name=milvus_config.chunks_collection,
                reqs=reqs,
                ranker_weights=(0.8, 0.2),
                norm_score=True,
                output_fields=["chunk_id", "content", "item_name"],
                limit=10
            )

            return res[0] if res else []

        except Exception as e:
            logger.exception(f"假设性向量搜索失败: {e}")
            raise


if __name__ == "__main__":
    init_state = {
        "rewritten_query": "ExampleCorp X100工业设备如何使用",
        "item_names": ["ExampleCorp X100工业设备"]
    }
    node_search_embedding_hyde = NodeSearchEmbeddingHyde()
    result = node_search_embedding_hyde(init_state)
    logger.info(format_json(result))

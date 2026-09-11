# knowledge_base/query_process/nodes/node_rrf.py
from typing import List

from knowledge_base.query_process.base import NodeBase
from knowledge_base.query_process.state import QueryGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.mongo_history_utils import format_json


class NodeRrf(NodeBase):
    """
    节点功能：Reciprocal Rank Fusion
    将多路召回的结果（向量、HyDE、Web）进行加权融合排序。
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_rrf"

    def process(self, state: QueryGraphState) :
        #1. 获取各路搜索结果（向量、假设性向量）
        embedding_chunks = state.get("embedding_chunks")
        embedding_search_list = [doc.get("entity") for doc in (embedding_chunks or []) if isinstance(doc, dict) ]

        hyde_embedding_chunks = state.get("hyde_embedding_chunks")
        hyde_embedding_search_list = [doc.get("entity") for doc in (hyde_embedding_chunks or []) if isinstance(doc, dict)]

        # 2. 定义不同搜索路的权重
        rrf_inputs = [
            (embedding_search_list, 1.0),
            (hyde_embedding_search_list, 0.8),
        ]

        # 3. 利用RRF融合重排序算法对所有搜索路上的文档进行初步排序
        rrf_merge_results = self._rrf_merge(rrf_inputs, max_results = 5)

        # 4. 获取最终的排序结果:只要文档，不要分数
        rrf_chunks = [doc for doc, _ in rrf_merge_results]

        return {
            "rrf_chunks": rrf_chunks
        }

    def _rrf_merge(self, rrf_inputs, k: int = 60, max_results: int = None) -> List:
        """
        :param rrf_inputs: 待融合排序的数据列表
        :param k:           平滑常数
        :param max_results: 合并后保留的文档数量，默认：全部保留
        :return: 合并且已排序之后的文档列表（按照得分降序）
        """

        # 1.存放分数的集合： key:chunk_id，value:所有搜索路的分数综合
        chunk_scores = {}

        # 2. 存放数据的集合： key:chunk_id，value:当前文档
        chunk_data = {}

        # 3. 遍历所有搜索路
        for rrf_input, weight in rrf_inputs:
            for rank, doc in enumerate(rrf_input, start=1):
                chunk_id = doc.get("chunk_id")
                chunk_scores[chunk_id] = chunk_scores.get(chunk_id, 0.0) +  weight / (k + rank)

                # 只有首次设置会成功
                chunk_data.setdefault(chunk_id, doc)

        # 4. 按照得分降序对数据进行排序
        # print(chunk_scores)
        # 组装结果列表：[(文档1, score),(文档2, score)，(文档3, score)...]
        unsorted_results = [(chunk_data[cid], score) for cid, score in chunk_scores.items()]
        sorted_results = sorted(unsorted_results, key=lambda x: x[1], reverse=True)

        # 5. 取前max_results个数据返回
        return sorted_results[:max_results] if max_results else sorted_results

if __name__ == "__main__":
    mock_state = {
        "embedding_chunks": [
            {
                "entity": {
                    "chunk_id": "chunk-1",
                    "item_name": "example-product",
                    "content": "Reset the device after replacing the sensor.",
                }
            },
            {
                "entity": {
                    "chunk_id": "chunk-2",
                    "item_name": "example-product",
                    "content": "Check the controller cable and power supply.",
                }
            },
        ],
        "hyde_embedding_chunks": [
            {
                "entity": {
                    "chunk_id": "chunk-2",
                    "item_name": "example-product",
                    "content": "Check the controller cable and power supply.",
                }
            },
            {
                "entity": {
                    "chunk_id": "chunk-3",
                    "item_name": "example-product",
                    "content": "Escalate to an authorized technician if the error persists.",
                }
            },
        ],
    }

    result = NodeRrf().process(mock_state)
    logger.info(format_json(result))

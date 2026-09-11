# knowledge_base/query_process/nodes/node_rerank.py
from typing import Any, Dict, List

from knowledge_base.query_process.base import NodeBase
from knowledge_base.query_process.state import QueryGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.mongo_history_utils import format_json
from knowledge_base.utils.reranker_http_utils import rerank_documents


class NodeRerank(NodeBase):
    """
    节点功能：使用 Cross-Encoder 模型对 RRF 后的结果进行精确打分重排。
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_rerank"

    # -----------------------------
    # Rerank / TopK 全局常量（不从 state 读取）
    # -----------------------------
    # 动态 TopK 硬上限：最多取前 N 条（<=10）
    RERANK_MAX_TOPK: int = 10
    # 最小 TopK：至少保留前 N 条（>=1，且 <= RERANK_MAX_TOPK）
    RERANK_MIN_TOPK: int = 2  # 总数最少条数

    # 断崖阈值（相对 - 一般针对低分文档）
    RERANK_GAP_RATIO: float = 0.25
    # 断崖阈值（绝对 - 一般针对高分文档）
    RERANK_GAP_ABS: float = 0.10

    # 最低入选标准
    SCORE_MIN: float = 0.8

    def process(self, state: QueryGraphState):

        # 1. 合并多数据源的文档(rrf 和 mcp 组装)
        merged_multi_docs: List[Dict[str, Any]] = self._step1_merge_multi_source_docs(state)

        # 2. Rerank精排
        # 调用reranker_http_utils实现精排获取分数列表
        # 将分数列表和原始文档对应后降序排列
        reranked_docs: List[Dict[str, Any]] = self._step2_rerank_merged_docs(state, merged_multi_docs)

        # 3. 动态topk截断（断崖检测）
        cutoff_docs = self._step3_cliff_cutoff(reranked_docs)

        # 4. 返回state结果
        return {
            "reranked_docs": cutoff_docs
        }

    def _step1_merge_multi_source_docs(self, state):

        # {
        # "title":"", b
        # "content":"",
        # "chunk_id":"",
        # "url":"",
        # "source":"",
        # }

        # 1. 定义结果集合
        merged_multi_docs = []

        # 2. 获取本地rrf结果文档列表，并组织数据
        for rrf_doc in state.get("rrf_chunks"):
            format_rrf_doc = {
                "title": rrf_doc.get("item_name"),
                "content": rrf_doc.get("content"),
                "chunk_id": rrf_doc.get("chunk_id"),
                "url": None,
                "source": "local",
            }
            merged_multi_docs.append(format_rrf_doc)

        # 3. 获取网搜结果列表，并组织数据
        for web_doc in state.get("web_search_docs"):
            format_web_doc = {
                "title": web_doc.get("title"),
                "content": web_doc.get("snippet"),
                "chunk_id": None,
                "url": web_doc.get("url"),
                "source": "web",
            }
            merged_multi_docs.append(format_web_doc)

        # 4. 返回结果
        return merged_multi_docs

    def _step2_rerank_merged_docs(self, state, merged_multi_docs):

        # 1. 获取改写后的用户问题
        user_query = state.get("rewritten_query")

        # 2. 获取文档的内容列表
        contents = [doc.get("content") for doc in merged_multi_docs]

        # 3. 调用reranker_http_utils实现精排
        rerank_scores = rerank_documents(user_query, contents)

        # 4. 组装文档和分数
        reranked_docs = [{"score": score, **doc} for doc, score in zip(merged_multi_docs, rerank_scores)]

        # 5. 按照得分降序对数据进行排序
        sorted_score_docs = sorted(reranked_docs, key=lambda x: x.get("score"), reverse=True)

        # 6. 返回结果
        return sorted_score_docs

    def _step3_cliff_cutoff(self, ranked_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        """断崖检测截断：相邻得分差距超过阈值时截断。"""
        if not ranked_docs:
            return []

        # 0. 如果第一条数据没有达到最低分数标准，则返回空列表
        if ranked_docs[0].get("score") < self.SCORE_MIN:
            return []

        # 1. 计算断崖文档数量硬上限
        upper_bound = min(self.RERANK_MAX_TOPK, len(ranked_docs))
        # 2. 计算断崖文档数量硬下限
        lower_bound = min(self.RERANK_MIN_TOPK, upper_bound)

        # 3. 默认：取满硬上限
        cutoff_pos = upper_bound

        # 4. 遍历文档
        # 起点：从硬下限和其后的文档之间进行比较
        # 终点：硬上限和他的前一条之间进行比较
        for index in range(lower_bound - 1, upper_bound - 1):
            current_score = ranked_docs[index].get("score")
            next_score = ranked_docs[index + 1].get("score")

            # 两条记录的绝对差值
            abs_gap = current_score - next_score

            # 两条记录的相对差值
            rel_gap = abs_gap / (abs(current_score) + 1e-6)

            # 满足任意条件及达到断崖阈值
            # 两条记录的分数差的绝对值 >= 断崖绝对阈值
            # 两条记录的分数差的相对值 >= 断崖相对阈值
            if abs_gap >= self.RERANK_GAP_ABS or rel_gap >= self.RERANK_GAP_RATIO:
                cutoff_pos = index + 1
                logger.info(f"断崖位置：{cutoff_pos}")
                break

        return ranked_docs[:cutoff_pos]


if __name__ == '__main__':
    mock_state = {
        "rewritten_query": "怎么测这块主板的短路问题？",
        "rrf_chunks": [
            {
                "chunk_id": "local_1",
                "item_name": "主板维修手册",
                "content": "主板短路通常表现为通电后风扇转一下就停，可以使用万用表的蜂鸣档测量。"
            },
            {
                "chunk_id": "local_2",
                "item_name": "闲聊",
                "content": "今天中午去吃猪脚饭吧，这块主板外观很漂亮。"
            },
        ],
        "web_search_docs": [
            {
                "url": "https://example.com/repair",
                "title": "短路查修指南",
                "snippet": "主板通电前先打各主供电电感对地阻值，阻值偏低就是短路。"
            },
            {
                "url": "https://example.com/news",
                "title": "科技新闻",
                "snippet": "苹果发布新款手机，A系列芯片性能提升20%。"
            },
        ],
    }

    node_rerank = NodeRerank()
    result = node_rerank(mock_state)
    logger.info(format_json(result))

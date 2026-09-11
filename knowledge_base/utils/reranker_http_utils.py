from http import HTTPStatus
from typing import List

import dashscope

from knowledge_base.config.config import reranker_http_config
from knowledge_base.tool.logger import logger


def rerank_documents(query: str, documents: list) -> List[float]:
    # 设置API_key
    dashscope.api_key = reranker_http_config.api_key
    # dashscope.base_http_api_url = reranker_http_config.base_url

    # 模型初始化配置
    resp = dashscope.TextReRank.call(
        model=reranker_http_config.model,
        query=query,
        documents=documents,
        top_n=len(documents),
        return_documents=False,
        instruct=reranker_http_config.instruct
    )

    # 重排序模型调用失败
    if resp.status_code != HTTPStatus.OK:
        message = resp.message
        raise RuntimeError(f"reranker调用失败: status_code ={resp.status_code}；message = {message}")

    results = resp.output.results

    scores = [0.0] * len(documents)
    for item in results:
        index = item.index
        score = item.relevance_score
        scores[index] = score
    return scores


if __name__ == '__main__':
    query = "什么是重排序模型"
    documents = [
        "重排序模型广泛应用于搜索引擎和推荐系统，按相关性对候选文本进行排序",
        "量子计算是计算科学的前沿领域",
        "预训练语言模型的发展为重排序模型带来了新的进展"
    ]

    results = rerank_documents(query, documents)

    logger.info(results)

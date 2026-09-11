from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker

from knowledge_base.config.config import milvus_config
from knowledge_base.tool.logger import logger

# 1. 定义全局单例对象
_milvus_client = None


# 2. 获取全局单例对象(延迟加载)
def get_milvus_client():
    """
    获取Milvus客户端对象
    :return:
    """

    # 2.1 如果客户端对象已经被实例化，则获取当前实例化对象
    global _milvus_client
    if _milvus_client is not None:
        return _milvus_client

    if not milvus_config.milvus_url:
        raise ValueError("Milvus URL cannot be empty")

    # 2.2 如果客户端对象没有被实例化，则创建客户端对象
    _milvus_client = MilvusClient(uri=milvus_config.milvus_url)

    # 2.3 返回milvus客户端对象
    return _milvus_client


# knowledge_base/utils/llm_utils.py
def escape_milvus_string(value: str) -> str:
    """
    Milvus数据库过滤表达式中字符串的安全转义函数（防止解析失败）
    作用： 转义特殊字符（反斜杠、双引号），避免Milvus解析filter时报错
    参数 value: 需要转义的原始字符串
    返回 str: 转义后的安全字符串
    """
    # 转义反斜杠（\ → \\） 双引号（" → \"） 单引号（' → \'）
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    return value


def create_hybrid_search_request(
        dense_vector, sparse_vector, dense_params=None, sparse_params=None, expr=None, limit=5
):
    """
    组装混合向量搜索的搜索条件
    """
    # query_text = "white headphones, quiet and comfortable"
    # query_dense_vector = [0.3580376395471989, -0.6023495712049978, 0.5142999509918703, ...]

    if dense_params is None:
        dense_params = {
            "metric_type": "COSINE"
        }

    if sparse_params is None:
        sparse_params = {
            "metric_type": "IP"
        }

    # 首先构建搜索条件
    request_dense = AnnSearchRequest(
        data=[dense_vector],
        anns_field="dense_vector",
        param=dense_params,
        expr=expr,
        limit=limit
    )

    request_sparse = AnnSearchRequest(
        data=[sparse_vector],
        anns_field="sparse_vector",
        param=sparse_params,
        expr=expr,
        limit=limit
    )

    return [request_dense, request_sparse]


def hybrid_search(
        collection_name, reqs,
        ranker_weights=(0.5, 0.5), norm_score=False,
        limit=5, output_fields=None):
    try:
        # 1. 初始化加权排名器
        rerank = WeightedRanker(ranker_weights[0], ranker_weights[1], norm_score=norm_score)

        # 2. 获取milvus客户端对象
        client = get_milvus_client()

        # 3.执行向量查询
        res = client.hybrid_search(
            collection_name=collection_name,  # 设置集合名字
            reqs=reqs,
            ranker=rerank,  # 设置排序规则
            limit=limit,
            output_fields=output_fields
            # search_params=search_params
        )

        logger.info("混合向量搜索完毕")
        return res
    except:
        raise RuntimeError("混合向量搜索失败")

from pymilvus.model.hybrid import BGEM3EmbeddingFunction

from knowledge_base.tool.logger import logger

from knowledge_base.config.config import embedding_config

# 1. 定义一个全局单例对象
_bge_m3_ef = None

# 2. 获取全局单例对象(延迟加载)
def get_bge_m3_ef():

    # 2.1 如果模型已经被实例化，则获取当前实例化对象
    global _bge_m3_ef
    if _bge_m3_ef is not None:
        return _bge_m3_ef

    # 2.2 如果模型没有被实例化，创建模型客户端对象
    # 如果本地bge_m3_path没有模型，则会自动下载
    _bge_m3_ef = BGEM3EmbeddingFunction(
        model_name=embedding_config.bge_m3_path,
        device=embedding_config.bge_device, #如果未开启cuda（没有gpu），则无法开启半精度推理
        use_fp16=embedding_config.bge_fp16
    )

    # 2.3 返回模型客户端
    return _bge_m3_ef

# 3. 生成嵌入式向量
def generate_embeddings(texts):

    model = get_bge_m3_ef()
    docs_embeddings = model.encode_documents(texts)

    return  {
        "dense":[emb.tolist() for emb in docs_embeddings["dense"]],
        # "sparse":[dict(zip(row.indices, row.data)) for row in docs_embeddings["sparse"]]
        "sparse": [{int(k): float(v) for k, v in zip(row.indices, row.data)} for row in docs_embeddings["sparse"]]
    }

if __name__ == '__main__':


    docs = [
        "Artificial intelligence was founded as an academic discipline in 1956.",
        "Alan Turing was the first person to conduct substantial research in AI.",
        "Born in Maida Vale, London, Turing was raised in southern England.",
    ]

    result = generate_embeddings(docs)

    logger.info( result)

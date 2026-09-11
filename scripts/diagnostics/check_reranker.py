import dashscope
from http import HTTPStatus

from knowledge_base.config.config import reranker_http_config

# 以下为华北2（北京）地域的配置，调用时请将{WorkspaceId}替换为真实的业务空间ID，各地域的配置不同。
# dashscope.base_http_api_url = 'https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1'

dashscope.api_key = reranker_http_config.api_key
resp = dashscope.TextReRank.call(
  model="qwen3-rerank",
  query="什么是重排序模型",
  documents=[
    "重排序模型广泛应用于搜索引擎和推荐系统，按相关性对候选文本进行排序",
    "量子计算是计算科学的前沿领域",
    "预训练语言模型的发展为重排序模型带来了新的进展"
  ],
  top_n=2,
  return_documents=False
)

if resp.status_code == HTTPStatus.OK:
  print(resp)
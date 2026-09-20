# knowledge_base/utils/llm_utils.py

from langchain_openai import ChatOpenAI

from knowledge_base.config.config import lm_config
from knowledge_base.utils.langfuse_utils import get_current_langfuse_handler

# key: 模型名 + json_mode
# value: 模型对象
_llm_client_cache = {}


def _build_llm(model: str, json_mode: bool, callbacks) -> ChatOpenAI:
    # 关闭思考模式
    # 注意：不同的模型思考模式默认开启状态不一样，因此这里我们统一设置为非思考模式
    extra_body = {"enable_thinking": False}

    # 配置响应数据类型是否是json
    model_kwargs: dict = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}

    return ChatOpenAI(
        model=model,
        api_key=lm_config.api_key,
        base_url=lm_config.base_url,
        temperature=lm_config.llm_temperature,
        extra_body=extra_body,
        model_kwargs=model_kwargs,
        callbacks=callbacks,
    )


def get_llm_client(model: str | None = None, json_mode: bool = False) -> ChatOpenAI:
    # 1. 获取模型名称，如果参数没有指定则使用默认模型
    m = model or lm_config.llm_model

    # 2. 若当前查询上下文绑定了 Langfuse 回调，则绕过缓存，
    #    为本次调用创建挂载该回调的新客户端，确保所有 LLM 调用
    #    归并到同一条 trace 下（并发查询互不串扰）。
    langfuse_handler = get_current_langfuse_handler()
    if langfuse_handler is not None:
        return _build_llm(m, json_mode, callbacks=[langfuse_handler])

    # 3. 定义缓存key
    key = (m, json_mode)

    # 4. 无追踪时沿用全局缓存
    if key in _llm_client_cache:
        return _llm_client_cache[key]

    llm = _build_llm(m, json_mode, callbacks=None)

    # 5. 缓存模型对象
    _llm_client_cache[key] = llm

    return llm

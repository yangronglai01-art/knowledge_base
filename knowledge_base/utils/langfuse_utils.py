# knowledge_base/utils/langfuse_utils.py
"""Langfuse 可观测集成：追踪 LLM 调用与整条查询链路。

设计说明：
- 使用 Langfuse v2 核心 API（trace/generation），不依赖其 langchain 集成，
  从而避免 langfuse v2 SDK 与 langchain 1.x 的旧导入路径冲突。
- 每个查询通过 contextvar 绑定一个独立的 trace + 回调处理器，
  保证并发查询的 trace 归属互不串扰。
- 未启用（LANGFUSE_ENABLED 未开启、依赖未安装或密钥缺失）时完全 no-op。
"""
from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from knowledge_base.tool.logger import logger

try:
    from langfuse import Langfuse
    from langchain_core.callbacks.base import BaseCallbackHandler

    _AVAILABLE = True
except Exception:  # pragma: no cover - 可选依赖未安装
    Langfuse = None
    BaseCallbackHandler = None
    _AVAILABLE = False


def langfuse_enabled() -> bool:
    """Langfuse 是否已启用（依赖已装 + 开关 + 公钥/私钥齐全）。"""
    if not _AVAILABLE:
        return False
    if os.getenv("LANGFUSE_ENABLED") not in ("1", "true", "True", "TRUE"):
        return False
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        return False
    return True


# 当前查询上下文绑定的回调处理器（contextvar 隔离不同查询/线程）。
_current_handler: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "langfuse_llm_handler", default=None
)


class _LLMCallbackHandler(BaseCallbackHandler):
    """把 LLM 调用记录为当前 trace 下的 generation。"""

    def __init__(self, trace, logger_):
        super().__init__()
        self.trace = trace
        self._logger = logger_
        self._generations: dict = {}

    @staticmethod
    def _extract_model(serialized: dict, invocation_params: Optional[dict] = None) -> str:
        try:
            inv = invocation_params or {}
            model = inv.get("model") or inv.get("model_name")
            if model:
                return str(model)
            kwargs = (serialized or {}).get("kwargs") or {}
            model = kwargs.get("model_name") or kwargs.get("model")
            if model:
                return str(model)
            ids = (serialized or {}).get("id") or ["unknown"]
            return str(ids[-1])
        except Exception:
            return "unknown"

    @staticmethod
    def _extract_output(response: Any) -> Optional[str]:
        try:
            generations = getattr(response, "generations", None)
            if not generations:
                return None
            first = generations[0][0]
            msg = getattr(first, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if content:
                    return str(content)
            return getattr(first, "text", None)
        except Exception:
            return None

    @staticmethod
    def _extract_usage(response: Any) -> Optional[dict]:
        def _get(obj, key):
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        try:
            generations = getattr(response, "generations", None)
            if generations:
                msg = getattr(generations[0][0], "message", None)
                um = getattr(msg, "usage_metadata", None)
                if um:
                    return {
                        "input": _get(um, "input_tokens") or _get(um, "prompt_tokens"),
                        "output": _get(um, "output_tokens") or _get(um, "completion_tokens"),
                        "total": _get(um, "total_tokens"),
                    }
            llm_output = getattr(response, "llm_output", None) or {}
            tu = llm_output.get("token_usage") or {}
            if tu:
                return {
                    "input": tu.get("prompt_tokens"),
                    "output": tu.get("completion_tokens"),
                    "total": tu.get("total_tokens"),
                }
            return None
        except Exception:
            return None

    def on_llm_start(self, serialized, prompts, **kwargs):
        try:
            gen = self.trace.generation(
                name="llm_generation",
                model=self._extract_model(serialized or {}, kwargs.get("invocation_params")),
                input=prompts[0] if prompts else "",
            )
            self._generations[kwargs.get("run_id")] = gen
        except Exception as e:  # pragma: no cover
            self._logger.warning(f"Langfuse generation 开始失败: {e}")

    def on_llm_end(self, response, **kwargs):
        gen = self._generations.pop(kwargs.get("run_id"), None)
        if gen is None:
            return
        try:
            gen.end(output=self._extract_output(response), usage=self._extract_usage(response))
        except Exception as e:  # pragma: no cover
            self._logger.warning(f"Langfuse generation 结束失败: {e}")

    def on_llm_error(self, error, **kwargs):
        gen = self._generations.pop(kwargs.get("run_id"), None)
        if gen is None:
            return
        try:
            gen.end(level="ERROR", status_message=str(error)[:200])
        except Exception:  # pragma: no cover
            pass


@contextmanager
def trace_query_context(
    *,
    trace_name: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    tags: Optional[list] = None,
) -> Iterator[Optional[Any]]:
    """上下文管理器：为整条查询建立一条 Langfuse trace 并绑定回调处理器。

    用法::

        with trace_query_context(trace_name=..., session_id=..., ...):
            # 此处的 LLM 调用会自动归并到同一条 trace
            ...

    结束时自动 flush 上报。未启用时为空 no-op。
    """
    if not langfuse_enabled():
        yield None
        return

    client = None
    trace = None
    try:
        client = Langfuse()
        trace_input = None
        if metadata and metadata.get("query"):
            trace_input = str(metadata["query"])[:500]
        trace = client.trace(
            name=trace_name,
            input=trace_input,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
            tags=tags,
        )
        handler = _LLMCallbackHandler(trace, logger)
        token = _current_handler.set(handler)
        try:
            yield handler
        finally:
            _current_handler.reset(token)
            try:
                trace.end()
            except Exception:  # pragma: no cover
                pass
            try:
                client.flush()
            except Exception as e:  # pragma: no cover
                logger.warning(f"Langfuse flush 失败: {e}")
    except Exception as e:  # pragma: no cover
        logger.warning(f"Langfuse 建立 trace 失败，追踪降级关闭: {e}")
        yield None


def get_current_langfuse_handler() -> Optional[Any]:
    """返回当前查询上下文绑定的回调处理器（无则 None）。

    由 get_llm_client 调用，用于将 LLM 调用归并到当前查询的 trace。
    """
    if not langfuse_enabled():
        return None
    return _current_handler.get()


def flush_langfuse() -> None:
    """主动刷新当前查询的积压上报事件（按需调用）。"""
    if not langfuse_enabled():
        return
    try:
        Langfuse().flush()
    except Exception as e:  # pragma: no cover
        logger.warning(f"Langfuse flush 失败: {e}")

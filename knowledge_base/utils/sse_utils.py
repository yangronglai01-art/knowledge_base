import asyncio
from typing import Dict, Any

from knowledge_base.tool.logger import logger
from knowledge_base.utils.task_utils import get_task_status, get_done_task_list, get_running_task_list
from fastapi import Request

class SSEEvent:
    PROGRESS = "progress"  # 任务节点进度
    DELTA = "delta"  # LLM 流式输出增量
    FINAL = "final"  # 最终完整答案
    ERROR = "error"  # 错误信息


# 全局 SSE 会话队列存储
# Key: task_id,
# Value: asyncio.Queue()
task_queues: Dict[str, asyncio.Queue] = {}


def create_sse_queue(task_id: str):
    """
    创建并注册一个 sse 队列
    """
    queue = asyncio.Queue()
    task_queues[task_id] = queue
    return queue


async def push_sse_event(task_id: str, event: str, data: Dict[str, Any]):
    """
    加入 sse 队列
    """
    queue = task_queues[task_id]
    await queue.put({"event": event, "data": data})

def remove_sse_queue(task_id: str):
    """
    移除 sse 队列, 不存在则返回 None
    """
    task_queues.pop(task_id, None)


# SSE 生成器
async def event_generator(task_id: str, request: Request):

    while task_id not in task_queues:
        await asyncio.sleep(0.5)

    queue = task_queues[task_id]
    logger.info(f"开始生成 SSE 结果: {task_id}")

    try:
        while True:
            msg = await queue.get()
            logger.info(f"msg: {msg}")
            # 拼接自定义Event的SSE格式
            yield f"event: {msg['event']}\n"
            yield f"data: {msg['data']}\n\n"
    except Exception  as e:
        # 服务端中断 协程被取消 重新抛出，让外层知道它被成功取消()
        raise
    finally:
        # 清理资源
        remove_sse_queue(task_id)


def push_progress(task_id: str):
    push_sse_event(task_id, SSEEvent.PROGRESS, {
        "status": get_task_status(task_id),
        "done_list": get_done_task_list(task_id),
        "running_list": get_running_task_list(task_id),
    })
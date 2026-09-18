# 1. 创建应用
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, StreamingResponse

from knowledge_base.query_process.main_graph import KBQueryWorkflow
from knowledge_base.utils.mongo_history_utils import get_recent_messages, clear_history
from knowledge_base.utils.feedback_utils import save_feedback, get_feedback_stats, FEEDBACK_TYPES
from knowledge_base.utils.metrics_utils import record_query_metric, check_alerts
from knowledge_base.utils.sse_utils_sync import event_generator, create_sse_queue, push_progress
from knowledge_base.utils.task_utils import update_task_status, get_node_durations, TASK_STATUS_PROCESSING, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED
from knowledge_base.tool.logger import logger
from fastapi import Request
app = FastAPI(
    title="掌柜智库-查询API",
    description="此文档是掌柜智库查询流程的API接口说明"
)

# 2. 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的源
    allow_credentials=True,  # 允许携带cookie
    allow_methods=["*"],  # 允许的请求方法
    allow_headers=["*"],  # 允许的请求头
)

# 3. 静态页面路由
@app.get("/chat.html")  # 对外访问地址
async def chat():
    # 拼接HTML文件绝对路径
    html_path = Path(__file__).absolute().parent.parent / "page" / "chat.html"
    return FileResponse(html_path)

# 4. 定义接口接收的数据结构
class QueryRequest(BaseModel):
    """查询请求数据结构"""
    query: str = Field(..., description="查询内容")
    session_id: str = Field(None, description="会话ID")
    departments: list = Field(None, description="用户所属部门列表")
    clearance_level: int = Field(None, description="用户密级（可访问密级 <= 自身密级 的文档）")


# 5. 后台任务
def run_query_graph(session_id: str, task_id: str, user_query: str, departments=None, clearance_level=None):
    start_time = time.time()
    try:
        # 1. 更新任务状态: 处理中
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        push_progress(task_id)

        # 2. 定义初始化状态
        init_state = {
            "original_query": user_query,
            "session_id": session_id,
            "task_id": task_id,
            "departments": departments,
            "clearance_level": clearance_level
        }

        # 3. 启动工作流(调用invoke)
        # KBQueryWorkflow.create_and_run(init_state, stream=True)
        for chunk in KBQueryWorkflow.create_and_run(init_state, stream=True):
            for node_name, node_result in chunk.items():
                logger.info(f"{node_name}: {node_result}")

        # 4. 更新任务状态: 完成
        update_task_status(task_id, TASK_STATUS_COMPLETED)
        push_progress(task_id)

        # 5. 记录整条查询指标（总延迟 + 状态 + 各节点耗时）
        total_latency_ms = (time.time() - start_time) * 1000
        record_query_metric(
            task_id=task_id,
            session_id=session_id,
            question=user_query,
            status=TASK_STATUS_COMPLETED,
            total_latency_ms=round(total_latency_ms, 2),
            durations=get_node_durations(task_id),
        )

    except Exception as e:
        #  6. 更新任务状态:失败
        update_task_status(task_id, TASK_STATUS_FAILED)
        push_progress(task_id)
        logger.error(f"流程执行异常: {e}")

        # 7. 记录失败指标
        total_latency_ms = (time.time() - start_time) * 1000
        record_query_metric(
            task_id=task_id,
            session_id=session_id,
            question=user_query,
            status=TASK_STATUS_FAILED,
            total_latency_ms=round(total_latency_ms, 2),
            error=str(e),
        )

# 6. RAG查询
@app.post("/query")
async def query(background_tasks: BackgroundTasks, request: QueryRequest):

    # 1. 获取用户问题
    user_query = request.query

    # 2. 获取session_id,如果没有则创建一个
    session_id = request.session_id

    # 3. 获取用户权限信息（部门列表 + 密级）
    departments = request.departments
    clearance_level = request.clearance_level

    # 4. 生成任务id
    task_id = str(uuid.uuid4())

    # 5. 创建一个异步队列
    create_sse_queue(task_id)

    # 6. 启动后台任务
    background_tasks.add_task(run_query_graph, session_id, task_id, user_query, departments, clearance_level)

    # 6. 返回结果
    return {
        "message": "查询请求已经提交，结果正在处理中...",
        "session_id": session_id,
        "task_id": task_id
    }

# 7. sse 实时返回结果
@app.get("/stream/{task_id}")
async def stream(task_id: str, request: Request):

    return StreamingResponse(
        event_generator(task_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# 8. 清空指定会话的历史记录
@app.delete("/history/{session_id}")
async def clear_chat_history(session_id: str):
    count = clear_history(session_id)
    return {"message": "历史会话已清空", "deleted_count": count}

# 9. 查询指定会话的历史记录
@app.get("/history/{session_id}")
async def history(session_id: str, limit: int = 50):
    try:
        records = reversed(get_recent_messages(session_id, limit=limit))
        items = [{
            "_id": str(r.get("_id")) if r.get("_id") is not None else "",
            "session_id": r.get("session_id", ""),
            "role": r.get("role", ""),
            "text": r.get("text", ""),
            "rewritten_query": r.get("rewritten_query", ""),
            "item_names": r.get("item_names", []),
            "ts": r.get("ts")
        } for r in records]

        return {"session_id": session_id, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"history error: {e}")

class FeedbackRequest(BaseModel):
    """用户反馈请求数据结构"""
    session_id: str = Field(None, description="会话ID")
    message_id: str = Field(None, description="被评价的助手消息ID")
    question: str = Field(None, description="对应问题")
    answer: str = Field(None, description="助手回答原文")
    feedback_type: str = Field(..., description="反馈类型：like/dislike/correction")
    correction: str = Field(None, description="纠错内容（feedback_type=correction 时）")
    user_id: str = Field(None, description="反馈用户标识")


# 10. 用户反馈（知识运营闭环：点赞/点踩/纠错沉淀）
@app.post("/feedback")
async def feedback(request: FeedbackRequest):
    try:
        feedback_id = save_feedback(
            session_id=request.session_id,
            feedback_type=request.feedback_type,
            message_id=request.message_id,
            question=request.question or "",
            answer=request.answer or "",
            correction=request.correction or "",
            user_id=request.user_id or "",
        )
        return {"message": "反馈已记录", "feedback_id": feedback_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"feedback error: {e}")


# 11. 反馈统计（可选按会话过滤）
@app.get("/feedback/stats")
async def feedback_stats(session_id: str = None):
    try:
        stats = get_feedback_stats(session_id)
        stats["feedback_types"] = list(FEEDBACK_TYPES)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"feedback stats error: {e}")


# 12. 监控指标汇总（最近时间窗口聚合统计）
@app.get("/metrics/summary")
async def metrics_summary(window_seconds: int = 300):
    try:
        result = check_alerts(window_seconds=window_seconds)
        return {
            "window_seconds": window_seconds,
            "aggregate": result.get("aggregate"),
            "alert_count": len(result.get("alerts", [])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics summary error: {e}")


# 13. 监控告警（返回当前触发的告警列表）
@app.get("/metrics/alerts")
async def metrics_alerts(window_seconds: int = 300):
    try:
        result = check_alerts(window_seconds=window_seconds)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics alerts error: {e}")


# 14. 健康检查
@app.get("/health")
async def health():
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
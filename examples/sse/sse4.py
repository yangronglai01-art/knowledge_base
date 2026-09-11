import asyncio

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

# 1. 初始化
app = FastAPI()

# 2. 跨域处理
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的源
    allow_credentials=True,  # 允许携带cookie
    allow_methods=["*"],  # 允许的请求方法
    allow_headers=["*"],  # 允许的请求头
)

# key: 会话id session_id
# value: 任务队列
task_queues = {}


async def gen_answer(session_id: str, query: str):
    queue = asyncio.Queue()
    task_queues[session_id] = queue

    # 调用向量转换查询向量数据库 query
    # 启动langgraph工作流

    for i in range(5):
        await queue.put(f"【{query}】【{session_id}】的第{i + 1}个答案")
        await asyncio.sleep(1)
    await queue.put(None)



class QueryRequest(BaseModel):
    query: str
    session_id: str

# 提交要买球的请求
@app.post("/submit_query")
async def submit(query_request: QueryRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(gen_answer, query_request.session_id, query_request.query)
    return {"message": "已收到您的查询请求，查询已开始"}


# 定义正常消息生成器函数
async def event_generator(session_id):
    while session_id not in task_queues:
        await asyncio.sleep(0.5)

    queue = task_queues[session_id]

    while True:
        answer = await queue.get()
        if answer is None:
            break
        yield f"data: {answer}\n\n"


# 接受订阅（生产一个给客户交付一个）
@app.get("/stream/{session_id}")
async def stream(session_id: str):
    print(f"调用服务器的stream方法, session_id = {session_id}")

    return StreamingResponse(
        event_generator(session_id),
        media_type="text/event-stream"
    )


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8001)

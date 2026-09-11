import asyncio

import uvicorn
from fastapi import FastAPI, BackgroundTasks
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


async def gen_balls(session_id: str):
    queue = asyncio.Queue()
    task_queues[session_id] = queue

    for i in range(5):
        await queue.put(f"这是会话{session_id}的第{i + 1}个球")
        await asyncio.sleep(1)
    await queue.put(None)


# 提交要买球的请求
@app.get("/submit/{session_id}")
async def submit(session_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(gen_balls, session_id)
    return {"message": "已接受到您发送的任务，任务已启动", "sessionId": session_id}


# 接受订阅（生产一个给客户交付一个）
@app.get("/stream/{session_id}")
async def stream(session_id: str):
    print(f"调用服务器的stream方法, session_id = {session_id}")

    # 定义正常消息生成器函数
    async def event_generator():
        while session_id not in task_queues:
            await asyncio.sleep(0.5)

        queue = task_queues[session_id]

        while True:
            ball = await queue.get()
            if ball is None:
                break
            yield f"data: {ball}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8001)

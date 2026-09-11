import asyncio

import uvicorn
from fastapi import FastAPI
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


@app.get("/stream/{session_id}")
async def stream(session_id: str):

    print(f"调用服务器的stream方法, session_id = {session_id}")

    # 定义正常消息生成器函数
    async def event_generator():
        # 模拟持续发送5条消息
        for i in range(5):
            # data:内容\n\n
            yield f"data: 这是会话sse2-1 {session_id}的第{i}条消息\n\n"
            await asyncio.sleep(1)
        yield f"data: [END]\n\n"

    # 定义错误消息生成器函数
    async def error_event_generator():
        yield f"data: 无效会话\n\n"
        yield f"data: [END]\n\n"


    if session_id == "666":

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    else:
        return StreamingResponse(
            error_event_generator(),
            media_type="text/event-stream"
        )


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8001)
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


# 定义生成器函数
async def event_generator():
    # 模拟持续发送5条消息
    for i in range(5):
        # data:内容\n\n
        yield f"data: 这是第{i}条消息\n\n"
        await asyncio.sleep(1)
    yield f"data: [END]\n\n"

@app.get("/simple_stream")
async def simple_stream():

    print("调用服务器的simple_stream方法")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8001)
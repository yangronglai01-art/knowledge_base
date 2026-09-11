import asyncio
import time

import uvicorn
from fastapi import FastAPI, BackgroundTasks

# 创建fastapi实例
app = FastAPI()


# 定义后台任务函数: 一个模拟的耗时任务
def write_log1(email:  str, content: str):
    while True:
        print(f"正在写入日志...向{email}发邮件，内容是{content}, 当花钱时间：{time.asctime()}")
        # CPU密集型，不释放CPU资源
        time.sleep(1)


async def write_log2(email: str, content: str):
    while True:
        print(f"正在写入日志...向{email}发邮件，内容是{content}, 当花钱时间：{time.asctime()}")
        # IO密集型，释放CPU资源
        await asyncio.sleep(1)


@app.post("/send-task/{email}")
async def send_task(email: str, background_tasks:  BackgroundTasks):
    background_tasks.add_task(write_log2, email, "这是日志内容")
    print("任务正在执行")
    return {"message": "任务已启动"}


@app.post("/send/{email}")
async def send_task(email: str):
    for i in range(10):
        content = f"这是日志内容{i}"
        print(f"正在写入日志...向{email}发邮件，内容是{content}, 当花钱时间：{time.asctime()}")
        time.sleep(1)
    print("任务正在执行")
    return {"message": "任务已启动"}

if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8000)

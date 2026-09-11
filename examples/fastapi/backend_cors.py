import time
from typing import Optional

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()


# ⚠️ 注意：这里先故意不配置 CORS！测试不跨域的效果
# ✅ 然后再配置 CORS 允许跨域！测试跨域的效果
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发环境方便测试）
    allow_credentials=True, # 允许携带 Cookie
    allow_methods=["*"],  # 允许所有 HTTP 方法（GET, POST, PUT, DELETE 等）
    allow_headers=["*"],  # 允许所有请求头
)


class Person(BaseModel):
    id: Optional[int] = None  # id 是可选字段，默认为 None
    name: str
    age: int

@app.get("/api/data/{id}")
async def get_data(id: int):

    # TODO 去数据库中获取id为1的用户的基本信息
    time.sleep(5)
    print(f"获取id为{id}的数据")
    return {"message": "获取成功", "data": Person(id=id, name="张三", age=18)}

@app.post("/api/data")
async def save_data(p: Person):
    print(p)
    # TODO 保存用户数据
    print("保存")
    p.id = 100
    time.sleep(2)
    return {"message": "ok", "id": p.id}


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8001)
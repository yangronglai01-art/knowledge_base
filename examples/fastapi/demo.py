import uvicorn
from fastapi import FastAPI, Form
from pydantic import BaseModel
from starlette.responses import HTMLResponse, RedirectResponse, PlainTextResponse

from knowledge_base.tool.logger import logger
# 创建一个 FastAPI 应用实例
app = FastAPI()

@app.get("/", summary="第一个测试")
async def index():
    return {"Hello": "World666"}


# 访问 http://127.0.0.1:8000/items/5?q=somequery
# item_id: 路径参数 (自动转为 int)
# q: 查询参数 (可选，默认 None)    queryString
@app.get("/items/{item_id}", summary="获取指定参数")
async def read_item(item_id: int = 100, q: str | None = None):
    return {"item_id": item_id, "q": q}


# 接收? skip=? & limit = ?
@app.get("/items", summary="分页")
async def read_item(skip: int = 0, limit: int = 10):

    logger.info(f"skip: {skip}, limit: {limit}")


    return {"skip": skip, "limit": limit}

#get\post\put\delete：允许路径和queryString传参
# post\put\delete：允许body传参


# 定义数据模型
class Item(BaseModel):
    name: str
    price: float
    is_offer: bool = None
# item = Item(name="键盘", price=299.0, is_offer=True)
# item = Item(name="鼠标", price=99.0)  # is_offer 有默认值 None，可不传

class Product(BaseModel):
    title: str
    price: float
    is_list: bool = None


# 请求体中的json
# POST 请求接收 JSON 数据
@app.post("/items", summary="类型检查")
async def create_item(item: Item):
    # item 已经是验证过的 Item 对象
    # 如果客户端传来的 price 是字符串 "abc"，FastAPI 会自动报错
    item.price = item.price + 666
    item.name = "heihei"
    return {"name": item.name, "price": item.price, "is_offer": item.is_offer}

# 请求体中的键值对
@app.post("/save", summary="")
async def create_item(name: str = Form(...), age: int = Form(...)):

    logger.info(f"name: {name}, age: {age}")
    return {"name": name, "age": age}


# url传参
@app.post("/save1", summary="")
async def create_item(name: str, age: int):

    logger.info(f"name: {name}, age: {age}")
    return {"name": name, "age": age}

# url传参
@app.get("/save2", summary="")
async def create_item(name: str, age: int):

    logger.info(f"name: {name}, age: {age}")
    return {"name": name, "age": age}


# 1、路由处理函数返回一个 Pydantic 模型实例，FastAPI 将自动将其转换为 JSON 格式，并作为响应发送给客户端：
@app.post("/items/return", summary="返回 Pydantic 模型实例")
async def create_item(item: Item):

    product = Product(title=item.name, price=item.price, is_list=item.is_offer)

    return product

#2、使用 HTTPException 抛出异常，返回自定义的状态码和详细信息。
#以下实例在 item_id 为 42 会返回 404 状态码：
from fastapi import HTTPException

@app.delete("/items/{item_id}", summary="抛出异常")
async def read_item(item_id: int):
    if item_id == 42:
        raise HTTPException(status_code=404, detail="Item 找不到")
    return {"item_id": item_id}


from fastapi.responses import JSONResponse
@app.get("/api/user")
async def get_user():
    # 等价于直接 return {"name": "张三", "age": 20}（FastAPI 自动转 JSONResponse）
    return JSONResponse(
        content={"name": "张三", "age": 201},
        status_code=200,  # 可选，默认 200
        headers={"aaa": "aaavalue"}  # 可选，自定义响应头
    )


from fastapi.responses import FileResponse



@app.post("/download/excel")
async def download_excel():
    excel_path = "data/example.xls"

    # 返回 data 目录中的示例文件
    # TODO

    # 返回文件并指定下载文件名
    return FileResponse(
        path=excel_path,
        filename="月度报表.xlsx",

        # 媒体类型
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/hello")
async def hello(name: str = "游客"):
    html_content = f"""
    <html>
        <body>
            <h1>你好，{name}！</h1>
            <h2>你好，{name}！</h2>
            <img src="">
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)


@app.get("/hello_response")
async def hello(name: str = "游客"):
    html_content = f"""
    <html>
        <body>
            <h1>你好，{name}！</h1>
            <h2>你好，{name}！</h2>
            <img src="">
        </body>
    </html>
    """
    return Response(content=html_content, status_code=200, media_type = "text/plain")


@app.get("/hello_plain")
async def hello(name: str = "游客"):
    html_content = f"""
    <html>
        <body>
            <h1>你好，{name}！</h1>
            <h2>你好，{name}！</h2>
            <img src="">
        </body>
    </html>
    """
    return PlainTextResponse(content=html_content, status_code=200)

import io
import random
import string
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from fastapi.responses import Response

@app.get("/captcha")
async def generate_captcha():
    """动态生成验证码图片，返回 PNG 格式"""

    # 随机生成 4 位验证码（大写字母 + 数字）
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=4))

    # 创建白色背景图片
    width, height = 120, 50
    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)

    # 绘制干扰点（噪点）
    for _ in range(100):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(0, 200), random.randint(0, 200), random.randint(0, 200)))

    # 绘制干扰线
    for _ in range(3):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=2)

    # 绘制验证码文字（用默认字体）
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except IOError:
        font = ImageFont.load_default()

    for i, char in enumerate(code):
        x = 15 + i * 25
        y = random.randint(5, 15)
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
        draw.text((x, y), char, font=font, fill=color)

    # 轻微模糊，增加辨识难度
    image = image.filter(ImageFilter.GaussianBlur(radius=0.3))

    # 将图片转为 PNG 字节流
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        status_code=200)


#
# @app.post("/code")
# async def download_excel():
#
#
#     # 返回文件并指定下载文件名
#     return FileResponse(
#
#         # 媒体类型
#         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#     )



from fastapi.responses import StreamingResponse
import asyncio

async def generate_stream():
    # 模拟流式输出（逐字返回）
    words = ["你", "好", "，", "这", "是", "流", "式", "响", "应"]
    for word in words:
        await asyncio.sleep(0.5)
        yield word.encode("utf-8")  # 流式输出需返回字节流

@app.get("/stream")
async def stream_response():
    return StreamingResponse(generate_stream(), media_type="text/event-stream")



@app.get("/old-path")
async def redirect_old_path():
    # 重定向到 /new-path，状态码 307 表示临时重定向
    return RedirectResponse(url="/new-path", status_code=307)

@app.get("/new-path")
async def new_path():
    return {"message": "这是新接口"}


if __name__ == "__main__":
    """服务启动入口：本地开发环境直接运行"""
    logger.info("File Import Service 服务启动中...")
    # 启动uvicorn服务，绑定本地IP和8000端口，关闭自动重载（生产环境建议用workers多进程）
    uvicorn.run(
        app=app,
        host="127.0.0.1",  # 仅本地访问，生产环境改为0.0.0.0（允许所有IP访问）
        port=8001  # 服务端口
    )

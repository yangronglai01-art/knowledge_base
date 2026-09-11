from pathlib import Path

import uvicorn
from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

# 实例化fastapi
app = FastAPI()
print(str(Path(__file__).parent / "static"))

# 挂载一个静态资源目录
# 静态资源：图片，css，js，html
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8000)

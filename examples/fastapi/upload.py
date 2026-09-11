import os
import uuid
from typing import Optional

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import Field, BaseModel

app = FastAPI()

UPLOAD_FOLDER = os.path.join("data", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "application/pdf", "text/markdown"]
CHUNK_SIZE = 1024 * 1024  # 1MB分块


# ========== Pydantic 模型定义 ==========

class UploadResponseData(BaseModel):
    """上传成功后的数据"""
    filename: str = Field(..., description="原始文件名")
    saved_filename: str = Field(..., description="保存的文件名")
    content_type: str = Field(..., description="文件类型")
    file_size: int = Field(..., description="文件大小（字节）")
    save_path: str = Field(..., description="保存路径")
    remark: Optional[str] = Field(default=None, description="备注信息")


class UploadResponse(BaseModel):
    """统一响应格式"""
    code: int = Field(default=0, description="状态码：0-成功，其他-失败")
    msg: str = Field(default="success", description="响应消息")
    data: Optional[UploadResponseData] = Field(default=None, description="上传的文件的基本信息")


def generate_unique_filename(original_filename: str) -> str:
    """生成唯一文件名，避免文件覆盖"""
    ext = os.path.splitext(original_filename)[1]  # 获取扩展名
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return unique_name

def validate_file_type(content_type: str, allowed_types: list) -> bool:
    """验证文件类型"""
    return content_type in allowed_types


@app.post("/upload", summary="单个文件上传")
async def upload(file: UploadFile = File(
    ..., # 必填项
    description="需要上传的文件（图片、pdf、md）",
    media_type="application/octet-stream"),  # 可以接收任何类型的文件
    remark: str = None # 可选参数
):

    if not validate_file_type(file.content_type, ALLOWED_TYPES):
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    print(f"remark = {remark}")

    # file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    original_filename = file.filename
    saved_filename = generate_unique_filename(original_filename)
    file_path = os.path.join(UPLOAD_FOLDER, saved_filename)

    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)

   # TODO 调用MinerU的API接口将 file_path 文件上传到MinerU上

    response_data = UploadResponseData(
        filename=original_filename,
        saved_filename=saved_filename,
        content_type=file.content_type,
        file_size=file.size,
        save_path=file_path,
        remark=remark
    )

    return UploadResponse(code=0, msg="上传成功", data=response_data)


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8000)

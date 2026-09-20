import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from knowledge_base.config.config import file_upload_config, minio_config
from knowledge_base.import_process.main_graph2 import KBImportWorkflow
from knowledge_base.utils.minio_utils import get_minio_client
from knowledge_base.utils.task_utils import add_running_task, add_done_task, get_running_task_list, get_done_task_list, \
    get_task_status, update_task_status, TASK_STATUS_PROCESSING, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, \
    get_node_durations, get_task_info
from knowledge_base.tool.logger import logger

# 1. 定义应用
app = FastAPI(
    title="知犀:文档导入",
    description="当前文档是知犀文档导入相关接口的定义"
)

# 2. 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的源
    allow_credentials=True,  # 允许携带cookie
    allow_methods=["*"],  # 允许的请求方法
    allow_headers=["*"],  # 允许的请求头
)


# 3. 静态页面的加载
@app.get("/import.html")
async def get_import_page():
    html_path = Path(__file__).absolute().parent.parent / "page" / "import.html"
    return FileResponse(html_path)

# 4. 后台任务
def run_graph_task(task_id, local_dir, local_file_path, dept=None, clearance_level=None):

    try:
        # 1. 更新任务的全局状态为处理中
        update_task_status(task_id, TASK_STATUS_PROCESSING)

        # 2. 定义初始化状态
        init_state = {
            "task_id": task_id,
            "local_file_path": local_file_path,
            "local_dir": local_dir,
            "dept": dept,
            "clearance_level": clearance_level
        }

        # 3. 启动工作流
        for chunk in KBImportWorkflow.create_and_run(init_state, stream=True):
            for node_name, node_result in chunk.items():
                logger.info(f"{node_name}: {node_result}")

        update_task_status(task_id, TASK_STATUS_COMPLETED)
    except Exception as e:
        update_task_status(task_id, TASK_STATUS_FAILED)
        logger.error(f"{task_id} : 任务执行失败: {e}", exc_info=True)
        # logger.exception(f"{task_id} : 任务执行失败: {e}")


# 5. 文件上传
@app.post("/upload", summary="上传文件接口", description="自动触发知识库导入的工作流")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="需要上传的文件（pdf、md）"),
    dept: str = Form(None, description="文档所属部门（* 表示全员可访问）"),
    clearance_level: int = Form(None, description="文档密级 1-5，越大越机密")
):
    """
    上传文件接口
    """

    # ======================将文件上传到Python服务器上====================
    # 1. 构建服务器本地的文件存储目录: data/YYYYMMDD（按日期方便管理）
    data_based_root_dir = file_upload_config.data_based_root_dir
    data_dir = os.path.join(data_based_root_dir, datetime.now().strftime("%Y%m%d"))

    # 2. 生成唯一任务标识
    task_id = str(uuid.uuid4())

    # 3. 对文件上传的任务进行追踪(正在执行)
    add_running_task(task_id, "upload_file")

    # 4. 构建一个本地任务目录: data/YYYYMMDD/task_id
    local_dir = os.path.join(data_dir, task_id)
    os.makedirs(local_dir, exist_ok=True)
    local_file_path = os.path.join(local_dir, file.filename)

    # 5. 将上传的文件保存到服务器的本地目录中
    with open(local_file_path, "wb") as file_buffer:
        shutil.copyfileobj(file.file, file_buffer, length=1024*1024)

    # ======================将文件上传到MinIO服务器上====================


    # 6. 将文件上传到MinIO
    try:
        minio_client = get_minio_client()
        minio_bucket_name = minio_config.bucket_name
        minio_object_name = f"pdf_files/{datetime.now().strftime('%Y%m%d')}/{file.filename}"

        minio_client.fput_object(minio_bucket_name, minio_object_name, local_file_path)
    except Exception as e:
        logger.warning(f"文件上传到MinIO失败: {e}")

    #
    # time.sleep(10)

    # 7. 对文件上传任务进行追踪(已完成)
    add_done_task(task_id, "upload_file")


    # 8. 启动后台任务,调用工作流
    background_tasks.add_task(run_graph_task, task_id, local_dir, local_file_path, dept, clearance_level)

    return {
        "code": 200,
        "message": "文件上传成功",
        "task_id": task_id
    }


@app.get("/status/{task_id}", summary="任务状态查询接口", description="前端根据task_id对此接口进行定时轮询")
async def get_task_progress(task_id: str):

    task_status_info: Dict = get_task_info(task_id)
    return task_status_info

# 6. 启动项目
if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)

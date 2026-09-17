# knowledge_base/config/config.py
import os
from dataclasses import dataclass

from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
load_dotenv(dotenv_path=env_path, override=True)


@dataclass
class LLMConfig:
    base_url: str
    api_key : str
    vl_model: str
    llm_model: str
    item_model: str
    llm_temperature: float

lm_config = LLMConfig(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
    vl_model=os.getenv("VL_MODEL"),
    llm_model=os.getenv("LLM_DEFAULT_MODEL"),
    item_model=os.getenv("ITEM_MODEL"),
    llm_temperature=float(os.getenv("LLM_DEFAULT_TEMPERATURE"))
)


@dataclass
class MinIOConfig:
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str
    img_dir: str

minio_config = MinIOConfig(
    endpoint=os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    bucket_name=os.getenv("MINIO_BUCKET_NAME"),
    img_dir=os.getenv("MINIO_IMG_DIR"),
)

@dataclass
class EmbeddingConfig:
    bge_m3_path: str
    bge_m3: str
    bge_device: str
    bge_fp16: bool

embedding_config = EmbeddingConfig(
    bge_m3_path=os.getenv("BGE_M3_PATH"),
    bge_m3=os.getenv("BGE_M3"),
    bge_device=os.getenv("BGE_DEVICE"),
    # 特殊处理：将.env中的1/0转为布尔值，兼容常见的数字/字符串格式
    bge_fp16=os.getenv("BGE_FP16") in ("1", "True", "true", 1)
)

@dataclass
class MilvusConfig:
    milvus_url: str
    chunks_collection: str
    item_name_collection: str

milvus_config = MilvusConfig(
    milvus_url=os.getenv("MILVUS_URL"),
    chunks_collection=os.getenv("CHUNKS_COLLECTION"),
    item_name_collection=os.getenv("ITEM_NAME_COLLECTION")
)

@dataclass
class MongoConfig:
    mongo_url: str
    mongo_db_name: str

mongo_config = MongoConfig(
    mongo_url=os.getenv("MONGO_URL"),
    mongo_db_name=os.getenv("MONGO_DB_NAME")
)


# 定义mcp的服务配置
@dataclass
class McpConfig:
    mcp_base_url: str
    api_key : str

mcp_config = McpConfig(
    mcp_base_url=os.getenv("MCP_DASHSCOPE_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY")
)


@dataclass
class RerankerHttpConfig:
    model: str # 模型名称
    instruct: str # 是否使用指令
    api_key: str

reranker_http_config = RerankerHttpConfig(
    api_key = os.getenv("OPENAI_API_KEY"),
    model=os.getenv("TEXT_RERANK_MODEL"),
    instruct=os.getenv("TEXT_RERANK_INSTRUCT")
)

@dataclass
class FileUploadConfig:
    data_based_root_dir: str

file_upload_config = FileUploadConfig(
    data_based_root_dir=os.getenv("DATA_BASED_ROOT_DIR")
)

@dataclass
class PermissionConfig:
    # 权限过滤总开关：置为 false 可整体关闭权限过滤（默认开启）
    filter_enabled: bool
    # 文档导入时未指定部门时的默认部门（"*" 表示全员可访问）
    default_dept: str
    # 文档导入时未指定密级时的默认密级（1-5，越大越机密）
    default_clearance_level: int

permission_config = PermissionConfig(
    filter_enabled=os.getenv("PERMISSION_FILTER_ENABLED") not in ("0", "False", "false"),
    default_dept=os.getenv("DEFAULT_DOC_DEPT") or "*",
    default_clearance_level=int(os.getenv("DEFAULT_DOC_CLEARANCE_LEVEL") or "1"),
)

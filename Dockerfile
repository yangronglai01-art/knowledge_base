# syntax=docker/dockerfile:1
# =============================================================
# 掌柜智库 RAG 应用镜像
# 导入服务(import_service) 与 查询服务(query_service) 共用一个镜像，
# 通过 docker-compose 中的 command 区分启动入口。
#
# 注意事项：
# 1. pyproject.toml 通过 [tool.uv.sources] 强制从 pytorch-cuda(cu128) 安装
#    torch，镜像体积较大（约 6-8GB）。若纯 CPU 部署，用 Dockerfile.cpu +
#    docker-compose.cpu.yml（见《部署指南》「四、构建与启动 → CPU 版（瘦身）构建」）。
# 2. 本镜像不内置 .env（凭据）、模型权重、上传数据；均通过 docker-compose
#    的 env_file 与挂载卷注入。
# =============================================================

FROM python:3.11-slim-bookworm

# 系统依赖：curl(健康检查/下载)、git、编译工具链、torch 运行所需 libgomp1
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（生产环境建议固定版本号，如 ghcr.io/astral-sh/uv:0.12.5）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先复制依赖清单，充分利用 Docker 构建缓存（源码改动不触发依赖重装）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 复制应用源码（不含 .env，凭据由 docker-compose env_file 注入）
COPY knowledge_base ./knowledge_base
COPY scripts ./scripts
COPY tests ./tests

# 模型权重与上传数据通过挂载卷提供，不打进镜像
# BGE_M3_PATH 指向挂载的本地模型目录（可在 compose 中覆盖）
ENV BGE_M3_PATH=/models/bge-m3 \
    DATA_BASED_ROOT_DIR=/app/data

# 默认启动文档导入服务；查询服务在 compose 中通过 command 覆盖
CMD ["uv", "run", "--frozen", "--no-sync", "python", "-m", "knowledge_base.web.api.import_service"]

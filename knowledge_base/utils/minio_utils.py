import json

from minio import Minio

from knowledge_base.config.config import minio_config
from knowledge_base.tool.logger import logger


minio_client = None
try:
    # 1. 创建MinIO客户端对象
    minio_client = Minio(
        endpoint=minio_config.endpoint,
        access_key=minio_config.access_key,
        secret_key=minio_config.secret_key,

        # 禁用SSL(https加密传输)
        # secure=True,
        secure=False
    )

    # 2. 如果Bucket不存在，则创建Bucket
    found = minio_client.bucket_exists(minio_config.bucket_name)
    if not found:
        # 创建Bucket
        minio_client.make_bucket(minio_config.bucket_name)

    # 3. 设置访问权限
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": [
                        "*"
                    ]
                },
                "Action": [
                    "s3:GetObject"
                ],
                "Resource": [
                    f"arn:aws:s3:::{minio_config.bucket_name}/*"
                ]
            }
        ]
    }
    minio_client.set_bucket_policy(minio_config.bucket_name, json.dumps(policy))
except Exception as e:
    logger.error(f"MinIO初始化失败: {e}" )

def get_minio_client():
    return minio_client

if __name__ == '__main__':
    minio_client = get_minio_client()
    logger.info(minio_client)
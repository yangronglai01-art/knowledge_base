
from knowledge_base.config.config import milvus_config
from knowledge_base.utils.milvus_utils import get_milvus_client, escape_milvus_string

milvus_client = get_milvus_client()

# 双引号、单引号、反斜线
collection_name = milvus_config.item_name_collection
file_title = 'hak180\\产品安全手册'
print(escape_milvus_string(file_title))
# milvus_client.delete(collection_name=collection_name, filter=f"file_title=='{file_title}'")
# milvus_client.delete(collection_name=collection_name, filter=f'file_title=="{escape_milvus_string(file_title)}"')


print("\\")
print("\\\\")

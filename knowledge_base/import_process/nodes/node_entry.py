# knowledge_base/import_process/nodes/node_entry.py
import json
import os.path
from os.path import splitext
from shlex import split

from pydantic import ValidationError

from knowledge_base.import_process.base import NodeBase
from knowledge_base.import_process.state import ImportGraphState
from knowledge_base.tool.logger import logger


class NodeEntry(NodeBase):
    """
    入口节点：任务分发
    """

    name = "node_entry"

    def process(self, state: ImportGraphState):

        logger.info(f"【{self.name}】，程序的入口节点")

        # 1. 参数非空校验
        local_file_path = state.get('local_file_path')
        if not local_file_path:
            raise ValueError("请指定文件路径")

        # 2. 提取文件名称
        file_title = splitext(os.path.basename(local_file_path))[0]

        # 3. 文件类型检查
        # 是否是pdf
        if local_file_path.endswith(".pdf"):
            logger.info(f"PDF文件检查：{local_file_path}")

            return {
                "is_pdf_read_enabled": True,
                "pdf_path": local_file_path,
                "file_title": file_title
            }

        # 是否是md
        elif local_file_path.endswith(".md"):
            logger.info(f"MD文件检查：{local_file_path}")

            return {
                "is_md_read_enabled": True,
                "md_path": local_file_path,
                "file_title": file_title
            }

        # 其它文件
        else:

            last_index = local_file_path.rfind(".")
            current_type = local_file_path[last_index + 1:]
            raise ValidationError(f"不支持的文件类型：{current_type}" )


if __name__ == '__main__':
    init_state = {
        "task_id": "task_001",
        "local_file_path": "data/examples/example_manual.md"
    }

    node_entry = NodeEntry()
    result = node_entry(init_state)
    logger.info(
        json.dumps(result, indent=4, ensure_ascii=False)
    )

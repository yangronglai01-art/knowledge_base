from knowledge_base.import_process.base import NodeBase
from knowledge_base.import_process.state import ImportGraphState
from knowledge_base.tool.logger import logger


class NodeTest(NodeBase):

    name: str = "node_test"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        logger.info(f"【{self.name}】节点的逻辑正在执行")
        return state


if __name__ == '__main__':
    init_state = {"local_file_path": "data/examples/example.pdf"}
    node_test = NodeTest()

    result = node_test(init_state)

    logger.info(result)

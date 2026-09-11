from typing import Optional

from langgraph.constants import END
from langgraph.graph import StateGraph

from knowledge_base.import_process.nodes.node_bge_embedding import NodeBGEEmbedding
from knowledge_base.import_process.nodes.node_document_split import NodeDocumentSplit
from knowledge_base.import_process.nodes.node_entry import NodeEntry
from knowledge_base.import_process.nodes.node_import_milvus import NodeImportMilvus
from knowledge_base.import_process.nodes.node_item_name_recognition import NodeItemNameRecognition
from knowledge_base.import_process.nodes.node_md_img import NodeMDImg
from knowledge_base.import_process.nodes.node_pdf_to_md import NodePDFToMD
from knowledge_base.import_process.state import ImportGraphState
from knowledge_base.tool.logger import logger


class KBImportWorkflow:
    """
    知识库导入工作流类
    """

    def __init__(self):
        """
        初始化知识库导入工作流类
        """

        # 1. 初始化工作流
        self.workflow = StateGraph(ImportGraphState)
        # 2. 初始化节点
        self._init_nodes()
        # 3. 注册节点到工作流
        self._register_nodes()
        # 4. 设置入口节点和路由规则
        self._setup_routes()
        # 5. 编译工作流（懒加载/延迟加载，第一次执行的时候编译，第二次开始则无需编译）
        self._compiled_app: Optional[object] = None

    def _init_nodes(self):
        """初始化所有业务节点（私有方法，封装节点创建逻辑）"""
        self.node_entry = NodeEntry()
        self.node_pdf_to_md = NodePDFToMD()
        self.node_md_img = NodeMDImg()
        self.node_document_split = NodeDocumentSplit()
        self.node_item_name_recognition = NodeItemNameRecognition()
        self.node_bge_embedding = NodeBGEEmbedding()
        self.node_import_milvus = NodeImportMilvus()

    def _register_nodes(self):
        """注册所有节点到工作流"""
        # 节点标识与实例属性名保持一致，便于维护
        self.workflow.add_node("node_entry", self.node_entry)
        self.workflow.add_node("node_pdf_to_md", self.node_pdf_to_md)
        self.workflow.add_node("node_md_img", self.node_md_img)
        self.workflow.add_node("node_document_split", self.node_document_split)
        self.workflow.add_node("node_item_name_recognition", self.node_item_name_recognition)
        self.workflow.add_node("node_bge_embedding", self.node_bge_embedding)
        self.workflow.add_node("node_import_milvus", self.node_import_milvus)

    def _route_after_entry(self, state: ImportGraphState) -> str:
        """入口节点后的条件路由函数（私有方法，封装路由逻辑）"""
        if state.get("is_md_read_enabled"):
            return "md_read"
        elif state.get("is_pdf_read_enabled"):
            return "pdf_read"
        else:
            return END

    def _setup_routes(self):
        """设置工作流路由规则（私有方法，封装边的定义）"""
        # 设置入口节点
        self.workflow.set_entry_point("node_entry")
        # 注册条件路由边
        self.workflow.add_conditional_edges(
            "node_entry",
            self._route_after_entry,
            {
                "md_read": "node_md_img",
                "pdf_read": "node_pdf_to_md",
                END: END
            }
        )
        # 注册静态顺序边
        self.workflow.add_edge("node_pdf_to_md", "node_md_img")
        self.workflow.add_edge("node_md_img", "node_document_split")
        self.workflow.add_edge("node_document_split", "node_item_name_recognition")
        self.workflow.add_edge("node_item_name_recognition", "node_bge_embedding")
        self.workflow.add_edge("node_bge_embedding", "node_import_milvus")
        self.workflow.add_edge("node_import_milvus", END)

    def compile(self):
        """编译工作流"""
        # if self._compiled_app is None:
        if not self._compiled_app:
            self._compiled_app = self.workflow.compile()
        return self._compiled_app

    def run(self, init_state: ImportGraphState, stream: bool = False):
        if not self._compiled_app:
            self.compile()
        if stream:
            return self._compiled_app.stream(init_state)
        else:
            return self._compiled_app.invoke(init_state)

    @classmethod
    def create_and_run(cls, init_state: ImportGraphState, stream: bool = False):
        """
        快捷方法：创建工作流实例并且执行
        :param init_state:
        :param stream: 是否流式输出
        :return:
        """

        workflow = cls()
        return workflow.run(init_state, stream)


if __name__ == '__main__':
    init_state = {
        "task_id": "task_demo",
        "local_file_path": "data/examples/example.pdf"
    }
    # kb_import_app = KBImportWorkflow()
    # for chunk in kb_import_app.run(init_state, stream=True):
    #     logger.info(chunk.keys())
    #     logger.info(chunk.items())

    # final_state = KBImportWorkflow.create_and_run(init_state)
    for chunk in KBImportWorkflow.create_and_run(init_state, stream=True):
        logger.info(chunk.keys())
        logger.info(chunk.items())

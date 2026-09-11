from langgraph.constants import START, END
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

# 1. 初始化图
workflow = StateGraph(ImportGraphState)

# 2. 注册节点
workflow.add_node("node_entry", NodeEntry())
workflow.add_node("node_pdf_to_md", NodePDFToMD())
workflow.add_node("node_md_img", NodeMDImg())
workflow.add_node("node_document_split", NodeDocumentSplit())
workflow.add_node("node_item_name_recognition", NodeItemNameRecognition())
workflow.add_node("node_bge_embedding", NodeBGEEmbedding())
workflow.add_node("node_import_milvus", NodeImportMilvus())

# 3. 设置入口节点
workflow.set_entry_point("node_entry")
# workflow.add_edge(START, "node_entry")

# 4. 定义路由规则
def rout_after_entry(state: ImportGraphState):
    if state.get("is_md_read_enabled"):
        return "md_read"
    elif state.get("is_pdf_read_enabled"):
        return "pdf_read"
    return END

# 5. 添加条件边
workflow.add_conditional_edges(
    "node_entry",
    rout_after_entry,
    {
        "md_read": "node_md_img",
        "pdf_read": "node_pdf_to_md",
        END:END
    })

# 6. 定义普通边
workflow.add_edge("node_pdf_to_md", "node_md_img")
workflow.add_edge("node_md_img", "node_document_split")
workflow.add_edge("node_document_split", "node_item_name_recognition")
workflow.add_edge("node_item_name_recognition", "node_bge_embedding")
workflow.add_edge("node_bge_embedding", "node_import_milvus")
workflow.add_edge("node_import_milvus", END)

# 7. 编译工作流
kb_import_app = workflow.compile()

# 8. 运行工作流
if __name__ == '__main__':

    init_state = {
        "task_id":"task_demo",
        "local_file_path": "data/examples/example.pdf"
    }
    final_state = kb_import_app.invoke(init_state)
    logger.info(final_state)

# knowledge_base/query_process/nodes/node_web_search_mcp.py
import asyncio
import json

from agents.mcp import MCPServerStreamableHttp

from knowledge_base.config.config import mcp_config
from knowledge_base.query_process.base import NodeBase
from knowledge_base.query_process.state import QueryGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.mongo_history_utils import format_json


class NodeWebSearchMcp(NodeBase):
    """
    节点功能，调用外部搜索引擎补充信息
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_web_search_mcp"

    def process(self, state: QueryGraphState):
        try:
            query = state.get("rewritten_query")
            result = asyncio.run(self._mcp_call(query))

            result_dict = json.loads(result.content[0].text)
            pages = result_dict.get("pages") or []

            docs = []
            for item in pages:
                snippet = item.get("snippet") or ""
                title = item.get("title") or ""
                url = item.get("url") or ""
                docs.append({"title": title, "snippet": snippet, "url": url})

            return {"web_search_docs": docs}
        except Exception as e:
            logger.exception(f"MCP调用失败:{e}")
            return {"web_search_docs": []}

    async def _mcp_call(self, query: str):
        async with MCPServerStreamableHttp(
                name="search_mcp",
                params={
                    "url": mcp_config.mcp_base_url,
                    "headers": {"Authorization": f"Bearer {mcp_config.api_key}"},
                    "timeout": 30,  # http连接的超时时间
                },
                cache_tools_list=True,
                max_retry_attempts=3,
                # MCP协议层面等待对方回复消息的最长时间
                # 包括握手、列出工具列表、调用当前工具
                client_session_timeout_seconds=30
        ) as server:
            # 阿里云百炼不支持Agent模型
            # 使用call_tool
            result = await server.call_tool(
                tool_name="bailian_web_search",
                arguments={"query": query, "count": 5}
            )
            return result


if __name__ == '__main__':
    init_state = {
        "rewritten_query": "ExampleCorp X100工业设备如何使用？"
    }

    node_web_search_mcp = NodeWebSearchMcp()
    result = node_web_search_mcp(init_state)
    logger.info(format_json(result))

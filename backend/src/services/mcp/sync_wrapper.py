"""MCP 兼容的同步工具封装。

提供 MCP 标准接口，内部直接调用本地函数。
当 MCP 服务器可用时可切换为真正的 MCP 客户端。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MCPToolWrapper:
    """MCP 兼容的工具封装器。

    将本地函数包装为 MCP 风格的工具接口，
    后续可无缝切换为真正的 MCP 客户端连接。
    """

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Any,
    ) -> None:
        """注册一个工具。"""
        self._tools[name] = {
            "description": description,
            "input_schema": input_schema,
            "handler": handler,
        }

    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有工具（MCP list_tools 等价）。"""
        return [
            {
                "name": name,
                "description": info["description"],
                "input_schema": info["input_schema"],
            }
            for name, info in self._tools.items()
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """调用工具（MCP call_tool 等价）。"""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Tool not found: {name}"}

        try:
            handler = tool["handler"]
            return handler(**arguments)
        except Exception as exc:
            logger.exception("Tool call failed: %s", name)
            return {"error": str(exc)}

    def has_tool(self, name: str) -> bool:
        """检查工具是否已注册。"""
        return name in self._tools


# 全局实例
_global_wrapper: MCPToolWrapper | None = None


def get_mcp_wrapper() -> MCPToolWrapper:
    """获取全局 MCP 工具封装实例。"""
    global _global_wrapper
    if _global_wrapper is None:
        _global_wrapper = MCPToolWrapper()
    return _global_wrapper


def init_mcp_servers() -> None:
    """初始化并注册所有工具。

    当前实现：直接注册本地函数为 MCP 工具。
    未来可扩展：连接远程 MCP 服务器。
    """
    wrapper = get_mcp_wrapper()

    # 注册 Google Scholar 搜索工具
    from services.scholar_search import search_google_scholar

    wrapper.register_tool(
        name="search_google_scholar",
        description="搜索 Google Scholar 学术文献，返回标题、作者、年份、引用数、摘要等结构化信息",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "description": "最大返回数量", "default": 10},
                "sort_by": {"type": "string", "enum": ["relevance", "date"], "default": "relevance"},
                "year_low": {"type": "integer", "description": "起始年份"},
                "year_high": {"type": "integer", "description": "截止年份"},
            },
            "required": ["query"],
        },
        handler=search_google_scholar,
    )

    # 注册 Zotero 工具
    from services.zotero_manager import ZoteroManager
    import os

    zotero_manager = ZoteroManager(
        library_id=os.getenv("ZOTERO_LIBRARY_ID"),
        library_type=os.getenv("ZOTERO_LIBRARY_TYPE", "user"),
        api_key=os.getenv("ZOTERO_API_KEY"),
    )

    if zotero_manager.available:
        wrapper.register_tool(
            name="zotero_create_collection",
            description="创建 Zotero 文献集合",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "集合名称"},
                },
                "required": ["name"],
            },
            handler=zotero_manager.create_collection,
        )

        wrapper.register_tool(
            name="zotero_add_paper",
            description="添加文献到 Zotero 图书馆",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "文献标题"},
                    "authors": {"type": "array", "items": {"type": "string"}, "description": "作者列表"},
                    "year": {"type": "string", "description": "发表年份"},
                    "abstract": {"type": "string", "description": "摘要"},
                    "url": {"type": "string", "description": "文献 URL"},
                    "doi": {"type": "string", "description": "DOI"},
                    "venue": {"type": "string", "description": "期刊/会议名称"},
                    "collection_key": {"type": "string", "description": "目标集合 key"},
                },
                "required": ["title"],
            },
            handler=zotero_manager.add_paper,
        )

        wrapper.register_tool(
            name="zotero_list_collections",
            description="列出所有 Zotero 集合",
            input_schema={"type": "object", "properties": {}},
            handler=zotero_manager.list_collections,
        )

        wrapper.register_tool(
            name="zotero_list_items",
            description="列出 Zotero 文献",
            input_schema={
                "type": "object",
                "properties": {
                    "collection_key": {"type": "string", "description": "集合 key"},
                    "limit": {"type": "integer", "description": "返回数量限制", "default": 25},
                },
            },
            handler=zotero_manager.list_items,
        )

    tools = wrapper.list_tools()
    logger.info("MCP tools registered: %d", len(tools))
    for tool in tools:
        logger.info("  - %s", tool["name"])

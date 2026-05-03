"""MCP 客户端封装 — 连接 MCP 服务器并调用工具。"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP 客户端，管理与 MCP 服务器的连接和工具调用。"""

    def __init__(self) -> None:
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, dict[str, Any]] = {}  # tool_name -> server_name
        self._context_managers: list[Any] = []

    async def connect_server(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """连接到一个 MCP 服务器。

        Args:
            server_name: 服务器名称标识
            command: 启动命令（如 python）
            args: 命令参数
            env: 环境变量
        """
        server_params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )

        try:
            # 启动服务器进程并建立连接
            read_stream, write_stream = await asyncio.to_thread(
                lambda: asyncio.run(self._connect_stdio(server_params))
            )

            session = ClientSession(read_stream, write_stream)
            await session.initialize()

            self._sessions[server_name] = session

            # 注册该服务器提供的工具
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                self._tools[tool.name] = {
                    "server": server_name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                logger.info("MCP tool registered: %s (from %s)", tool.name, server_name)

        except Exception as exc:
            logger.exception("Failed to connect MCP server '%s': %s", server_name, exc)

    async def _connect_stdio(self, params: StdioServerParameters) -> tuple:
        """建立 stdio 连接（内部辅助）。"""
        transport = await stdio_client(params).__aenter__()
        return transport

    @asynccontextmanager
    async def connect_server_ctx(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[None]:
        """异步上下文管理器方式连接服务器。"""
        server_params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            self._sessions[server_name] = session

            # 注册工具
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                self._tools[tool.name] = {
                    "server": server_name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                logger.info("MCP tool registered: %s (from %s)", tool.name, server_name)

            try:
                yield
            finally:
                self._sessions.pop(server_name, None)
                # 清理该服务器的工具
                to_remove = [
                    name for name, info in self._tools.items()
                    if info["server"] == server_name
                ]
                for name in to_remove:
                    del self._tools[name]

    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有可用工具。"""
        return [
            {
                "name": name,
                "description": info["description"],
                "input_schema": info["input_schema"],
                "server": info["server"],
            }
            for name, info in self._tools.items()
        ]

    def get_tool_info(self, tool_name: str) -> dict[str, Any] | None:
        """获取工具信息。"""
        return self._tools.get(tool_name)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """调用 MCP 工具。

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果（已解析为 Python 对象）
        """
        tool_info = self._tools.get(tool_name)
        if not tool_info:
            return {"error": f"Tool not found: {tool_name}"}

        server_name = tool_info["server"]
        session = self._sessions.get(server_name)
        if not session:
            return {"error": f"Server not connected: {server_name}"}

        try:
            result = await session.call_tool(tool_name, arguments)

            # 解析结果
            if result.content:
                text_content = result.content[0]
                if hasattr(text_content, "text"):
                    try:
                        return json.loads(text_content.text)
                    except (json.JSONDecodeError, TypeError):
                        return {"result": text_content.text}

            return {"result": str(result)}

        except Exception as exc:
            logger.exception("MCP tool call failed: %s.%s", server_name, tool_name, exc)
            return {"error": str(exc)}

    async def close(self) -> None:
        """关闭所有连接。"""
        self._sessions.clear()
        self._tools.clear()


# 全局客户端实例
_global_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """获取全局 MCP 客户端实例。"""
    global _global_client
    if _global_client is None:
        _global_client = MCPClient()
    return _global_client


async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """便捷函数：调用 MCP 工具。"""
    client = get_mcp_client()
    return await client.call_tool(tool_name, arguments)

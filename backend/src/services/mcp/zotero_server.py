"""MCP Server: Zotero 文献管理服务。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

try:
    from pyzotero import zotero as pyzotero
    PYZOTERO_AVAILABLE = True
except ImportError:
    PYZOTERO_AVAILABLE = False


def _get_client() -> Any:
    """获取 Zotero 客户端实例。"""
    if not PYZOTERO_AVAILABLE:
        return None

    library_id = os.getenv("ZOTERO_LIBRARY_ID", "")
    api_key = os.getenv("ZOTERO_API_KEY", "")
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "user")

    if not library_id or not api_key:
        return None

    try:
        return pyzotero.Zotero(library_id, library_type, api_key)
    except Exception as exc:
        logger.warning("Zotero client init failed: %s", exc)
        return None


def _create_collection(name: str) -> dict[str, Any]:
    """创建 Zotero 集合。"""
    client = _get_client()
    if not client:
        return {"success": False, "error": "Zotero 客户端不可用"}

    try:
        result = client.create_collections([{"name": name}])
        if result and "success" in result:
            key = result["success"].get("0")
            return {"success": True, "key": key, "name": name}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {"success": False, "error": "创建失败"}


def _add_paper(
    title: str,
    authors: list[str] | None = None,
    year: str = "",
    abstract: str = "",
    url: str = "",
    doi: str = "",
    venue: str = "",
    collection_key: str | None = None,
) -> dict[str, Any]:
    """添加文献到 Zotero。"""
    client = _get_client()
    if not client:
        return {"success": False, "error": "Zotero 客户端不可用"}

    item: dict[str, Any] = {
        "itemType": "journalArticle",
        "title": title,
        "creators": [],
        "abstractNote": abstract,
        "url": url,
        "DOI": doi,
        "date": year,
        "publicationTitle": venue,
    }

    if authors:
        for author in authors:
            parts = author.strip().split(" ", 1)
            if len(parts) == 2:
                item["creators"].append({
                    "creatorType": "author",
                    "firstName": parts[0],
                    "lastName": parts[1],
                })
            else:
                item["creators"].append({
                    "creatorType": "author",
                    "firstName": "",
                    "lastName": author,
                })

    try:
        result = client.create_items([item])
        if result and "success" in result:
            key = result["success"].get("0")

            if collection_key and key:
                try:
                    client.addto_collection(collection_key, [{"key": key}])
                except Exception:
                    pass

            return {"success": True, "key": key, "title": title}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {"success": False, "error": "添加失败"}


def _list_collections() -> dict[str, Any]:
    """列出所有集合。"""
    client = _get_client()
    if not client:
        return {"success": False, "error": "Zotero 客户端不可用"}

    try:
        collections = client.collections()
        return {
            "success": True,
            "collections": [
                {"key": c["key"], "name": c["data"]["name"]}
                for c in collections
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _list_items(collection_key: str | None = None, limit: int = 25) -> dict[str, Any]:
    """列出文献。"""
    client = _get_client()
    if not client:
        return {"success": False, "error": "Zotero 客户端不可用"}

    try:
        if collection_key:
            items = client.collection_items(collection_key, limit=limit)
        else:
            items = client.items(limit=limit)

        return {
            "success": True,
            "items": [
                {
                    "key": item["key"],
                    "title": item["data"].get("title", ""),
                    "itemType": item["data"].get("itemType", ""),
                    "date": item["data"].get("date", ""),
                    "creators": [
                        f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
                        for c in item["data"].get("creators", [])
                    ],
                }
                for item in items
                if item.get("data", {}).get("itemType") != "attachment"
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


app = Server("zotero")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="zotero_create_collection",
            description="创建 Zotero 文献集合",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "集合名称"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="zotero_add_paper",
            description="添加文献到 Zotero 图书馆",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "文献标题"},
                    "authors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "作者列表",
                    },
                    "year": {"type": "string", "description": "发表年份"},
                    "abstract": {"type": "string", "description": "摘要"},
                    "url": {"type": "string", "description": "文献 URL"},
                    "doi": {"type": "string", "description": "DOI"},
                    "venue": {"type": "string", "description": "期刊/会议名称"},
                    "collection_key": {"type": "string", "description": "目标集合 key（可选）"},
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="zotero_list_collections",
            description="列出所有 Zotero 集合",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="zotero_list_items",
            description="列出 Zotero 文献",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_key": {"type": "string", "description": "集合 key（可选，不填则列出全部）"},
                    "limit": {"type": "integer", "description": "返回数量限制，默认 25", "default": 25},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "zotero_create_collection":
        result = await asyncio.to_thread(_create_collection, arguments["name"])
    elif name == "zotero_add_paper":
        result = await asyncio.to_thread(
            _add_paper,
            title=arguments["title"],
            authors=arguments.get("authors"),
            year=arguments.get("year", ""),
            abstract=arguments.get("abstract", ""),
            url=arguments.get("url", ""),
            doi=arguments.get("doi", ""),
            venue=arguments.get("venue", ""),
            collection_key=arguments.get("collection_key"),
        )
    elif name == "zotero_list_collections":
        result = await asyncio.to_thread(_list_collections)
    elif name == "zotero_list_items":
        result = await asyncio.to_thread(
            _list_items,
            collection_key=arguments.get("collection_key"),
            limit=arguments.get("limit", 25),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

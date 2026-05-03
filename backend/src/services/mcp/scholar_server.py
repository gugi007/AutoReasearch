"""MCP Server: Google Scholar 学术搜索服务。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

try:
    from scholarly import scholarly
    SCHOLARLY_AVAILABLE = True
except ImportError:
    SCHOLARLY_AVAILABLE = False


def _search_scholar(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    year_low: int | None = None,
    year_high: int | None = None,
) -> dict[str, Any]:
    """执行 Google Scholar 搜索。"""
    if not SCHOLARLY_AVAILABLE:
        return {
            "results": [],
            "backend": "google_scholar",
            "error": "scholarly 未安装",
        }

    results: list[dict[str, Any]] = []

    try:
        search_query = scholarly.search_pubs(query)

        if year_low or year_high:
            filters: dict[str, Any] = {}
            if year_low:
                filters["year_low"] = year_low
            if year_high:
                filters["year_high"] = year_high
            search_query = scholarly.search_pubs(query, **filters)

        count = 0
        for pub in search_query:
            if count >= max_results:
                break

            bib = pub.get("bib", {})
            title = bib.get("title", "")
            if not title:
                continue

            authors = ", ".join(bib.get("author", []))
            year = bib.get("pub_year", "")
            abstract = bib.get("abstract", "")
            venue = bib.get("venue", "")
            citations = pub.get("num_citations", 0)
            url = pub.get("pub_url", "") or pub.get("eprint_url", "")

            results.append({
                "title": title,
                "url": url or f"https://scholar.google.com/scholar?q={title}",
                "content": abstract,
                "authors": authors,
                "year": year,
                "venue": venue,
                "citations": citations,
            })
            count += 1

        if sort_by == "relevance" and results:
            results.sort(key=lambda x: x.get("citations", 0), reverse=True)

    except StopIteration:
        pass
    except Exception as exc:
        return {"results": [], "backend": "google_scholar", "error": str(exc)}

    return {"results": results, "backend": "google_scholar"}


app = Server("google-scholar")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_google_scholar",
            description="搜索 Google Scholar 学术文献，返回标题、作者、年份、引用数、摘要等结构化信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回数量，默认 10",
                        "default": 10,
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["relevance", "date"],
                        "description": "排序方式，默认 relevance",
                        "default": "relevance",
                    },
                    "year_low": {
                        "type": "integer",
                        "description": "起始年份（可选）",
                    },
                    "year_high": {
                        "type": "integer",
                        "description": "截止年份（可选）",
                    },
                },
                "required": ["query"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "search_google_scholar":
        result = await asyncio.to_thread(
            _search_scholar,
            query=arguments["query"],
            max_results=arguments.get("max_results", 10),
            sort_by=arguments.get("sort_by", "relevance"),
            year_low=arguments.get("year_low"),
            year_high=arguments.get("year_high"),
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

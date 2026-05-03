"""Utility helpers shared across deep researcher services."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union

CHARS_PER_TOKEN = 4

logger = logging.getLogger(__name__)


def get_config_value(value: Any) -> str:
    """Return configuration value as plain string."""

    return value if isinstance(value, str) else value.value


def strip_thinking_tokens(text: str) -> str:
    """Remove ``<think>`` sections from model responses."""

    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text


def deduplicate_and_format_sources(
    search_response: Dict[str, Any] | List[Dict[str, Any]],
    max_tokens_per_source: int,
    *,
    fetch_full_page: bool = False,
) -> str:
    """Format and deduplicate search results for downstream prompting."""

    if isinstance(search_response, dict):
        sources_list = search_response.get("results", [])
    else:
        sources_list = search_response

    unique_sources: dict[str, Dict[str, Any]] = {}
    for source in sources_list:
        url = source.get("url")
        if not url:
            continue
        if url not in unique_sources:
            unique_sources[url] = source

    formatted_parts: List[str] = []
    for source in unique_sources.values():
        title = source.get("title") or source.get("url", "")
        content = source.get("content", "")
        formatted_parts.append(f"信息来源: {title}\n\n")
        formatted_parts.append(f"URL: {source.get('url', '')}\n\n")
        formatted_parts.append(f"信息内容: {content}\n\n")

        if fetch_full_page:
            raw_content = source.get("raw_content")
            if raw_content is None:
                logger.debug("raw_content missing for %s", source.get("url", ""))
                raw_content = ""
            char_limit = max_tokens_per_source * CHARS_PER_TOKEN
            if len(raw_content) > char_limit:
                raw_content = f"{raw_content[:char_limit]}... [truncated]"
            formatted_parts.append(
                f"详细信息内容限制为 {max_tokens_per_source} 个 token: {raw_content}\n\n"
            )

    return "".join(formatted_parts).strip()


def format_sources(search_results: Dict[str, Any] | None) -> str:
    """Return bullet list summarising search sources."""

    if not search_results:
        return ""

    results = search_results.get("results", [])
    backend = search_results.get("backend", "")

    lines = []
    for item in results:
        if not item.get("url"):
            continue

        title = item.get("title", item.get("url", ""))
        url = item.get("url", "")

        # 学术来源增加作者、年份、引用数
        if backend == "google_scholar" and item.get("authors"):
            authors = item.get("authors", "")
            year = item.get("year", "")
            citations = item.get("citations", 0)
            venue = item.get("venue", "")

            meta = []
            if authors:
                meta.append(authors)
            if year:
                meta.append(f"({year})")
            if venue:
                meta.append(f"[{venue}]")
            if citations:
                meta.append(f"被引{citations}次")

            meta_str = " ".join(meta)
            lines.append(f"* {title} — {meta_str}\n  {url}")
        else:
            lines.append(f"* {title} : {url}")

    return "\n".join(lines)

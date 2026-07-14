"""Search dispatch helpers — Web search + Google Scholar (via MCP)。"""

from __future__ import annotations

import logging
from typing import Any

from services.search_tool import SearchTool
from config import Configuration
from utils import (
    deduplicate_and_format_sources,
    format_sources,
    get_config_value,
)

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000
_GLOBAL_SEARCH_TOOL = SearchTool(backend="hybrid")


def dispatch_search(
    query: str,
    config: Configuration,
    loop_count: int,
) -> tuple[dict[str, Any] | None, list[str], str | None, str]:
    """Execute configured search backend and normalise response payload."""

    search_api = get_config_value(config.search_api)
    max_results = config.papers_per_task  # 使用配置的每任务文献篇数

    try:
        if search_api == "academic":
            from services.academic_search import search_academic
            raw_response = search_academic(query, max_results=max_results)
        elif search_api == "arxiv":
            from services.arxiv_search import search_arxiv
            raw_response = search_arxiv(query, max_results=max_results)
        elif search_api == "google_scholar":
            raw_response = _search_via_mcp(query)
        else:
            raw_response = _GLOBAL_SEARCH_TOOL.run(
                {
                    "input": query,
                    "backend": search_api,
                    "mode": "structured",
                    "fetch_full_page": config.fetch_full_page,
                    "max_results": max_results,
                    "max_tokens_per_source": MAX_TOKENS_PER_SOURCE,
                    "loop_count": loop_count,
                }
            )
    except Exception as exc:
        logger.exception("Search backend %s failed: %s", search_api, exc)
        raise

    if isinstance(raw_response, str):
        notices = [raw_response]
        logger.warning("Search backend %s returned text notice: %s", search_api, raw_response)
        payload: dict[str, Any] = {
            "results": [],
            "backend": search_api,
            "answer": None,
            "notices": notices,
        }
    else:
        payload = raw_response
        notices = list(payload.get("notices") or [])

    backend_label = str(payload.get("backend") or search_api)
    answer_text = payload.get("answer")
    results = payload.get("results", [])

    # 应用 venue 分区筛选
    if config.venue_tiers and results:
        from services.venue_filter import VenueFilter
        vf = VenueFilter()
        filtered = vf.filter_results(results, config.venue_tiers)
        if filtered:
            payload["results"] = filtered
            results = filtered
            tier_labels = ", ".join(config.venue_tiers)
            notices.append(f"已按 {tier_labels} 筛选，保留 {len(filtered)} 篇文献")
            logger.info("Venue filter applied: %s, kept %d/%d results",
                       tier_labels, len(filtered), len(results))
        else:
            tier_labels = ", ".join(config.venue_tiers)
            notices.append(f"未找到符合 {tier_labels} 的文献，返回全部结果")
            logger.info("Venue filter %s returned no matches, keeping all results", tier_labels)

    # 为结果添加分区信息
    if results:
        from services.venue_filter import VenueFilter
        vf = VenueFilter()
        results = vf.enrich_results(results)
        payload["results"] = results

    if notices:
        for notice in notices:
            logger.info("Search notice (%s): %s", backend_label, notice)

    logger.info(
        "Search backend=%s resolved_backend=%s answer=%s results=%s",
        search_api,
        backend_label,
        bool(answer_text),
        len(results),
    )

    return payload, notices, answer_text, backend_label


def _search_via_mcp(query: str) -> dict[str, Any]:
    """通过 MCP 调用 Google Scholar 搜索。"""
    from services.mcp.sync_wrapper import get_mcp_wrapper

    wrapper = get_mcp_wrapper()

    if not wrapper.has_tool("search_google_scholar"):
        # 回退到直接调用
        from services.scholar_search import search_google_scholar
        return search_google_scholar(query, max_results=10)

    result = wrapper.call_tool("search_google_scholar", {"query": query, "max_results": 10})

    if isinstance(result, dict) and "error" in result:
        logger.warning("MCP Google Scholar error: %s", result["error"])
        # 回退到直接调用
        from services.scholar_search import search_google_scholar
        return search_google_scholar(query, max_results=10)

    return result


def prepare_research_context(
    search_result: dict[str, Any] | None,
    answer_text: str | None,
    config: Configuration,
) -> tuple[str, str]:
    """Build structured context and source summary for downstream agents."""

    sources_summary = format_sources(search_result)
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )

    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"

    return sources_summary, context

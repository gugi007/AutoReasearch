"""Google Scholar 学术搜索模块 — 基于 scholarly 库。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from scholarly import scholarly
    SCHOLARLY_AVAILABLE = True
except ImportError:
    SCHOLARLY_AVAILABLE = False
    logger.warning("scholarly not installed, Google Scholar search unavailable")


def search_google_scholar(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    year_low: int | None = None,
    year_high: int | None = None,
) -> dict[str, Any]:
    """搜索 Google Scholar，返回结构化文献列表。

    Args:
        query: 搜索关键词
        max_results: 最大返回数量
        sort_by: 排序方式 ("relevance" 或 "date")
        year_low: 起始年份
        year_high: 截止年份

    Returns:
        结构化结果，格式与 SearchTool 兼容
    """
    if not SCHOLARLY_AVAILABLE:
        return {
            "results": [],
            "backend": "google_scholar",
            "answer": None,
            "notices": ["scholarly 未安装，无法使用 Google Scholar 搜索"],
        }

    results: list[dict[str, Any]] = []
    notices: list[str] = []

    try:
        search_query = scholarly.search_pubs(query)

        # 应用年份过滤
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
            authors = ", ".join(bib.get("author", []))
            year = bib.get("pub_year", "")
            abstract = bib.get("abstract", "")
            venue = bib.get("venue", "")
            citations = pub.get("num_citations", 0)
            url = pub.get("pub_url", "") or pub.get("eprint_url", "")

            if not title:
                continue

            # 构建结构化摘要
            meta_parts = []
            if authors:
                meta_parts.append(f"作者: {authors}")
            if year:
                meta_parts.append(f"年份: {year}")
            if venue:
                meta_parts.append(f"期刊/会议: {venue}")
            if citations:
                meta_parts.append(f"引用数: {citations}")

            content = "\n".join(meta_parts)
            if abstract:
                content += f"\n\n摘要: {abstract}"

            results.append({
                "title": title,
                "url": url or f"https://scholar.google.com/scholar?q={title}",
                "content": content,
                "raw_content": abstract,
                "authors": authors,
                "year": year,
                "venue": venue,
                "citations": citations,
            })
            count += 1

        # 按引用数排序（如果 relevance）
        if sort_by == "relevance" and results:
            results.sort(key=lambda x: x.get("citations", 0), reverse=True)

    except StopIteration:
        pass
    except Exception as exc:
        logger.exception("Google Scholar search failed: %s", exc)
        notices.append(f"Google Scholar 搜索失败: {exc}")

    return {
        "results": results,
        "backend": "google_scholar",
        "answer": None,
        "notices": notices,
    }

"""Crossref metadata search based on the public REST API."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

CROSSREF_WORKS_API = "https://api.crossref.org/works"


def search_crossref(
    query: str,
    max_results: int = 10,
    mailto: str | None = None,
) -> dict[str, Any]:
    """Search Crossref and return normalized publication metadata."""
    results: list[dict[str, Any]] = []
    notices: list[str] = []

    headers = {"User-Agent": "AutoResearch/1.0"}
    if mailto:
        headers["User-Agent"] = f"AutoResearch/1.0 (mailto:{mailto})"

    try:
        response = requests.get(
            CROSSREF_WORKS_API,
            params={
                "query.bibliographic": query,
                "rows": min(max_results, 50),
                "sort": "relevance",
                "order": "desc",
            },
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        for item in data.get("message", {}).get("items", []):
            title = _first(item.get("title"))
            if not title:
                continue

            authors = _format_authors(item.get("author", []))
            year = _extract_year(item)
            venue = _first(item.get("container-title"))
            doi = item.get("DOI", "")
            citations = item.get("is-referenced-by-count") or 0
            url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
            abstract = _strip_crossref_tags(item.get("abstract") or "")

            meta_parts = []
            if authors:
                meta_parts.append(f"作者: {authors}")
            if year:
                meta_parts.append(f"年份: {year}")
            if venue:
                meta_parts.append(f"期刊/会议: {venue}")
            meta_parts.append(f"引用数: {citations}")
            meta_parts.append("来源: Crossref")

            content = "\n".join(meta_parts)
            if abstract:
                content += f"\n\n摘要: {abstract}"

            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": content,
                    "raw_content": abstract,
                    "authors": authors,
                    "year": year,
                    "venue": venue,
                    "citations": citations,
                    "doi": doi,
                    "source": "crossref",
                }
            )

    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response else 0
        logger.warning("Crossref HTTP error: %s", exc)
        notices.append(f"Crossref 搜索失败: HTTP {status_code}")
    except Exception as exc:
        logger.warning("Crossref search failed: %s", exc)
        notices.append(f"Crossref 搜索失败: {exc}")

    return {
        "results": results,
        "backend": "crossref",
        "answer": None,
        "notices": notices,
    }


def _first(value: list[Any] | None) -> str:
    if not value:
        return ""
    first = value[0]
    return str(first) if first is not None else ""


def _format_authors(authors: list[dict[str, Any]]) -> str:
    names = []
    for author in authors[:12]:
        given = author.get("given", "")
        family = author.get("family", "")
        name = " ".join(part for part in [given, family] if part).strip()
        if name:
            names.append(name)
    return ", ".join(names)


def _extract_year(item: dict[str, Any]) -> int | str:
    for key in ["published-print", "published-online", "published", "created"]:
        date_parts = item.get(key, {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            return date_parts[0][0]
    return ""


def _strip_crossref_tags(value: str) -> str:
    if not value:
        return ""

    import re

    return re.sub(r"<[^>]+>", "", value).strip()

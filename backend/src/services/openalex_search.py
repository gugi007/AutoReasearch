"""OpenAlex literature search based on the public Works API."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

OPENALEX_WORKS_API = "https://api.openalex.org/works"


def search_openalex(
    query: str,
    max_results: int = 10,
    mailto: str | None = None,
) -> dict[str, Any]:
    """Search OpenAlex and return normalized paper records."""
    results: list[dict[str, Any]] = []
    notices: list[str] = []

    params: dict[str, Any] = {
        "search": query,
        "per-page": min(max_results, 50),
        "sort": "cited_by_count:desc",
    }
    if mailto:
        params["mailto"] = mailto

    try:
        response = requests.get(OPENALEX_WORKS_API, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        for item in data.get("results", []):
            title = item.get("title") or item.get("display_name") or ""
            if not title:
                continue

            authors = _format_authors(item.get("authorships", []))
            year = item.get("publication_year") or ""
            venue = _extract_venue(item)
            citations = item.get("cited_by_count") or 0
            abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
            doi = _normalize_doi(item.get("doi"))
            url = _best_url(item, doi)
            pdf_url = _best_pdf_url(item)

            meta_parts = []
            if authors:
                meta_parts.append(f"作者: {authors}")
            if year:
                meta_parts.append(f"年份: {year}")
            if venue:
                meta_parts.append(f"期刊/会议: {venue}")
            meta_parts.append(f"引用数: {citations}")
            meta_parts.append("来源: OpenAlex")

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
                    "source": "openalex",
                    "pdf_url": pdf_url,
                    "open_access": item.get("open_access", {}),
                }
            )

    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response else 0
        logger.warning("OpenAlex HTTP error: %s", exc)
        notices.append(f"OpenAlex 搜索失败: HTTP {status_code}")
    except Exception as exc:
        logger.warning("OpenAlex search failed: %s", exc)
        notices.append(f"OpenAlex 搜索失败: {exc}")

    return {
        "results": results,
        "backend": "openalex",
        "answer": None,
        "notices": notices,
    }


def _format_authors(authorships: list[dict[str, Any]]) -> str:
    names = []
    for authorship in authorships[:12]:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    return ", ".join(names)


def _extract_venue(item: dict[str, Any]) -> str:
    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") or {}
    if source.get("display_name"):
        return source["display_name"]

    host_venue = item.get("host_venue") or {}
    return host_venue.get("display_name") or ""


def _normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("https://doi.org/", "").strip()


def _best_url(item: dict[str, Any], doi: str) -> str:
    open_access = item.get("open_access") or {}
    if open_access.get("oa_url"):
        return open_access["oa_url"]

    primary_location = item.get("primary_location") or {}
    if primary_location.get("landing_page_url"):
        return primary_location["landing_page_url"]

    ids = item.get("ids") or {}
    if ids.get("openalex"):
        return ids["openalex"]

    if doi:
        return f"https://doi.org/{doi}"

    return ""


def _best_pdf_url(item: dict[str, Any]) -> str:
    open_access = item.get("open_access") or {}
    oa_url = open_access.get("oa_url") or ""
    if oa_url.lower().endswith(".pdf"):
        return oa_url

    primary_location = item.get("primary_location") or {}
    pdf_url = primary_location.get("pdf_url") or ""
    if pdf_url:
        return pdf_url

    return ""


def _reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""

    positions: list[tuple[int, str]] = []
    for word, offsets in index.items():
        for offset in offsets:
            positions.append((offset, word))

    if not positions:
        return ""

    positions.sort(key=lambda item: item[0])
    return " ".join(word for _offset, word in positions)

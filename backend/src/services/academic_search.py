"""Multi-source academic search aggregator.

The default path avoids Google Scholar scraping and combines stable APIs:
OpenAlex, Semantic Scholar, arXiv, and Crossref. Google Scholar can still be
enabled explicitly as a best-effort fallback, but it is not part of the normal
pipeline because it is not automation-friendly.
"""

from __future__ import annotations

import concurrent.futures
import logging
import math
import os
import re
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

TITLE_SIMILARITY_THRESHOLD = 0.86
SOURCE_TIMEOUT = 15

SearchFn = Callable[..., dict[str, Any]]


def search_academic(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    include_google_scholar: bool | None = None,
) -> dict[str, Any]:
    """Search academic papers across multiple stable sources.

    Args:
        query: Search keywords.
        max_results: Maximum merged records to return.
        sort_by: "relevance" or "citations".
        include_google_scholar: Optional override. Defaults to env
            ENABLE_GOOGLE_SCHOLAR=false.
    """
    if include_google_scholar is None:
        include_google_scholar = os.getenv("ENABLE_GOOGLE_SCHOLAR", "").lower() in {
            "1",
            "true",
            "yes",
        }

    source_calls: list[tuple[str, SearchFn, dict[str, Any]]] = [
        ("openalex", _search_openalex, {"query": query, "max_results": max_results}),
        (
            "semantic_scholar",
            _search_semantic_scholar,
            {"query": query, "max_results": max_results},
        ),
        ("arxiv", _search_arxiv, {"query": query, "max_results": max_results}),
        ("crossref", _search_crossref, {"query": query, "max_results": max_results}),
    ]

    if include_google_scholar:
        source_calls.append(
            (
                "google_scholar",
                _search_google_scholar,
                {"query": query, "max_results": max_results},
            )
        )

    collected: list[dict[str, Any]] = []
    notices: list[str] = []
    source_counts: dict[str, int] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(source_calls)) as pool:
        future_map = {
            pool.submit(_run_source, name, fn, kwargs): name
            for name, fn, kwargs in source_calls
        }
        done, pending = concurrent.futures.wait(
            future_map,
            timeout=SOURCE_TIMEOUT,
            return_when=concurrent.futures.ALL_COMPLETED,
        )

        for future in pending:
            name = future_map[future]
            future.cancel()
            source_counts[name] = 0
            notices.append(f"{name} 搜索超时，已跳过")

        for future in done:
            name = future_map[future]
            try:
                results, source_notices = future.result()
            except Exception as exc:
                logger.warning("%s search failed: %s", name, exc)
                results, source_notices = [], [f"{name} 搜索失败: {exc}"]

            source_counts[name] = len(results)
            collected.extend(results)
            notices.extend(source_notices)

    merged = _merge_and_deduplicate(collected)
    for item in merged:
        item["academic_score"] = _score_paper(item, query)

    if sort_by == "citations":
        merged.sort(key=lambda item: item.get("citations") or 0, reverse=True)
    else:
        merged.sort(key=lambda item: item.get("academic_score") or 0, reverse=True)

    limited = merged[:max_results]
    if include_google_scholar:
        notices.append("Google Scholar 已作为可选兜底源启用，结果稳定性取决于网页访问情况")
    else:
        notices.append("Google Scholar 默认未启用；当前使用 OpenAlex/Semantic Scholar/arXiv/Crossref 聚合")

    logger.info(
        "Academic aggregate query=%r counts=%s merged=%d returned=%d",
        query,
        source_counts,
        len(merged),
        len(limited),
    )

    return {
        "results": limited,
        "backend": "academic_aggregate",
        "answer": None,
        "notices": notices,
        "source_counts": source_counts,
    }


def _run_source(
    name: str,
    fn: SearchFn,
    kwargs: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    payload = fn(**kwargs)
    if not isinstance(payload, dict):
        return [], [f"{name} 返回了非结构化结果"]

    results = payload.get("results", []) or []
    for item in results:
        item.setdefault("source", name)

    return results, list(payload.get("notices") or [])


def _search_openalex(**kwargs: Any) -> dict[str, Any]:
    from services.openalex_search import search_openalex

    return search_openalex(**kwargs)


def _search_semantic_scholar(**kwargs: Any) -> dict[str, Any]:
    from services.semantic_scholar_search import search_semantic_scholar

    return search_semantic_scholar(**kwargs)


def _search_arxiv(**kwargs: Any) -> dict[str, Any]:
    from services.arxiv_search import search_arxiv

    return search_arxiv(**kwargs)


def _search_crossref(**kwargs: Any) -> dict[str, Any]:
    from services.crossref_search import search_crossref

    return search_crossref(**kwargs)


def _search_google_scholar(**kwargs: Any) -> dict[str, Any]:
    from services.scholar_search import search_google_scholar

    return search_google_scholar(**kwargs)


def _merge_and_deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_titles: list[str] = []

    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue

        normalized = _normalize_title(title)
        duplicate_idx = _find_duplicate_index(normalized, seen_titles)
        if duplicate_idx is None:
            seen_titles.append(normalized)
            merged.append(dict(item))
            continue

        merged[duplicate_idx] = _merge_records(merged[duplicate_idx], item)

    return merged


def _merge_records(primary: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = dict(primary)

    primary_sources = _as_source_list(result.get("source"))
    incoming_sources = _as_source_list(incoming.get("source"))
    result["source"] = sorted(set(primary_sources + incoming_sources))

    for key in ["doi", "url", "raw_content", "authors", "year", "venue"]:
        if not result.get(key) and incoming.get(key):
            result[key] = incoming[key]

    result["citations"] = max(_safe_int(result.get("citations")), _safe_int(incoming.get("citations")))

    if len(str(incoming.get("content") or "")) > len(str(result.get("content") or "")):
        result["content"] = incoming["content"]

    if incoming.get("open_access") and not result.get("open_access"):
        result["open_access"] = incoming["open_access"]

    return result


def _score_paper(item: dict[str, Any], query: str) -> float:
    title = str(item.get("title") or "")
    query_terms = set(_tokenize(query))
    title_terms = set(_tokenize(title))
    title_overlap = len(query_terms & title_terms) / max(1, len(query_terms))

    citation_score = math.log1p(_safe_int(item.get("citations"))) / 12
    citation_score = min(citation_score, 1.0)

    current_year = 2026
    year = _safe_int(item.get("year"))
    if year:
        recency_score = max(0.0, min(1.0, 1 - ((current_year - year) / 12)))
    else:
        recency_score = 0.2

    has_pdf_or_oa = bool(_has_pdf_signal(item))
    has_doi = bool(item.get("doi"))
    source_score = _source_confidence(item.get("source"))

    return (
        title_overlap * 0.35
        + citation_score * 0.25
        + recency_score * 0.15
        + (0.10 if has_pdf_or_oa else 0.0)
        + (0.05 if has_doi else 0.0)
        + source_score * 0.10
    )


def _find_duplicate_index(title: str, seen_titles: list[str]) -> int | None:
    for idx, seen in enumerate(seen_titles):
        if title == seen:
            return idx
        if SequenceMatcher(None, title, seen).ratio() >= TITLE_SIMILARITY_THRESHOLD:
            return idx
    return None


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(token) > 2]


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_source_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _source_confidence(source: Any) -> float:
    sources = set(_as_source_list(source))
    score = 0.0
    if "openalex" in sources:
        score += 0.35
    if "semantic_scholar" in sources:
        score += 0.3
    if "arxiv" in sources:
        score += 0.2
    if "crossref" in sources:
        score += 0.15
    if "google_scholar" in sources:
        score += 0.05
    return min(score, 1.0)


def _has_pdf_signal(item: dict[str, Any]) -> bool:
    url = str(item.get("url") or "").lower()
    if url.endswith(".pdf") or "arxiv.org/abs/" in url or "arxiv.org/pdf/" in url:
        return True

    open_access = item.get("open_access") or {}
    return bool(open_access.get("oa_url"))

"""Semantic Scholar 学术搜索模块 — 基于 REST API。"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_MIN_REQUEST_INTERVAL = float(os.getenv("SEMANTIC_SCHOLAR_MIN_INTERVAL", "2.0"))


def search_semantic_scholar(
    query: str,
    max_results: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
) -> dict[str, Any]:
    """搜索 Semantic Scholar，返回结构化文献列表。

    Args:
        query: 搜索关键词
        max_results: 最大返回数量
        year_from: 起始年份
        year_to: 截止年份

    Returns:
        结构化结果，格式与 search_google_scholar 兼容
    """
    results: list[dict[str, Any]] = []
    notices: list[str] = []

    try:
        params = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": "title,authors,year,abstract,url,venue,citationCount,externalIds",
        }

        if year_from:
            params["year"] = f"{year_from}-"
        if year_to:
            params["year"] = f"-{year_to}"
        if year_from and year_to:
            params["year"] = f"{year_from}-{year_to}"

        headers = {"User-Agent": "AutoResearch/1.0"}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key

        with _REQUEST_LOCK:
            global _LAST_REQUEST_AT
            elapsed = time.monotonic() - _LAST_REQUEST_AT
            if elapsed < _MIN_REQUEST_INTERVAL:
                time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
            response = requests.get(
                SEMANTIC_SCHOLAR_API,
                params=params,
                headers=headers,
                timeout=15,
            )
            _LAST_REQUEST_AT = time.monotonic()
        response.raise_for_status()
        data = response.json()

        for paper in data.get("data", []):
            title = paper.get("title", "")
            if not title:
                continue

            authors_list = paper.get("authors", [])
            authors = ", ".join(a.get("name", "") for a in authors_list if a.get("name"))
            year = paper.get("year", "")
            abstract = paper.get("abstract", "")
            url = paper.get("url", "")
            venue = paper.get("venue", "")
            citations = paper.get("citationCount", 0)

            # 获取 PDF 链接
            external_ids = paper.get("externalIds", {})
            arxiv_id = external_ids.get("ArXiv")
            pdf_url = ""
            if arxiv_id:
                url = f"https://arxiv.org/abs/{arxiv_id}"
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

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
            meta_parts.append(f"来源: Semantic Scholar")

            content = "\n".join(meta_parts)
            if abstract:
                content += f"\n\n摘要: {abstract}"

            results.append({
                "title": title,
                "url": url or f"https://www.semanticscholar.org/search?q={title}",
                "content": content,
                "raw_content": abstract,
                "authors": authors,
                "year": year,
                "venue": venue,
                "citations": citations,
                "source": "semantic_scholar",
                "pdf_url": pdf_url,
            })

        # 按引用数排序
        results.sort(key=lambda x: x.get("citations", 0), reverse=True)

    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        if status_code == 429:
            logger.warning("Semantic Scholar rate limited")
            notices.append("Semantic Scholar 请求过于频繁，请稍后重试")
        else:
            logger.warning("Semantic Scholar HTTP error: %s", exc)
            notices.append(f"Semantic Scholar 搜索失败: HTTP {status_code}")
    except Exception as exc:
        logger.exception("Semantic Scholar search failed: %s", exc)
        notices.append(f"Semantic Scholar 搜索失败: {exc}")

    return {
        "results": results,
        "backend": "semantic_scholar",
        "answer": None,
        "notices": notices,
    }

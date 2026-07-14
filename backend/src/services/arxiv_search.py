"""arXiv 学术搜索模块 — 基于 arxiv 库。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import arxiv
    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False
    logger.warning("arxiv not installed, arXiv search unavailable")


def search_arxiv(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """搜索 arXiv，返回结构化文献列表。

    Args:
        query: 搜索关键词（英文）
        max_results: 最大返回数量
        sort_by: 排序方式 ("relevance" 或 "date")
        categories: arXiv 分类过滤，如 ["cs.AI", "cs.CL", "cs.CV"]

    Returns:
        结构化结果，格式与 search_google_scholar 兼容
    """
    if not ARXIV_AVAILABLE:
        return {
            "results": [],
            "backend": "arxiv",
            "answer": None,
            "notices": ["arxiv 未安装，无法使用 arXiv 搜索"],
        }

    results: list[dict[str, Any]] = []
    notices: list[str] = []

    try:
        # 构建查询
        search_query = query
        if categories:
            cat_filter = " OR ".join(f"cat:{cat}" for cat in categories)
            search_query = f"({query}) AND ({cat_filter})"

        # 设置排序
        sort_criterion = arxiv.SortCriterion.Relevance
        if sort_by == "date":
            sort_criterion = arxiv.SortCriterion.SubmittedDate

        # 执行搜索（减少请求数量避免限流）
        client = arxiv.Client(
            page_size=max_results,
            delay_seconds=3.0,  # 请求间隔，避免 429
            num_retries=3,
        )
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=sort_criterion,
        )

        for paper in client.results(search):
            title = paper.title
            authors = ", ".join(author.name for author in paper.authors)
            year = paper.published.year if paper.published else ""
            abstract = paper.summary
            url = paper.entry_id
            categories_list = paper.categories
            venue = "arXiv"

            if not title:
                continue

            # 构建结构化摘要
            meta_parts = []
            if authors:
                meta_parts.append(f"作者: {authors}")
            if year:
                meta_parts.append(f"年份: {year}")
            if categories_list:
                meta_parts.append(f"分类: {', '.join(categories_list)}")
            meta_parts.append(f"来源: arXiv")

            content = "\n".join(meta_parts)
            if abstract:
                content += f"\n\n摘要: {abstract}"

            results.append({
                "title": title,
                "url": url,
                "pdf_url": paper.pdf_url,
                "content": content,
                "raw_content": abstract,
                "authors": authors,
                "year": year,
                "venue": venue,
                "citations": 0,  # arXiv 不提供引用数
                "categories": categories_list,
            })

    except Exception as exc:
        logger.exception("arXiv search failed: %s", exc)
        notices.append(f"arXiv 搜索失败: {exc}")

    return {
        "results": results,
        "backend": "arxiv",
        "answer": None,
        "notices": notices,
    }

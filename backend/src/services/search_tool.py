"""独立的搜索工具模块 — 从 HelloAgents SearchTool 提取，无外部框架依赖。"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

try:
    from ddgs import DDGS
except Exception:
    DDGS = None  # type: ignore

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None  # type: ignore

try:
    from markdownify import markdownify
except Exception:
    markdownify = None  # type: ignore

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
DEFAULT_MAX_RESULTS = 5
SUPPORTED_BACKENDS = {
    "academic",
    "arxiv",
    "google_scholar",
    "hybrid",
    "advanced",
    "tavily",
    "duckduckgo",
    "searxng",
    "perplexity",
}


def _limit_text(text: str, token_limit: int) -> str:
    char_limit = token_limit * CHARS_PER_TOKEN
    if len(text) <= char_limit:
        return text
    return text[:char_limit] + "... [truncated]"


def _fetch_raw_content(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as exc:
        logger.debug("Failed to fetch raw content for %s: %s", url, exc)
        return None

    if markdownify is not None:
        try:
            return markdownify(response.text)  # type: ignore[arg-type]
        except Exception as exc:
            logger.debug("markdownify failed for %s: %s", url, exc)
    return response.text


def _normalized_result(
    *,
    title: str,
    url: str,
    content: str,
    raw_content: str | None,
) -> dict[str, str]:
    payload: dict[str, str] = {
        "title": title or url,
        "url": url,
        "content": content or "",
    }
    if raw_content is not None:
        payload["raw_content"] = raw_content
    return payload


def _structured_payload(
    results: list[dict[str, Any]],
    *,
    backend: str,
    answer: str | None = None,
    notices: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "results": results,
        "backend": backend,
        "answer": answer,
        "notices": list(notices or []),
    }


class SearchTool:
    """支持多后端的搜索工具，与 HelloAgents SearchTool 接口兼容。"""

    def __init__(
        self,
        backend: str = "hybrid",
        tavily_key: str | None = None,
        perplexity_key: str | None = None,
    ) -> None:
        self.backend = (backend or "hybrid").lower()
        self.tavily_key = tavily_key or os.getenv("TAVILY_API_KEY")
        self.perplexity_key = perplexity_key or os.getenv("PERPLEXITY_API_KEY")
        self.tavily_client = None
        self._setup_backends()

    def _setup_backends(self) -> None:
        if self.tavily_key and TavilyClient is not None:
            try:
                self.tavily_client = TavilyClient(api_key=self.tavily_key)
                logger.info("Tavily search backend initialized")
            except Exception as exc:
                logger.warning("Tavily init failed: %s", exc)

        if self.backend not in SUPPORTED_BACKENDS:
            self.backend = "hybrid"

    def run(self, parameters: dict[str, Any]) -> dict[str, Any] | str:
        """执行搜索，返回结构化结果或文本。"""
        query = (parameters.get("input") or parameters.get("query") or "").strip()
        if not query:
            return "错误：搜索查询不能为空"

        backend = str(parameters.get("backend", self.backend) or "hybrid").lower()
        if backend not in SUPPORTED_BACKENDS:
            backend = "hybrid"

        mode = str(parameters.get("mode") or "text").lower()
        fetch_full_page = bool(parameters.get("fetch_full_page", False))
        max_results = int(parameters.get("max_results", DEFAULT_MAX_RESULTS))
        max_tokens = int(parameters.get("max_tokens_per_source", 2000))
        loop_count = int(parameters.get("loop_count", 0))

        payload = self._structured_search(
            query=query,
            backend=backend,
            fetch_full_page=fetch_full_page,
            max_results=max_results,
            max_tokens=max_tokens,
            loop_count=loop_count,
        )

        if mode in {"structured", "json", "dict"}:
            return payload

        return self._format_text_response(query=query, payload=payload)

    # ------------------------------------------------------------------
    # Backend dispatch
    # ------------------------------------------------------------------

    def _structured_search(
        self,
        *,
        query: str,
        backend: str,
        fetch_full_page: bool,
        max_results: int,
        max_tokens: int,
        loop_count: int,
    ) -> dict[str, Any]:
        target = "advanced" if backend == "hybrid" else backend

        if target == "tavily":
            return self._search_tavily(
                query=query,
                fetch_full_page=fetch_full_page,
                max_results=max_results,
                max_tokens=max_tokens,
            )
        if target == "duckduckgo":
            return self._search_duckduckgo(
                query=query,
                fetch_full_page=fetch_full_page,
                max_results=max_results,
                max_tokens=max_tokens,
            )
        if target == "searxng":
            return self._search_searxng(
                query=query,
                fetch_full_page=fetch_full_page,
                max_results=max_results,
                max_tokens=max_tokens,
            )
        if target == "perplexity":
            return self._search_perplexity(
                query=query,
                fetch_full_page=fetch_full_page,
                max_results=max_results,
                max_tokens=max_tokens,
                loop_count=loop_count,
            )
        if target == "advanced":
            return self._search_advanced(
                query=query,
                fetch_full_page=fetch_full_page,
                max_results=max_results,
                max_tokens=max_tokens,
                loop_count=loop_count,
            )

        raise ValueError(f"Unsupported search backend: {backend}")

    def _search_tavily(
        self,
        *,
        query: str,
        fetch_full_page: bool,
        max_results: int,
        max_tokens: int,
    ) -> dict[str, Any]:
        if not self.tavily_client:
            raise RuntimeError("TAVILY_API_KEY 未配置或 tavily 未安装")

        response = self.tavily_client.search(
            query=query,
            max_results=max_results,
            include_raw_content=fetch_full_page,
        )

        results = []
        for item in response.get("results", [])[:max_results]:
            raw = item.get("raw_content") if fetch_full_page else item.get("content")
            if raw and fetch_full_page:
                raw = _limit_text(raw, max_tokens)
            results.append(
                _normalized_result(
                    title=item.get("title") or item.get("url", ""),
                    url=item.get("url", ""),
                    content=item.get("content") or "",
                    raw_content=raw,
                )
            )

        return _structured_payload(
            results, backend="tavily", answer=response.get("answer")
        )

    def _search_duckduckgo(
        self,
        *,
        query: str,
        fetch_full_page: bool,
        max_results: int,
        max_tokens: int,
    ) -> dict[str, Any]:
        if DDGS is None:
            raise RuntimeError("未安装 ddgs，无法使用 DuckDuckGo 搜索")

        results: list[dict[str, Any]] = []
        notices: list[str] = []

        try:
            with DDGS(timeout=10) as client:
                search_results = client.text(
                    query, max_results=max_results, backend="duckduckgo"
                )
        except Exception as exc:
            raise RuntimeError(f"DuckDuckGo 搜索失败: {exc}")

        for entry in search_results:
            url = entry.get("href") or entry.get("url")
            title = entry.get("title") or url or ""
            content = entry.get("body") or entry.get("content") or ""

            if not url or not title:
                notices.append(f"忽略不完整的 DuckDuckGo 结果: {entry}")
                continue

            raw_content = content
            if fetch_full_page and url:
                fetched = _fetch_raw_content(url)
                if fetched:
                    raw_content = _limit_text(fetched, max_tokens)

            results.append(
                _normalized_result(
                    title=title,
                    url=url,
                    content=content,
                    raw_content=raw_content,
                )
            )

        return _structured_payload(results, backend="duckduckgo", notices=notices)

    def _search_searxng(
        self,
        *,
        query: str,
        fetch_full_page: bool,
        max_results: int,
        max_tokens: int,
    ) -> dict[str, Any]:
        host = os.getenv("SEARXNG_URL", "http://localhost:8888").rstrip("/")
        endpoint = f"{host}/search"

        try:
            response = requests.get(
                endpoint,
                params={
                    "q": query,
                    "format": "json",
                    "language": "zh-CN",
                    "safesearch": 1,
                    "categories": "general",
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"SearXNG 搜索失败: {exc}")

        results = []
        for entry in payload.get("results", [])[:max_results]:
            url = entry.get("url") or entry.get("link")
            title = entry.get("title") or url or ""
            if not url or not title:
                continue
            content = entry.get("content") or entry.get("snippet") or ""
            raw_content = content
            if fetch_full_page and url:
                fetched = _fetch_raw_content(url)
                if fetched:
                    raw_content = _limit_text(fetched, max_tokens)
            results.append(
                _normalized_result(
                    title=title, url=url, content=content, raw_content=raw_content
                )
            )

        return _structured_payload(results, backend="searxng")

    def _search_perplexity(
        self,
        *,
        query: str,
        fetch_full_page: bool,
        max_results: int,
        max_tokens: int,
        loop_count: int,
    ) -> dict[str, Any]:
        if not self.perplexity_key:
            raise RuntimeError("PERPLEXITY_API_KEY 未配置，无法使用 Perplexity 搜索")

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": f"Bearer {self.perplexity_key}",
        }
        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system",
                    "content": "Search the web and provide factual information with sources.",
                },
                {"role": "user", "content": query},
            ],
        }

        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        citations = data.get("citations", []) or ["https://perplexity.ai"]

        results = []
        for idx, url in enumerate(citations[:max_results], start=1):
            snippet = content if idx == 1 else "See main Perplexity response above."
            raw = _limit_text(content, max_tokens) if fetch_full_page and idx == 1 else None
            results.append(
                _normalized_result(
                    title=f"Perplexity Source {loop_count + 1}-{idx}",
                    url=url,
                    content=snippet,
                    raw_content=raw,
                )
            )

        return _structured_payload(results, backend="perplexity", answer=content)

    def _search_advanced(
        self,
        *,
        query: str,
        fetch_full_page: bool,
        max_results: int,
        max_tokens: int,
        loop_count: int,
    ) -> dict[str, Any]:
        notices: list[str] = []

        if self.tavily_client:
            try:
                tavily_payload = self._search_tavily(
                    query=query,
                    fetch_full_page=fetch_full_page,
                    max_results=max_results,
                    max_tokens=max_tokens,
                )
                if tavily_payload["results"]:
                    return tavily_payload
                notices.append("Tavily 未返回有效结果，尝试其他搜索源")
            except Exception as exc:
                notices.append(f"Tavily 搜索失败：{exc}")

        try:
            ddg_payload = self._search_duckduckgo(
                query=query,
                fetch_full_page=fetch_full_page,
                max_results=max_results,
                max_tokens=max_tokens,
            )
            ddg_payload["notices"] = notices + ddg_payload.get("notices", [])
            return ddg_payload
        except Exception as exc:
            notices.append(f"DuckDuckGo 搜索失败：{exc}")

        return _structured_payload([], backend="advanced", notices=notices)

    # ------------------------------------------------------------------
    # Text formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_text_response(*, query: str, payload: dict[str, Any]) -> str:
        answer = payload.get("answer")
        notices = payload.get("notices") or []
        results = payload.get("results") or []
        backend = payload.get("backend", "unknown")

        lines = [f"搜索关键词：{query}", f"使用搜索源：{backend}"]
        if answer:
            lines.append(f"直接答案：{answer}")

        if results:
            lines.append("")
            lines.append("参考来源：")
            for idx, item in enumerate(results, start=1):
                title = item.get("title") or item.get("url", "")
                lines.append(f"[{idx}] {title}")
                if item.get("content"):
                    lines.append(f"    {item['content']}")
                if item.get("url"):
                    lines.append(f"    来源: {item['url']}")
                lines.append("")
        else:
            lines.append("未找到相关搜索结果。")

        if notices:
            lines.append("注意事项：")
            for notice in notices:
                if notice:
                    lines.append(f"- {notice}")

        return "\n".join(line for line in lines if line is not None)

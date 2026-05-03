"""Zotero 文献管理集成模块 — 基于 pyzotero。"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from pyzotero import zotero
    PYZOTERO_AVAILABLE = True
except ImportError:
    PYZOTERO_AVAILABLE = False
    logger.warning("pyzotero not installed, Zotero integration unavailable")


class ZoteroManager:
    """Zotero 文献管理器，支持创建集合、导入文献、获取全文。"""

    def __init__(
        self,
        library_id: str | None = None,
        library_type: str = "user",
        api_key: str | None = None,
    ) -> None:
        self.library_id = library_id or os.getenv("ZOTERO_LIBRARY_ID", "")
        self.library_type = library_type or os.getenv("ZOTERO_LIBRARY_TYPE", "user")
        self.api_key = api_key or os.getenv("ZOTERO_API_KEY", "")
        self._client: Any = None

        if not PYZOTERO_AVAILABLE:
            logger.warning("pyzotero not available, Zotero operations will be skipped")
            return

        if self.library_id and self.api_key:
            try:
                self._client = zotero.Zotero(
                    self.library_id,
                    self.library_type,
                    self.api_key,
                )
                logger.info("Zotero client initialized (library=%s)", self.library_id)
            except Exception as exc:
                logger.warning("Zotero client init failed: %s", exc)
        else:
            logger.info("Zotero credentials not configured (ZOTERO_LIBRARY_ID, ZOTERO_API_KEY)")

    @property
    def available(self) -> bool:
        """Check if Zotero client is ready."""
        return self._client is not None

    def create_collection(self, name: str) -> str | None:
        """Create a Zotero collection and return its key.

        Args:
            name: Collection name

        Returns:
            Collection key, or None if failed
        """
        if not self.available:
            logger.warning("Zotero not available, skipping collection creation")
            return None

        try:
            result = self._client.create_collections([{"name": name}])
            if result and "success" in result:
                key = result["success"].get("0")
                logger.info("Created Zotero collection '%s' key=%s", name, key)
                return key
        except Exception as exc:
            logger.exception("Failed to create Zotero collection: %s", exc)

        return None

    def add_paper(
        self,
        title: str,
        authors: list[str] | None = None,
        year: str = "",
        abstract: str = "",
        url: str = "",
        doi: str = "",
        venue: str = "",
        collection_key: str | None = None,
    ) -> str | None:
        """Add a paper to Zotero library.

        Args:
            title: Paper title
            authors: List of author names
            year: Publication year
            abstract: Paper abstract
            url: Paper URL
            doi: DOI identifier
            venue: Journal/conference name
            collection_key: Optional collection to add to

        Returns:
            Zotero item key, or None if failed
        """
        if not self.available:
            logger.warning("Zotero not available, skipping paper addition")
            return None

        # 构建 Zotero item
        item = {
            "itemType": "journalArticle",
            "title": title,
            "creators": [],
            "abstractNote": abstract,
            "url": url,
            "DOI": doi,
            "date": year,
            "publicationTitle": venue,
        }

        # 添加作者
        if authors:
            for author in authors:
                # 支持 "FirstName LastName" 格式
                parts = author.strip().split(" ", 1)
                if len(parts) == 2:
                    item["creators"].append({
                        "creatorType": "author",
                        "firstName": parts[0],
                        "lastName": parts[1],
                    })
                else:
                    item["creators"].append({
                        "creatorType": "author",
                        "firstName": "",
                        "lastName": author,
                    })

        try:
            result = self._client.create_items([item])
            if result and "success" in result:
                key = result["success"].get("0")
                logger.info("Added paper to Zotero: '%s' key=%s", title, key)

                # 添加到集合
                if collection_key and key:
                    try:
                        self._client.addto_collection(collection_key, [{"key": key}])
                    except Exception as exc:
                        logger.warning("Failed to add to collection: %s", exc)

                return key
        except Exception as exc:
            logger.exception("Failed to add paper to Zotero: %s", exc)

        return None

    def add_paper_from_search_result(
        self,
        paper: dict[str, Any],
        collection_key: str | None = None,
    ) -> str | None:
        """Add a paper from search result dict to Zotero.

        Args:
            paper: Paper dict from scholar_search or search_tool
            collection_key: Optional collection key

        Returns:
            Zotero item key, or None if failed
        """
        authors_raw = paper.get("authors", "")
        if isinstance(authors_raw, str):
            authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
        elif isinstance(authors_raw, list):
            authors = authors_raw
        else:
            authors = []

        return self.add_paper(
            title=paper.get("title", ""),
            authors=authors,
            year=str(paper.get("year", "")),
            abstract=paper.get("raw_content", "") or paper.get("content", ""),
            url=paper.get("url", ""),
            doi=paper.get("doi", ""),
            venue=paper.get("venue", ""),
            collection_key=collection_key,
        )

    def get_fulltext(self, item_key: str) -> str | None:
        """Get full text content of a Zotero item.

        Args:
            item_key: Zotero item key

        Returns:
            Full text content, or None if not available
        """
        if not self.available:
            return None

        try:
            # 获取 item 详情
            item = self._client.item(item_key)
            if not item:
                return None

            data = item.get("data", {})
            content_parts = []

            # 标题
            title = data.get("title", "")
            if title:
                content_parts.append(f"# {title}")

            # 摘要
            abstract = data.get("abstractNote", "")
            if abstract:
                content_parts.append(f"\n## 摘要\n{abstract}")

            # 尝试获取附件中的全文
            children = self._client.children(item_key)
            for child in children:
                child_data = child.get("data", {})
                if child_data.get("contentType") in [
                    "application/pdf",
                    "text/html",
                    "text/plain",
                ]:
                    # 尝试获取附件内容
                    attachment_key = child_data.get("key")
                    if attachment_key:
                        try:
                            # 注意：pyzotero 不直接支持读取附件内容
                            # 这里返回附件的 URL 供后续处理
                            attachment_url = child_data.get("url", "")
                            if attachment_url:
                                content_parts.append(f"\n## 附件\n{attachment_url}")
                        except Exception:
                            pass

            return "\n".join(content_parts) if content_parts else None

        except Exception as exc:
            logger.exception("Failed to get fulltext from Zotero: %s", exc)
            return None

    def list_collections(self) -> list[dict[str, str]]:
        """List all collections in the library.

        Returns:
            List of dicts with 'key' and 'name'
        """
        if not self.available:
            return []

        try:
            collections = self._client.collections()
            return [
                {"key": c["key"], "name": c["data"]["name"]}
                for c in collections
            ]
        except Exception as exc:
            logger.exception("Failed to list Zotero collections: %s", exc)
            return []

    def list_items(
        self,
        collection_key: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """List items in the library or a specific collection.

        Args:
            collection_key: Optional collection key to filter
            limit: Maximum items to return

        Returns:
            List of item dicts
        """
        if not self.available:
            return []

        try:
            if collection_key:
                items = self._client.collection_items(collection_key, limit=limit)
            else:
                items = self._client.items(limit=limit)

            return [
                {
                    "key": item["key"],
                    "title": item["data"].get("title", ""),
                    "itemType": item["data"].get("itemType", ""),
                    "date": item["data"].get("date", ""),
                    "creators": [
                        f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
                        for c in item["data"].get("creators", [])
                    ],
                }
                for item in items
                if item.get("data", {}).get("itemType") != "attachment"
            ]
        except Exception as exc:
            logger.exception("Failed to list Zotero items: %s", exc)
            return []

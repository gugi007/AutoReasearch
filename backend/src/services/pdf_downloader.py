"""PDF 下载模块 — 支持从 arXiv 和 DOI 下载论文 PDF。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 默认下载目录
DEFAULT_PDF_DIR = Path(__file__).parent.parent.parent.parent / "papers"

# arXiv PDF URL 模式
ARXIV_PDF_PATTERN = re.compile(r"arxiv\.org/abs/(\d+\.\d+)")
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}.pdf"

class PDFDownloader:
    """论文 PDF 下载器，支持 arXiv 和 DOI。"""

    def __init__(self, pdf_dir: str | Path | None = None) -> None:
        self.pdf_dir = Path(pdf_dir) if pdf_dir else DEFAULT_PDF_DIR
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        logger.info("PDF download directory: %s", self.pdf_dir)

    def download_paper(
        self,
        paper: dict[str, Any],
        task_id: int | None = None,
    ) -> Path | None:
        """下载论文 PDF，返回本地路径。

        Args:
            paper: 论文信息字典，包含 url, title 等
            task_id: 任务 ID，用于组织目录

        Returns:
            下载成功返回 PDF 路径，失败返回 None
        """
        title = paper.get("title", "untitled")
        url = paper.get("url", "")
        pdf_url = paper.get("pdf_url", "")

        if not url and not pdf_url:
            logger.warning("No URL for paper: %s", title)
            return None

        # 生成安全的文件名
        safe_title = self._safe_filename(title)
        if task_id is not None:
            save_dir = self.pdf_dir / f"task_{task_id}"
        else:
            save_dir = self.pdf_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = save_dir / f"{safe_title}.pdf"

        # 如果已下载，直接返回
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            logger.info("PDF already exists: %s", pdf_path.name)
            return pdf_path

        # 尝试下载
        download_url = self._resolve_pdf_url(
            url,
            pdf_url=pdf_url,
            doi=paper.get("doi"),
        )
        if not download_url:
            logger.info("No direct PDF URL for paper, skipping download: %s", title)
            return None

        try:
            logger.info("Downloading PDF: %s", download_url[:80])
            response = requests.get(
                download_url,
                timeout=30,
                headers={"User-Agent": "AutoResearch/1.0"},
                allow_redirects=True,
            )
            response.raise_for_status()

            # 验证是 PDF 文件
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type and not response.content[:5] == b"%PDF-":
                logger.warning("Response is not a PDF: %s", content_type)
                return None

            pdf_path.write_bytes(response.content)
            logger.info("Downloaded PDF: %s (%.1f KB)", pdf_path.name, len(response.content) / 1024)
            return pdf_path

        except Exception as exc:
            logger.warning("Failed to download PDF from %s: %s", download_url[:50], exc)
            return None

    def download_batch(
        self,
        papers: list[dict[str, Any]],
        task_id: int | None = None,
        max_papers: int = 10,
    ) -> list[dict[str, Any]]:
        """批量下载论文 PDF。

        Args:
            papers: 论文列表
            task_id: 任务 ID
            max_papers: 最大下载数量

        Returns:
            包含 pdf_path 的论文列表
        """
        downloaded = []
        for paper in papers[:max_papers]:
            pdf_path = self.download_paper(paper, task_id)
            paper["pdf_path"] = str(pdf_path) if pdf_path else None
            paper["downloaded"] = pdf_path is not None
            downloaded.append(paper)

        success = sum(1 for p in downloaded if p["downloaded"])
        logger.info("Batch download: %d/%d succeeded", success, len(downloaded))
        return downloaded

    def _resolve_pdf_url(
        self,
        url: str,
        *,
        pdf_url: str | None = None,
        doi: str | None = None,
    ) -> str | None:
        """从论文 URL 解析出 PDF 下载链接。"""
        if pdf_url:
            return pdf_url

        # arXiv
        arxiv_match = ARXIV_PDF_PATTERN.search(url)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)
            return ARXIV_PDF_URL.format(arxiv_id=arxiv_id)

        # 直接是 PDF 链接
        if url.lower().endswith(".pdf"):
            return url

        # DOI/landing pages usually return HTML. Only use Unpaywall when an
        # email is configured, otherwise skip instead of producing noisy errors.
        doi_value = doi or self._extract_doi_from_url(url)
        if doi_value:
            return self._resolve_unpaywall_pdf(doi_value)

        return None

    @staticmethod
    def _extract_doi_from_url(url: str) -> str:
        if "doi.org/" not in url:
            return ""
        return url.split("doi.org/", 1)[1].strip()

    @staticmethod
    def _resolve_unpaywall_pdf(doi: str) -> str | None:
        import os

        email = os.getenv("UNPAYWALL_EMAIL")
        if not email:
            return None

        try:
            response = requests.get(
                f"https://api.unpaywall.org/v2/{doi}",
                params={"email": email},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.debug("Unpaywall lookup failed for %s: %s", doi, exc)
            return None

        best_location = data.get("best_oa_location") or {}
        return best_location.get("url_for_pdf") or None

    @staticmethod
    def _safe_filename(title: str, max_len: int = 80) -> str:
        """生成安全的文件名。"""
        # 移除特殊字符
        safe = re.sub(r'[<>:"/\\|?*]', "", title)
        # 替换空格为下划线
        safe = re.sub(r"\s+", "_", safe.strip())
        # 截断
        if len(safe) > max_len:
            safe = safe[:max_len]
        return safe or "untitled"

"""PDF 解析模块 — 提取论文全文文本。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 最大文本长度限制（字符数）
MAX_TEXT_LENGTH = 500_000


class PDFParser:
    """PDF 文本提取器，基于 PyMuPDF。"""

    def __init__(self, max_text_length: int = MAX_TEXT_LENGTH) -> None:
        self.max_text_length = max_text_length

    def extract_text(self, pdf_path: str | Path) -> str | None:
        """从 PDF 文件提取全文文本。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            提取的文本内容，失败返回 None
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logger.warning("PDF file not found: %s", pdf_path)
            return None

        try:
            import pymupdf
        except ImportError:
            logger.error("pymupdf not installed, cannot parse PDF")
            return None

        try:
            doc = pymupdf.open(str(pdf_path))
            text_parts = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text("text")
                if page_text.strip():
                    text_parts.append(page_text)

            doc.close()

            if not text_parts:
                logger.warning("No text extracted from PDF: %s", pdf_path.name)
                return None

            full_text = "\n\n".join(text_parts)

            # 截断过长的文本
            if len(full_text) > self.max_text_length:
                full_text = full_text[:self.max_text_length] + "\n\n... [文本截断]"
                logger.info("PDF text truncated to %d chars", self.max_text_length)

            logger.info(
                "Extracted %d chars from PDF: %s",
                len(full_text),
                pdf_path.name,
            )
            return full_text

        except Exception as exc:
            logger.warning("Failed to parse PDF %s: %s", pdf_path.name, exc)
            return None

    def extract_metadata(self, pdf_path: str | Path) -> dict[str, Any]:
        """从 PDF 提取元数据。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            元数据字典
        """
        pdf_path = Path(pdf_path)
        metadata: dict[str, Any] = {}

        try:
            import pymupdf

            doc = pymupdf.open(str(pdf_path))
            meta = doc.metadata or {}
            metadata = {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
                "keywords": meta.get("keywords", ""),
                "page_count": len(doc),
            }
            doc.close()
        except Exception as exc:
            logger.debug("Failed to extract PDF metadata: %s", exc)

        return metadata

    def extract_with_structure(self, pdf_path: str | Path) -> dict[str, Any]:
        """提取 PDF 文本并尝试保留结构（标题、摘要、正文）。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            结构化的文本字典
        """
        pdf_path = Path(pdf_path)
        result: dict[str, Any] = {
            "full_text": "",
            "abstract": "",
            "sections": [],
        }

        try:
            import pymupdf

            doc = pymupdf.open(str(pdf_path))
            all_text = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text("text")
                if page_text.strip():
                    all_text.append(page_text)

            doc.close()

            if not all_text:
                return result

            full_text = "\n\n".join(all_text)
            result["full_text"] = full_text[:self.max_text_length]

            # 尝试提取摘要
            abstract = self._extract_abstract(full_text)
            if abstract:
                result["abstract"] = abstract

            # 尝试分段
            sections = self._extract_sections(full_text)
            if sections:
                result["sections"] = sections

        except Exception as exc:
            logger.warning("Failed to extract structured PDF: %s", exc)

        return result

    @staticmethod
    def _extract_abstract(text: str) -> str:
        """尝试从文本中提取摘要部分。"""
        import re

        # 常见摘要标记
        patterns = [
            r"(?:^|\n)\s*Abstract[:\s]*\n(.*?)(?:\n\s*(?:Introduction|1\.|Keywords|I\.))",
            r"(?:^|\n)\s*ABSTRACT[:\s]*\n(.*?)(?:\n\s*(?:INTRODUCTION|1\.|KEYWORDS))",
            r"(?:^|\n)\s*摘要[:\s]*\n(.*?)(?:\n\s*(?:引言|关键词|1\.))",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                abstract = match.group(1).strip()
                # 截断过长的摘要
                if len(abstract) > 2000:
                    abstract = abstract[:2000] + "..."
                return abstract

        return ""

    @staticmethod
    def _extract_sections(text: str) -> list[dict[str, str]]:
        """尝试从文本中提取章节结构。"""
        import re

        sections = []
        # 匹配常见的章节标题模式
        section_pattern = re.compile(
            r"(?:^|\n)\s*(?:(\d+\.?\s+)|(?:[IVX]+\.?\s+))([A-Z][A-Za-z\s]+?)(?:\n|$)",
            re.MULTILINE,
        )

        matches = list(section_pattern.finditer(text))
        for i, match in enumerate(matches):
            title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()

            if title and content:
                sections.append({
                    "title": title,
                    "content": content[:5000],  # 限制每个章节长度
                })

        return sections[:20]  # 最多 20 个章节

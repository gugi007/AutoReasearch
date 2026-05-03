"""独立的笔记工具模块 — 从 HelloAgents NoteTool 提取，无外部框架依赖。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


class NoteTool:
    """结构化笔记工具，支持创建/读取/更新/删除/搜索笔记。

    笔记以 Markdown 格式持久化，带 YAML 前置元数据。
    """

    def __init__(
        self,
        workspace: str = "./notes",
        max_notes: int = 1000,
    ) -> None:
        self.workspace = Path(workspace)
        self.max_notes = max_notes
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.index_file = self.workspace / "notes_index.json"
        self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, parameters: dict[str, Any]) -> str:
        """执行笔记操作（与 HelloAgents NoteTool 接口兼容）。"""
        action = parameters.get("action")
        if action == "create":
            return self._create_note(
                title=parameters.get("title"),
                content=parameters.get("content"),
                note_type=parameters.get("note_type", "general"),
                tags=parameters.get("tags"),
            )
        if action == "read":
            return self._read_note(note_id=parameters.get("note_id"))
        if action == "update":
            return self._update_note(
                note_id=parameters.get("note_id"),
                title=parameters.get("title"),
                content=parameters.get("content"),
                note_type=parameters.get("note_type"),
                tags=parameters.get("tags"),
            )
        if action == "delete":
            return self._delete_note(note_id=parameters.get("note_id"))
        if action == "list":
            return self._list_notes(
                note_type=parameters.get("note_type"),
                limit=parameters.get("limit", 10),
            )
        if action == "search":
            return self._search_notes(
                query=parameters.get("query"),
                limit=parameters.get("limit", 10),
            )
        if action == "summary":
            return self._get_summary()
        return f"不支持的操作: {action}"

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _load_index(self) -> None:
        if self.index_file.exists():
            with open(self.index_file, "r", encoding="utf-8") as f:
                self.notes_index = json.load(f)
        else:
            self.notes_index = {
                "notes": [],
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "total_notes": 0,
                },
            }
            self._save_index()

    def _save_index(self) -> None:
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self.notes_index, f, ensure_ascii=False, indent=2)

    def _generate_note_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        count = len(self.notes_index["notes"])
        return f"note_{timestamp}_{count}"

    def _get_note_path(self, note_id: str) -> Path:
        return self.workspace / f"{note_id}.md"

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def _create_note(
        self,
        title: str,
        content: str,
        note_type: str = "general",
        tags: list[str] | None = None,
    ) -> str:
        if not title or not content:
            return "创建笔记需要提供 title 和 content"

        if len(self.notes_index["notes"]) >= self.max_notes:
            return f"笔记数量已达上限 ({self.max_notes})"

        note_id = self._generate_note_id()
        now = datetime.now().isoformat()
        note = {
            "id": note_id,
            "title": title,
            "content": content,
            "type": note_type,
            "tags": tags if isinstance(tags, list) else [],
            "created_at": now,
            "updated_at": now,
        }

        note_path = self._get_note_path(note_id)
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(self._note_to_markdown(note))

        self.notes_index["notes"].append(
            {
                "id": note_id,
                "title": title,
                "type": note_type,
                "tags": note["tags"],
                "created_at": now,
            }
        )
        self.notes_index["metadata"]["total_notes"] = len(self.notes_index["notes"])
        self._save_index()

        return f"笔记创建成功\nID: {note_id}\n标题: {title}\n类型: {note_type}"

    def _read_note(self, note_id: str) -> str:
        if not note_id:
            return "读取笔记需要提供 note_id"

        note_path = self._get_note_path(note_id)
        if not note_path.exists():
            return f"笔记不存在: {note_id}"

        with open(note_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        note = self._markdown_to_note(markdown_text)
        return self._format_note(note)

    def _update_note(
        self,
        note_id: str,
        title: str | None = None,
        content: str | None = None,
        note_type: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        if not note_id:
            return "更新笔记需要提供 note_id"

        note_path = self._get_note_path(note_id)
        if not note_path.exists():
            return f"笔记不存在: {note_id}"

        with open(note_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()
        note = self._markdown_to_note(markdown_text)

        if title:
            note["title"] = title
        if content:
            note["content"] = content
        if note_type:
            note["type"] = note_type
        if tags is not None:
            note["tags"] = tags if isinstance(tags, list) else []

        note["updated_at"] = datetime.now().isoformat()

        with open(note_path, "w", encoding="utf-8") as f:
            f.write(self._note_to_markdown(note))

        for idx_note in self.notes_index["notes"]:
            if idx_note["id"] == note_id:
                idx_note["title"] = note["title"]
                idx_note["type"] = note["type"]
                idx_note["tags"] = note["tags"]
                break
        self._save_index()

        return f"笔记更新成功: {note_id}"

    def _delete_note(self, note_id: str) -> str:
        if not note_id:
            return "删除笔记需要提供 note_id"

        note_path = self._get_note_path(note_id)
        if not note_path.exists():
            return f"笔记不存在: {note_id}"

        note_path.unlink()
        self.notes_index["notes"] = [
            n for n in self.notes_index["notes"] if n["id"] != note_id
        ]
        self.notes_index["metadata"]["total_notes"] = len(self.notes_index["notes"])
        self._save_index()

        return f"笔记已删除: {note_id}"

    def _list_notes(self, note_type: str | None = None, limit: int = 10) -> str:
        filtered = self.notes_index["notes"]
        if note_type:
            filtered = [n for n in filtered if n["type"] == note_type]
        filtered = filtered[:limit]

        if not filtered:
            return "暂无笔记"

        result = f"笔记列表（共 {len(filtered)} 条）\n\n"
        for note in filtered:
            result += f"[{note['type']}] {note['title']}\n"
            result += f"  ID: {note['id']}\n"
            if note.get("tags"):
                result += f"  标签: {', '.join(note['tags'])}\n"
            result += f"  创建时间: {note['created_at']}\n\n"

        return result

    def _search_notes(self, query: str, limit: int = 10) -> str:
        if not query:
            return "搜索需要提供 query"

        query_lower = query.lower()
        matched = []
        for idx_note in self.notes_index["notes"]:
            note_path = self._get_note_path(idx_note["id"])
            if not note_path.exists():
                continue
            with open(note_path, "r", encoding="utf-8") as f:
                markdown_text = f.read()
            try:
                note = self._markdown_to_note(markdown_text)
            except Exception:
                continue
            if (
                query_lower in note["title"].lower()
                or query_lower in note["content"].lower()
                or any(query_lower in tag.lower() for tag in note.get("tags", []))
            ):
                matched.append(note)

        matched = matched[:limit]
        if not matched:
            return f"未找到匹配 '{query}' 的笔记"

        result = f"搜索结果（共 {len(matched)} 条）\n\n"
        for note in matched:
            result += self._format_note(note, compact=True) + "\n"

        return result

    def _get_summary(self) -> str:
        total = len(self.notes_index["notes"])
        type_counts: dict[str, int] = {}
        for note in self.notes_index["notes"]:
            type_counts[note["type"]] = type_counts.get(note["type"], 0) + 1

        result = f"笔记摘要\n\n总笔记数: {total}\n\n按类型统计:\n"
        for note_type, count in sorted(type_counts.items()):
            result += f"  {note_type}: {count}\n"

        return result

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _note_to_markdown(note: dict[str, Any]) -> str:
        frontmatter = "---\n"
        frontmatter += f"id: {note['id']}\n"
        frontmatter += f"title: {note['title']}\n"
        frontmatter += f"type: {note['type']}\n"
        if note.get("tags"):
            frontmatter += f"tags: {json.dumps(note['tags'])}\n"
        frontmatter += f"created_at: {note['created_at']}\n"
        frontmatter += f"updated_at: {note['updated_at']}\n"
        frontmatter += "---\n\n"
        content = f"# {note['title']}\n\n{note['content']}"
        return frontmatter + content

    @staticmethod
    def _markdown_to_note(markdown_text: str) -> dict[str, Any]:
        frontmatter_match = re.match(
            r"^---\s*\n(.*?)\n---\s*\n", markdown_text, re.DOTALL
        )
        if not frontmatter_match:
            raise ValueError("无效的笔记格式：缺少 YAML 前置元数据")

        frontmatter_text = frontmatter_match.group(1)
        content_start = frontmatter_match.end()

        note: dict[str, Any] = {}
        for line in frontmatter_text.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key == "tags":
                    try:
                        note[key] = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        note[key] = []
                else:
                    note[key] = value

        markdown_content = markdown_text[content_start:].strip()
        lines = markdown_content.split("\n")
        if lines and lines[0].startswith("# "):
            markdown_content = "\n".join(lines[1:]).strip()

        note["content"] = markdown_content
        return note

    @staticmethod
    def _format_note(note: dict[str, Any], compact: bool = False) -> str:
        if compact:
            content_preview = note["content"][:100]
            if len(note["content"]) > 100:
                content_preview += "..."
            return (
                f"[{note['type']}] {note['title']}\n"
                f"ID: {note['id']}\n"
                f"内容: {content_preview}"
            )
        result = f"笔记详情\n\n"
        result += f"ID: {note['id']}\n"
        result += f"标题: {note['title']}\n"
        result += f"类型: {note['type']}\n"
        if note.get("tags"):
            result += f"标签: {', '.join(note['tags'])}\n"
        result += f"创建时间: {note['created_at']}\n"
        result += f"更新时间: {note['updated_at']}\n"
        result += f"\n内容:\n{note['content']}\n"
        return result

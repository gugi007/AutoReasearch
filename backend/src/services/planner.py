"""Service responsible for converting the research topic into actionable tasks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI

from models import SummaryState, TodoItem
from config import Configuration
from prompts import get_current_date, todo_planner_instructions, todo_planner_system_prompt
from utils import strip_thinking_tokens

logger = logging.getLogger(__name__)

TOOL_CALL_PATTERN = re.compile(
    r"\[TOOL_CALL:(?P<tool>[^:]+):(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)


class PlanningService:
    """Wraps an LLM call to produce structured TODO items."""

    def __init__(self, llm_client: OpenAI, model: str, config: Configuration) -> None:
        self._client = llm_client
        self._model = model
        self._config = config

    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        """Ask the LLM to break the topic into actionable tasks."""

        prompt = todo_planner_instructions.format(
            current_date=get_current_date(),
            research_topic=state.research_topic,
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": todo_planner_system_prompt.strip()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        text = response.choices[0].message.content or ""

        logger.info("Planner raw output (truncated): %s", text[:500])

        tasks_payload = self._extract_tasks(text)
        todo_items: list[TodoItem] = []

        for idx, item in enumerate(tasks_payload, start=1):
            title = str(item.get("title") or f"任务{idx}").strip()
            intent = str(item.get("intent") or "聚焦主题的关键问题").strip()
            query = str(item.get("query") or state.research_topic).strip()

            if not query:
                query = state.research_topic

            task = TodoItem(
                id=idx,
                title=title,
                intent=intent,
                query=query,
            )
            todo_items.append(task)

        state.todo_items = todo_items

        titles = [task.title for task in todo_items]
        logger.info("Planner produced %d tasks: %s", len(todo_items), titles)
        return todo_items

    @staticmethod
    def create_fallback_task(state: SummaryState) -> TodoItem:
        """Create a minimal fallback task when planning failed."""
        return TodoItem(
            id=1,
            title="基础背景梳理",
            intent="收集主题的核心背景与最新动态",
            query=f"{state.research_topic} 最新进展" if state.research_topic else "基础背景梳理",
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _extract_tasks(self, raw_response: str) -> list[dict[str, Any]]:
        """Parse planner output into a list of task dictionaries."""
        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)

        json_payload = self._extract_json_payload(text)
        tasks: list[dict[str, Any]] = []

        if isinstance(json_payload, dict):
            candidate = json_payload.get("tasks")
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        tasks.append(item)
        elif isinstance(json_payload, list):
            for item in json_payload:
                if isinstance(item, dict):
                    tasks.append(item)

        if not tasks:
            tool_payload = self._extract_tool_payload(text)
            if tool_payload and isinstance(tool_payload.get("tasks"), list):
                for item in tool_payload["tasks"]:
                    if isinstance(item, dict):
                        tasks.append(item)

        return tasks

    def _extract_json_payload(self, text: str) -> dict[str, Any] | list | None:
        """Try to locate and parse a JSON object or array from the text."""
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None

        return None

    def _extract_tool_payload(self, text: str) -> dict[str, Any] | None:
        """Parse the first TOOL_CALL expression in the output."""
        match = TOOL_CALL_PATTERN.search(text)
        if not match:
            return None

        body = match.group("body")
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        parts = [segment.strip() for segment in body.split(",") if segment.strip()]
        payload: dict[str, Any] = {}
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            payload[key.strip()] = value.strip().strip('"').strip("'")

        return payload or None

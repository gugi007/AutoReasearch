"""Service that consolidates task results into the final report."""

from __future__ import annotations

import json

from openai import OpenAI

from models import SummaryState
from config import Configuration
from utils import strip_thinking_tokens
from services.text_processing import strip_tool_calls


class ReportingService:
    """Generates the final structured report."""

    def __init__(self, llm_client: OpenAI, model: str, config: Configuration) -> None:
        self._client = llm_client
        self._model = model
        self._config = config

    def generate_report(self, state: SummaryState) -> str:
        """Generate a structured report based on completed tasks."""

        tasks_block = []
        for task in state.todo_items:
            summary_block = task.summary or "暂无可用信息"
            sources_block = task.sources_summary or "暂无来源"
            tasks_block.append(
                f"### 任务 {task.id}: {task.title}\n"
                f"- 任务目标：{task.intent}\n"
                f"- 检索查询：{task.query}\n"
                f"- 执行状态：{task.status}\n"
                f"- 任务总结：\n{summary_block}\n"
                f"- 来源概览：\n{sources_block}\n"
            )

        note_references = []
        for task in state.todo_items:
            if task.note_id:
                note_references.append(
                    f"- 任务 {task.id}《{task.title}》：note_id={task.note_id}"
                )

        notes_section = "\n".join(note_references) if note_references else "暂无可用任务笔记"

        system_prompt = (
            "你是一名专业的分析报告撰写者，请根据输入的任务总结与参考信息，生成结构化的研究报告。\n\n"
            "报告模板：\n"
            "1. **背景概览**：简述研究主题的重要性与上下文。\n"
            "2. **核心洞见**：提炼 3-5 条最重要的结论，标注文献/任务编号。\n"
            "3. **证据与数据**：罗列支持性的事实或指标，可引用任务摘要中的要点。\n"
            "4. **风险与挑战**：分析潜在的问题、限制或仍待验证的假设。\n"
            "5. **参考来源**：按任务列出关键来源条目（标题 + 链接）。\n\n"
            "要求：\n"
            "- 报告使用 Markdown\n"
            "- 各部分明确分节，禁止添加额外的封面或结语\n"
            "- 若某部分信息缺失，说明'暂无相关信息'\n"
            "- 引用来源时使用任务标题或来源标题，确保可追溯\n"
            "- 输出给用户的内容中禁止残留 [TOOL_CALL:...] 指令"
        )

        user_prompt = (
            f"研究主题：{state.research_topic}\n"
            f"任务概览：\n{''.join(tasks_block)}\n"
            f"可用任务笔记：\n{notes_section}\n"
            f"请整合所有信息后撰写报告。"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        text = response.choices[0].message.content or ""

        report_text = text.strip()
        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)

        report_text = strip_tool_calls(report_text).strip()

        return report_text or "报告生成失败，请检查输入。"

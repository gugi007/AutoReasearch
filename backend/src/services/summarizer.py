"""Task summarization utilities."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Callable

from openai import OpenAI

from models import SummaryState, TodoItem
from config import Configuration
from utils import strip_thinking_tokens
from services.notes import build_note_guidance
from services.text_processing import strip_tool_calls


class SummarizationService:
    """Handles synchronous and streaming task summarization."""

    def __init__(
        self,
        llm_client: OpenAI,
        model: str,
        config: Configuration,
    ) -> None:
        self._client = llm_client
        self._model = model
        self._config = config

    def summarize_task(self, state: SummaryState, task: TodoItem, context: str) -> str:
        """Generate a task-specific summary using the LLM."""

        messages = self._build_messages(state, task, context)

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.0,
        )
        text = response.choices[0].message.content or ""

        summary_text = text.strip()
        # 移除思考令牌，避免在摘要中包含思考过程
        # 这可以提高摘要的质量和可读性
        if self._config.strip_thinking_tokens:
            summary_text = strip_thinking_tokens(summary_text)

        summary_text = strip_tool_calls(summary_text).strip()

        return summary_text or "暂无可用信息"

    def stream_task_summary(
        self, state: SummaryState, task: TodoItem, context: str
    ) -> tuple[Iterator[str], Callable[[], str]]:
        """Stream the summary text for a task while collecting full output."""

        messages = self._build_messages(state, task, context)
        remove_thinking = self._config.strip_thinking_tokens
        raw_buffer = ""
        visible_output = ""
        emit_index = 0
        # 清除缓冲区中的思考令牌，只保留可见文本
        # 这可以确保摘要中不包含思考过程，只包含任务相关的信息
        def flush_visible() -> Iterator[str]:
            nonlocal emit_index, raw_buffer
            while True:
                start = raw_buffer.find("<think>", emit_index)
                if start == -1:
                    if emit_index < len(raw_buffer):
                        segment = raw_buffer[emit_index:]
                        emit_index = len(raw_buffer)
                        if segment:
                            yield segment
                    break

                if start > emit_index:
                    segment = raw_buffer[emit_index:start]
                    emit_index = start
                    if segment:
                        yield segment

                end = raw_buffer.find("</think>", start)
                if end == -1:
                    break
                emit_index = end + len("</think>")

        # 流式生成摘要文本
        def generator() -> Iterator[str]:
            #这三个变量用外层的，不自己造新的
            #generator / flush_visible / get_summary
            nonlocal raw_buffer, visible_output, emit_index
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.0,
                stream=True,
            )
            # 遍历流式响应，处理每个小片段
            # 每个小片段可能包含思考令牌，需要清除并只保留可见文本
            for chunk in stream:
                #chunk是LLM吐出来的一个小片段
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    raw_buffer += delta.content
                    if remove_thinking:
                        for segment in flush_visible():
                            visible_output += segment
                            if segment:
                                yield segment
                    else:
                        visible_output += delta.content
                        yield delta.content

            # Final flush
            if remove_thinking:
                for segment in flush_visible():
                    visible_output += segment
                    if segment:
                        yield segment
        # 获取最终摘要文本
        def get_summary() -> str:
            if remove_thinking:
                cleaned = strip_thinking_tokens(visible_output)
            else:
                cleaned = visible_output
            return strip_tool_calls(cleaned).strip()

        return generator(), get_summary

    #由于每个任务都不一样，如果放在prompt中需要传入的参数太多
    # 所以这里将任务信息和上下文作为参数，构建一个通用的提示模板
    #f-string直接拼接，更直观，更易维护
    def _build_messages(
        self, state: SummaryState, task: TodoItem, context: str
    ) -> list[dict[str, str]]:
        """Construct the messages list shared by both modes."""

        system_prompt = (
            "你是一名研究执行专家，请基于给定的上下文，为特定任务生成要点总结，"
            "对内容进行详尽且细致的总结而不是走马观花，需要勇于创新、打破常规思维，"
            "并尽可能多维度，从原理、应用、优缺点、工程实践、对比、历史演变等角度进行拓展。"
        )

        user_prompt = (
            f"任务主题：{state.research_topic}\n"
            f"任务名称：{task.title}\n"
            f"任务目标：{task.intent}\n"
            f"检索查询：{task.query}\n"
            f"任务上下文：\n{context}\n"
            f"{build_note_guidance(task)}\n"
            "请按照以上协作要求先同步笔记，然后返回一份面向用户的 Markdown 总结（仍遵循任务总结模板）。"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

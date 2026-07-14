"""CAMEL Researcher-Reviewer dialogue for quality review of task summaries."""

from __future__ import annotations

import logging
from typing import Any

from config import Configuration
from models import TodoItem
from prompts import camel_researcher_prompt, camel_reviewer_prompt

logger = logging.getLogger(__name__)


class CAMELReviewer:
    """Run a Researcher-Reviewer dialogue to verify and enrich task summaries."""

    def __init__(self, config: Configuration) -> None:
        self._config = config

    def review(
        self,
        task: TodoItem,
        context: str,
        initial_summary: str,
        max_rounds: int = 3,
    ) -> str | None:
        """Run the dialogue and return the reviewed summary, or None on failure."""
        try:
            return self._run_dialogue(task, context, initial_summary, max_rounds)
        except Exception as exc:
            logger.warning(
                "CAMEL review failed for task %d, using original summary: %s",
                task.id,
                exc,
            )
            return None

    def _run_dialogue(
        self,
        task: TodoItem,
        context: str,
        initial_summary: str,
        max_rounds: int,
    ) -> str:
        from camel.messages import BaseMessage
        from camel.societies import RolePlaying
        from camel.types import ModelPlatformType, ModelType

        # Build the model for the OpenAI-compatible backend
        model = self._build_model()

        # Build task prompt
        task_prompt = (
            f"## 任务信息\n"
            f"- 任务名称：{task.title}\n"
            f"- 任务目标：{task.intent}\n"
            f"- 检索查询：{task.query}\n\n"
            f"## 检索上下文\n{context}\n\n"
            f"## 初始摘要（需审查）\n{initial_summary}"
        )

        # Create role-playing society
        society = RolePlaying(
            assistant_role_name="文献研究员",
            user_role_name="质量审查员",
            task_prompt=task_prompt,
            with_task_specify=False,
            output_language="Chinese",
            assistant_agent_kwargs={
                "system_message": camel_researcher_prompt,
                "model": model,
            },
            user_agent_kwargs={
                "system_message": camel_reviewer_prompt,
                "model": model,
            },
        )

        # Init dialogue
        assistant_msg = society.init_chat()
        chat_history: list[Any] = []

        for round_num in range(max_rounds):
            logger.info("CAMEL review round %d/%d for task %d", round_num + 1, max_rounds, task.id)

            assistant_response, user_response = society.step(assistant_msg)
            assistant_msg_content = assistant_response.msg.content
            user_msg_content = user_response.msg.content

            chat_history.append(("researcher", assistant_msg_content))
            chat_history.append(("reviewer", user_msg_content))

            # Check for PASS verdict
            if "VERDICT: PASS" in user_msg_content:
                logger.info("CAMEL review passed at round %d for task %d", round_num + 1, task.id)
                return assistant_msg_content

            # Prepare next round message
            assistant_msg = assistant_response.msg

        # Max rounds reached without PASS - return the last researcher output
        logger.info("CAMEL review max rounds reached for task %d", task.id)
        return chat_history[-2][1] if len(chat_history) >= 2 else initial_summary

    def _build_model(self):
        """Create a CAMEL model instance for the configured LLM backend."""
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType, ModelType

        provider = (self._config.llm_provider or "").strip().lower()

        if provider == "ollama":
            return ModelFactory.create(
                model_platform=ModelPlatformType.OLLAMA,
                model_type=ModelType(value=self._config.resolved_model() or "llama3.2"),
                url=self._config.sanitized_ollama_url(),
                api_key=self._config.llm_api_key or "ollama",
            )
        elif provider == "lmstudio":
            return ModelFactory.create(
                model_platform=ModelPlatformType.LMSTUDIO,
                model_type=ModelType(value=self._config.resolved_model() or "llama3.2"),
                url=self._config.lmstudio_base_url,
                api_key=self._config.llm_api_key or "lmstudio",
            )
        else:
            return ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
                model_type=ModelType(value=self._config.resolved_model() or "llama3.2"),
                url=self._config.llm_base_url or "http://localhost:11434/v1",
                api_key=self._config.llm_api_key or "ollama",
            )

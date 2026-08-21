"""Orchestrator coordinating the deep research workflow via LangGraph."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Iterator

from config import Configuration
from graph.state import ResearchState
from graph.workflow import build_research_graph
from models import SummaryStateOutput

logger = logging.getLogger(__name__)

#将topic转换为ResearchState，初始化对象，用于存储研究流程的状态和结果
def _empty_state(topic: str) -> ResearchState:
    """Create the initial ResearchState for a new research run."""
    return {
        "research_topic": topic,
        "run_id": uuid.uuid4().hex,
        "todo_items": [],
        "completed_tasks": [],
        "web_research_results": [],
        "sources_gathered": [],
        "research_loop_count": 0,
        "structured_report": None,
        "running_summary": None,
        "report_note_id": None,
        "report_note_path": None,
        "stream_events": [],
    }

# DeepResearchAgent 是研究流程的协调器，负责协调 LangGraph 中的节点（任务）来完成研究任务。
#提供了三种不同的调用方式，run( ) 同步调用，run_stream_async( ) 异步调用
# run_stream_sync( ) 同步调用
class DeepResearchAgent:
    """Coordinator orchestrating TODO-based research workflow via LangGraph."""
    # 初始化时，根据配置创建 LangGraph 实例
    def __init__(self, config: Configuration | None = None) -> None:
        """Initialise the coordinator with configuration."""
        self.config = config or Configuration.from_env()
        self._graph = build_research_graph(self.config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    # 同步执行研究流程，返回最终报告
    def run(self, topic: str) -> SummaryStateOutput:
        """Execute the research workflow synchronously and return the final report."""
        final_state = self._graph.invoke(_empty_state(topic))
        todo_items = final_state.get("completed_tasks") or final_state.get("todo_items", [])
        return SummaryStateOutput(
            running_summary=final_state.get("running_summary") or "",
            report_markdown=final_state.get("structured_report") or "",
            todo_items=todo_items,
        )
    # 异步执行研究流程，返回增量 SSE 事件
    async def run_stream_async(self, topic: str):
        """Execute the workflow yielding incremental SSE events (async generator)."""
        initial_state = _empty_state(topic)
        yield {
            "type": "status",
            "run_id": initial_state["run_id"],
            "message": "初始化研究流程",
        }

        async for event in self._graph.astream(initial_state, stream_mode="updates"):
            for _node_name, update in event.items():
                for sse_event in update.get("stream_events", []):
                    yield sse_event
    # 同步执行研究流程，返回增量进度事件
    def run_stream(self, topic: str) -> Iterator[dict[str, Any]]:
        """Execute the workflow yielding incremental progress events (sync wrapper)."""

        async def _collect() -> list[dict[str, Any]]:
            return [e async for e in self.run_stream_async(topic)]

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                for event in pool.submit(asyncio.run, _collect()).result():
                    yield event
        else:
            for event in asyncio.run(_collect()):
                yield event

# 方便函数，用于同步执行研究流程
def run_deep_research(topic: str, config: Configuration | None = None) -> SummaryStateOutput:
    """Convenience function mirroring the class-based API."""
    agent = DeepResearchAgent(config=config)
    return agent.run(topic)

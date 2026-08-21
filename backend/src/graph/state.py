"""State definitions for the LangGraph research workflow."""
#
from __future__ import annotations

import operator
from typing import Any, Optional

from typing_extensions import Annotated, TypedDict

from models import TodoItem


class ResearchState(TypedDict, total=False):
    """Main graph state with reducers for parallel accumulation."""
    #整个工作流共享一个字段，但是有两种不同的状态
    #一个只读共享字段 research_topic run_id等是只读共享的，不能被修改
    #一个可写共享字段 todo_items completed_tasks等是可写共享的，可以被修改

    research_topic: str
    run_id: str
    todo_items: list[TodoItem]
    completed_tasks: Annotated[list[TodoItem], operator.add]
    web_research_results: Annotated[list[str], operator.add]
    sources_gathered: Annotated[list[str], operator.add]
    research_loop_count: Annotated[int, operator.add]
    structured_report: Optional[str]
    running_summary: Optional[str]
    report_note_id: Optional[str]
    report_note_path: Optional[str]
    stream_events: Annotated[list[dict[str, Any]], operator.add]


class TaskPipelineInput(TypedDict):
    """Input payload for each parallel task_pipeline invocation via Send."""

    research_topic: str
    run_id: str
    task: TodoItem
    todo_items: list[TodoItem]

"""LangGraph StateGraph construction for the research workflow."""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from config import Configuration
from graph.nodes import (
    fan_out_tasks,
    planner_node,
    synthesizer_node,
    task_pipeline_node,
)
from graph.state import ResearchState


def build_research_graph(config: Configuration):
    """Build and compile the research workflow graph.

    Topology:
        START -> planner -> [Send x N] -> task_pipeline -> synthesizer -> END
    """
    graph = StateGraph(ResearchState)

    graph.add_node("planner", partial(planner_node, app_config=config))
    graph.add_node("task_pipeline", partial(task_pipeline_node, app_config=config))
    graph.add_node("synthesizer", partial(synthesizer_node, app_config=config))

    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", fan_out_tasks, ["task_pipeline"])
    graph.add_edge("task_pipeline", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile()

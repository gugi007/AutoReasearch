"""LangGraph StateGraph construction for the research workflow."""
# 定义研究工作流的节点连接和状态流转
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
    #创建一个图容器
    graph = StateGraph(ResearchState)
    #添加三个节点：planner、task_pipeline、synthesizer
    graph.add_node("planner", partial(planner_node, app_config=config))
    graph.add_node("task_pipeline", partial(task_pipeline_node, app_config=config))
    graph.add_node("synthesizer", partial(synthesizer_node, app_config=config))
    #设置入口点为planner
    graph.set_entry_point("planner")
    #添加条件边：planner -> task_pipeline
    graph.add_conditional_edges("planner", fan_out_tasks, ["task_pipeline"])
    #添加边来进行状态流转
    graph.add_edge("task_pipeline", "synthesizer")
    #synthesizer -> END
    graph.add_edge("synthesizer", END)
    
    return graph.compile()

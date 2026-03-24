"""
LangGraph StateGraph for the Stake Advisor parse pipeline.

The pipeline has two nodes:
    parse  — LLM extraction via StakeParser (async)
    calc   — Deterministic odds math

An error_router conditional edge after parse routes to END on failure,
or continues to calc on success. Per D-23.

Usage:
    graph = build_pipeline_graph()
    result = await graph.ainvoke({"raw_input": raw_text})
"""

from langgraph.graph import StateGraph, END

from services.stake.pipeline.state import PipelineState
from services.stake.pipeline.nodes import parse_node, calc_node


def error_router(state: PipelineState) -> str:
    """Route to 'error' (END) if parse failed, otherwise continue to calc.

    Args:
        state: Current pipeline state after parse_node.

    Returns:
        "error" if state contains an error, otherwise "continue".
    """
    if state.get("error"):
        return "error"
    return "continue"


def build_pipeline_graph():
    """Build and compile the Stake Advisor parse pipeline StateGraph.

    Graph topology:
        parse -> [error_router] -> END (on error)
                                -> calc -> END (on success)

    Returns:
        Compiled LangGraph Runnable (supports ainvoke for async execution).
    """
    graph = StateGraph(PipelineState)

    graph.add_node("parse", parse_node)
    graph.add_node("calc", calc_node)

    graph.set_entry_point("parse")

    graph.add_conditional_edges(
        "parse",
        error_router,
        {
            "error": END,
            "continue": "calc",
        },
    )

    graph.add_edge("calc", END)

    return graph.compile()

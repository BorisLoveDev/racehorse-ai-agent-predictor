"""
LangGraph StateGraph for the Stake Advisor parse and analysis pipelines.

Two graphs:
    build_pipeline_graph()  — Phase 1: parse -> calc
    build_analysis_graph()  — Phase 2: pre_skip_check -> research -> analysis -> sizing -> format_recommendation

Usage:
    # Phase 1: parse raw text
    graph = build_pipeline_graph()
    result = await graph.ainvoke({"raw_input": raw_text})

    # Phase 2: run full analysis on confirmed parse state
    analysis_graph = build_analysis_graph()
    result = await analysis_graph.ainvoke(initial_state)
"""

from langgraph.graph import StateGraph, END

from services.stake.pipeline.state import PipelineState
from services.stake.pipeline.nodes import (
    analysis_node,
    calc_node,
    drawdown_check_node,
    format_recommendation_node,
    parse_node,
    pre_skip_check_node,
    sizing_node,
)
from services.stake.pipeline.research import research_node


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


def skip_router(state: PipelineState) -> str:
    """Route to format_recommendation (skip message) or research (continue).

    Used after pre_skip_check_node. If the race is flagged for Tier 1 skip
    (overround too high), jump directly to format_recommendation to show the
    skip message without running expensive LLM steps.

    Args:
        state: Current pipeline state after pre_skip_check_node.

    Returns:
        "skip" if skip_signal is True, otherwise "continue".
    """
    if state.get("skip_signal"):
        return "skip"
    return "continue"


def research_error_router(state: PipelineState) -> str:
    """Route to END on research error, otherwise continue to analysis.

    Args:
        state: Current pipeline state after research_node.

    Returns:
        "error" if state contains an error, otherwise "continue".
    """
    if state.get("error"):
        return "error"
    return "continue"


def analysis_error_router(state: PipelineState) -> str:
    """Route to END on analysis error, otherwise continue to sizing.

    Args:
        state: Current pipeline state after analysis_node.

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


def drawdown_router(state: PipelineState) -> str:
    """Route to format_recommendation if drawdown circuit breaker fired.

    Used after drawdown_check_node. If the bankroll has dropped >=threshold%
    from peak, jump directly to format_recommendation (skip message) without
    running any expensive LLM steps.

    Args:
        state: Current pipeline state after drawdown_check_node.

    Returns:
        "skip" if skip_signal is True (drawdown tripped), otherwise "continue".
    """
    if state.get("skip_signal"):
        return "skip"
    return "continue"


def build_analysis_graph():
    """Build Phase 2 analysis pipeline StateGraph.

    Graph topology:
        drawdown_check -> [drawdown_router] -> format_recommendation -> END  (drawdown tripped)
                                            -> pre_skip_check -> [skip_router] -> format_recommendation -> END  (Tier 1 skip)
                                                                               -> research -> [research_error_router] -> END  (on error)
                                                                                           -> analysis -> [analysis_error_router] -> END  (on error)
                                                                                                       -> sizing -> format_recommendation -> END

    Conditional routing:
        - Drawdown (balance >= threshold% below peak): format_recommendation shows protection message
        - Tier 1 skip (overround > threshold): format_recommendation shows skip message
        - Research error: format_recommendation (non-recoverable)
        - Analysis error: format_recommendation (non-recoverable)
        - Happy path: full research -> analysis -> sizing -> format_recommendation

    Returns:
        Compiled LangGraph Runnable (supports ainvoke for async execution).
    """
    graph = StateGraph(PipelineState)

    graph.add_node("drawdown_check", drawdown_check_node)
    graph.add_node("pre_skip_check", pre_skip_check_node)
    graph.add_node("research", research_node)
    graph.add_node("analysis", analysis_node)
    graph.add_node("sizing", sizing_node)
    graph.add_node("format_recommendation", format_recommendation_node)

    graph.set_entry_point("drawdown_check")

    # After drawdown_check: skip (drawdown tripped) -> show skip message; continue -> pre_skip_check
    graph.add_conditional_edges(
        "drawdown_check",
        drawdown_router,
        {
            "skip": "format_recommendation",
            "continue": "pre_skip_check",
        },
    )

    # After pre_skip_check: skip -> show skip message; continue -> research
    graph.add_conditional_edges(
        "pre_skip_check",
        skip_router,
        {
            "skip": "format_recommendation",
            "continue": "research",
        },
    )

    # After research: error -> format_recommendation (show error); continue -> analysis
    graph.add_conditional_edges(
        "research",
        research_error_router,
        {
            "error": "format_recommendation",
            "continue": "analysis",
        },
    )

    # After analysis: error -> format_recommendation (show error); continue -> sizing
    graph.add_conditional_edges(
        "analysis",
        analysis_error_router,
        {
            "error": "format_recommendation",
            "continue": "sizing",
        },
    )

    # sizing always leads to format_recommendation
    graph.add_edge("sizing", "format_recommendation")

    # format_recommendation always ends
    graph.add_edge("format_recommendation", END)

    return graph.compile()

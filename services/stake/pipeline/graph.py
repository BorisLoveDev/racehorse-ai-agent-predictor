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


# ===== Phase 1 super-graph (spec-aligned 11 steps with 2 interrupts) =====
#
# Thread_id per race: "race:{race_id}:{user_id}".
# Keep the legacy build_*_graph() helpers above intact for backward compat.

from services.stake.pipeline.nodes.interrupt_gate import make_interrupt_gate_node
from services.stake.pipeline.nodes.probability_model import make_probability_model_node
from services.stake.pipeline.nodes.analyst import make_analyst_node
from services.stake.pipeline.nodes.sizer import make_sizer_node
from services.stake.pipeline.nodes.decision_maker import make_decision_maker_node
from services.stake.pipeline.nodes.interrupt_approval import make_interrupt_approval_node
from services.stake.pipeline.nodes.result_recorder import make_result_recorder_node
from services.stake.pipeline.nodes.settlement import make_settlement_node
from services.stake.pipeline.nodes.reflection_update import make_reflection_update_node


async def _ingest_node(state: PipelineState) -> dict:
    """Normalise source_type. Phase 1 supports text only; unknown values are coerced."""
    st = state.get("source_type") or "text"
    if st not in ("text", "screenshot", "photo", "voice"):
        st = "text"
    return {"source_type": st}


async def _noop_node(state: PipelineState) -> dict:
    """Placeholder. Tasks 17 (result_recorder, settlement) and 18 (reflection_update)
    replace this with real node factories."""
    return {}


def _parse_err_router(state: PipelineState) -> str:
    return "error" if state.get("error") else "gate"


def _gate_router(state: PipelineState) -> str:
    return "skip" if state.get("skip_signal") else "go"


def _decision_router(state: PipelineState) -> str:
    return "skip" if state.get("skip_signal") else "approve"


def compile_race_graph(
    *,
    settings,
    checker,
    checkpointer,
    parse_node,
    research_node,
    analyst_llm,
    samples_repo,
    bankroll_repo,
    results_evaluator,          # reserved for Task 17; Phase 1 user-ping path ignores it
    calibrator_registry,
    reflection_writer=None,     # Task 18 wires this; Phase 1 tests pass a stub
    traces_repo=None,           # Task 19
    recorder_provider=None,     # Task 19
):
    """Compile the Phase-1 11-step race super-graph.

    Wires the spec-aligned 11 steps with two interrupt() pauses (gate, approval).
    Tasks 17/18/19 replace the _noop_node placeholders for result_recorder,
    settlement, and reflection_update.
    """
    g = StateGraph(PipelineState)
    g.add_node("ingest", _ingest_node)
    g.add_node("parse", parse_node)
    g.add_node("interrupt_gate", make_interrupt_gate_node(settings))
    g.add_node("research", research_node)
    g.add_node(
        "probability_model",
        make_probability_model_node(registry=calibrator_registry, samples_repo=samples_repo),
    )
    g.add_node(
        "analyst",
        make_analyst_node(llm_call=analyst_llm, paper_mode=(settings.mode == "paper")),
    )
    g.add_node(
        "sizer",
        make_sizer_node(settings=settings, checker=checker, bankroll_repo=bankroll_repo),
    )
    g.add_node("decision_maker", make_decision_maker_node())
    g.add_node(
        "interrupt_approval",
        make_interrupt_approval_node(bankroll_repo=bankroll_repo, mode=settings.mode),
    )
    g.add_node("result_recorder", make_result_recorder_node())
    g.add_node(
        "settlement",
        make_settlement_node(
            samples_repo=samples_repo,
            bankroll_repo=bankroll_repo,
            paper_mode=(settings.mode == "paper"),
        ),
    )
    g.add_node(
        "reflection_update",
        make_reflection_update_node(
            writer=reflection_writer,
            traces_repo=traces_repo,
            recorder_provider=recorder_provider,
        ),
    )

    g.set_entry_point("ingest")
    g.add_edge("ingest", "parse")
    g.add_conditional_edges(
        "parse", _parse_err_router,
        {"error": "reflection_update", "gate": "interrupt_gate"},
    )
    g.add_conditional_edges(
        "interrupt_gate", _gate_router,
        {"skip": "reflection_update", "go": "research"},
    )
    g.add_edge("research", "probability_model")
    g.add_edge("probability_model", "analyst")
    g.add_edge("analyst", "sizer")
    g.add_edge("sizer", "decision_maker")
    g.add_conditional_edges(
        "decision_maker", _decision_router,
        {"skip": "reflection_update", "approve": "interrupt_approval"},
    )
    g.add_edge("interrupt_approval", "result_recorder")
    g.add_edge("result_recorder", "settlement")
    g.add_edge("settlement", "reflection_update")
    g.add_edge("reflection_update", END)

    return g.compile(checkpointer=checkpointer)

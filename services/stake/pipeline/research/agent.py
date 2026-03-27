"""
Two-tier research orchestrator for the Stake Advisor pipeline.

Implements the D-02 pattern:
  - Senior orchestrator (AnalysisSettings.model, gemini-pro) creates research plan
    and synthesizes results into ResearchOutput.
  - Cheap sub-agents (ResearchSettings.model, flash-lite) execute individual searches.

The research_node function is the LangGraph node that runs the full three-phase process:
  Phase 1 — Planning: orchestrator creates a list of search queries
  Phase 2 — Execution: sub-agents execute each query in sequence
  Phase 3 — Synthesis: orchestrator synthesizes all results into ResearchOutput

Per D-06: research_node is a no-op if state["skip_signal"] is True.
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from services.stake.analysis.models import ResearchOutput
from services.stake.pipeline.research.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    SUB_AGENT_SYSTEM_PROMPT,
)
from services.stake.pipeline.research.tools import online_model_search, searxng_search
from services.stake.pipeline.state import PipelineState
from services.stake.settings import get_stake_settings


# ---------------------------------------------------------------------------
# Planning models — used for Phase 1 structured output
# ---------------------------------------------------------------------------


class SearchQuery(BaseModel):
    """A single search query in the research plan."""

    query: str
    purpose: str


class ResearchPlan(BaseModel):
    """Research plan produced by the orchestrator in Phase 1."""

    queries: list[SearchQuery]


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def build_search_sub_agent(settings):
    """Build a cheap React agent for executing individual search queries.

    Uses ResearchSettings.model (flash-lite) — the CHEAP model per D-02.
    Provider selection controlled by settings.research.provider (D-05):
      - 'online': uses online_model_search tool + web plugin extra_body
      - 'searxng': uses searxng_search tool, no extra_body
    """
    if settings.research.provider == "searxng":
        tools = [searxng_search]
        llm = ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=settings.openrouter_api_key,
            model=settings.research.model,
            temperature=settings.research.temperature,
            max_tokens=settings.research.max_tokens,
        )
    else:
        # Default: online provider with web grounding
        tools = [online_model_search]
        llm = ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=settings.openrouter_api_key,
            model=settings.research.model,
            temperature=settings.research.temperature,
            max_tokens=settings.research.max_tokens,
            extra_body={"plugins": [{"id": "web"}]},
        )

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SUB_AGENT_SYSTEM_PROMPT,
    )


def build_research_orchestrator(settings):
    """Build the senior orchestrator LLM (expensive model, synthesis only).

    Uses AnalysisSettings.model (gemini-pro) — the EXPENSIVE model per D-02.
    Returns the LLM (not a full agent) — orchestrator plans then synthesizes
    without calling tools directly. Tool calls are delegated to sub-agents.
    """
    return ChatOpenAI(
        openai_api_base="https://openrouter.ai/api/v1",
        openai_api_key=settings.openrouter_api_key,
        model=settings.analysis.model,
        temperature=settings.analysis.temperature,
        max_tokens=settings.analysis.max_tokens,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(obj, key, default=None):
    """Get attribute from Pydantic model or dict transparently."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _build_runners_context(state: PipelineState) -> str:
    """Build a human-readable race and runner summary for the orchestrator.

    Handles both Pydantic models and dicts (after Redis FSM serialization).
    """
    parsed_race = state.get("parsed_race")
    enriched_runners = state.get("enriched_runners") or []

    lines = []

    # Race header
    lines.append("=== RACE INFORMATION ===")
    if parsed_race:
        for field, label in [
            ("track", "Track"), ("race_number", "Race"), ("race_name", "Name"),
            ("distance", "Distance"), ("surface", "Surface"), ("date", "Date"),
            ("place_terms", "Place terms"),
        ]:
            val = _get(parsed_race, field)
            if val:
                lines.append(f"{label}: {val}")

    lines.append("")
    lines.append("=== RUNNERS ===")

    if enriched_runners:
        for runner in enriched_runners:
            if runner.get("status") == "scratched":
                continue
            parts = [f"#{runner.get('number', '?')} {runner.get('name', 'Unknown')}"]
            if runner.get("jockey"):
                parts.append(f"J: {runner['jockey']}")
            if runner.get("trainer"):
                parts.append(f"T: {runner['trainer']}")
            if runner.get("form_string"):
                parts.append(f"Form: {runner['form_string']}")
            if runner.get("decimal_odds") is not None:
                parts.append(f"Odds: {runner['decimal_odds']:.2f}")
            if runner.get("implied_prob") is not None:
                parts.append(f"Impl.Prob: {runner['implied_prob']:.1%}")
            if runner.get("odds_drift") is not None:
                parts.append(f"Drift: {runner['odds_drift']:+.1f}%")
            if runner.get("tips_text"):
                parts.append(f"Tips: {runner['tips_text']}")
            lines.append(" | ".join(parts))
    elif parsed_race:
        runners_list = _get(parsed_race, "runners") or []
        for runner in runners_list:
            if _get(runner, "status") == "scratched":
                continue
            parts = [f"#{_get(runner, 'number', '?')} {_get(runner, 'name', 'Unknown')}"]
            if _get(runner, "jockey"):
                parts.append(f"J: {_get(runner, 'jockey')}")
            if _get(runner, "trainer"):
                parts.append(f"T: {_get(runner, 'trainer')}")
            if _get(runner, "form_string"):
                parts.append(f"Form: {_get(runner, 'form_string')}")
            if _get(runner, "win_odds"):
                parts.append(f"Odds: {_get(runner, 'win_odds')}")
            lines.append(" | ".join(parts))
    else:
        lines.append("No runner data available.")

    return "\n".join(lines)


async def _execute_search_query(sub_agent, query: str) -> str:
    """Invoke the sub-agent with a search query, returning the result as string.

    On exception, returns "Search failed: {str(e)}" rather than propagating.
    """
    try:
        result = await sub_agent.ainvoke({"messages": [HumanMessage(content=query)]})
        # Extract final message from the agent's message list
        messages = result.get("messages", [])
        if messages:
            last_msg = messages[-1]
            return str(last_msg.content)
        return "No response from sub-agent."
    except Exception as e:
        return f"Search failed: {str(e)}"


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


async def research_node(state: PipelineState) -> dict:
    """Run the three-phase research pipeline and return ResearchOutput.

    Per D-06: skips immediately if state["skip_signal"] is True.

    Phase 1 — Planning: orchestrator creates list of search queries
    Phase 2 — Execution: sub-agents execute each query
    Phase 3 — Synthesis: orchestrator synthesizes into ResearchOutput

    Returns:
        dict with research_results (ResearchOutput.model_dump()) and research_error.
        On error: research_results=None, research_error=str(e).
    """
    import time as _time
    logger = logging.getLogger("stake")

    # D-06: respect skip signal — don't waste LLM calls on a race we're already skipping
    if state.get("skip_signal"):
        return {}

    try:
        t0 = _time.time()
        settings = get_stake_settings()
        runners_context = _build_runners_context(state)

        logger.info("[RESEARCH] Starting — orchestrator=%s, sub-agent=%s, provider=%s",
                     settings.analysis.model, settings.research.model, settings.research.provider)

        # ----------------------------------------------------------------
        # Phase 1 — Planning: orchestrator decides what to research
        # ----------------------------------------------------------------
        planning_llm = build_research_orchestrator(settings).with_structured_output(
            ResearchPlan
        )

        planning_prompt = (
            f"{runners_context}\n\n"
            "Analyze these runners and create a research plan. "
            "Return a JSON list of search queries you want executed. "
            "Each query should target specific information about one or more runners. "
            "Aim for 3-8 queries total. Maximum 15 queries.\n\n"
            "Focus on gaps in the provided data — runners with no form, unknown trainers, "
            "or interesting market movements."
        )

        research_plan: ResearchPlan = await planning_llm.ainvoke(
            [
                SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT),
                HumanMessage(content=planning_prompt),
            ]
        )

        logger.info("[RESEARCH] Plan: %d queries in %.1fs",
                     len(research_plan.queries), _time.time() - t0)
        for i, q in enumerate(research_plan.queries, 1):
            logger.info("[RESEARCH]   Q%d: %s", i, q.query[:80])

        # ----------------------------------------------------------------
        # Phase 2 — Execution: sub-agents run each search query
        # ----------------------------------------------------------------
        sub_agent = build_search_sub_agent(settings)
        search_results = []

        for i, search_query in enumerate(research_plan.queries, 1):
            qt0 = _time.time()
            result_str = await _execute_search_query(sub_agent, search_query.query)
            logger.info("[RESEARCH]   Q%d done in %.1fs — %d chars",
                         i, _time.time() - qt0, len(result_str))
            search_results.append(
                {
                    "query": search_query.query,
                    "purpose": search_query.purpose,
                    "result": result_str,
                }
            )

        logger.info("[RESEARCH] All queries done in %.1fs — synthesizing...", _time.time() - t0)

        # ----------------------------------------------------------------
        # Phase 3 — Synthesis: orchestrator consolidates into ResearchOutput
        # ----------------------------------------------------------------
        synthesis_llm = build_research_orchestrator(settings).with_structured_output(
            ResearchOutput
        )

        # Build search results summary for the synthesis prompt
        results_text_parts = []
        for i, sr in enumerate(search_results, 1):
            results_text_parts.append(
                f"[Query {i}] {sr['query']}\n"
                f"Purpose: {sr['purpose']}\n"
                f"Result: {sr['result']}"
            )
        results_text = "\n\n---\n\n".join(results_text_parts)

        synthesis_prompt = (
            f"{runners_context}\n\n"
            "=== SEARCH RESULTS ===\n\n"
            f"{results_text}\n\n"
            "Based on the race data and search results above, synthesize your findings "
            "into a ResearchOutput. For each runner:\n"
            "- Summarize the form narrative\n"
            "- Note trainer/jockey statistics found\n"
            "- Include expert opinions or tips found\n"
            "- Record any external odds found (TAB, Betfair, etc.)\n"
            "- Assess data_quality: 'rich' (good data), 'sparse' (limited), 'none' (nothing found)\n"
            "- Add confidence notes on data reliability\n\n"
            "For overall_notes: describe any race-level context (track bias, conditions, market patterns)."
        )

        research_output: ResearchOutput = await synthesis_llm.ainvoke(
            [
                SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT),
                HumanMessage(content=synthesis_prompt),
            ]
        )

        research_dict = research_output.model_dump()
        qualities = [r.get("data_quality", "?") for r in research_dict.get("runners", [])]
        logger.info("[RESEARCH] Done in %.1fs — %d runners researched, qualities: %s",
                     _time.time() - t0, len(qualities), qualities)
        return {
            "research_results": research_dict,
            "research_error": None,
        }

    except Exception as e:
        logger.exception("[RESEARCH] Failed: %s", e)
        return {
            "research_results": None,
            "research_error": str(e),
        }

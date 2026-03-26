"""
Research pipeline package for the Stake Advisor Bot.

Contains nodes for web research (SearXNG and/or OpenRouter online models)
that gather form data, trainer stats, and expert opinions for each runner.

Exports:
  research_node: LangGraph node — runs three-phase research pipeline
  build_research_orchestrator: factory for senior orchestrator LLM (expensive model)
  build_search_sub_agent: factory for cheap search sub-agent (flash-lite)
"""

from services.stake.pipeline.research.agent import (
    build_research_orchestrator,
    build_search_sub_agent,
    research_node,
)

__all__ = [
    "research_node",
    "build_research_orchestrator",
    "build_search_sub_agent",
]

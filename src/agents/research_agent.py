"""
Research Agent - Pre-fetches web search results for betting agents.

Runs BEFORE betting agents to:
1. Generate intelligent search queries based on race data
2. Perform all searches once
3. Cache results for both Gemini and Grok to use

This eliminates duplicate searches and ensures consistent context.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config.settings import get_settings
from ..web_search import WebResearcher
from ..web_search.research_modes import ResearchResult


@dataclass
class RaceResearchContext:
    """Complete research context for a race, shared between betting agents."""

    race_url: str
    queries_generated: List[str]
    search_results: List[Dict[str, Any]]
    summaries: List[str] = field(default_factory=list)
    formatted_context: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "race_url": self.race_url,
            "queries_generated": self.queries_generated,
            "search_results": self.search_results,
            "summaries": self.summaries,
            "formatted_context": self.formatted_context,
        }


class ResearchAgent:
    """
    Dedicated research agent that pre-fetches all web search data.

    Architecture:
    1. Orchestrator receives race
    2. ResearchAgent.research(race_data) runs FIRST
    3. Returns RaceResearchContext
    4. GeminiAgent and GrokAgent receive the same context
    5. No duplicate searches!
    """

    def __init__(self):
        settings = get_settings()
        research_settings = settings.agents.research
        web_search_settings = settings.web_search

        self.enabled = research_settings.enabled and web_search_settings.enabled
        self.top_horses = research_settings.top_horses_to_research
        self.include_jockeys = research_settings.include_jockeys
        self.include_trainers = research_settings.include_trainers

        if not self.enabled:
            self.llm = None
            self.web_researcher = None
            return

        # Initialize LLM for query generation
        api_key = settings.api_keys.openrouter_api_key.get_secret_value()
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        self.llm = ChatOpenAI(
            model=research_settings.model_id,
            temperature=research_settings.temperature,
            max_tokens=research_settings.max_tokens,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1"
        )

        # Initialize WebResearcher with shared cache (uses SearXNG)
        self.web_researcher = WebResearcher(
            mode=web_search_settings.mode,
            max_results_per_query=web_search_settings.max_results_per_query,
            max_queries=web_search_settings.max_queries_per_race,
            deep_mode_max_sites=web_search_settings.deep_mode_max_sites,
            enable_cache=web_search_settings.enable_cache,
            cache_ttl_seconds=web_search_settings.cache_ttl_seconds,
            search_engine=web_search_settings.engine,
            searxng_url=web_search_settings.searxng_url,
        )

    async def research(self, race_data: Dict[str, Any]) -> RaceResearchContext:
        """
        Perform comprehensive research for a race.

        Args:
            race_data: Race data with race_info and runners

        Returns:
            RaceResearchContext with all search results
        """
        race_info = race_data.get("race_info", {})
        race_url = race_info.get("url", "unknown")

        if not self.enabled:
            return RaceResearchContext(
                race_url=race_url,
                queries_generated=[],
                search_results=[],
                formatted_context="Web search disabled."
            )

        # Step 1: Generate search queries
        queries = await self._generate_queries(race_data)

        if not queries:
            return RaceResearchContext(
                race_url=race_url,
                queries_generated=[],
                search_results=[],
                formatted_context="No queries generated."
            )

        # Step 2: Perform all searches
        all_results = []
        all_summaries = []

        for query in queries:
            try:
                result = await self.web_researcher.research(query)
                all_results.append({
                    "query": query,
                    "results": [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": r.get("content", "")
                        }
                        for sr in result.search_results
                        for r in sr.results
                    ],
                    "summary": result.summary
                })
                if result.summary:
                    all_summaries.append(result.summary)
            except Exception as e:
                print(f"Research error for '{query}': {e}")

        # Step 3: Format context for betting agents
        formatted = self._format_research_context(race_data, all_results, all_summaries)

        return RaceResearchContext(
            race_url=race_url,
            queries_generated=queries,
            search_results=all_results,
            summaries=all_summaries,
            formatted_context=formatted
        )

    async def _generate_queries(self, race_data: Dict[str, Any]) -> List[str]:
        """Generate intelligent search queries based on race data."""
        runners = race_data.get("runners", [])
        race_info = race_data.get("race_info", {})

        # Sort by rating or odds to get top horses
        sorted_runners = sorted(
            runners,
            key=lambda r: r.get("rating", 0) or 0,
            reverse=True
        )[:self.top_horses]

        queries = []

        # Generate queries for each top horse
        for runner in sorted_runners:
            horse_name = runner.get("name", "")
            jockey = runner.get("jockey", "")
            trainer = runner.get("trainer", "")

            if horse_name:
                queries.append(f"{horse_name} horse racing form results Australia")

            if self.include_jockeys and jockey:
                queries.append(f"{jockey} jockey racing statistics")

            if self.include_trainers and trainer:
                queries.append(f"{trainer} horse trainer statistics")

        # Add race venue/track query
        location = race_info.get("location", "")
        track_condition = race_info.get("track_condition", "")
        if location:
            queries.append(f"{location} racecourse tips {track_condition}")

        # Use LLM to potentially refine or add queries
        if self.llm and sorted_runners:
            try:
                additional = await self._llm_generate_queries(race_data, sorted_runners)
                queries.extend(additional)
            except Exception as e:
                print(f"LLM query generation error: {e}")

        # Deduplicate and limit
        settings = get_settings()
        max_queries = settings.web_search.max_queries_per_race
        seen = set()
        unique_queries = []
        for q in queries:
            q_lower = q.lower()
            if q_lower not in seen:
                seen.add(q_lower)
                unique_queries.append(q)

        return unique_queries[:max_queries]

    async def _llm_generate_queries(
        self,
        race_data: Dict[str, Any],
        top_runners: List[Dict[str, Any]]
    ) -> List[str]:
        """Use LLM to generate additional smart queries."""
        race_info = race_data.get("race_info", {})

        prompt = f"""You are a horse racing research assistant. Based on the race data below, generate 2-3 additional search queries that would help analyze this race.

Race: {race_info.get('location', '')} Race {race_info.get('race_number', '')}
Distance: {race_info.get('distance', '')}
Track: {race_info.get('track_condition', '')}

Top Horses:
{chr(10).join(f"- {r.get('name', '')} (Form: {r.get('form', 'N/A')}, Barrier: {r.get('barrier', 'N/A')})" for r in top_runners)}

Return only the search queries, one per line. Focus on:
- Recent form of key horses
- Track/distance specialists
- Jockey/trainer combinations that work well together
"""

        response = await self.llm.ainvoke([
            SystemMessage(content="You are a horse racing research assistant. Return only search queries, one per line."),
            HumanMessage(content=prompt)
        ])

        # Parse response into queries
        queries = [
            line.strip().lstrip("-•*123456789. ")
            for line in response.content.strip().split("\n")
            if line.strip() and len(line.strip()) > 10
        ]

        return queries[:3]  # Limit LLM-generated queries

    def _format_research_context(
        self,
        race_data: Dict[str, Any],
        search_results: List[Dict[str, Any]],
        summaries: List[str]
    ) -> str:
        """Format research results as context for betting agents."""
        parts = ["# WEB RESEARCH RESULTS", ""]

        # Add summaries if available (from deep mode)
        if summaries:
            parts.append("## Research Summaries")
            for i, summary in enumerate(summaries[:3], 1):
                if summary:
                    parts.append(f"\n### Summary {i}")
                    parts.append(summary[:1500])
            parts.append("")

        # Add search snippets
        parts.append("## Search Snippets")
        for sr in search_results:
            query = sr.get("query", "")
            results = sr.get("results", [])

            parts.append(f"\n### Query: {query}")
            for idx, result in enumerate(results[:3], 1):
                title = result.get("title", "")
                content = result.get("content", "")
                if title:
                    parts.append(f"{idx}. **{title}**")
                    if content:
                        parts.append(f"   {content[:300]}...")

        return "\n".join(parts)

"""
Base agent implementation with LangGraph two-step workflow.
Step 1: Deep analysis with web search (or pre-fetched research)
Step 2: Structured bet output generation

Supports two modes:
- analyze_race(): Self-contained, performs own web search
- analyze_race_with_research(): Uses pre-fetched research from ResearchAgent
"""

import json
from typing import Any, Dict, Optional, TypedDict, TYPE_CHECKING

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from ..config.settings import get_settings
from ..models.bets import StructuredBetOutput
from ..web_search import WebResearcher

if TYPE_CHECKING:
    from .research_agent import RaceResearchContext


class AgentState(TypedDict):
    """State for the agent workflow."""
    race_data: Dict[str, Any]
    search_queries: list[str]
    search_results: list[Dict[str, Any]]
    research_context: Optional[str]  # Pre-fetched research (formatted)
    analysis: str
    structured_bet: Optional[StructuredBetOutput]
    messages: list[BaseMessage]


class BaseRaceAgent:
    """
    Base agent for race analysis with two-step workflow:
    1. Deep analysis with web search
    2. Structured bet generation
    """

    def __init__(
        self,
        agent_name: str,
        model_id: str,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        enable_web_search: bool = True
    ):
        self.agent_name = agent_name
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_web_search = enable_web_search

        settings = get_settings()

        # Initialize LLM
        openrouter_key = settings.api_keys.openrouter_api_key.get_secret_value()
        if not openrouter_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        self.llm = ChatOpenAI(
            model=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1"
        )

        # Initialize WebResearcher for web search (uses SearXNG)
        web_search_settings = settings.web_search
        if enable_web_search and web_search_settings.enabled:
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
        else:
            self.web_researcher = None

        # Build the workflow graph
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("generate_search_queries", self._generate_search_queries)
        workflow.add_node("web_search", self._web_search)
        workflow.add_node("deep_analysis", self._deep_analysis)
        workflow.add_node("structured_output", self._structured_output)

        # Define edges
        workflow.set_entry_point("generate_search_queries")
        workflow.add_edge("generate_search_queries", "web_search")
        workflow.add_edge("web_search", "deep_analysis")
        workflow.add_edge("deep_analysis", "structured_output")
        workflow.add_edge("structured_output", END)

        return workflow.compile()

    def _generate_search_queries(self, state: AgentState) -> AgentState:
        """Step 0: Generate search queries for web research."""
        # Skip if research already provided (from ResearchAgent)
        if state.get("research_context") or state.get("search_results"):
            return state

        if not self.enable_web_search or not self.web_researcher:
            state["search_queries"] = []
            return state

        race_data = state["race_data"]
        runners = race_data.get("runners", [])

        # Generate queries for top horses, jockeys, trainers
        queries = []

        # Top 5 horses by rating or odds
        top_runners = sorted(runners, key=lambda r: r.get("rating", 0), reverse=True)[:5]
        for runner in top_runners:
            horse_name = runner.get("name", "")
            jockey = runner.get("jockey", "")
            trainer = runner.get("trainer", "")

            if horse_name:
                queries.append(f"{horse_name} horse racing recent form results")
            if jockey:
                queries.append(f"{jockey} jockey statistics win rate")
            if trainer:
                queries.append(f"{trainer} trainer racing statistics")

        # Limit queries based on settings
        settings = get_settings()
        max_queries = settings.web_search.max_queries_per_race
        state["search_queries"] = queries[:max_queries]
        return state

    async def _web_search_async(self, state: AgentState) -> AgentState:
        """Step 1: Perform web searches for additional context (async)."""
        if not self.web_researcher or not state["search_queries"]:
            state["search_results"] = []
            return state

        search_results = []
        settings = get_settings()

        for query in state["search_queries"]:
            try:
                # Use the configured mode (basic or deep)
                result = await self.web_researcher.research(query)

                # Format results to match expected structure
                search_results.append({
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
                    "summary": result.summary  # Available in deep mode
                })
            except Exception as e:
                print(f"Search error for '{query}': {e}")

        state["search_results"] = search_results
        return state

    def _web_search(self, state: AgentState) -> AgentState:
        """Step 1: Perform web searches for additional context (sync wrapper)."""
        import asyncio

        # Skip if research already provided (from ResearchAgent)
        if state.get("research_context") or state.get("search_results"):
            return state

        if not self.web_researcher or not state["search_queries"]:
            state["search_results"] = []
            return state

        # Run async search in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, create task
                import nest_asyncio
                nest_asyncio.apply()
                return asyncio.get_event_loop().run_until_complete(
                    self._web_search_async(state)
                )
            else:
                return loop.run_until_complete(self._web_search_async(state))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self._web_search_async(state))

    def _deep_analysis(self, state: AgentState) -> AgentState:
        """Step 2: Perform deep analysis with race data and search results."""
        race_data = state["race_data"]
        search_results = state["search_results"]
        research_context = state.get("research_context")

        # Build context - prefer pre-fetched research if available
        if research_context:
            context = self._format_race_context_with_research(race_data, research_context)
        else:
            context = self._format_race_context(race_data, search_results)

        # Analysis prompt
        analysis_prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=self._get_analysis_system_prompt()),
            HumanMessage(content=context)
        ])

        # Generate analysis
        messages = analysis_prompt.format_messages()
        response = self.llm.invoke(messages)
        state["analysis"] = response.content
        state["messages"] = messages + [response]

        return state

    def _structured_output(self, state: AgentState) -> AgentState:
        """Step 3: Generate structured bet output."""
        race_data = state["race_data"]
        analysis = state["analysis"]

        # Build structured output prompt
        structured_prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=self._get_structured_output_system_prompt()),
            HumanMessage(content=f"""
Race Data:
{json.dumps(race_data, indent=2)}

Analysis:
{analysis}

Now provide your structured bet recommendations following the exact schema.
Remember: Set bet types to null if you don't want to make that bet. Never use amount=0.
""")
        ])

        # Use structured output
        structured_llm = self.llm.with_structured_output(StructuredBetOutput)
        messages = structured_prompt.format_messages()
        structured_bet = structured_llm.invoke(messages)

        # Handle None response
        if structured_bet is None:
            raise ValueError(f"LLM returned None for structured output")

        # Set agent name
        structured_bet.agent_name = self.agent_name

        state["structured_bet"] = structured_bet
        return state

    def _format_race_context(
        self,
        race_data: Dict[str, Any],
        search_results: list[Dict[str, Any]]
    ) -> str:
        """Format race data and search results for analysis."""
        context_parts = [
            "# RACE INFORMATION",
            json.dumps(race_data, indent=2),
            ""
        ]

        if search_results:
            context_parts.append("# WEB SEARCH RESULTS")

            # Check for deep mode summaries
            summaries = [
                sr.get("summary") for sr in search_results
                if sr.get("summary")
            ]
            if summaries:
                context_parts.append("\n## Research Summaries")
                for summary in summaries[:3]:
                    context_parts.append(summary[:1000])
                    context_parts.append("")

            # Add individual search results
            context_parts.append("\n## Search Snippets")
            for sr in search_results:
                query = sr.get("query", "")
                results = sr.get("results", [])
                context_parts.append(f"\nQuery: {query}")
                for idx, result in enumerate(results[:3], 1):
                    title = result.get("title", "")
                    content = result.get("content", "")
                    context_parts.append(f"{idx}. {title}")
                    if content:
                        context_parts.append(f"   {content[:300]}...")

        return "\n".join(context_parts)

    def _format_race_context_with_research(
        self,
        race_data: Dict[str, Any],
        research_context: str
    ) -> str:
        """Format race data with pre-fetched research context."""
        context_parts = [
            "# RACE INFORMATION",
            json.dumps(race_data, indent=2),
            "",
            research_context  # Already formatted by ResearchAgent
        ]
        return "\n".join(context_parts)

    def _get_analysis_system_prompt(self) -> str:
        """Get the system prompt for deep analysis."""
        return """You are an expert horse racing analyst with deep knowledge of form analysis, track conditions, jockey/trainer statistics, and betting strategies.

Your task is to analyze the provided race information and web search results to provide a comprehensive analysis.

Focus on:
1. **Form Analysis**: Recent performance, consistency, class
2. **Track Conditions**: How horses perform on this surface/distance
3. **Jockey/Trainer**: Statistics and recent form
4. **Barrier Position**: Impact on race strategy
5. **Weight**: Handicap considerations
6. **Odds Analysis**: Value identification
7. **Race Dynamics**: Likely pace, positioning

Provide a detailed analysis that will inform betting decisions. Be specific about strengths and weaknesses of key contenders.
"""

    def _get_structured_output_system_prompt(self) -> str:
        """Get the system prompt for structured output generation."""
        return """Based on your analysis, provide structured betting recommendations.

CRITICAL RULES:
- If you do NOT want to make a particular bet type, set it to null. DO NOT set amount to 0.
- Every bet you include MUST have amount > 0 (minimum $1).
- Only include bets you actually recommend. Omit others by setting them to null.

Guidelines:
- Only recommend bets you have confidence in (confidence_score >= 0.5)
- Win bets: Horse most likely to win
- Place bets: Safer option for top 3 finish
- Exacta: Specific 1-2 finish order
- Quinella: Two horses for 1-2 in any order
- Trifecta: Specific 1-2-3 finish order
- First4: Specific 1-2-3-4 finish order
- QPS: 2-4 horses where any 2 finish in top 3

Bet amounts should reflect confidence (minimum $1 for any bet):
- High confidence (0.8+): $5-10
- Medium confidence (0.6-0.8): $2-5
- Lower confidence (0.5-0.6): $1-2

Set risk_level based on:
- Low: Clear favorites, proven form
- Medium: Competitive field, some uncertainty
- High: Long shots, unpredictable race

Provide clear reasoning for each bet recommendation.
"""

    async def analyze_race(self, race_data: Dict[str, Any]) -> StructuredBetOutput:
        """
        Main entry point: Analyze a race and generate structured bet output.
        Performs its own web search (legacy mode).
        """
        initial_state: AgentState = {
            "race_data": race_data,
            "search_queries": [],
            "search_results": [],
            "research_context": None,
            "analysis": "",
            "structured_bet": None,
            "messages": []
        }

        # Run workflow
        final_state = await self.workflow.ainvoke(initial_state)

        if not final_state["structured_bet"]:
            raise ValueError("Failed to generate structured bet output")

        return final_state["structured_bet"]

    async def analyze_race_with_research(
        self,
        race_data: Dict[str, Any],
        research_context: "RaceResearchContext"
    ) -> StructuredBetOutput:
        """
        Analyze a race using pre-fetched research from ResearchAgent.
        This is the preferred method when multiple agents analyze the same race.

        Args:
            race_data: Race data with race_info and runners
            research_context: Pre-fetched research from ResearchAgent

        Returns:
            StructuredBetOutput with betting recommendations
        """
        initial_state: AgentState = {
            "race_data": race_data,
            "search_queries": research_context.queries_generated,
            "search_results": research_context.search_results,
            "research_context": research_context.formatted_context,
            "analysis": "",
            "structured_bet": None,
            "messages": []
        }

        # Run workflow - will skip search steps since results are pre-populated
        final_state = await self.workflow.ainvoke(initial_state)

        if not final_state["structured_bet"]:
            raise ValueError("Failed to generate structured bet output")

        return final_state["structured_bet"]

    def analyze_race_sync(self, race_data: Dict[str, Any]) -> StructuredBetOutput:
        """Synchronous version of analyze_race."""
        initial_state: AgentState = {
            "race_data": race_data,
            "search_queries": [],
            "search_results": [],
            "research_context": None,
            "analysis": "",
            "structured_bet": None,
            "messages": []
        }

        # Run workflow
        final_state = self.workflow.invoke(initial_state)

        if not final_state["structured_bet"]:
            raise ValueError("Failed to generate structured bet output")

        return final_state["structured_bet"]

    def analyze_race_with_research_sync(
        self,
        race_data: Dict[str, Any],
        research_context: "RaceResearchContext"
    ) -> StructuredBetOutput:
        """Synchronous version of analyze_race_with_research."""
        initial_state: AgentState = {
            "race_data": race_data,
            "search_queries": research_context.queries_generated,
            "search_results": research_context.search_results,
            "research_context": research_context.formatted_context,
            "analysis": "",
            "structured_bet": None,
            "messages": []
        }

        # Run workflow
        final_state = self.workflow.invoke(initial_state)

        if not final_state["structured_bet"]:
            raise ValueError("Failed to generate structured bet output")

        return final_state["structured_bet"]

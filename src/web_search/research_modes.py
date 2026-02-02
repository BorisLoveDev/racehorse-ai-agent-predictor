"""
Web research modes based on simple_deep_research reference implementation.

Modes:
- off: No web search
- raw: Search only, return snippets without LLM processing
- lite: Search → Relevance → visit_site → Extraction → Summarization
- deep: Complexity → Decompose → visit → Sum per query → Final Sum → Judge loop
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .duckduckgo import DuckDuckGoSearch
from .searxng import SearXNGSearch
from .search_cache import SearchCache
from .site_visitor import SiteVisitor
from .research_agents import (
    ComplexityAgent,
    DecomposeAgent,
    ExtractionAgent,
    JudgeAgent,
    RelevanceAgent,
    SummarizationAgent,
)


@dataclass
class SearchResult:
    """Result from a search query."""
    query: str
    results: List[Dict[str, str]]
    extracted_content: Optional[str] = None


@dataclass
class ResearchResult:
    """Complete research result."""
    queries_used: List[str]
    search_results: List[SearchResult]
    summary: Optional[str] = None
    mode: str = "raw"


class WebResearcher:
    """
    Main web research interface supporting multiple modes.

    Modes (from simple_deep_research reference):
    - off: No search, returns empty result
    - raw: Search only, returns snippets without LLM
    - lite: Search → Relevance filter → visit sites → Extraction → Summarization
    - deep: Complexity check → Decompose → visit all → Sum per query → Judge loop
    """

    def __init__(
        self,
        mode: str = "raw",
        max_results_per_query: int = 5,
        max_queries: int = 10,
        deep_mode_max_sites: int = 3,
        enable_cache: bool = True,
        cache_ttl_seconds: int = 300,
        search_engine: str = "searxng",
        searxng_url: str = "http://localhost:8080",
    ):
        """
        Initialize WebResearcher.

        Args:
            mode: "off", "raw", "lite", or "deep"
            max_results_per_query: Max search results per query
            max_queries: Max total queries (for limiting deep mode)
            deep_mode_max_sites: Max sites to visit per query
            enable_cache: Whether to cache search results
            cache_ttl_seconds: Cache TTL in seconds
            search_engine: "searxng" (default) or "duckduckgo"
            searxng_url: SearXNG instance URL
        """
        self.mode = mode
        self.max_results_per_query = max_results_per_query
        self.max_queries = max_queries
        self.deep_mode_max_sites = deep_mode_max_sites

        # Initialize search engine
        if search_engine == "searxng":
            self.search_engine = SearXNGSearch(base_url=searxng_url)
        else:
            self.search_engine = DuckDuckGoSearch()

        self.site_visitor = SiteVisitor()

        # Cache
        self.enable_cache = enable_cache
        self.cache = SearchCache(
            ttl_seconds=cache_ttl_seconds
        ) if enable_cache else None

        # LLM agents (lazy initialized)
        self._complexity_agent: Optional[ComplexityAgent] = None
        self._decompose_agent: Optional[DecomposeAgent] = None
        self._relevance_agent: Optional[RelevanceAgent] = None
        self._extraction_agent: Optional[ExtractionAgent] = None
        self._summarization_agent: Optional[SummarizationAgent] = None
        self._judge_agent: Optional[JudgeAgent] = None

    def _get_complexity_agent(self) -> ComplexityAgent:
        if self._complexity_agent is None:
            self._complexity_agent = ComplexityAgent()
        return self._complexity_agent

    def _get_decompose_agent(self) -> DecomposeAgent:
        if self._decompose_agent is None:
            self._decompose_agent = DecomposeAgent()
        return self._decompose_agent

    def _get_relevance_agent(self) -> RelevanceAgent:
        if self._relevance_agent is None:
            self._relevance_agent = RelevanceAgent()
        return self._relevance_agent

    def _get_extraction_agent(self) -> ExtractionAgent:
        if self._extraction_agent is None:
            self._extraction_agent = ExtractionAgent()
        return self._extraction_agent

    def _get_summarization_agent(self) -> SummarizationAgent:
        if self._summarization_agent is None:
            self._summarization_agent = SummarizationAgent()
        return self._summarization_agent

    def _get_judge_agent(self) -> JudgeAgent:
        if self._judge_agent is None:
            self._judge_agent = JudgeAgent()
        return self._judge_agent

    async def _cached_search(
        self,
        query: str,
        max_results: int
    ) -> List[Dict[str, str]]:
        """Search with optional caching."""
        if self.cache:
            cached = await self.cache.get(query, max_results)
            if cached is not None:
                return cached

        results = await self.search_engine.search(query, max_results)

        if self.cache and results:
            await self.cache.set(query, max_results, results)

        return results

    async def research(
        self,
        query: str,
        mode: Optional[str] = None
    ) -> ResearchResult:
        """
        Perform web research using configured or specified mode.

        Args:
            query: Research query
            mode: Override mode ("off", "raw", "lite", "deep")

        Returns:
            ResearchResult with search results and optional summary
        """
        use_mode = mode or self.mode

        if use_mode == "off":
            return await self.research_off(query)
        elif use_mode == "raw":
            return await self.research_raw(query)
        elif use_mode == "lite":
            return await self.research_lite(query)
        elif use_mode == "deep":
            return await self.research_deep(query)
        else:
            # Default to raw for backward compatibility with "basic"
            return await self.research_raw(query)

    async def research_off(self, query: str) -> ResearchResult:
        """
        Off mode: No web search, returns empty result.

        Args:
            query: Search query (unused)

        Returns:
            Empty ResearchResult
        """
        return ResearchResult(
            queries_used=[],
            search_results=[],
            summary=None,
            mode="off"
        )

    async def research_raw(self, query: str) -> ResearchResult:
        """
        Raw mode: Search only, return snippets without LLM processing.

        This is the fastest mode - just returns what the search engine gives us.

        Args:
            query: Search query

        Returns:
            ResearchResult with search snippets only
        """
        results = await self._cached_search(query, self.max_results_per_query)

        search_result = SearchResult(
            query=query,
            results=results
        )

        return ResearchResult(
            queries_used=[query],
            search_results=[search_result],
            mode="raw"
        )

    async def research_lite(self, query: str) -> ResearchResult:
        """
        Lite mode: Search → Relevance → visit_site → Extraction → Summarization.

        Based on run_lite_deep_research.py from reference:
        1. Search for results
        2. For each result, check relevance with RelevanceAgent
        3. Visit relevant sites
        4. Extract information with ExtractionAgent
        5. Summarize everything with SummarizationAgent

        Args:
            query: Search query

        Returns:
            ResearchResult with extracted content and summary
        """
        # Step 1: Search
        results = await self._cached_search(query, self.max_results_per_query)

        if not results:
            return ResearchResult(
                queries_used=[query],
                search_results=[SearchResult(query=query, results=[])],
                mode="lite"
            )

        search_result = SearchResult(query=query, results=results)

        # Step 2-4: Filter by relevance, visit sites, extract
        relevance_agent = self._get_relevance_agent()
        extraction_agent = self._get_extraction_agent()

        accumulated_content: List[str] = []

        for idx, result in enumerate(results[:self.deep_mode_max_sites]):
            title = result.get("title", "")
            url = result.get("url", "")

            # Step 2: Check relevance
            is_relevant = await relevance_agent.is_relevant(query, title)

            if is_relevant:
                # Step 3: Visit site
                site_content = await self.site_visitor.visit(url)

                if site_content:
                    # Step 4: Extract relevant information
                    extracted = await extraction_agent.extract(query, site_content)
                    accumulated_content.append(
                        f"Site {idx + 1} ({url}):\n{extracted}"
                    )

        # Step 5: Summarize everything
        summary = None
        if accumulated_content:
            summarization_agent = self._get_summarization_agent()
            combined = "\n\n".join(accumulated_content)
            summary = await summarization_agent.summarize(query, combined)
            search_result.extracted_content = combined

        return ResearchResult(
            queries_used=[query],
            search_results=[search_result],
            summary=summary,
            mode="lite"
        )

    async def research_deep(
        self,
        query: str,
        max_iterations: int = 3
    ) -> ResearchResult:
        """
        Deep mode: Full multi-agent research pipeline with Judge loop.

        Based on run_full_deep_research.py from reference:
        1. ComplexityAgent determines if query is complex
        2. If simple → run lite mode
        3. If complex → DecomposeAgent breaks into sub-queries
        4. For each sub-query:
           - Search
           - Visit each result site
           - SummarizationAgent summarizes for this query
        5. Final SummarizationAgent combines all results
        6. JudgeAgent checks if answer is complete
        7. If not complete → JudgeAgent returns new queries → repeat from step 4

        Args:
            query: Research query
            max_iterations: Max research iterations (Judge loop limit)

        Returns:
            ResearchResult with comprehensive summary
        """
        all_queries: List[str] = []
        all_search_results: List[SearchResult] = []

        # Step 1: Check complexity
        complexity_agent = self._get_complexity_agent()
        is_complex = await complexity_agent.analyze(query)

        # Step 2: If simple, use lite approach
        if not is_complex:
            print("Prompt is simple, using lite approach")
            return await self._deep_simple_path(query)

        # Step 3: Complex query - decompose
        print("Prompt is complex, decomposing")
        decompose_agent = self._get_decompose_agent()
        current_queries = await decompose_agent.decompose(query, num_queries=2)

        iteration = 0
        final_summary = None

        while current_queries and iteration < max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")
            print(f"Queries: {current_queries}")

            # Limit queries
            remaining_quota = self.max_queries - len(all_queries)
            current_queries = current_queries[:min(remaining_quota, 3)]

            if not current_queries:
                break

            all_queries.extend(current_queries)

            # Step 4: For each sub-query
            merged_results: List[str] = []
            summarization_agent = self._get_summarization_agent()

            for q in current_queries:
                print(f"Searching for: {q}")

                # Search
                results = await self._cached_search(q, self.max_results_per_query)
                search_result = SearchResult(query=q, results=results)
                all_search_results.append(search_result)

                if not results:
                    continue

                # Visit each site
                query_content: List[str] = []
                for idx, result in enumerate(results[:self.deep_mode_max_sites]):
                    url = result.get("url", "")
                    site_content = await self.site_visitor.visit(url)

                    if site_content:
                        # Summarize this site for this query
                        site_summary = await summarization_agent.summarize(q, site_content)
                        query_content.append(f"Site {idx + 1}:\n{site_summary}")

                # Summarize all sites for this query
                if query_content:
                    combined = "\n\n".join(query_content)
                    query_summary = await summarization_agent.summarize(q, combined)
                    merged_results.append(f"Query: {q}\nResult:\n{query_summary}")
                    search_result.extracted_content = query_summary

            # Step 5: Final summarization of all results
            if merged_results:
                combined_all = "\n\n---\n\n".join(merged_results)
                final_summary = await summarization_agent.summarize(query, combined_all)

                # Step 6: Judge if complete
                print("Judging completeness...")
                judge_agent = self._get_judge_agent()
                additional_queries = await judge_agent.evaluate(query, final_summary)

                if additional_queries is None:
                    # Step 7a: Answer is complete
                    print("Judge: Answer is complete")
                    return ResearchResult(
                        queries_used=all_queries,
                        search_results=all_search_results,
                        summary=final_summary,
                        mode="deep"
                    )

                # Step 7b: Need more queries
                print(f"Judge: Need more info, new queries: {additional_queries}")
                current_queries = additional_queries[:2]
            else:
                current_queries = []

        # Return what we have
        return ResearchResult(
            queries_used=all_queries,
            search_results=all_search_results,
            summary=final_summary,
            mode="deep"
        )

    async def _deep_simple_path(self, query: str) -> ResearchResult:
        """
        Simple path for deep mode when query is not complex.
        Same as lite but returns as deep mode.

        Args:
            query: Search query

        Returns:
            ResearchResult in deep mode format
        """
        # Search
        results = await self._cached_search(query, self.max_results_per_query)
        search_result = SearchResult(query=query, results=results)

        if not results:
            return ResearchResult(
                queries_used=[query],
                search_results=[search_result],
                mode="deep"
            )

        # Visit sites and collect content
        accumulated: List[str] = []
        summarization_agent = self._get_summarization_agent()

        for idx, result in enumerate(results[:self.deep_mode_max_sites]):
            url = result.get("url", "")
            site_content = await self.site_visitor.visit(url)

            if site_content:
                accumulated.append(f"Site {idx + 1}:\n{site_content}")

        # Summarize
        summary = None
        if accumulated:
            combined = "\n\n".join(accumulated)
            summary = await summarization_agent.summarize(query, combined)
            search_result.extracted_content = summary

        return ResearchResult(
            queries_used=[query],
            search_results=[search_result],
            summary=summary,
            mode="deep"
        )

    async def research_batch(
        self,
        queries: List[str],
        mode: Optional[str] = None
    ) -> List[ResearchResult]:
        """
        Research multiple queries in parallel.

        Args:
            queries: List of research queries
            mode: Override mode for all queries

        Returns:
            List of ResearchResults
        """
        tasks = [self.research(q, mode) for q in queries]
        return await asyncio.gather(*tasks)

    def format_for_context(
        self,
        result: ResearchResult,
        max_length: int = 5000
    ) -> str:
        """
        Format research result as context for LLM.

        Args:
            result: Research result to format
            max_length: Maximum output length

        Returns:
            Formatted string for LLM context
        """
        parts: List[str] = []

        if result.summary:
            parts.append("## Research Summary")
            parts.append(result.summary)
            parts.append("")

        parts.append("## Search Results")
        for sr in result.search_results:
            parts.append(f"\n### Query: {sr.query}")
            for idx, r in enumerate(sr.results[:3], 1):
                title = r.get("title", "")
                content = r.get("content", "")
                parts.append(f"{idx}. **{title}**")
                if content:
                    parts.append(f"   {content[:300]}...")

        output = "\n".join(parts)

        if len(output) > max_length:
            output = output[:max_length] + "\n\n[Truncated...]"

        return output

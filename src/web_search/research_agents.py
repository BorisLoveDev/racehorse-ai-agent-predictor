"""
LLM research agents for deep search mode.
Uses OpenRouter API via LangChain for consistency with existing agents.
"""

from typing import List, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ..config.settings import get_settings


def _get_llm(temperature: float = 0.3, max_tokens: int = 1000) -> ChatOpenAI:
    """Get LLM instance for research agents using existing settings."""
    settings = get_settings()
    api_key = settings.api_keys.openrouter_api_key.get_secret_value()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    # Use a fast, cheap model for research sub-tasks (same as research agent)
    return ChatOpenAI(
        model="google/gemini-3-flash-preview",
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1"
    )


class ComplexityAgent:
    """Determines if a query requires multiple searches."""

    def __init__(self):
        self.llm = _get_llm(temperature=0.1, max_tokens=10)

    async def analyze(self, query: str) -> bool:
        """
        Analyze if query is complex and needs decomposition.

        Args:
            query: Search query

        Returns:
            True if complex (needs multiple searches), False if simple
        """
        prompt = (
            "Analyze the prompt. Decide whether the question requires "
            "multiple queries or just one. If multiple, return only 1; "
            f"otherwise, return 0. Prompt: {query}"
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return "1" in response.content
        except Exception as e:
            print(f"ComplexityAgent error: {e}")
            return False  # Default to simple on error


class DecomposeAgent:
    """Breaks complex queries into multiple sub-queries."""

    def __init__(self):
        self.llm = _get_llm(temperature=0.5, max_tokens=500)

    async def decompose(self, query: str, num_queries: int = 2) -> List[str]:
        """
        Decompose a complex query into simpler sub-queries.

        Args:
            query: Complex search query
            num_queries: Number of sub-queries to generate

        Returns:
            List of sub-queries
        """
        prompt = f"""Analyze the user prompt and break it down into {num_queries} diverse search queries.
Each simple query must target a different sub-part of the original prompt to ensure maximum information coverage.

Example:
User Prompt: "How to build a local RAG system with Llama 3?"
Search Queries:
Llama 3 hardware requirements and quantization for local inference
Best vector databases and embedding models for RAG

Prompt: {query}

Return only queries separated by newlines, no numbering."""

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            # Parse response into list of queries
            queries = [
                q.strip() for q in response.content.strip().split("\n")
                if q.strip() and not q.strip().startswith(("-", "*", "•"))
            ]
            return queries[:num_queries] if queries else [query]
        except Exception as e:
            print(f"DecomposeAgent error: {e}")
            return [query]


class RelevanceAgent:
    """Filters search results by relevance."""

    def __init__(self):
        self.llm = _get_llm(temperature=0.1, max_tokens=10)

    async def is_relevant(self, query: str, title: str) -> bool:
        """
        Check if a search result is relevant to the query.

        Args:
            query: Original search query
            title: Title of search result

        Returns:
            True if relevant, False otherwise
        """
        prompt = (
            f"Act as a relevance filter. Compare the search result title "
            f"with the user query. Query: {query} Title: {title}. "
            "If relevant, return only 1, else 0"
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return "1" in response.content
        except Exception as e:
            print(f"RelevanceAgent error: {e}")
            return True  # Include by default on error


class ExtractionAgent:
    """Extracts relevant information from page content."""

    def __init__(self):
        self.llm = _get_llm(temperature=0.3, max_tokens=2000)

    async def extract(self, query: str, content: str) -> str:
        """
        Extract relevant information from page content.

        Args:
            query: Original search query
            content: Page content to extract from

        Returns:
            Extracted relevant information
        """
        # Truncate content to avoid token limits
        max_content = 8000
        if len(content) > max_content:
            content = content[:max_content] + "..."

        prompt = (
            f"Extract information relevant to the query: {query}.\n\n"
            f"Text for extraction: {content}\n\n"
            "Return only the relevant extracted information, concisely."
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            print(f"ExtractionAgent error: {e}")
            return content[:1000]  # Return truncated content on error


class SummarizationAgent:
    """Synthesizes multiple search results into a report."""

    def __init__(self):
        self.llm = _get_llm(temperature=0.5, max_tokens=3000)

    async def summarize(self, query: str, results: str) -> str:
        """
        Summarize multiple search results into a coherent report.

        Args:
            query: Original search query
            results: Combined search results text

        Returns:
            Summarized report
        """
        prompt = f"""Create a single detailed report based on multiple search snippets.

User Query: {query}

Results to process: {results}

If a result is empty or not available, just skip it.

Provide a comprehensive summary addressing the user's query.

Final Report:"""

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            print(f"SummarizationAgent error: {e}")
            return results[:2000]  # Return truncated results on error


class JudgeAgent:
    """Evaluates if research results are complete or need more queries."""

    def __init__(self):
        self.llm = _get_llm(temperature=0.3, max_tokens=500)

    async def evaluate(
        self,
        query: str,
        current_result: str
    ) -> Optional[List[str]]:
        """
        Evaluate if current results are sufficient or need more research.

        Args:
            query: Original search query
            current_result: Current research results

        Returns:
            None if results are sufficient, list of new queries otherwise
        """
        prompt = (
            "Analyze the result and decide whether additional queries "
            "need to be made. If so, return only the new queries, "
            "separated by newlines; otherwise, return 0. "
            f"Prompt: {query}. Answer: {current_result[:3000]}"
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            content = response.content.strip()

            if "0" in content and len(content) < 10:
                return None  # Results are sufficient

            # Parse additional queries
            queries = [
                q.strip() for q in content.split("\n")
                if q.strip() and q.strip() != "0"
            ]
            return queries if queries else None

        except Exception as e:
            print(f"JudgeAgent error: {e}")
            return None  # Assume complete on error

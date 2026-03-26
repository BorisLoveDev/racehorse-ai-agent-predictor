"""
Search tools for the horse racing research pipeline.

Two async @tool functions for web search:
  - searxng_search: queries the SearXNG instance via httpx (SEARCH-01)
  - online_model_search: queries an OpenRouter online model with web grounding (SEARCH-02)

Provider selection is controlled by ResearchSettings.provider (D-05):
  - 'searxng': use searxng_search
  - 'online': use online_model_search (default)

Per D-01: online model is primary, SearXNG is fallback. Both tools share the
same @tool interface so the sub-agent can call either interchangeably.
"""

import httpx
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from services.stake.settings import get_stake_settings


@tool
async def searxng_search(query: str) -> str:
    """Search for horse racing information using SearXNG. Use for: runner form, trainer stats, track conditions, expert tips."""
    settings = get_stake_settings()
    url = settings.research.searxng_url

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                url,
                params={
                    "q": query,
                    "format": "json",
                    "language": "en",
                    "categories": "general,news",
                },
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        if not results:
            return "No results found."

        formatted = []
        for result in results[:5]:
            title = result.get("title", "")
            content = result.get("content", "")
            formatted.append(f"[{title}] {content[:300]}")

        return "\n\n".join(formatted)

    except Exception as e:
        return f"Search error: {str(e)}"


@tool
async def online_model_search(query: str) -> str:
    """Search for horse racing information using an AI model with web access. Use for: runner form, trainer stats, expert opinions."""
    settings = get_stake_settings()

    try:
        llm = ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=settings.openrouter_api_key,
            model=settings.research.model,
            temperature=0.0,
            extra_body={"plugins": [{"id": "web"}]},
        )
        response = await llm.ainvoke([HumanMessage(content=query)])
        return str(response.content)

    except Exception as e:
        return f"Online search error: {str(e)}"

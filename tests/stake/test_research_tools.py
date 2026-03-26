"""
Unit tests for research pipeline tools (SEARCH-01, SEARCH-02).

Tests:
  - searxng_search formats results correctly from mocked httpx response
  - searxng_search returns "No results found." on empty results
  - searxng_search returns error message on httpx exception
  - online_model_search returns error message on LLM exception
  - online_model_search returns response content on success
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.stake.pipeline.research.tools import online_model_search, searxng_search


@pytest.mark.asyncio
async def test_searxng_search_formats_results():
    """searxng_search should format top 5 results as [title] content."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"title": "Thunder Bolt Form", "content": "Won last 3 races at Flemington"},
            {"title": "Trainer Stats", "content": "Trainer J. Smith has 45% win rate this season"},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("services.stake.pipeline.research.tools.httpx.AsyncClient", return_value=mock_client):
        result = await searxng_search.ainvoke({"query": "Thunder Bolt horse racing form"})

    assert "[Thunder Bolt Form]" in result
    assert "Won last 3 races at Flemington" in result
    assert "[Trainer Stats]" in result
    assert "Trainer J. Smith has 45% win rate" in result
    assert "\n\n" in result


@pytest.mark.asyncio
async def test_searxng_search_empty_results():
    """searxng_search should return 'No results found.' when results list is empty."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("services.stake.pipeline.research.tools.httpx.AsyncClient", return_value=mock_client):
        result = await searxng_search.ainvoke({"query": "unknown horse"})

    assert result == "No results found."


@pytest.mark.asyncio
async def test_searxng_search_handles_httpx_exception():
    """searxng_search should return 'Search error: ...' on httpx exceptions."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=Exception("Connection timeout"))

    with patch("services.stake.pipeline.research.tools.httpx.AsyncClient", return_value=mock_client):
        result = await searxng_search.ainvoke({"query": "some query"})

    assert result.startswith("Search error:")
    assert "Connection timeout" in result


@pytest.mark.asyncio
async def test_online_model_search_handles_exception():
    """online_model_search should return 'Online search error: ...' on LLM exceptions."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("API rate limit exceeded"))

    with patch("services.stake.pipeline.research.tools.ChatOpenAI", return_value=mock_llm):
        result = await online_model_search.ainvoke({"query": "Thunder Bolt racing form"})

    assert result.startswith("Online search error:")
    assert "API rate limit exceeded" in result


@pytest.mark.asyncio
async def test_online_model_search_returns_content():
    """online_model_search should return the LLM response content as string."""
    mock_response = MagicMock()
    mock_response.content = "Thunder Bolt won 3 of last 5 starts at Flemington."

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("services.stake.pipeline.research.tools.ChatOpenAI", return_value=mock_llm):
        result = await online_model_search.ainvoke({"query": "Thunder Bolt racing form"})

    assert result == "Thunder Bolt won 3 of last 5 starts at Flemington."


@pytest.mark.asyncio
async def test_searxng_search_truncates_long_content():
    """searxng_search should truncate content to 300 chars per result."""
    long_content = "A" * 500
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "results": [{"title": "Test", "content": long_content}]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("services.stake.pipeline.research.tools.httpx.AsyncClient", return_value=mock_client):
        result = await searxng_search.ainvoke({"query": "test query"})

    # Content should be truncated to 300 chars within brackets
    # Format: "[Test] {content[:300]}"
    # So total should be len("[Test] ") + 300 = 307
    assert len(result) <= 310  # title + space + 300 chars + small buffer
    assert result.startswith("[Test]")

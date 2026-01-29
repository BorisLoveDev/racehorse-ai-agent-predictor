"""
SearXNG search client.
Uses the JSON API for reliable, structured results.
"""

import asyncio
import os
from typing import Dict, List, Optional

import aiohttp


class SearXNGSearch:
    """Async SearXNG search client using JSON API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize SearXNG search client.

        Args:
            base_url: SearXNG instance URL (default: from env or localhost)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("SEARXNG_URL", "http://localhost:8080")
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        categories: str = "general",
        language: str = "en"
    ) -> List[Dict[str, str]]:
        """
        Perform a search query and return results.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            categories: Search categories (general, images, news, etc.)
            language: Search language

        Returns:
            List of search results with keys: title, url, content
        """
        if not query or not query.strip():
            return []

        params = {
            "q": query,
            "format": "json",
            "categories": categories,
            "language": language,
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                url = f"{self.base_url}/search"
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()

                    results = []
                    for item in data.get("results", [])[:max_results]:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "content": item.get("content", ""),
                        })
                    return results

        except asyncio.TimeoutError:
            print(f"SearXNG search timeout for query: {query}")
            return []
        except aiohttp.ClientError as e:
            print(f"SearXNG search error for '{query}': {e}")
            return []
        except Exception as e:
            print(f"Unexpected error in SearXNG search: {e}")
            return []

    async def search_batch(
        self,
        queries: List[str],
        max_results_per_query: int = 3,
        max_concurrent: int = 5
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Perform multiple search queries concurrently.

        Args:
            queries: List of search queries
            max_results_per_query: Max results per query
            max_concurrent: Maximum concurrent requests

        Returns:
            Dict mapping query to list of results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_with_limit(query: str) -> tuple[str, List[Dict[str, str]]]:
            async with semaphore:
                results = await self.search(query, max_results_per_query)
                await asyncio.sleep(0.2)  # Small delay between requests
                return query, results

        tasks = [search_with_limit(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            query: res if isinstance(res, list) else []
            for query, res in results
            if not isinstance(res, Exception)
        }

    async def health_check(self) -> bool:
        """Check if SearXNG is available."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/healthz") as response:
                    return response.status == 200
        except Exception:
            return False

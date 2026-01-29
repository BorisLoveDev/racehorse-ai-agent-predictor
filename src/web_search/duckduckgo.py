"""
Async DuckDuckGo search implementation.
Uses the HTML endpoint for reliable results.
"""

import asyncio
from typing import Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup


class DuckDuckGoSearch:
    """Async DuckDuckGo search client using HTML endpoint."""

    BASE_URL = "https://html.duckduckgo.com/html/"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, timeout: int = 30):
        """
        Initialize DuckDuckGo search client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def search(
        self,
        query: str,
        max_results: int = 5
    ) -> List[Dict[str, str]]:
        """
        Perform a search query and return results.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            List of search results with keys: title, url, content
        """
        if not query or not query.strip():
            return []

        try:
            async with aiohttp.ClientSession(
                headers=self.DEFAULT_HEADERS,
                timeout=self.timeout
            ) as session:
                # DuckDuckGo expects POST for HTML endpoint
                data = {"q": query}
                async with session.post(self.BASE_URL, data=data) as response:
                    response.raise_for_status()
                    html = await response.text()
                    return self._parse_results(html, max_results)

        except asyncio.TimeoutError:
            print(f"DuckDuckGo search timeout for query: {query}")
            return []
        except aiohttp.ClientError as e:
            print(f"DuckDuckGo search error for '{query}': {e}")
            return []
        except Exception as e:
            print(f"Unexpected error in DuckDuckGo search: {e}")
            return []

    def _parse_results(self, html: str, max_results: int) -> List[Dict[str, str]]:
        """Parse search results from HTML response."""
        soup = BeautifulSoup(html, "lxml")
        results = []

        for result_div in soup.select(".result")[:max_results]:
            # Extract title and URL
            title_elem = result_div.select_one(".result__a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            url = title_elem.get("href", "")

            # Extract snippet/content
            snippet_elem = result_div.select_one(".result__snippet")
            content = ""
            if snippet_elem:
                content = snippet_elem.get_text(strip=True)

            if title and url:
                results.append({
                    "title": title,
                    "url": url,
                    "content": content
                })

        return results

    async def search_batch(
        self,
        queries: List[str],
        max_results_per_query: int = 3,
        max_concurrent: int = 3
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
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.5)
                return query, results

        tasks = [search_with_limit(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            query: res if isinstance(res, list) else []
            for query, res in results
            if not isinstance(res, Exception)
        }

"""
Async site visitor for extracting content from web pages.
Handles DuckDuckGo redirect URLs and extracts clean text.
"""

import asyncio
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import aiohttp
from bs4 import BeautifulSoup


class SiteVisitor:
    """Async web page content extractor."""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, timeout: int = 15, max_content_length: int = 50000):
        """
        Initialize site visitor.

        Args:
            timeout: Request timeout in seconds
            max_content_length: Maximum content length to process
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_content_length = max_content_length

    def _resolve_duckduckgo_url(self, url: str) -> str:
        """
        Resolve DuckDuckGo redirect URLs to actual URLs.

        DuckDuckGo uses tracking redirects like:
        //duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com
        """
        # Handle protocol-relative URLs
        if url.startswith("//"):
            url = "https:" + url

        # Handle DuckDuckGo redirect URLs
        if "duckduckgo.com/l/" in url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "uddg" in params:
                url = unquote(params["uddg"][0])

        return url

    async def visit(self, url: str) -> Optional[str]:
        """
        Visit a URL and extract clean text content.

        Args:
            url: URL to visit (may be DuckDuckGo redirect)

        Returns:
            Clean text content or None if extraction failed
        """
        # Resolve DuckDuckGo redirects
        actual_url = self._resolve_duckduckgo_url(url)

        try:
            async with aiohttp.ClientSession(
                headers=self.DEFAULT_HEADERS,
                timeout=self.timeout
            ) as session:
                async with session.get(actual_url) as response:
                    response.raise_for_status()

                    # Check content type
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" not in content_type.lower():
                        return None

                    # Read with size limit
                    html = await response.text()
                    if len(html) > self.max_content_length:
                        html = html[:self.max_content_length]

                    return self._extract_text(html)

        except asyncio.TimeoutError:
            print(f"Timeout visiting {actual_url}")
            return None
        except aiohttp.ClientError as e:
            print(f"Error visiting {actual_url}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error visiting {actual_url}: {e}")
            return None

    def _extract_text(self, html: str) -> str:
        """Extract clean text from HTML, removing scripts and styles."""
        soup = BeautifulSoup(html, "lxml")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Get text with spacing
        text = soup.get_text(separator=" ", strip=True)

        # Clean up excessive whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return text

    async def visit_batch(
        self,
        urls: list[str],
        max_concurrent: int = 3
    ) -> dict[str, Optional[str]]:
        """
        Visit multiple URLs concurrently.

        Args:
            urls: List of URLs to visit
            max_concurrent: Maximum concurrent requests

        Returns:
            Dict mapping URL to extracted text (or None on failure)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def visit_with_limit(url: str) -> tuple[str, Optional[str]]:
            async with semaphore:
                content = await self.visit(url)
                await asyncio.sleep(0.3)  # Rate limiting
                return url, content

        tasks = [visit_with_limit(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            url: content if isinstance(content, (str, type(None))) else None
            for url, content in results
            if not isinstance(content, Exception)
        }

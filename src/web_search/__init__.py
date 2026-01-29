"""
Web search module with SearXNG integration and two research modes.

Basic mode: Single-pass search with optional relevance filtering
Deep mode: Multi-agent research loop with decomposition and synthesis
"""

from .duckduckgo import DuckDuckGoSearch
from .searxng import SearXNGSearch
from .site_visitor import SiteVisitor
from .search_cache import SearchCache
from .research_modes import WebResearcher

__all__ = [
    "DuckDuckGoSearch",
    "SearXNGSearch",
    "SiteVisitor",
    "SearchCache",
    "WebResearcher",
]

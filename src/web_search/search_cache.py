"""
In-memory search result cache with TTL support.
Avoids duplicate searches for the same queries.
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CacheEntry:
    """Cache entry with value and expiration time."""
    value: Any
    expires_at: float


@dataclass
class SearchCache:
    """
    In-memory cache for search results with TTL.

    Thread-safe for concurrent async access (uses asyncio.Lock).
    """

    ttl_seconds: int = 300  # 5 minutes default
    max_entries: int = 1000
    _cache: Dict[str, CacheEntry] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _make_key(self, query: str, max_results: int) -> str:
        """Generate cache key from query and parameters."""
        key_str = f"{query.lower().strip()}:{max_results}"
        return hashlib.md5(key_str.encode()).hexdigest()

    async def get(
        self,
        query: str,
        max_results: int
    ) -> Optional[List[Dict[str, str]]]:
        """
        Get cached search results if available and not expired (thread-safe).

        Args:
            query: Search query
            max_results: Max results parameter

        Returns:
            Cached results or None if not found/expired
        """
        async with self._lock:
            key = self._make_key(query, max_results)
            entry = self._cache.get(key)

            if entry is None:
                return None

            if time.time() > entry.expires_at:
                # Expired, remove and return None
                del self._cache[key]
                return None

            return entry.value

    async def set(
        self,
        query: str,
        max_results: int,
        results: List[Dict[str, str]]
    ) -> None:
        """
        Cache search results (thread-safe).

        Args:
            query: Search query
            max_results: Max results parameter
            results: Search results to cache
        """
        async with self._lock:
            # Evict old entries if at capacity
            if len(self._cache) >= self.max_entries:
                self._evict_expired()

            key = self._make_key(query, max_results)
            self._cache[key] = CacheEntry(
                value=results,
                expires_at=time.time() + self.ttl_seconds
            )

    def _evict_expired(self) -> None:
        """Remove expired entries from cache."""
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry.expires_at
        ]
        for key in expired_keys:
            del self._cache[key]

        # If still at capacity, remove oldest entries
        if len(self._cache) >= self.max_entries:
            # Sort by expiration time, remove oldest 10%
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1].expires_at
            )
            entries_to_remove = max(1, len(sorted_entries) // 10)
            for key, _ in sorted_entries[:entries_to_remove]:
                del self._cache[key]

    async def clear(self) -> None:
        """Clear all cached entries (thread-safe)."""
        async with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return len(self._cache)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = time.time()
        valid_count = sum(
            1 for entry in self._cache.values()
            if now <= entry.expires_at
        )
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_count,
            "expired_entries": len(self._cache) - valid_count,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
        }

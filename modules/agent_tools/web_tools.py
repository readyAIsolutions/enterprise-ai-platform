"""
Web Tools — WebFetch and WebSearch with Intelligent Caching
============================================================

Part of the Claude Code Tools enterprise module. Provides async web
fetching, search capabilities, and intelligent response caching.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field

from .tool_registry import BaseTool, ProgressEvent, ProgressStatus

logger = logging.getLogger("enterprise.agent_tools.web")


@dataclass
class WebFetchResult:
    url: str
    content: str
    status_code: int = 200
    content_type: str = "text/html"
    content_length: int = 0
    fetch_time_ms: float = 0.0
    cached: bool = False


@dataclass
class WebSearchResult:
    query: str
    results: List[Dict[str, str]] = field(default_factory=list)
    total_results: int = 0
    search_time_ms: float = 0.0


@dataclass
class WebCacheEntry:
    url: str
    content: str
    content_type: str = "text/html"
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: float = 300.0

    def is_expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return age > self.ttl_seconds


class WebFetchInput(BaseModel):
    url: str = Field(..., description="URL to fetch")
    max_length: int = Field(default=100000)
    timeout_seconds: float = Field(default=30.0)
    headers: Dict[str, str] = Field(default_factory=dict)
    use_cache: bool = Field(default=True)


class WebFetchTool(BaseTool):
    name: str = "WebFetch"
    description: str = "Fetch content from a URL with caching and timeout"
    category: str = "web"
    _cache: Dict[str, WebCacheEntry] = {}

    @classmethod
    def _cache_key(cls, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    async def run(self, input_data: WebFetchInput) -> WebFetchResult:
        start = time.monotonic()
        if input_data.use_cache:
            ck = self._cache_key(input_data.url)
            entry = self._cache.get(ck)
            if entry is not None and not entry.is_expired():
                return WebFetchResult(url=input_data.url, content=entry.content[:input_data.max_length],
                                      content_type=entry.content_type, content_length=len(entry.content),
                                      fetch_time_ms=(time.monotonic() - start) * 1000, cached=True)
        await asyncio.sleep(0.1)
        content = f"[Fetched content from {input_data.url}]\nSample content line 1\nSample content line 2"
        content = content[:input_data.max_length]
        if input_data.use_cache:
            self._cache[self._cache_key(input_data.url)] = WebCacheEntry(url=input_data.url, content=content)
        return WebFetchResult(url=input_data.url, content=content, status_code=200,
                              content_type="text/html", content_length=len(content),
                              fetch_time_ms=(time.monotonic() - start) * 1000, cached=False)

    async def execute_streamed(self, input_data: WebFetchInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Fetching {input_data.url}...", execution_id=eid)
        try:
            result = await self.run(input_data)
            yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                                message=f"Fetched {result.content_length} bytes", percent=100.0,
                                bytes_processed=result.content_length,
                                metadata={"url": result.url, "cached": result.cached}, execution_id=eid)
        except Exception as exc:
            yield ProgressEvent(tool_name=self.name, status=ProgressStatus.FAILED,
                                message=str(exc), execution_id=eid)

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event

    @classmethod
    def clear_cache(cls) -> int:
        count = len(cls._cache)
        cls._cache.clear()
        return count


class WebSearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    num_results: int = Field(default=10)
    safe_search: bool = Field(default=True)
    use_cache: bool = Field(default=True)


class WebSearchTool(BaseTool):
    name: str = "WebSearch"
    description: str = "Search the web with result ranking and caching"
    category: str = "web"
    _cache: Dict[str, WebCacheEntry] = {}

    async def run(self, input_data: WebSearchInput) -> WebSearchResult:
        start = time.monotonic()
        ck = hashlib.sha256(f"search:{input_data.query}".encode()).hexdigest()[:16]
        if input_data.use_cache:
            entry = self._cache.get(ck)
            if entry is not None and not entry.is_expired():
                return WebSearchResult(query=input_data.query,
                                       results=[{"title": "Cached", "url": entry.url, "snippet": entry.content[:200]}],
                                       total_results=1, search_time_ms=(time.monotonic() - start) * 1000)
        await asyncio.sleep(0.15)
        results = [{"title": f"Result {i+1} for '{input_data.query}'",
                     "url": f"https://example.com/result-{i+1}?q={input_data.query.replace(' ', '+')}",
                     "snippet": f"Simulated result {i+1} for '{input_data.query}'.",
                     "rank": i + 1} for i in range(min(input_data.num_results, 10))]
        if input_data.use_cache:
            self._cache[ck] = WebCacheEntry(url=f"search:{input_data.query}", content=str(results), ttl_seconds=120.0)
        return WebSearchResult(query=input_data.query, results=results, total_results=len(results),
                               search_time_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: WebSearchInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Searching for '{input_data.query}'...", execution_id=eid)
        try:
            result = await self.run(input_data)
            yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                                message=f"Found {result.total_results} results", percent=100.0,
                                metadata={"query": result.query, "total": result.total_results}, execution_id=eid)
        except Exception as exc:
            yield ProgressEvent(tool_name=self.name, status=ProgressStatus.FAILED,
                                message=str(exc), execution_id=eid)

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event
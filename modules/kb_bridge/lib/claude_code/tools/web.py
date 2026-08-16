#!/usr/bin/env python3
"""
WebFetchTool / WebSearchTool
=============================
Fetch web content and search the web.
Mirrors: src/tools/WebFetchTool/, WebSearchTool/
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from typing import Any

import aiohttp
from pydantic import BaseModel, Field

from lib.claude_code.tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    ToolProgressData,
    CanUseToolFn,
    ToolProgress,
)


# ─── WebFetchTool ────────────────────────────────────────────────────────────

class WebFetchInput(BaseModel):
    url: str = Field(..., description="URL to fetch")
    method: str = Field(default="GET", description="HTTP method")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    body: str | None = Field(default=None, description="Request body")
    timeout: int = Field(default=30000, description="Timeout in milliseconds")
    max_size: int = Field(default=1048576, description="Max response size in bytes")


class WebFetchOutput(BaseModel):
    url: str
    status: int
    content: str
    content_type: str
    headers: dict[str, str]
    truncated: bool = False


class WebFetchProgress(ToolProgressData):
    stage: str = "fetching"


class WebFetchTool(Tool[WebFetchInput, WebFetchOutput, WebFetchProgress]):
    name = "web_fetch"
    aliases = ["fetch", "http_get"]
    search_hint = "Fetch content from a URL"
    input_schema = WebFetchInput
    output_schema = WebFetchOutput
    progress_schema = WebFetchProgress

    async def call(
        self,
        args: WebFetchInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[WebFetchOutput]:
        if on_progress:
            on_progress(ToolProgress(
                tool_use_id="",
                data=WebFetchProgress(stage="connecting")
            ))

        timeout = aiohttp.ClientTimeout(total=args.timeout / 1000)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    args.method,
                    args.url,
                    headers=args.headers,
                    data=args.body,
                ) as response:
                    if on_progress:
                        on_progress(ToolProgress(
                            tool_use_id="",
                            data=WebFetchProgress(stage="reading")
                        ))

                    content = await response.text()
                    truncated = len(content) > args.max_size
                    if truncated:
                        content = content[:args.max_size]

                    return ToolResult(
                        data=WebFetchOutput(
                            url=str(response.url),
                            status=response.status,
                            content=content,
                            content_type=response.headers.get("Content-Type", ""),
                            headers=dict(response.headers),
                            truncated=truncated,
                        )
                    )

        except asyncio.TimeoutError:
            return ToolResult(
                data=WebFetchOutput(
                    url=args.url,
                    status=0,
                    content="Request timed out",
                    content_type="",
                    headers={},
                )
            )
        except Exception as e:
            return ToolResult(
                data=WebFetchOutput(
                    url=args.url,
                    status=0,
                    content=f"Error: {str(e)}",
                    content_type="",
                    headers={},
                )
            )


# ─── WebSearchTool ───────────────────────────────────────────────────────────

class WebSearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    engine: str = Field(default="duckduckgo", description="Search engine: duckduckgo, google, bing")
    max_results: int = Field(default=10, description="Maximum results")
    safe_search: bool = Field(default=True, description="Enable safe search")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchOutput(BaseModel):
    query: str
    results: list[SearchResult]
    count: int


class WebSearchTool(Tool[WebSearchInput, WebSearchOutput, ToolProgressData]):
    name = "web_search"
    aliases = ["search", "google"]
    search_hint = "Search the web for information"
    input_schema = WebSearchInput
    output_schema = WebSearchOutput

    async def call(
        self,
        args: WebSearchInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[WebSearchOutput]:
        # Use DuckDuckGo HTML scraping (no API key needed)
        query_encoded = urllib.parse.quote_plus(args.query)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    html = await response.text()

            # Parse results (simplified)
            results = []
            # Pattern for DuckDuckGo results
            pattern = r'<a class="result__snippet" href="([^"]+)">([^<]+)</a>'
            matches = re.findall(pattern, html)

            for href, title in matches[:args.max_results]:
                results.append(SearchResult(
                    title=title.strip(),
                    url=href,
                    snippet=title[:200],  # Simplified
                ))

            return ToolResult(
                data=WebSearchOutput(
                    query=args.query,
                    results=results,
                    count=len(results),
                )
            )

        except Exception as e:
            return ToolResult(
                data=WebSearchOutput(
                    query=args.query,
                    results=[],
                    count=0,
                )
            )


# ─── Exports ─────────────────────────────────────────────────────────────────

web_fetch_tool = WebFetchTool()
web_search_tool = WebSearchTool()

__all__ = [
    "WebFetchTool", "WebFetchInput", "WebFetchOutput", "web_fetch_tool",
    "WebSearchTool", "WebSearchInput", "WebSearchOutput", "SearchResult", "web_search_tool",
]
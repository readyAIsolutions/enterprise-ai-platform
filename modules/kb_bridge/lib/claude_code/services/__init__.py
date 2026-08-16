#!/usr/bin/env python3
"""
Services — API Client, MCP, LSP, Compact, Plugins
===================================================
Mirrors: src/services/api/, mcp/, lsp/, compact/, plugins/
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator

import aiohttp
from pydantic import BaseModel, Field


# ─── API Service (Anthropic/OpenRouter) ─────────────────────────────────────


class APIConfig(BaseModel):
    """API configuration."""
    provider: str = "openrouter"  # anthropic, openrouter, free-router
    api_key: str | None = None
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "free-router"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60000


class MessageParam(BaseModel):
    role: str  # user, assistant, system
    content: str | list[dict[str, Any]]


class CompletionRequest(BaseModel):
    model: str
    messages: list[MessageParam]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


class CompletionResponse(BaseModel):
    id: str
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] | None = None


class APIClient:
    """Anthropic/OpenRouter API client with streaming support."""

    def __init__(self, config: APIConfig | None = None):
        self.config = config or APIConfig()
        self.session: aiohttp.ClientSession | None = None
        self._usage = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.config.api_key or os.getenv('OPENROUTER_API_KEY', '')}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/hunter/eni-swarm",
                "X-Title": "ENI Swarm",
            }
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Non-streaming completion."""
        if not self.session:
            await self.__aenter__()

        url = f"{self.config.base_url}/chat/completions"
        payload = request.model_dump(exclude_none=True)
        payload.setdefault("model", self.config.model)

        async with self.session.post(url, json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(f"API Error {resp.status}: {data}")

            # Track usage
            if "usage" in data:
                u = data["usage"]
                self._usage["input_tokens"] += u.get("prompt_tokens", 0)
                self._usage["output_tokens"] += u.get("completion_tokens", 0)
                # Rough cost estimate
                self._usage["total_cost"] += (u.get("prompt_tokens", 0) * 0.15 + u.get("completion_tokens", 0) * 0.6) / 1_000_000

            return CompletionResponse(**data)

    async def stream_complete(self, request: CompletionRequest) -> AsyncGenerator[dict[str, Any], None]:
        """Streaming completion."""
        if not self.session:
            await self.__aenter__()

        request.stream = True
        url = f"{self.config.base_url}/chat/completions"
        payload = request.model_dump(exclude_none=True)
        payload.setdefault("model", self.config.model)

        async with self.session.post(url, json=payload) as resp:
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        pass

    def get_usage(self) -> dict[str, Any]:
        return self._usage.copy()


# ─── MCP Service ────────────────────────────────────────────────────────────


@dataclass
class MCPServerConfig:
    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class MCPClient:
    """Model Context Protocol client."""

    def __init__(self):
        self.servers: dict[str, MCPServerConfig] = {}
        self.processes: dict[str, subprocess.Popen] = {}

    def add_server(self, config: MCPServerConfig) -> None:
        self.servers[config.name] = config

    def remove_server(self, name: str) -> None:
        if name in self.processes:
            self.processes[name].terminate()
            del self.processes[name]
        if name in self.servers:
            del self.servers[name]

    async def start_server(self, name: str) -> bool:
        if name not in self.servers:
            return False
        config = self.servers[name]
        try:
            proc = subprocess.Popen(
                config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, **config.env},
            )
            self.processes[name] = proc
            # Wait for initialization
            await asyncio.sleep(1)
            return True
        except Exception:
            return False

    async def call(self, server: str, method: str, params: dict[str, Any]) -> Any:
        if server not in self.processes:
            await self.start_server(server)
            if server not in self.processes:
                raise Exception(f"Server {server} not running")

        proc = self.processes[server]
        request = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params,
        }

        try:
            proc.stdin.write((json.dumps(request) + "\n").encode())
            proc.stdin.flush()

            # Read response
            line = await asyncio.get_event_loop().run_in_executor(
                None, proc.stdout.readline
            )
            response = json.loads(line.decode())
            if "error" in response:
                raise Exception(response["error"])
            return response.get("result")
        except Exception as e:
            raise Exception(f"MCP call failed: {e}")


# ─── LSP Service ────────────────────────────────────────────────────────────


class LSPClient:
    """Language Server Protocol client."""

    def __init__(self):
        self.servers: dict[str, subprocess.Popen] = {}
        self.capabilities: dict[str, Any] = {}

    async def start_server(self, name: str, command: list[str], root_path: Path) -> bool:
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=root_path,
            )
            self.servers[name] = proc

            # Initialize
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "processId": os.getpid(),
                    "rootUri": root_path.as_uri(),
                    "capabilities": {},
                },
            }
            proc.stdin.write((json.dumps(init_request) + "\n").encode())
            proc.stdin.flush()

            # Read initialize response
            await asyncio.sleep(0.5)
            return True
        except Exception:
            return False

    async def request(self, server: str, method: str, params: dict[str, Any]) -> Any:
        if server not in self.servers:
            raise Exception(f"Server {server} not running")

        proc = self.servers[server]
        request = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params,
        }

        try:
            proc.stdin.write((json.dumps(request) + "\n").encode())
            proc.stdin.flush()

            line = await asyncio.get_event_loop().run_in_executor(
                None, proc.stdout.readline
            )
            response = json.loads(line.decode())
            if "error" in response:
                raise Exception(response["error"])
            return response.get("result")
        except Exception as e:
            raise Exception(f"LSP request failed: {e}")


# ─── Compact Service ────────────────────────────────────────────────────────


class CompactService:
    """Conversation context compression service."""

    def __init__(self):
        self.strategies = {
            "summarize": self._summarize,
            "truncate": self._truncate,
            "auto": self._auto,
        }

    async def compact(
        self,
        messages: list[dict[str, Any]],
        strategy: str = "auto",
        threshold: float = 0.8,
    ) -> list[dict[str, Any]]:
        """Compact messages using the specified strategy."""
        if strategy not in self.strategies:
            strategy = "auto"
        return await self.strategies[strategy](messages, threshold)

    async def _summarize(self, messages: list[dict], threshold: float) -> list[dict]:
        """Summarize older messages."""
        # Keep recent messages, summarize older ones
        keep_recent = 10
        if len(messages) <= keep_recent:
            return messages

        recent = messages[-keep_recent:]
        older = messages[:-keep_recent]

        # Create summary
        summary = f"[Summary of {len(older)} previous messages]"
        return [{"role": "system", "content": summary}] + recent

    async def _truncate(self, messages: list[dict], threshold: float) -> list[dict]:
        """Truncate to fit threshold."""
        # Simple truncation - keep last N messages
        max_messages = 20
        return messages[-max_messages:] if len(messages) > max_messages else messages

    async def _auto(self, messages: list[dict], threshold: float) -> list[dict]:
        """Auto-select strategy based on message count."""
        if len(messages) > 30:
            return await self._summarize(messages, threshold)
        return await self._truncate(messages, threshold)


# ─── Plugin Service ─────────────────────────────────────────────────────────


@dataclass
class PluginConfig:
    name: str
    path: Path
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


class PluginManager:
    """Plugin loading and management."""

    def __init__(self, plugin_dirs: list[Path] | None = None):
        self.plugin_dirs = plugin_dirs or [
            Path.home() / ".claude_code" / "plugins",
            Path.home() / ".config" / "claude_code" / "plugins",
        ]
        self.plugins: dict[str, PluginConfig] = {}
        self.modules: dict[str, Any] = {}

    def discover_plugins(self) -> list[PluginConfig]:
        """Discover available plugins."""
        plugins = []
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
            for plugin_path in plugin_dir.iterdir():
                if plugin_path.is_dir() and (plugin_path / "plugin.py").exists():
                    # Load plugin config
                    config_file = plugin_path / "plugin.json"
                    if config_file.exists():
                        config = json.loads(config_file.read_text())
                        plugins.append(PluginConfig(
                            name=config.get("name", plugin_path.name),
                            path=plugin_path,
                            enabled=config.get("enabled", True),
                            config=config.get("config", {}),
                        ))
        return plugins

    def load_plugin(self, name: str) -> bool:
        """Load a plugin by name."""
        plugins = self.discover_plugins()
        for plugin in plugins:
            if plugin.name == name:
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        name, plugin.path / "plugin.py"
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.modules[name] = module
                    self.plugins[name] = plugin
                    return True
                except Exception as e:
                    print(f"Failed to load plugin {name}: {e}")
                    return False
        return False

    def get_plugin(self, name: str) -> Any:
        return self.modules.get(name)

    def list_plugins(self) -> list[PluginConfig]:
        return list(self.plugins.values())


# ─── Global Instances ───────────────────────────────────────────────────────

_plugin_manager: PluginManager | None = None
_mcp_client: MCPClient | None = None
_lsp_client: LSPClient | None = None
_compact_service: CompactService | None = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def get_mcp_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


def get_lsp_client() -> LSPClient:
    global _lsp_client
    if _lsp_client is None:
        _lsp_client = LSPClient()
    return _lsp_client


def get_compact_service() -> CompactService:
    global _compact_service
    if _compact_service is None:
        _compact_service = CompactService()
    return _compact_service


# ─── Export ─────────────────────────────────────────────────────────────────

__all__ = [
    # API
    "APIConfig", "APIClient", "MessageParam", "CompletionRequest", "CompletionResponse",
    # MCP
    "MCPServerConfig", "MCPClient",
    # LSP
    "LSPClient",
    # Compact
    "CompactService",
    # Plugins
    "PluginConfig", "PluginManager",
    # Globals
    "get_plugin_manager", "get_mcp_client", "get_lsp_client", "get_compact_service",
]
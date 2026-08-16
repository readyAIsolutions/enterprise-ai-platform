#!/usr/bin/env python3
"""
Local Agent Client - Hermes skill to interact with local agent server.
Provides tools for shell commands, file I/O, search, and system info.
"""

import os
import json
import asyncio
import aiohttp
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocalAgentConfig:
    """Configuration for local agent client."""
    base_url: str = "http://127.0.0.1:8765"
    timeout: int = 120
    api_key: Optional[str] = None


class LocalAgentClient:
    """Async client for Hermes Local Agent server."""
    
    def __init__(self, config: LocalAgentConfig = None):
        self.config = config or LocalAgentConfig()
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        self._session = aiohttp.ClientSession(
            base_url=self.config.base_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers
    
    async def _request(self, method: str, path: str, **kwargs) -> Dict:
        if not self._session:
            async with self:
                return await self._request(method, path, **kwargs)
        
        async with self._session.request(method, path, **kwargs) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    # =========================================================================
    # Command Execution
    # =========================================================================
    
    async def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 120,
        background: bool = False
    ) -> Dict[str, Any]:
        """Execute a shell command."""
        payload = {
            "command": command,
            "cwd": cwd,
            "timeout": timeout,
            "background": background
        }
        return await self._request("POST", "/command", json=payload)
    
    async def get_background_result(self, task_id: str) -> Dict[str, Any]:
        """Get result of a background command."""
        return await self._request("GET", f"/command/{task_id}")
    
    # =========================================================================
    # File Operations
    # =========================================================================
    
    async def read_file(self, path: str, offset: int = 0, limit: int = 500) -> Dict[str, Any]:
        """Read file contents."""
        return await self._request("POST", "/file/read", json={"path": path, "offset": offset, "limit": limit})
    
    async def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write file contents."""
        return await self._request("POST", "/file/write", json={"path": path, "content": content})
    
    async def list_files(self, path: str, pattern: Optional[str] = None) -> Dict[str, Any]:
        """List directory contents."""
        payload = {"path": path}
        if pattern:
            payload["pattern"] = pattern
        return await self._request("POST", "/file/list", json=payload)
    
    # =========================================================================
    # Search
    # =========================================================================
    
    async def search(
        self,
        pattern: str,
        path: str = ".",
        file_glob: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Search files using ripgrep (with Python fallback)."""
        payload = {
            "pattern": pattern,
            "path": path,
            "file_glob": file_glob,
            "limit": limit
        }
        return await self._request("POST", "/search", json=payload)
    
    # =========================================================================
    # Task Execution
    # =========================================================================
    
    async def execute_task(
        self,
        prompt: str,
        agent_type: str = "subagent",
        max_turns: int = 20,
        toolsets: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute a complex task via the agent."""
        payload = {
            "prompt": prompt,
            "agent_type": agent_type,
            "max_turns": max_turns,
            "toolsets": toolsets or []
        }
        return await self._request("POST", "/task", json=payload)
    
    # =========================================================================
    # System Info
    # =========================================================================
    
    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information (CPU, memory, disk, platform)."""
        return await self._request("GET", "/system/info")
    
    async def get_workspace_info(self) -> Dict[str, Any]:
        """Get workspace and allowed directories info."""
        return await self._request("GET", "/workspace")
    
    async def health_check(self) -> bool:
        """Check if local agent is healthy."""
        try:
            result = await self._request("GET", "/health")
            return result.get("status") == "ok"
        except Exception:
            return False


# =============================================================================
# Convenience Functions (for sync usage)
# =============================================================================

async def local_shell(
    command: str,
    cwd: str = "/home/hunter",
    timeout: int = 120,
    base_url: str = "http://127.0.0.1:8765"
) -> Dict[str, Any]:
    """Execute shell command via local agent."""
    async with LocalAgentClient(LocalAgentConfig(base_url=base_url)) as client:
        return await client.execute_command(command, cwd=cwd, timeout=timeout)


async def local_read_file(
    path: str,
    offset: int = 0,
    limit: int = 500,
    base_url: str = "http://127.0.0.1:8765"
) -> Dict[str, Any]:
    """Read file via local agent."""
    async with LocalAgentClient(LocalAgentConfig(base_url=base_url)) as client:
        return await client.read_file(path, offset=offset, limit=limit)


async def local_write_file(
    path: str,
    content: str,
    base_url: str = "http://127.0.0.1:8765"
) -> Dict[str, Any]:
    """Write file via local agent."""
    async with LocalAgentClient(LocalAgentConfig(base_url=base_url)) as client:
        return await client.write_file(path, content)


async def local_search(
    pattern: str,
    path: str = ".",
    file_glob: Optional[str] = None,
    limit: int = 10,
    base_url: str = "http://127.0.0.1:8765"
) -> Dict[str, Any]:
    """Search codebase via local agent."""
    async with LocalAgentClient(LocalAgentConfig(base_url=base_url)) as client:
        return await client.search(pattern, path=path, file_glob=file_glob, limit=limit)


async def local_system_info(
    base_url: str = "http://127.0.0.1:8765"
) -> Dict[str, Any]:
    """Get system info via local agent."""
    async with LocalAgentClient(LocalAgentConfig(base_url=base_url)) as client:
        return await client.get_system_info()


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Local Agent CLI Client")
    parser.add_argument("command", choices=["shell", "read", "write", "list", "search", "system", "health"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="Local agent base URL")
    parser.add_argument("--api-key", help="API key for authentication")
    
    # shell
    parser.add_argument("shell_cmd", nargs="?", help="Shell command to execute")
    parser.add_argument("--cwd", default="/home/hunter", help="Working directory")
    parser.add_argument("--timeout", type=int, default=120, help="Command timeout")
    
    # read/write
    parser.add_argument("--path", help="File path")
    parser.add_argument("--content", help="File content to write")
    parser.add_argument("--offset", type=int, default=0, help="Read offset")
    parser.add_argument("--limit", type=int, default=500, help="Read limit")
    
    # search
    parser.add_argument("--pattern", help="Search pattern")
    parser.add_argument("--file-glob", help="File glob pattern")
    
    args = parser.parse_args()
    
    config = LocalAgentConfig(base_url=args.base_url, api_key=args.api_key)
    
    async def run():
        async with LocalAgentClient(config) as client:
            if args.command == "shell":
                if not args.shell_cmd:
                    parser.error("shell command required")
                result = await client.execute_command(args.shell_cmd, cwd=args.cwd, timeout=args.timeout)
                print(json.dumps(result, indent=2))
            
            elif args.command == "read":
                if not args.path:
                    parser.error("path required for read")
                result = await client.read_file(args.path, args.offset, args.limit)
                print(json.dumps(result, indent=2))
            
            elif args.command == "write":
                if not args.path:
                    parser.error("path required for write")
                if args.content is None:
                    parser.error("content required for write")
                result = await client.write_file(args.path, args.content)
                print(json.dumps(result, indent=2))
            
            elif args.command == "list":
                result = await client.list_files(args.path or "/home/hunter", args.file_glob)
                print(json.dumps(result, indent=2))
            
            elif args.command == "search":
                if not args.pattern:
                    parser.error("pattern required for search")
                result = await client.search(args.pattern, args.path or ".", args.file_glob, args.limit)
                print(json.dumps(result, indent=2))
            
            elif args.command == "system":
                result = await client.get_system_info()
                print(json.dumps(result, indent=2))
            
            elif args.command == "health":
                healthy = await client.health_check()
                print(f"Healthy: {healthy}")
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
ENI Swarm ↔ Hermes KB Integration
==================================
Unified client for minis to query MCP and LSP servers.
Provides: context retrieval, code intelligence, operation logging
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.hermes_kb_universal import (
    get_kb,
    store_pattern,
    search_patterns,
    store_operation,
    store_file_op,
    store_config_change,
    store_session,
    update_session_stats,
    end_session,
    sync_skills,
    offload_hermes_memory,
)


# ─── KB Client (Direct DB Access) ───────────────────────────────────────────


class KBClient:
    """Direct client for Hermes Knowledge Base (no MCP/LSP needed for basic ops)."""

    def __init__(self, profile: str | None = None, session_id: str | None = None):
        self.profile = profile or os.environ.get("HERMES_PROFILE", "default")
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.workdir = Path.cwd()

        # Start session tracking
        store_session(self.session_id, self.profile, f"ENI Mini session in {self.workdir}")

    def search(self, query: str, pattern_type: str | None = None, tags: list[str] | None = None, limit: int = 20) -> list[dict]:
        """Search knowledge base."""
        return search_patterns(
            query=query,
            pattern_type=pattern_type,
            profile=self.profile,
            tags=tags,
            limit=limit,
        )

    def get_stats(self) -> dict:
        """Get KB statistics."""
        from lib.hermes_kb_universal import get_stats
        return get_stats()

    def log_tool(self, tool_name: str, input_data: dict, output_data: dict, result: str = "success", error: str | None = None, duration_ms: int | None = None) -> str:
        """Log a tool execution."""
        op_id = store_operation(
            op_type="tool",
            tool_name=tool_name,
            input_data=input_data,
            output_data=output_data,
            result=result,
            error_message=error,
            duration_ms=duration_ms,
            session_id=self.session_id,
            profile=self.profile,
            working_dir=str(self.workdir),
            tags=["tool", tool_name, self.profile],
        )
        update_session_stats(self.session_id, tool_delta=1)
        return op_id

    def log_command(self, command_name: str, input_data: dict, output_data: dict, result: str = "success", error: str | None = None, duration_ms: int | None = None) -> str:
        """Log a command execution."""
        op_id = store_operation(
            op_type="command",
            command_name=command_name,
            input_data=input_data,
            output_data=output_data,
            result=result,
            error_message=error,
            duration_ms=duration_ms,
            session_id=self.session_id,
            profile=self.profile,
            working_dir=str(self.workdir),
            tags=["command", command_name, self.profile],
        )
        update_session_stats(self.session_id, command_delta=1)
        return op_id

    def log_file_read(self, file_path: str, content: str | None = None, line_count: int | None = None) -> int:
        """Log a file read operation."""
        fid = store_file_op(
            file_path=file_path,
            operation="read",
            content=content,
            session_id=self.session_id,
            profile=self.profile,
            line_count=line_count,
        )
        update_session_stats(self.session_id, file_delta=1)
        return fid

    def log_file_write(self, file_path: str, content: str, line_count: int | None = None) -> int:
        """Log a file write operation."""
        fid = store_file_op(
            file_path=file_path,
            operation="write",
            content=content,
            session_id=self.session_id,
            profile=self.profile,
            line_count=line_count,
        )
        update_session_stats(self.session_id, file_delta=1)
        return fid

    def log_file_edit(self, file_path: str, content: str, line_count: int | None = None) -> int:
        """Log a file edit operation."""
        fid = store_file_op(
            file_path=file_path,
            operation="edit",
            content=content,
            session_id=self.session_id,
            profile=self.profile,
            line_count=line_count,
        )
        update_session_stats(self.session_id, file_delta=1)
        return fid

    def log_config_change(self, config_key: str, config_value: str, previous_value: str | None = None, config_type: str = "yaml", file_path: str | None = None) -> int:
        """Log a configuration change."""
        cid = store_config_change(
            profile=self.profile,
            config_key=config_key,
            config_value=config_value,
            config_type=config_type,
            file_path=file_path,
            changed_by="eni_mini",
            previous_value=previous_value,
        )
        return cid

    def store_learning(self, title: str, content: str, pattern_type: str = "tool_result", tags: list[str] | None = None) -> int | None:
        """Store a learning/pattern from this session."""
        return store_pattern(
            pattern_type=pattern_type,
            title=title,
            content=content,
            profile=self.profile,
            session=self.session_id,
            tags=tags or ["eni_mini", self.profile, pattern_type],
        )

    def end_session(self, summary: str | None = None):
        """End the session."""
        end_session(self.session_id, summary or f"Completed session in {self.workdir}")


# ─── MCP Client (for external tools) ────────────────────────────────────────


class MCPClient:
    """Client for MCP server (stdio or HTTP)."""

    def __init__(self, server_cmd: list[str] | None = None, http_url: str | None = None):
        self.server_cmd = server_cmd or [sys.executable, "-m", "lib.mcp_kb_server", "--stdio"]
        self.http_url = http_url
        self.process: subprocess.Popen | None = None
        self.request_id = 0

    async def start(self):
        """Start MCP server process."""
        if self.http_url:
            return  # HTTP mode doesn't need local process

        self.process = subprocess.Popen(
            self.server_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Wait for server ready
        await asyncio.sleep(0.5)

        # Initialize
        await self.call("initialize", {})

    async def stop(self):
        """Stop MCP server process."""
        if self.process:
            await self.call("shutdown", {})
            await self.call("exit", {})
            self.process.terminate()
            await asyncio.get_event_loop().run_in_executor(None, self.process.wait)

    async def call(self, method: str, params: dict) -> Any:
        """Call MCP method."""
        self.request_id += 1
        request = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}

        if self.http_url:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.http_url}/mcp", json=request) as resp:
                    result = await resp.json()
                    return result.get("result")
        else:
            # Stdio mode
            if not self.process:
                await self.start()

            request_line = json.dumps(request) + "\n"
            self.process.stdin.write(request_line)
            self.process.stdin.flush()

            # Read response
            response_line = await asyncio.get_event_loop().run_in_executor(None, self.process.stdout.readline)
            response = json.loads(response_line.strip())
            return response.get("result")

    async def search(self, query: str, **kwargs) -> list[dict]:
        """Search via MCP."""
        result = await self.call("tools/call", {
            "name": "kb_search",
            "arguments": {"query": query, **kwargs}
        })
        return json.loads(result["content"][0]["text"])

    async def stats(self) -> dict:
        """Get stats via MCP."""
        result = await self.call("tools/call", {"name": "kb_stats", "arguments": {}})
        return json.loads(result["content"][0]["text"])

    async def list_skills(self, **kwargs) -> list[dict]:
        """List skills via MCP."""
        result = await self.call("tools/call", {"name": "kb_list_skills", "arguments": kwargs})
        return json.loads(result["content"][0]["text"])

    async def get_skill(self, name: str) -> dict:
        """Get skill via MCP."""
        result = await self.call("tools/call", {"name": "kb_get_skill", "arguments": {"name": name}})
        return json.loads(result["content"][0]["text"])

    async def record_operation(self, **kwargs) -> str:
        """Record operation via MCP."""
        result = await self.call("tools/call", {"name": "kb_record_operation", "arguments": kwargs})
        return json.loads(result["content"][0]["text"])

    async def offload_memory(self, profile: str | None = None) -> dict:
        """Offload Hermes memory via MCP."""
        result = await self.call("tools/call", {"name": "kb_offload_hermes_memory", "arguments": {"profile": profile} if profile else {}})
        return json.loads(result["content"][0]["text"])


# ─── LSP Client ─────────────────────────────────────────────────────────────


class LSPClient:
    """Client for LSP server."""

    def __init__(self, server_cmd: list[str] | None = None, workspace_root: Path | None = None):
        self.server_cmd = server_cmd or [sys.executable, "-m", "lib.lsp_kb_server", "--stdio"]
        self.workspace_root = workspace_root or Path.cwd()
        self.process: subprocess.Popen | None = None
        self.request_id = 0
        self.initialized = False

    async def start(self):
        """Start LSP server process."""
        self.process = subprocess.Popen(
            self.server_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        await asyncio.sleep(0.5)

        # Initialize
        result = await self._send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": self.workspace_root.as_uri(),
            "capabilities": {},
        })
        self.initialized = True

        # Send initialized notification
        await self._send_notification("initialized", {})

    async def stop(self):
        """Stop LSP server."""
        if self.process:
            await self._send_request("shutdown", {})
            await self._send_notification("exit", {})
            self.process.terminate()
            await asyncio.get_event_loop().run_in_executor(None, self.process.wait)

    async def _send_request(self, method: str, params: dict) -> Any:
        self.request_id += 1
        request = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
        await self._send(request)
        return await self._read_response()

    async def _send_notification(self, method: str, params: dict):
        request = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._send(request)

    async def _send(self, request: dict):
        if not self.process:
            await self.start()
        body = json.dumps(request)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self.process.stdin.write(header + body)
        self.process.stdin.flush()

    async def _read_response(self) -> Any:
        # Read headers
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, self.process.stdout.readline)
            if not line:
                return None
            if line.startswith("Content-Length:"):
                content_length = int(line.split(":")[1].strip())
                break
        # Read empty line
        await asyncio.get_event_loop().run_in_executor(None, self.process.stdout.readline)
        # Read body
        body = await asyncio.get_event_loop().run_in_executor(None, self.process.stdout.read, content_length)
        response = json.loads(body)
        return response.get("result")

    async def hover(self, file_path: Path, line: int, character: int) -> dict | None:
        """Get hover info."""
        if not self.initialized:
            await self.start()

        # Open document first
        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": file_path.as_uri(),
                "languageId": "python",
                "version": 1,
                "text": file_path.read_text(),
            }
        })

        return await self._send_request("textDocument/hover", {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line, "character": character},
        })

    async def definition(self, file_path: Path, line: int, character: int) -> list[dict] | None:
        """Get definition."""
        if not self.initialized:
            await self.start()

        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": file_path.as_uri(),
                "languageId": "python",
                "version": 1,
                "text": file_path.read_text(),
            }
        })

        return await self._send_request("textDocument/definition", {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line, "character": character},
        })

    async def completion(self, file_path: Path, line: int, character: int) -> dict:
        """Get completions."""
        if not self.initialized:
            await self.start()

        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": file_path.as_uri(),
                "languageId": "python",
                "version": 1,
                "text": file_path.read_text(),
            }
        })

        return await self._send_request("textDocument/completion", {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line, "character": character},
        })

    async def references(self, file_path: Path, line: int, character: int) -> list[dict] | None:
        """Get references."""
        if not self.initialized:
            await self.start()

        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": file_path.as_uri(),
                "languageId": "python",
                "version": 1,
                "text": file_path.read_text(),
            }
        })

        return await self._send_request("textDocument/references", {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        })

    async def document_symbols(self, file_path: Path) -> list[dict]:
        """Get document symbols."""
        if not self.initialized:
            await self.start()

        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": file_path.as_uri(),
                "languageId": "python",
                "version": 1,
                "text": file_path.read_text(),
            }
        })

        return await self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": file_path.as_uri()},
        })

    async def workspace_symbols(self, query: str) -> list[dict]:
        """Get workspace symbols."""
        if not self.initialized:
            await self.start()

        return await self._send_request("workspace/symbol", {"query": query})


# ─── Unified ENI Mini Context ───────────────────────────────────────────────


class ENIMiniContext:
    """
    Unified context for ENI minis.
    Combines KB (direct), MCP, and LSP for maximum capability.
    """

    def __init__(
        self,
        mini_name: str,
        profile: str | None = None,
        use_mcp: bool = False,
        use_lsp: bool = False,
        mcp_http_url: str | None = None,
    ):
        self.mini_name = mini_name
        self.profile = profile or os.environ.get("HERMES_PROFILE", "default")
        self.session_id = f"{mini_name}_{uuid.uuid4().hex[:8]}"

        # Direct KB access (always available)
        self.kb = KBClient(profile=self.profile, session_id=self.session_id)

        # Optional MCP client
        self.mcp: MCPClient | None = None
        if use_mcp:
            if mcp_http_url:
                self.mcp = MCPClient(http_url=mcp_http_url)
            else:
                self.mcp = MCPClient()

        # Optional LSP client
        self.lsp: LSPClient | None = None
        if use_lsp:
            self.lsp = LSPClient(workspace_root=Path.cwd())

    async def start(self):
        """Start MCP/LSP connections."""
        if self.mcp:
            await self.mcp.start()
        if self.lsp:
            await self.lsp.start()

    async def stop(self):
        """Stop MCP/LSP connections."""
        if self.mcp:
            await self.mcp.stop()
        if self.lsp:
            await self.lsp.stop()
        self.kb.end_session(f"ENI Mini {self.mini_name} completed")

    # === Knowledge Retrieval ===

    def recall(self, query: str, **kwargs) -> list[dict]:
        """Recall relevant knowledge from KB."""
        return self.kb.search(query, **kwargs)

    async def recall_mcp(self, query: str, **kwargs) -> list[dict]:
        """Recall via MCP."""
        if not self.mcp:
            return self.recall(query, **kwargs)
        return await self.mcp.search(query, **kwargs)

    def get_skill(self, name: str) -> dict | None:
        """Get skill from KB."""
        from lib.hermes_kb_universal import get_kb
        kb = get_kb()
        with kb.transaction("skills") as conn:
            row = conn.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    async def get_skill_mcp(self, name: str) -> dict:
        """Get skill via MCP."""
        if not self.mcp:
            return self.get_skill(name) or {}
        return await self.mcp.get_skill(name)

    def list_skills(self, category: str | None = None) -> list[dict]:
        """List available skills."""
        from lib.hermes_kb_universal import get_kb
        kb = get_kb()
        with kb.transaction("skills") as conn:
            sql = "SELECT * FROM skills WHERE enabled = 1"
            params = []
            if category:
                sql += " AND category = ?"
                params.append(category)
            sql += " ORDER BY name"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # === Code Intelligence ===

    async def hover(self, file_path: str | Path, line: int, character: int) -> dict | None:
        """Get hover info (LSP + KB fallback)."""
        path = Path(file_path)
        if self.lsp:
            try:
                result = await self.lsp.hover(path, line, character)
                if result:
                    return result
            except Exception:
                pass

        # KB fallback - search for symbol at position
        content = path.read_text()
        lines = content.split("\n")
        if line < len(lines):
            line_text = lines[line]
            import re
            for match in re.finditer(r"\b\w+\b", line_text):
                if match.start() <= character <= match.end():
                    word = match.group()
                    kb_results = self.recall(word, limit=3)
                    if kb_results:
                        return {"contents": [{"kind": "markdown", "value": f"**{word}** (KB)\n" + "\n---\n".join(r["content"][:300] for r in kb_results)}]}
        return None

    async def definition(self, file_path: str | Path, line: int, character: int) -> list[dict] | None:
        """Go to definition."""
        path = Path(file_path)
        if self.lsp:
            try:
                return await self.lsp.definition(path, line, character)
            except Exception:
                pass
        return None

    async def completion(self, file_path: str | Path, line: int, character: int) -> dict:
        """Get completions."""
        path = Path(file_path)
        if self.lsp:
            try:
                return await self.lsp.completion(path, line, character)
            except Exception:
                pass
        return {"items": []}

    async def references(self, file_path: str | Path, line: int, character: int) -> list[dict] | None:
        """Find references."""
        path = Path(file_path)
        if self.lsp:
            try:
                return await self.lsp.references(path, line, character)
            except Exception:
                pass
        return None

    async def workspace_symbol(self, query: str) -> list[dict]:
        """Search workspace symbols."""
        if self.lsp:
            try:
                return await self.lsp.workspace_symbols(query)
            except Exception:
                pass
        # KB fallback
        return self.recall(query, limit=20)

    # === Operation Logging ===

    def log_tool(self, tool_name: str, input_data: dict, output_data: dict, **kwargs) -> str:
        """Log tool execution."""
        return self.kb.log_tool(tool_name, input_data, output_data, **kwargs)

    def log_command(self, command_name: str, input_data: dict, output_data: dict, **kwargs) -> str:
        """Log command execution."""
        return self.kb.log_command(command_name, input_data, output_data, **kwargs)

    def log_file_read(self, file_path: str, content: str | None = None) -> int:
        """Log file read."""
        return self.kb.log_file_read(file_path, content)

    def log_file_write(self, file_path: str, content: str) -> int:
        """Log file write."""
        return self.kb.log_file_write(file_path, content)

    def store_learning(self, title: str, content: str, **kwargs) -> int | None:
        """Store a learning from this session."""
        return self.kb.store_learning(title, content, **kwargs)

    # === Stats ===

    def stats(self) -> dict:
        """Get KB stats."""
        return self.kb.get_stats()


# ─── Convenience Functions ──────────────────────────────────────────────────


def create_mini_context(mini_name: str, **kwargs) -> ENIMiniContext:
    """Create an ENI mini context."""
    return ENIMiniContext(mini_name, **kwargs)


async def run_with_context(mini_name: str, task: str, callback, **kwargs) -> Any:
    """
    Run a task with full KB/MCP/LSP context.
    Automatically starts/stops connections.
    """
    ctx = create_mini_context(mini_name, **kwargs)
    await ctx.start()
    try:
        return await callback(ctx, task)
    finally:
        await ctx.stop()


# ─── CLI ────────────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Mini KB Context")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="Search KB")
    p_search.add_argument("query")
    p_search.add_argument("--mini", default="cli")
    p_search.add_argument("--profile", default="default")

    p_skill = sub.add_parser("skill", help="Get skill")
    p_skill.add_argument("name")
    p_skill.add_argument("--mini", default="cli")

    p_stats = sub.add_parser("stats", help="Show stats")
    p_stats.add_argument("--mini", default="cli")

    p_learn = sub.add_parser("learn", help="Store learning")
    p_learn.add_argument("title")
    p_learn.add_argument("content")
    p_learn.add_argument("--mini", default="cli")
    p_learn.add_argument("--type", default="tool_result")

    args = parser.parse_args()

    ctx = create_mini_context(args.mini, profile=args.profile)

    if args.cmd == "search":
        results = ctx.recall(args.query)
        print(json.dumps(results, indent=2, default=str))

    elif args.cmd == "skill":
        skill = ctx.get_skill(args.name)
        print(json.dumps(skill, indent=2, default=str) if skill else "Not found")

    elif args.cmd == "stats":
        print(json.dumps(ctx.stats(), indent=2))

    elif args.cmd == "learn":
        pid = ctx.store_learning(args.title, args.content, pattern_type=args.type)
        print(f"Stored: {pid}")


if __name__ == "__main__":
    main()
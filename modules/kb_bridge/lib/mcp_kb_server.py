#!/usr/bin/env python3
"""
Hermes Knowledge Base MCP Server
=================================
Exposes the universal KB via Model Context Protocol.
Tools: search, get_pattern, store_pattern, get_stats, list_skills, get_skill, sync_skills, query_operations, session management
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.hermes_kb_universal import (
    get_kb,
    store_pattern,
    search_patterns,
    get_stats,
    sync_skills,
    store_operation,
    store_session,
    update_session_stats,
    end_session,
    store_file_op,
    store_config_change,
    KBManager,
    PATTERNS_DB,
    SKILLS_DB,
    SESSIONS_DB,
    OPERATIONS_DB,
)


# ─── MCP Protocol ───────────────────────────────────────────────────────────


class MCPServer:
    """MCP Server for Hermes Knowledge Base."""

    def __init__(self):
        self.tools = self._define_tools()

    def _define_tools(self) -> list[dict]:
        return [
            {
                "name": "kb_search",
                "description": "Search the Hermes knowledge base for patterns, memories, skills, operations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (text search in title/content)"},
                        "pattern_type": {"type": "string", "description": "Filter by type: memory, user, tool_result, command_result, file_op, git_commit, test_result, skill, config, session"},
                        "profile": {"type": "string", "description": "Filter by Hermes profile"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                        "limit": {"type": "integer", "default": 20, "description": "Max results"},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                    },
                },
            },
            {
                "name": "kb_get_pattern",
                "description": "Get a specific pattern by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern_id": {"type": "integer", "description": "Pattern ID"},
                    },
                    "required": ["pattern_id"],
                },
            },
            {
                "name": "kb_store_pattern",
                "description": "Store a new pattern in the knowledge base",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern_type": {"type": "string", "description": "Type: memory, user, tool_result, command_result, file_op, git_commit, test_result, skill, config, session"},
                        "title": {"type": "string", "description": "Pattern title"},
                        "content": {"type": "string", "description": "Pattern content"},
                        "metadata": {"type": "object", "description": "Additional metadata"},
                        "profile": {"type": "string", "description": "Hermes profile"},
                        "session": {"type": "string", "description": "Session ID"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
                    },
                    "required": ["pattern_type", "title", "content"],
                },
            },
            {
                "name": "kb_stats",
                "description": "Get knowledge base statistics",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "kb_list_skills",
                "description": "List all synced skills",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Filter by category"},
                        "enabled_only": {"type": "boolean", "default": True},
                        "limit": {"type": "integer", "default": 50},
                    },
                },
            },
            {
                "name": "kb_get_skill",
                "description": "Get full skill content by name",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Skill name"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "kb_sync_skills",
                "description": "Sync all Hermes skills to knowledge base",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "kb_query_operations",
                "description": "Query operation history (tool calls, commands, file ops)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Filter by session"},
                        "op_type": {"type": "string", "description": "Filter by type: tool, command, file_read, file_write, file_edit, git, test, skill_load, config_change"},
                        "tool_name": {"type": "string", "description": "Filter by tool name"},
                        "profile": {"type": "string", "description": "Filter by profile"},
                        "limit": {"type": "integer", "default": 50},
                        "offset": {"type": "integer", "default": 0},
                    },
                },
            },
            {
                "name": "kb_session_start",
                "description": "Start tracking a new session",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID (auto-generated if not provided)"},
                        "profile": {"type": "string", "default": "default", "description": "Hermes profile"},
                        "title": {"type": "string", "description": "Session title"},
                        "metadata": {"type": "object", "description": "Additional metadata"},
                    },
                },
            },
            {
                "name": "kb_session_end",
                "description": "End a session with summary",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "summary": {"type": "string", "description": "Session summary"},
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "kb_session_stats",
                "description": "Get session statistics",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID (latest if not provided)"},
                    },
                },
            },
            {
                "name": "kb_offload_hermes_memory",
                "description": "Offload Hermes MEMORY.md and USER.md to KB",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "profile": {"type": "string", "description": "Specific profile (all if not provided)"},
                    },
                },
            },
            {
                "name": "kb_record_operation",
                "description": "Record an operation (tool call, command, file op, etc.)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "op_type": {"type": "string", "description": "Operation type"},
                        "tool_name": {"type": "string", "description": "Tool name (if tool op)"},
                        "command_name": {"type": "string", "description": "Command name (if command op)"},
                        "input_data": {"type": "object", "description": "Input parameters"},
                        "output_data": {"type": "object", "description": "Output/result"},
                        "result": {"type": "string", "enum": ["success", "error", "partial"], "default": "success"},
                        "error_message": {"type": "string", "description": "Error message if failed"},
                        "duration_ms": {"type": "integer", "description": "Duration in milliseconds"},
                        "session_id": {"type": "string", "description": "Session ID"},
                        "profile": {"type": "string", "description": "Hermes profile"},
                        "working_dir": {"type": "string", "description": "Working directory"},
                        "git_commit": {"type": "string", "description": "Git commit hash"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
                    },
                    "required": ["op_type"],
                },
            },
            {
                "name": "kb_record_file_op",
                "description": "Record a file operation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "File path"},
                        "operation": {"type": "string", "enum": ["read", "write", "edit", "delete", "create"]},
                        "content": {"type": "string", "description": "File content (for hash/preview)"},
                        "session_id": {"type": "string", "description": "Session ID"},
                        "profile": {"type": "string", "description": "Hermes profile"},
                        "line_count": {"type": "integer", "description": "Number of lines"},
                        "git_status": {"type": "string", "description": "Git status"},
                    },
                    "required": ["file_path", "operation"],
                },
            },
            {
                "name": "kb_record_config_change",
                "description": "Record a configuration change",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "profile": {"type": "string", "description": "Hermes profile"},
                        "config_key": {"type": "string", "description": "Config key"},
                        "config_value": {"type": "string", "description": "New value"},
                        "config_type": {"type": "string", "default": "yaml", "description": "Config type: yaml, json, env, cli"},
                        "file_path": {"type": "string", "description": "Config file path"},
                        "changed_by": {"type": "string", "default": "user", "description": "Who/what changed it"},
                        "previous_value": {"type": "string", "description": "Previous value"},
                    },
                    "required": ["profile", "config_key"],
                },
            },
        ]

    async def handle_request(self, request: dict) -> dict:
        """Handle MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "hermes-kb", "version": "1.0.0"},
                    },
                }

            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": self.tools},
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await self.call_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]},
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }

    async def call_tool(self, name: str, args: dict) -> Any:
        """Call a tool by name."""
        kb = get_kb()

        if name == "kb_search":
            return search_patterns(
                query=args.get("query"),
                pattern_type=args.get("pattern_type"),
                profile=args.get("profile"),
                tags=args.get("tags"),
                limit=args.get("limit", 20),
                offset=args.get("offset", 0),
            )

        elif name == "kb_get_pattern":
            with kb.transaction("patterns") as conn:
                row = conn.execute("SELECT * FROM patterns WHERE id = ?", (args["pattern_id"],)).fetchone()
                if row:
                    # Update access
                    conn.execute(
                        "UPDATE patterns SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                        (int(time.time()), args["pattern_id"]),
                    )
                    return dict(row)
                return {"error": "Pattern not found"}

        elif name == "kb_store_pattern":
            pid = store_pattern(
                pattern_type=args["pattern_type"],
                title=args["title"],
                content=args["content"],
                metadata=args.get("metadata"),
                profile=args.get("profile"),
                session=args.get("session"),
                tags=args.get("tags"),
            )
            return {"pattern_id": pid, "status": "stored"}

        elif name == "kb_stats":
            return get_stats()

        elif name == "kb_list_skills":
            with kb.transaction("skills") as conn:
                sql = "SELECT * FROM skills WHERE 1=1"
                params = []
                if args.get("category"):
                    sql += " AND category = ?"
                    params.append(args["category"])
                if args.get("enabled_only", True):
                    sql += " AND enabled = 1"
                sql += " ORDER BY last_used DESC NULLS LAST, name LIMIT ?"
                params.append(args.get("limit", 50))
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]

        elif name == "kb_get_skill":
            with kb.transaction("skills") as conn:
                row = conn.execute("SELECT * FROM skills WHERE name = ?", (args["name"],)).fetchone()
                if row:
                    # Update use count
                    conn.execute(
                        "UPDATE skills SET last_used = ?, use_count = use_count + 1 WHERE id = ?",
                        (int(time.time()), row["id"]),
                    )
                    return dict(row)
                return {"error": "Skill not found"}

        elif name == "kb_sync_skills":
            return sync_skills()

        elif name == "kb_query_operations":
            with kb.transaction("operations") as conn:
                sql = "SELECT * FROM operations WHERE 1=1"
                params = []
                if args.get("session_id"):
                    sql += " AND session_id = ?"
                    params.append(args["session_id"])
                if args.get("op_type"):
                    sql += " AND op_type = ?"
                    params.append(args["op_type"])
                if args.get("tool_name"):
                    sql += " AND tool_name = ?"
                    params.append(args["tool_name"])
                if args.get("profile"):
                    sql += " AND profile = ?"
                    params.append(args["profile"])
                sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([args.get("limit", 50), args.get("offset", 0)])
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]

        elif name == "kb_session_start":
            sid = args.get("session_id") or str(uuid.uuid4())[:8]
            store_session(sid, args.get("profile", "default"), args.get("title"), args.get("metadata"))
            return {"session_id": sid, "status": "started"}

        elif name == "kb_session_end":
            end_session(args["session_id"], args.get("summary"))
            return {"session_id": args["session_id"], "status": "ended"}

        elif name == "kb_session_stats":
            with kb.transaction("sessions") as conn:
                if args.get("session_id"):
                    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (args["session_id"],)).fetchone()
                else:
                    row = conn.execute("SELECT * FROM sessions ORDER BY start_time DESC LIMIT 1").fetchone()
                if row:
                    return dict(row)
                return {"error": "No session found"}

        elif name == "kb_offload_hermes_memory":
            return offload_hermes_memory(args.get("profile"))

        elif name == "kb_record_operation":
            op_id = store_operation(
                op_type=args["op_type"],
                tool_name=args.get("tool_name"),
                command_name=args.get("command_name"),
                input_data=args.get("input_data"),
                output_data=args.get("output_data"),
                result=args.get("result", "success"),
                error_message=args.get("error_message"),
                duration_ms=args.get("duration_ms"),
                session_id=args.get("session_id"),
                profile=args.get("profile"),
                working_dir=args.get("working_dir"),
                git_commit=args.get("git_commit"),
                tags=args.get("tags"),
            )
            return {"op_id": op_id, "status": "recorded"}

        elif name == "kb_record_file_op":
            fid = store_file_op(
                file_path=args["file_path"],
                operation=args["operation"],
                content=args.get("content"),
                session_id=args.get("session_id"),
                profile=args.get("profile"),
                line_count=args.get("line_count"),
                git_status=args.get("git_status"),
            )
            return {"file_tracking_id": fid, "status": "recorded"}

        elif name == "kb_record_config_change":
            cid = store_config_change(
                profile=args["profile"],
                config_key=args["config_key"],
                config_value=args.get("config_value"),
                config_type=args.get("config_type", "yaml"),
                file_path=args.get("file_path"),
                changed_by=args.get("changed_by", "user"),
                previous_value=args.get("previous_value"),
            )
            return {"config_snapshot_id": cid, "status": "recorded"}

        else:
            raise ValueError(f"Unknown tool: {name}")


# ─── STDIO Transport ────────────────────────────────────────────────────────


async def run_stdio():
    """Run MCP server over stdio."""
    server = MCPServer()
    print(json.dumps({"jsonrpc": "2.0", "method": "server/started", "params": {}}), flush=True)

    try:
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                response = await server.handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        get_kb().close_all()


# ─── HTTP Transport (for testing) ───────────────────────────────────────────


async def run_http(host: str = "127.0.0.1", port: int = 8765):
    """Run MCP server over HTTP."""
    from aiohttp import web

    server = MCPServer()

    async def handle(request):
        data = await request.json()
        response = await server.handle_request(data)
        return web.json_response(response)

    app = web.Application()
    app.router.add_post("/mcp", handle)
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"MCP server running on http://{host}:{port}/mcp")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        get_kb().close_all()


if __name__ == "__main__":
    import time
    import uuid
    from pathlib import Path

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true", help="Run over stdio")
    parser.add_argument("--http", action="store_true", help="Run over HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.stdio:
        asyncio.run(run_stdio())
    elif args.http:
        asyncio.run(run_http(args.host, args.port))
    else:
        # Default to stdio for MCP clients
        asyncio.run(run_stdio())
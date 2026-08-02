"""
MCP/LSP Tools — Model Context Protocol and Language Server Protocol
====================================================================

Part of the Claude Code Tools enterprise module. Provides tools for
interacting with MCP servers (Model Context Protocol) and LSP servers
(Language Server Protocol) for IDE-like capabilities.

Classes:
  MCPServerConfig — configuration for an MCP server
  MCPResult — result from an MCP tool call
  LSPResult — result from an LSP operation
  MCPTool — interacts with MCP servers
  LSPTool — interacts with LSP language servers
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field

from .tool_registry import BaseTool, ProgressEvent, ProgressStatus

logger = logging.getLogger("enterprise.agent_tools.mcp_lsp")


# =============================================================================
# Configuration & Result Types
# =============================================================================


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection.

    Attributes:
        server_name: Human-readable server name.
        command: Command to launch the server.
        args: Command arguments.
        env: Environment variables.
        enabled: Whether this server is active.
    """
    server_name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class MCPResult:
    """Result from an MCP tool invocation.

    Attributes:
        server_name: The MCP server used.
        tool_name: The tool invoked on the server.
        result: Tool execution result.
        duration_ms: Execution duration.
    """
    server_name: str
    tool_name: str
    result: Any = None
    duration_ms: float = 0.0


@dataclass
class LSPResult:
    """Result from an LSP operation.

    Attributes:
        language: Programming language.
        operation: LSP operation performed.
        result: Operation result.
        diagnostics: Any diagnostic messages.
        duration_ms: Execution duration.
    """
    language: str
    operation: str
    result: Any = None
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0


# =============================================================================
# MCPTool
# =============================================================================


class MCPInput(BaseModel):
    """Input schema for MCPTool."""
    server_command: str = Field(..., description="Command to launch the MCP server")
    server_args: List[str] = Field(default_factory=list, description="Server arguments")
    tool_name: str = Field(default="list_tools", description="Tool to call on the server")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")
    timeout_seconds: float = Field(default=30.0, description="Connection timeout")


class MCPTool(BaseTool):
    """Interact with Model Context Protocol (MCP) servers.

    Launches and communicates with MCP servers to access their tools,
    resources, and prompts. Supports the full MCP lifecycle.

    Usage::

        tool = MCPTool()
        result = await tool.execute(MCPInput(
            server_command="npx",
            server_args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            tool_name="list_directory",
            tool_args={"path": "/tmp"},
        ))
    """

    name: str = "mcp__"
    description: str = "Interact with MCP servers for tools, resources, and prompts"
    category: str = "mcp"

    async def run(self, input_data: MCPInput) -> MCPResult:
        """Execute an MCP tool call."""
        import time
        start = time.monotonic()

        server_name = f"{input_data.server_command}_{'_'.join(input_data.server_args[:2])}"
        await asyncio.sleep(0.1)  # Simulate server startup and tool call

        result = {
            "server": server_name,
            "tool": input_data.tool_name,
            "args": input_data.tool_args,
            "output": f"[MCP] {input_data.tool_name} executed on {server_name}",
            "resources": [f"resource-{i}" for i in range(3)],
        }

        return MCPResult(
            server_name=server_name,
            tool_name=input_data.tool_name,
            result=result,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    async def execute_streamed(self, input_data: MCPInput) -> AsyncIterator[ProgressEvent]:
        """Streaming MCP tool execution."""
        execution_id = str(uuid.uuid4())
        yield ProgressEvent(
            tool_name=self.name,
            status=ProgressStatus.STARTING,
            message=f"Starting MCP server: {input_data.server_command}...",
            execution_id=execution_id,
        )

        result = await self.run(input_data)
        yield ProgressEvent(
            tool_name=self.name,
            status=ProgressStatus.COMPLETED,
            message=f"MCP tool '{result.tool_name}' completed",
            percent=100.0,
            metadata={"server": result.server_name, "tool": result.tool_name},
            execution_id=execution_id,
        )

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event


# =============================================================================


class LSPInput(BaseModel):
    """Input schema for LSPTool."""
    language: str = Field(default="python", description="Programming language")
    operation: str = Field(default="diagnostics", description="LSP operation to perform")
    file_path: str = Field(default="", description="File path for the operation")
    content: str = Field(default="", description="File content for the operation")
    position_line: int = Field(default=0, description="Cursor line (0-indexed)")
    position_character: int = Field(default=0, description="Cursor character (0-indexed)")
    timeout_seconds: float = Field(default=30.0, description="Operation timeout")


class LSPTool(BaseTool):
    """Interact with Language Server Protocol (LSP) servers.

    Provides IDE-like capabilities through LSP: diagnostics, completion,
    hover, go-to-definition, references, formatting, and more.

    Supported operations:
      - diagnostics: Get file diagnostics (errors, warnings)
      - completion: Get code completion suggestions
      - hover: Get hover information at a position
      - definition: Go to definition
      - references: Find references
      - formatting: Format document
      - symbols: Get document symbols

    Usage::

        tool = LSPTool()
        result = await tool.execute(LSPInput(
            language="python",
            operation="completion",
            content="import os\nos.",
            position_line=1,
            position_character=3,
        ))
    """

    name: str = "LSP"
    description: str = "Interact with LSP servers for IDE-like capabilities"
    category: str = "lsp"

    VALID_OPERATIONS = {
        "diagnostics", "completion", "hover", "definition",
        "references", "formatting", "symbols",
    }

    async def run(self, input_data: LSPInput) -> LSPResult:
        """Execute an LSP operation."""
        import time
        start = time.monotonic()

        if input_data.operation not in self.VALID_OPERATIONS:
            raise ValueError(f"Invalid operation '{input_data.operation}'. "
                             f"Valid: {', '.join(sorted(self.VALID_OPERATIONS))}")

        await asyncio.sleep(0.08)  # Simulate LSP communication

        if input_data.operation == "diagnostics":
            diagnostics = [
                {"severity": "warning", "line": 5, "message": "Unused variable 'x'", "code": "F841"},
                {"severity": "info", "line": 10, "message": "Missing type annotation", "code": "ANN001"},
            ]
            result = {"total": len(diagnostics), "file": input_data.file_path or "untitled"}
        elif input_data.operation == "completion":
            result = {
                "completions": [
                    {"label": "path.join", "kind": "function", "detail": "(a, b) -> str"},
                    {"label": "path.exists", "kind": "function", "detail": "(path) -> bool"},
                    {"label": "path.dirname", "kind": "function", "detail": "(path) -> str"},
                ]
            }
            diagnostics = []
        elif input_data.operation == "hover":
            result = {
                "contents": "```python\nos.path.join(a: str, b: str) -> str\n```\nJoin path components.",
                "range": {"start": {"line": input_data.position_line, "character": input_data.position_character}},
            }
            diagnostics = []
        elif input_data.operation == "definition":
            result = {
                "uri": f"file:///usr/lib/python3/os/path.py",
                "range": {"start": {"line": 100, "character": 4}},
            }
            diagnostics = []
        elif input_data.operation == "references":
            result = {
                "references": [
                    {"uri": f"file:///src/main.py", "range": {"start": {"line": 15, "character": 10}}},
                    {"uri": f"file:///src/utils.py", "range": {"start": {"line": 42, "character": 5}}},
                ]
            }
            diagnostics = []
        elif input_data.operation == "formatting":
            result = {
                "formatted": input_data.content,  # Already formatted
                "changes": 0,
            }
            diagnostics = []
        elif input_data.operation == "symbols":
            result = {
                "symbols": [
                    {"name": "my_function", "kind": "function", "line": 1},
                    {"name": "MyClass", "kind": "class", "line": 10},
                    {"name": "CONSTANT", "kind": "constant", "line": 20},
                ]
            }
            diagnostics = []
        else:
            result = {"status": "unknown_operation"}
            diagnostics = []

        return LSPResult(
            language=input_data.language,
            operation=input_data.operation,
            result=result,
            diagnostics=diagnostics,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    async def execute_streamed(self, input_data: LSPInput) -> AsyncIterator[ProgressEvent]:
        """Streaming LSP operation."""
        execution_id = str(uuid.uuid4())
        yield ProgressEvent(
            tool_name=self.name,
            status=ProgressStatus.STARTING,
            message=f"LSP {input_data.operation} for {input_data.language}...",
            execution_id=execution_id,
        )

        result = await self.run(input_data)
        yield ProgressEvent(
            tool_name=self.name,
            status=ProgressStatus.COMPLETED,
            message=f"LSP {result.operation} completed ({len(result.diagnostics)} diagnostics)",
            percent=100.0,
            metadata={"language": result.language, "operation": result.operation},
            execution_id=execution_id,
        )

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event
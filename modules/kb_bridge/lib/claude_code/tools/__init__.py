#!/usr/bin/env python3
"""
Claude Code Tools — Package Exports
====================================
All tool implementations exported for easy registration.
"""

from lib.claude_code.tools.bash import (
    BashTool,
    BashInput,
    BashOutput,
    BashProgress,
    bash_tool,
)

from lib.claude_code.tools.file_read import (
    FileReadTool,
    FileReadInput,
    FileReadOutput,
    file_read_tool,
)

from lib.claude_code.tools.file_write import (
    FileWriteTool,
    FileWriteInput,
    FileWriteOutput,
    file_write_tool,
)

from lib.claude_code.tools.file_edit import (
    FileEditTool,
    FileEditInput,
    FileEditOutput,
    file_edit_tool,
)

from lib.claude_code.tools.glob_tool import (
    GlobTool,
    GlobInput,
    GlobOutput,
    glob_tool,
)

from lib.claude_code.tools.grep_tool import (
    GrepTool,
    GrepInput,
    GrepOutput,
    GrepMatch,
    grep_tool,
)

from lib.claude_code.tools.task import (
    TaskCreateTool,
    TaskCreateInput,
    TaskCreateOutput,
    task_create_tool,
    TaskGetTool,
    TaskGetInput,
    TaskGetOutput,
    task_get_tool,
    TaskUpdateTool,
    TaskUpdateInput,
    TaskUpdateOutput,
    task_update_tool,
    TaskListTool,
    TaskListInput,
    TaskListOutput,
    task_list_tool,
)

from lib.claude_code.tools.agent import (
    AgentTool,
    AgentInput,
    AgentOutput,
    AgentProgress,
    agent_tool,
)

from lib.claude_code.tools.web import (
    WebFetchTool,
    WebFetchInput,
    WebFetchOutput,
    web_fetch_tool,
    WebSearchTool,
    WebSearchInput,
    WebSearchOutput,
    SearchResult,
    web_search_tool,
)

from lib.claude_code.tools.mcp_lsp import (
    MCPTool,
    MCPInput,
    MCPOutput,
    mcp_tool,
    LSPTool,
    LSPInput,
    LSPOutput,
    lsp_tool,
)


# ─── Default Tool Set ────────────────────────────────────────────────────────

DEFAULT_TOOLS = [
    bash_tool,
    file_read_tool,
    file_write_tool,
    file_edit_tool,
    glob_tool,
    grep_tool,
    task_create_tool,
    task_get_tool,
    task_update_tool,
    task_list_tool,
    agent_tool,
    web_fetch_tool,
    web_search_tool,
    mcp_tool,
    lsp_tool,
]

TOOL_MAP = {
    "bash": bash_tool,
    "read": file_read_tool,
    "write": file_write_tool,
    "edit": file_edit_tool,
    "glob": glob_tool,
    "grep": grep_tool,
    "task_create": task_create_tool,
    "task_get": task_get_tool,
    "task_update": task_update_tool,
    "task_list": task_list_tool,
    "agent": agent_tool,
    "web_fetch": web_fetch_tool,
    "web_search": web_search_tool,
    "mcp": mcp_tool,
    "lsp": lsp_tool,
}


def get_default_tools() -> list:
    """Get the default set of tools."""
    return DEFAULT_TOOLS.copy()


def get_tool(name: str):
    """Get a tool by name."""
    return TOOL_MAP.get(name)


def register_tool(name: str, tool) -> None:
    """Register a custom tool."""
    TOOL_MAP[name] = tool


__all__ = [
    "BashTool",
    "BashInput",
    "BashOutput",
    "BashProgress",
    "bash_tool",
    "FileReadTool",
    "FileReadInput",
    "FileReadOutput",
    "file_read_tool",
    "FileWriteTool",
    "FileWriteInput",
    "FileWriteOutput",
    "file_write_tool",
    "FileEditTool",
    "FileEditInput",
    "FileEditOutput",
    "file_edit_tool",
    "GlobTool",
    "GlobInput",
    "GlobOutput",
    "glob_tool",
    "GrepTool",
    "GrepInput",
    "GrepOutput",
    "GrepMatch",
    "grep_tool",
    "TaskCreateTool",
    "TaskCreateInput",
    "TaskCreateOutput",
    "task_create_tool",
    "TaskGetTool",
    "TaskGetInput",
    "TaskGetOutput",
    "task_get_tool",
    "TaskUpdateTool",
    "TaskUpdateInput",
    "TaskUpdateOutput",
    "task_update_tool",
    "TaskListTool",
    "TaskListInput",
    "TaskListOutput",
    "task_list_tool",
    "AgentTool",
    "AgentInput",
    "AgentOutput",
    "AgentProgress",
    "agent_tool",
    "WebFetchTool",
    "WebFetchInput",
    "WebFetchOutput",
    "web_fetch_tool",
    "WebSearchTool",
    "WebSearchInput",
    "WebSearchOutput",
    "SearchResult",
    "web_search_tool",
    "MCPTool",
    "MCPInput",
    "MCPOutput",
    "mcp_tool",
    "LSPTool",
    "LSPInput",
    "LSPOutput",
    "lsp_tool",
    "DEFAULT_TOOLS",
    "TOOL_MAP",
    "get_default_tools",
    "get_tool",
    "register_tool",
]
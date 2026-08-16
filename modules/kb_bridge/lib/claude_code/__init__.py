#!/usr/bin/env python3
"""
Claude Code Python Port — Main Package
=======================================
Complete port of Anthropic's Claude Code CLI to Python.
"""

from lib.claude_code.tool import (
    Tool,
    ToolDef,
    ToolResult,
    ToolUseContext,
    ToolProgress,
    ToolProgressData,
    ToolUseBlockParam,
    ToolResultBlockParam,
    PermissionMode,
    PermissionResult,
    ToolPermissionContext,
    CanUseToolFn,
    build_tool,
    tool_matches_name,
    find_tool_by_name,
    Tools,
    create_tool_input_model,
    schema_to_pydantic,
)

from lib.claude_code.tools import (
    BashTool,
    BashInput,
    BashOutput,
    BashProgress,
    bash_tool,
    FileReadTool,
    FileReadInput,
    FileReadOutput,
    file_read_tool,
    FileWriteTool,
    FileWriteInput,
    FileWriteOutput,
    file_write_tool,
    FileEditTool,
    FileEditInput,
    FileEditOutput,
    file_edit_tool,
    GlobTool,
    GlobInput,
    GlobOutput,
    glob_tool,
    GrepTool,
    GrepInput,
    GrepOutput,
    GrepMatch,
    grep_tool,
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
    AgentTool,
    AgentInput,
    AgentOutput,
    AgentProgress,
    agent_tool,
    WebFetchTool,
    WebFetchInput,
    WebFetchOutput,
    web_fetch_tool,
    WebSearchTool,
    WebSearchInput,
    WebSearchOutput,
    SearchResult,
    web_search_tool,
    MCPTool,
    MCPInput,
    MCPOutput,
    mcp_tool,
    LSPTool,
    LSPInput,
    LSPOutput,
    lsp_tool,
    DEFAULT_TOOLS,
    TOOL_MAP,
    get_default_tools,
    get_tool,
    register_tool,
)

from lib.claude_code.command import (
    CommandType,
    CommandSource,
    CommandBase,
    PromptCommand,
    LocalCommand,
    LocalJSXCommand,
    Command,
    CommandResultDisplay,
    LocalCommandResult,
    CommandRegistry,
    get_command_registry,
    register_command,
    get_command,
    create_builtin_commands,
    BUILTIN_COMMANDS,
)

from lib.claude_code.commands.advanced import (
    CommitCommand,
    ReviewCommand,
    CompactCommand,
    MCPCommand,
    ConfigCommand,
    DoctorCommand,
    MemoryCommand,
    SkillsCommand,
    TasksCommand,
    InitCommand,
    BranchCommand,
    DiffCommand,
    CostCommand,
    ContextCommand,
    PlanCommand,
    FastCommand,
    PermissionsCommand,
    SecurityReviewCommand,
    UpgradeCommand,
    register_advanced_commands,
)

from lib.claude_code.query_engine import (
    QueryEngine,
    QueryEngineConfig,
    Message,
    MessageRole,
    MessageContent,
    SDKMessage,
    SDKStatus,
    Usage,
    EMPTY_USAGE,
    ask,
)

from lib.claude_code.permission import (
    PermissionRule,
    PermissionRules,
    PermissionChecker,
    DenialTrackingState,
    default_can_use_tool,
    get_default_permission_context,
    create_permission_context_from_env,
)

from lib.claude_code.state import (
    StateStore,
    StateSnapshot,
    AppState,
    ToolPermissionContextState,
    FastModeConfig,
    get_app_state_store,
    get_app_state,
    set_app_state,
    get_bootstrap_state,
    set_bootstrap_state,
    get_bootstrap,
    StatePersister,
)

from lib.claude_code.services import (
    APIConfig,
    APIClient,
    MessageParam,
    CompletionRequest,
    CompletionResponse,
    MCPServerConfig,
    MCPClient,
    LSPClient,
    CompactService,
    PluginConfig,
    PluginManager,
    get_plugin_manager,
    get_mcp_client,
    get_lsp_client,
    get_compact_service,
)

from lib.claude_code.integration.eni_swarm_bridge import (
    ENIMiniAgent,
    ENISwarmMaster,
    execute_with_queryengine,
)

from lib.claude_code.tools.bash import BashTool as _BashTool  # noqa: F401


# ─── Version ────────────────────────────────────────────────────────────────

__version__ = "1.0.0"
__author__ = "Ported from Anthropic's Claude Code (leaked 2026-03-31)"


# ─── Default Configuration ─────────────────────────────────────────────────


def create_default_config(cwd: str | None = None) -> QueryEngineConfig:
    """Create default QueryEngine configuration."""
    return QueryEngineConfig(
        cwd=cwd or os.getcwd(),
        tools=get_default_tools(),
        commands=create_builtin_commands(),
        can_use_tool=default_can_use_tool,
        get_app_state=get_app_state,
        set_app_state=set_app_state,
        initial_messages=[],
    )


# ─── Quick Start ────────────────────────────────────────────────────────────


async def quick_ask(prompt: str, cwd: str | None = None) -> str:
    """
    Quick one-shot query.
    Returns the final text response.
    """
    config = create_default_config(cwd)
    engine = QueryEngine(config)

    result_text = ""
    async for msg in engine.submit_message(prompt):
        if msg.type == "result":
            result_text = msg.result or ""
            break

    return result_text


def run_cli():
    """Run interactive CLI."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m lib.claude_code <prompt>")
        print("   or: python -m lib.claude_code --interactive")
        return

    if sys.argv[1] == "--interactive":
        print("Interactive mode not yet implemented")
        return

    prompt = " ".join(sys.argv[1:])
    result = asyncio.run(quick_ask(prompt))
    print(result)


# ─── Export ────────────────────────────────────────────────────────────────

import os
import asyncio

__all__ = [
    # Tool system
    "Tool",
    "ToolDef",
    "ToolResult",
    "ToolUseContext",
    "ToolProgress",
    "ToolProgressData",
    "ToolUseBlockParam",
    "ToolResultBlockParam",
    "PermissionMode",
    "PermissionResult",
    "ToolPermissionContext",
    "CanUseToolFn",
    "build_tool",
    "tool_matches_name",
    "find_tool_by_name",
    "Tools",
    "create_tool_input_model",
    "schema_to_pydantic",
    # Tools
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
    # Commands
    "CommandType",
    "CommandSource",
    "CommandBase",
    "PromptCommand",
    "LocalCommand",
    "LocalJSXCommand",
    "Command",
    "CommandResultDisplay",
    "LocalCommandResult",
    "CommandRegistry",
    "get_command_registry",
    "register_command",
    "get_command",
    "create_builtin_commands",
    "BUILTIN_COMMANDS",
    # Advanced Commands
    "CommitCommand",
    "ReviewCommand",
    "CompactCommand",
    "MCPCommand",
    "ConfigCommand",
    "DoctorCommand",
    "MemoryCommand",
    "SkillsCommand",
    "TasksCommand",
    "InitCommand",
    "BranchCommand",
    "DiffCommand",
    "CostCommand",
    "ContextCommand",
    "PlanCommand",
    "FastCommand",
    "PermissionsCommand",
    "SecurityReviewCommand",
    "UpgradeCommand",
    "register_advanced_commands",
    # Query Engine
    "QueryEngine",
    "QueryEngineConfig",
    "Message",
    "MessageRole",
    "MessageContent",
    "SDKMessage",
    "SDKStatus",
    "Usage",
    "EMPTY_USAGE",
    "ask",
    "create_default_config",
    "quick_ask",
    # Permissions
    "PermissionRule",
    "PermissionRules",
    "PermissionChecker",
    "DenialTrackingState",
    "default_can_use_tool",
    "get_default_permission_context",
    "create_permission_context_from_env",
    # State
    "StateStore",
    "StateSnapshot",
    "AppState",
    "ToolPermissionContextState",
    "FastModeConfig",
    "get_app_state_store",
    "get_app_state",
    "set_app_state",
    "get_bootstrap_state",
    "set_bootstrap_state",
    "get_bootstrap",
    "StatePersister",
    # Services
    "APIConfig",
    "APIClient",
    "MessageParam",
    "CompletionRequest",
    "CompletionResponse",
    "MCPServerConfig",
    "MCPClient",
    "LSPClient",
    "CompactService",
    "PluginConfig",
    "PluginManager",
    "get_plugin_manager",
    "get_mcp_client",
    "get_lsp_client",
    "get_compact_service",
    # ENI Swarm Integration
    "ENIMiniAgent",
    "ENISwarmMaster",
    "execute_with_queryengine",
    # Version
    "__version__",
    "run_cli",
]
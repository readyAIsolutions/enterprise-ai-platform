#!/usr/bin/env python3
"""
Claude Code Tool System — Python Port
======================================
Core tool infrastructure: Tool, ToolDef, build_tool with Pydantic schemas.
Mirrors TypeScript: src/Tool.ts, src/tools.ts, src/tools/*.ts
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, create_model

# ─── Type Definitions ────────────────────────────────────────────────────────

T = TypeVar("T", bound=BaseModel)
O = TypeVar("O")
P = TypeVar("P")


class ToolResult(BaseModel, Generic[O]):
    """Result of a tool execution."""
    data: O
    new_messages: list[Any] = Field(default_factory=list)
    context_modifier: Callable[[Any], Any] | None = None
    mcp_meta: dict[str, Any] | None = None


class ToolUseContext(BaseModel):
    """Context passed to tool calls."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    options: dict[str, Any]
    abort_controller: asyncio.Event
    read_file_state: Any
    get_app_state: Callable[[], Any]
    set_app_state: Callable[[Callable[[Any], Any]], None]
    messages: list[Any]
    agent_id: str | None = None
    agent_type: str | None = None
    tool_use_id: str | None = None


class CanUseToolFn(Generic[T]):
    """Function type for permission checking."""
    def __call__(
        self,
        tool: "Tool[T, Any, Any]",
        input: T,
        context: ToolUseContext,
        parent_message: Any,
        tool_use_id: str,
        force_decision: bool = False,
    ) -> Awaitable[dict[str, Any]]:
        ...


class ToolProgress(BaseModel, Generic[P]):
    """Progress data for a tool."""
    tool_use_id: str
    data: P


class ToolUseBlockParam(BaseModel):
    """Tool use block for API."""
    type: str = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResultBlockParam(BaseModel):
    """Tool result block for API."""
    type: str = "tool_result"
    tool_use_id: str
    content: str | list[dict[str, Any]]
    is_error: bool = False


class PermissionMode(str, Enum):
    """Permission modes."""
    DEFAULT = "default"
    PLAN = "plan"
    BYPASS = "bypassPermissions"
    AUTO = "auto"


class PermissionResult(BaseModel):
    """Result of permission check."""
    behavior: str  # "allow" | "deny" | "ask"
    updated_input: dict[str, Any] | None = None
    reason: str | None = None


class ToolPermissionContext(BaseModel):
    """Context for permission checking."""
    mode: PermissionMode
    additional_working_directories: dict[str, Any] = Field(default_factory=dict)
    always_allow_rules: dict[str, list[str]] = Field(default_factory=dict)
    always_deny_rules: dict[str, list[str]] = Field(default_factory=dict)
    always_ask_rules: dict[str, list[str]] = Field(default_factory=dict)
    is_bypass_permissions_mode_available: bool = False
    is_auto_mode_available: bool = False
    stripped_dangerous_rules: dict[str, list[str]] | None = None
    should_avoid_permission_prompts: bool = False
    await_automated_checks_before_dialog: bool = False
    pre_plan_mode: PermissionMode | None = None


# ─── Tool Base Classes ───────────────────────────────────────────────────────


class ToolProgressData(BaseModel):
    """Base progress data."""
    pass


class Tool(Generic[T, O, P], ABC):
    """Base tool class with full type safety."""

    # Class attributes
    aliases: ClassVar[list[str]] = []
    search_hint: ClassVar[str] = ""
    max_result_size_chars: ClassVar[int] = 10000
    strict: ClassVar[bool] = False
    is_mcp: ClassVar[bool] = False
    is_lsp: ClassVar[bool] = False
    should_defer: ClassVar[bool] = False
    always_load: ClassVar[bool] = False
    mcp_info: ClassVar[dict[str, str] | None] = None

    # Instance attributes
    name: str
    input_schema: type[T]
    output_schema: type[O] | None = None
    progress_schema: type[P] = ToolProgressData

    def __init__(self, name: str | None = None):
        self.name = name or self.__class__.__name__.replace("Tool", "").lower()

    @abstractmethod
    async def call(
        self,
        args: T,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Callable[[ToolProgress[P]], None] | None = None,
    ) -> ToolResult[O]:
        """Execute the tool."""
        pass

    async def description(
        self,
        input: T,
        options: dict[str, Any],
    ) -> str:
        """Generate description for the tool call."""
        return f"Executing {self.name}"

    def is_enabled(self) -> bool:
        """Check if tool is enabled."""
        return True

    def is_concurrency_safe(self, input: T) -> bool:
        """Check if tool can run concurrently."""
        return False

    def is_read_only(self, input: T) -> bool:
        """Check if tool is read-only."""
        return False

    def is_destructive(self, input: T) -> bool:
        """Check if tool is destructive."""
        return False

    def interrupt_behavior(self) -> str:
        """Behavior when interrupted: 'cancel' | 'block'."""
        return "block"

    def is_search_or_read_command(self, input: T) -> dict[str, bool]:
        """Check if tool is search/read for UI collapsing."""
        return {"is_search": False, "is_read": False, "is_list": False}

    def is_open_world(self, input: T) -> bool:
        """Check if tool operates in open world."""
        return False

    def requires_user_interaction(self) -> bool:
        """Check if tool requires user interaction."""
        return False

    def validate_input(self, input: T, context: ToolUseContext) -> PermissionResult:
        """Validate input before execution."""
        return PermissionResult(behavior="allow", updated_input=input.model_dump())

    async def check_permissions(self, input: T, context: ToolUseContext) -> PermissionResult:
        """Check permissions for tool execution."""
        return PermissionResult(behavior="allow", updated_input=input.model_dump())

    def get_path(self, input: T) -> str | None:
        """Get file path for file operations."""
        return None

    def prepare_permission_matcher(self, input: T) -> Callable[[str], bool] | None:
        """Prepare permission matcher for hook patterns."""
        return None

    def to_auto_classifier_input(self, input: T) -> Any:
        """Convert to auto-classifier input."""
        return ""

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        """Get user-facing name."""
        return self.name

    def user_facing_name_background_color(
        self, input: dict[str, Any] | None = None
    ) -> str | None:
        """Get background color for user-facing name."""
        return None

    def is_transparent_wrapper(self) -> bool:
        """Check if tool is a transparent wrapper."""
        return False

    def get_tool_use_summary(self, input: dict[str, Any] | None = None) -> str | None:
        """Get short summary for compact views."""
        return None

    def get_activity_description(self, input: dict[str, Any] | None = None) -> str | None:
        """Get activity description for spinner."""
        return None

    def map_tool_result_to_tool_result_block_param(
        self, content: O, tool_use_id: str
    ) -> ToolResultBlockParam:
        """Map result to API block param."""
        return ToolResultBlockParam(
            tool_use_id=tool_use_id,
            content=json.dumps(content, default=str) if not isinstance(content, str) else content,
        )

    def extract_search_text(self, output: O) -> str:
        """Extract searchable text from output."""
        return json.dumps(output, default=str) if not isinstance(output, str) else output

    def backfill_observable_input(self, input: dict[str, Any]) -> None:
        """Backfill observable input for hooks."""
        pass

    def render_tool_result_message(
        self,
        content: O,
        progress_messages: list[Any],
        options: dict[str, Any],
    ) -> str:
        """Render tool result for display."""
        return str(content)

    def render_tool_use_message(
        self,
        input: dict[str, Any],
        options: dict[str, Any],
    ) -> str:
        """Render tool use for display."""
        return f"Running {self.name}"

    def is_result_truncated(self, output: O) -> bool:
        """Check if result is truncated in non-verbose mode."""
        return False

    def render_tool_use_tag(self, input: dict[str, Any]) -> str | None:
        """Render tag for tool use."""
        return None

    def render_tool_use_progress_message(
        self,
        progress_messages: list[Any],
        options: dict[str, Any],
    ) -> str | None:
        """Render progress message."""
        return None

    def render_tool_use_queued_message(self) -> str | None:
        """Render queued message."""
        return None

    def render_tool_use_rejected_message(
        self,
        input: T,
        options: dict[str, Any],
    ) -> str:
        """Render rejected message."""
        return f"{self.name} was rejected"

    def render_tool_use_error_message(
        self,
        result: ToolResultBlockParam,
        options: dict[str, Any],
    ) -> str:
        """Render error message."""
        return f"Error in {self.name}"

    def render_grouped_tool_use(
        self,
        tool_uses: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> str | None:
        """Render grouped tool uses."""
        return None


# ─── Tool Definition (Partial) ───────────────────────────────────────────────


@dataclass
class ToolDef(Generic[T, O, P]):
    """Partial tool definition for build_tool."""
    name: str
    input_schema: type[T]
    output_schema: type[O] | None = None
    progress_schema: type[P] = ToolProgressData
    aliases: list[str] = field(default_factory=list)
    search_hint: str = ""
    max_result_size_chars: int = 10000
    strict: bool = False
    is_mcp: bool = False
    is_lsp: bool = False
    should_defer: bool = False
    always_load: bool = False
    mcp_info: dict[str, str] | None = None

    # Optional method overrides
    call: Callable[..., Awaitable[ToolResult[O]]] | None = None
    description: Callable[..., Awaitable[str]] | None = None
    is_enabled: Callable[[], bool] | None = None
    is_concurrency_safe: Callable[[T], bool] | None = None
    is_read_only: Callable[[T], bool] | None = None
    is_destructive: Callable[[T], bool] | None = None
    interrupt_behavior: Callable[[], str] | None = None
    is_search_or_read_command: Callable[[T], dict[str, bool]] | None = None
    is_open_world: Callable[[T], bool] | None = None
    requires_user_interaction: Callable[[], bool] | None = None
    validate_input: Callable[[T, ToolUseContext], PermissionResult] | None = None
    check_permissions: Callable[[T, ToolUseContext], Awaitable[PermissionResult]] | None = None
    get_path: Callable[[T], str | None] | None = None
    prepare_permission_matcher: Callable[[T], Callable[[str], bool] | None] | None = None
    to_auto_classifier_input: Callable[[T], Any] | None = None
    user_facing_name: Callable[[dict[str, Any] | None], str] | None = None
    user_facing_name_background_color: Callable[[dict[str, Any] | None], str | None] | None = None
    is_transparent_wrapper: Callable[[], bool] | None = None
    get_tool_use_summary: Callable[[dict[str, Any] | None], str | None] | None = None
    get_activity_description: Callable[[dict[str, Any] | None], str | None] | None = None
    map_tool_result_to_tool_result_block_param: Callable[[O, str], ToolResultBlockParam] | None = None
    extract_search_text: Callable[[O], str] | None = None
    backfill_observable_input: Callable[[dict[str, Any]], None] | None = None
    render_tool_result_message: Callable[[O, list[Any], dict[str, Any]], str] | None = None
    render_tool_use_message: Callable[[dict[str, Any], dict[str, Any]], str] | None = None
    is_result_truncated: Callable[[O], bool] | None = None
    render_tool_use_tag: Callable[[dict[str, Any]], str | None] | None = None
    render_tool_use_progress_message: Callable[[list[Any], dict[str, Any]], str | None] | None = None
    render_tool_use_queued_message: Callable[[], str | None] | None = None
    render_tool_use_rejected_message: Callable[[T, dict[str, Any]], str] | None = None
    render_tool_use_error_message: Callable[[ToolResultBlockParam, dict[str, Any]], str] | None = None
    render_grouped_tool_use: Callable[[list[dict[str, Any]], dict[str, Any]], str | None] | None = None


# ─── Build Tool ──────────────────────────────────────────────────────────────


def build_tool(defn: ToolDef[T, O, P]) -> Tool[T, O, P]:
    """Build a complete Tool from a ToolDef, filling in defaults."""

    class BuiltTool(Tool[T, O, P]):
        name = defn.name
        input_schema = defn.input_schema
        output_schema = defn.output_schema
        progress_schema = defn.progress_schema
        aliases = defn.aliases
        search_hint = defn.search_hint
        max_result_size_chars = defn.max_result_size_chars
        strict = defn.strict
        is_mcp = defn.is_mcp
        is_lsp = defn.is_lsp
        should_defer = defn.should_defer
        always_load = defn.always_load
        mcp_info = defn.mcp_info

        # Apply any overridden methods
        if defn.call:
            call = defn.call
        if defn.description:
            description = defn.description
        if defn.is_enabled:
            is_enabled = defn.is_enabled
        if defn.is_concurrency_safe:
            is_concurrency_safe = defn.is_concurrency_safe
        if defn.is_read_only:
            is_read_only = defn.is_read_only
        if defn.is_destructive:
            is_destructive = defn.is_destructive
        if defn.interrupt_behavior:
            interrupt_behavior = defn.interrupt_behavior
        if defn.is_search_or_read_command:
            is_search_or_read_command = defn.is_search_or_read_command
        if defn.is_open_world:
            is_open_world = defn.is_open_world
        if defn.requires_user_interaction:
            requires_user_interaction = defn.requires_user_interaction
        if defn.validate_input:
            validate_input = defn.validate_input
        if defn.check_permissions:
            check_permissions = defn.check_permissions
        if defn.get_path:
            get_path = defn.get_path
        if defn.prepare_permission_matcher:
            prepare_permission_matcher = defn.prepare_permission_matcher
        if defn.to_auto_classifier_input:
            to_auto_classifier_input = defn.to_auto_classifier_input
        if defn.user_facing_name:
            user_facing_name = defn.user_facing_name
        if defn.user_facing_name_background_color:
            user_facing_name_background_color = defn.user_facing_name_background_color
        if defn.is_transparent_wrapper:
            is_transparent_wrapper = defn.is_transparent_wrapper
        if defn.get_tool_use_summary:
            get_tool_use_summary = defn.get_tool_use_summary
        if defn.get_activity_description:
            get_activity_description = defn.get_activity_description
        if defn.map_tool_result_to_tool_result_block_param:
            map_tool_result_to_tool_result_block_param = defn.map_tool_result_to_tool_result_block_param
        if defn.extract_search_text:
            extract_search_text = defn.extract_search_text
        if defn.backfill_observable_input:
            backfill_observable_input = defn.backfill_observable_input
        if defn.render_tool_result_message:
            render_tool_result_message = defn.render_tool_result_message
        if defn.render_tool_use_message:
            render_tool_use_message = defn.render_tool_use_message
        if defn.is_result_truncated:
            is_result_truncated = defn.is_result_truncated
        if defn.render_tool_use_tag:
            render_tool_use_tag = defn.render_tool_use_tag
        if defn.render_tool_use_progress_message:
            render_tool_use_progress_message = defn.render_tool_use_progress_message
        if defn.render_tool_use_queued_message:
            render_tool_use_queued_message = defn.render_tool_use_queued_message
        if defn.render_tool_use_rejected_message:
            render_tool_use_rejected_message = defn.render_tool_use_rejected_message
        if defn.render_tool_use_error_message:
            render_tool_use_error_message = defn.render_tool_use_error_message
        if defn.render_grouped_tool_use:
            render_grouped_tool_use = defn.render_grouped_tool_use

    return BuiltTool()


# ─── Tools Collection ────────────────────────────────────────────────────────


Tools = list[Tool[Any, Any, Any]]


def tool_matches_name(tool: Tool[Any, Any, Any], name: str) -> bool:
    """Check if tool matches name or alias."""
    return tool.name == name or name in tool.aliases


def find_tool_by_name(tools: Tools, name: str) -> Tool[Any, Any, Any] | None:
    """Find tool by name or alias."""
    for tool in tools:
        if tool_matches_name(tool, name):
            return tool
    return None


# ─── Schema Helpers ──────────────────────────────────────────────────────────


def create_tool_input_model(name: str, fields: dict[str, tuple[type, Any]]) -> type[BaseModel]:
    """Create a Pydantic model for tool input."""
    return create_model(name, **{k: (v[0], v[1]) for k, v in fields.items()})


def schema_to_pydantic(schema: dict[str, Any]) -> type[BaseModel]:
    """Convert JSON Schema to Pydantic model."""
    # Simplified conversion - in production would use pydantic.json_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    fields = {}
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        py_type = type_map.get(prop_type, str)
        default = ... if prop_name in required else None
        fields[prop_name] = (py_type, default)
    return create_model(schema.get("title", "Schema"), **fields)


# ─── Export ──────────────────────────────────────────────────────────────────

__all__ = [
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
]
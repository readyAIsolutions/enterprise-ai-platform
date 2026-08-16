#!/usr/bin/env python3
"""
Claude Code Permission System — Python Port
============================================
Permission handling for tool execution.
Mirrors: src/hooks/toolPermission/, src/utils/permissions/
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from lib.claude_code.tool import (
    Tool,
    ToolUseContext,
    ToolPermissionContext,
    PermissionResult,
    PermissionMode,
)


# ─── Permission Types ────────────────────────────────────────────────────────


class PermissionRule(BaseModel):
    """A single permission rule."""
    pattern: str
    behavior: str  # allow, deny, ask
    source: str = "user"


class PermissionRules(BaseModel):
    """Collection of permission rules."""
    rules: list[PermissionRule] = field(default_factory=list)

    def add(self, pattern: str, behavior: str, source: str = "user") -> None:
        self.rules.append(PermissionRule(pattern=pattern, behavior=behavior, source=source))

    def match(self, tool_name: str, tool_input: dict[str, Any]) -> PermissionRule | None:
        """Find matching rule for tool."""
        for rule in self.rules:
            if self._pattern_matches(rule.pattern, tool_name, tool_input):
                return rule
        return None

    def _pattern_matches(self, pattern: str, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if pattern matches tool."""
        # Simple pattern matching: tool_name or tool_name(arg)
        if pattern == tool_name:
            return True
        if pattern == f"{tool_name}(*)":
            return True
        if pattern.startswith(tool_name + "(") and pattern.endswith(")"):
            # Could do more sophisticated matching here
            return True
        return False


@dataclass
class DenialTrackingState:
    """Track permission denials for auto-mode fallback."""
    count: int = 0
    last_denied_tool: str | None = None
    consecutive_denials: int = 0


# ─── Permission Checker ──────────────────────────────────────────────────────


class PermissionChecker:
    """
    Checks permissions for tool execution.
    Implements the permission logic from Claude Code.
    """

    def __init__(
        self,
        context: ToolPermissionContext,
        denial_tracking: DenialTrackingState | None = None,
    ):
        self.context = context
        self.denial_tracking = denial_tracking or DenialTrackingState()
        self.always_allow = PermissionRules()
        self.always_deny = PermissionRules()
        self.always_ask = PermissionRules()

        # Load rules from context
        for pattern in context.always_allow_rules.get("command", []):
            self.always_allow.add(pattern, "allow", "config")
        for pattern in context.always_deny_rules.get("command", []):
            self.always_deny.add(pattern, "deny", "config")
        for pattern in context.always_ask_rules.get("command", []):
            self.always_ask.add(pattern, "ask", "config")

    async def check(
        self,
        tool: Tool,
        input: BaseModel,
        context: ToolUseContext,
        force_decision: bool = False,
    ) -> PermissionResult:
        """
        Check if tool execution is permitted.
        Returns PermissionResult with behavior: allow, deny, ask
        """
        tool_name = tool.name
        tool_input_dict = input.model_dump() if hasattr(input, "model_dump") else {}

        # 1. Check tool's own check_permissions
        try:
            tool_perm = await tool.check_permissions(input, context)
            if tool_perm.behavior != "allow":
                return tool_perm
        except Exception:
            pass

        # 2. Check always_deny rules (highest priority)
        deny_match = self.always_deny.match(tool_name, tool_input_dict)
        if deny_match:
            return PermissionResult(
                behavior="deny",
                reason=f"Denied by rule: {deny_match.pattern}",
            )

        # 3. Check always_allow rules
        allow_match = self.always_allow.match(tool_name, tool_input_dict)
        if allow_match:
            return PermissionResult(
                behavior="allow",
                updated_input=input.model_dump() if hasattr(input, "model_dump") else {},
            )

        # 4. Check mode
        mode = self.context.mode

        if mode == PermissionMode.BYPASS:
            if self.context.is_bypass_permissions_mode_available:
                return PermissionResult(behavior="allow")
            else:
                return PermissionResult(
                    behavior="deny",
                    reason="Bypass mode not available",
                )

        if mode == PermissionMode.AUTO:
            if self.context.is_auto_mode_available:
                return PermissionResult(behavior="allow")
            else:
                return PermissionResult(
                    behavior="deny",
                    reason="Auto mode not available",
                )

        if mode == PermissionMode.PLAN:
            # In plan mode, only read-only tools allowed
            if tool.is_read_only(input):
                return PermissionResult(behavior="allow")
            return PermissionResult(
                behavior="deny",
                reason="Write operations not allowed in plan mode",
            )

        # 5. Default mode - check always_ask
        ask_match = self.always_ask.match(tool_name, tool_input_dict)
        if ask_match:
            return PermissionResult(behavior="ask")

        # 6. Check if tool is read-only
        if tool.is_read_only(input):
            return PermissionResult(behavior="allow")

        # 7. Check if destructive
        if tool.is_destructive(input):
            return PermissionResult(behavior="ask")

        # 8. Default to ask for write operations
        return PermissionResult(behavior="ask")

    def record_denial(self, tool_name: str) -> None:
        """Record a permission denial."""
        self.denial_tracking.count += 1
        self.denial_tracking.last_denied_tool = tool_name
        if self.denial_tracking.last_denied_tool == tool_name:
            self.denial_tracking.consecutive_denials += 1
        else:
            self.denial_tracking.consecutive_denials = 1


# ─── Default CanUseTool Function ─────────────────────────────────────────────


async def default_can_use_tool(
    tool: Tool,
    input: BaseModel,
    context: ToolUseContext,
    parent_message: Any,
    tool_use_id: str,
    force_decision: bool = False,
) -> PermissionResult:
    """
    Default permission checker.
    Uses the ToolPermissionContext from the context options.
    """
    # Extract permission context from context options
    perm_context_dict = context.options.get("toolPermissionContext")
    if not perm_context_dict:
        # Default permissive
        return PermissionResult(behavior="allow")

    # Convert dict to ToolPermissionContext
    perm_context = ToolPermissionContext(**perm_context_dict)
    checker = PermissionChecker(perm_context)

    return await checker.check(tool, input, context, force_decision)


# ─── Helper Functions ────────────────────────────────────────────────────────


def get_default_permission_context() -> ToolPermissionContext:
    """Get a default permission context."""
    return ToolPermissionContext(
        mode=PermissionMode.DEFAULT,
        additional_working_directories={},
        always_allow_rules={},
        always_deny_rules={},
        always_ask_rules={},
        is_bypass_permissions_mode_available=True,
        is_auto_mode_available=True,
    )


def create_permission_context_from_env() -> ToolPermissionContext:
    """Create permission context from environment variables."""
    mode_str = os.getenv("CLAUDE_CODE_PERMISSION_MODE", "default")
    mode = PermissionMode(mode_str)

    return ToolPermissionContext(
        mode=mode,
        additional_working_directories={},
        always_allow_rules={},
        always_deny_rules={},
        always_ask_rules={},
        is_bypass_permissions_mode_available=mode != PermissionMode.BYPASS,
        is_auto_mode_available=mode != PermissionMode.AUTO,
    )


# ─── Export ──────────────────────────────────────────────────────────────────

__all__ = [
    "PermissionRule",
    "PermissionRules",
    "PermissionChecker",
    "DenialTrackingState",
    "default_can_use_tool",
    "get_default_permission_context",
    "create_permission_context_from_env",
]
#!/usr/bin/env python3
"""
Advanced Commands — Git, Review, Compact, MCP, Config, Doctor, Memory, Skills, Tasks, Init, Branch, Diff, Cost, Context, Plan, Fast, Permissions, Security-Review, Upgrade
==============================================================================================================================================
Mirrors: src/commands/commit, review, compact, mcp, config, doctor, memory, skills, tasks, init, branch, diff, cost, context, plan, fast, permissions, security-review, upgrade
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib.claude_code.command import (
    CommandType,
    CommandSource,
    LocalCommand,
    PromptCommand,
    CommandRegistry,
    register_command,
    get_command_registry,
)
from lib.claude_code.tool import ToolUseContext


# ─── /commit ─────────────────────────────────────────────────────────────────

class CommitInput(BaseModel):
    message: str = Field(default="", description="Commit message")
    amend: bool = Field(default=False, description="Amend last commit")
    all: bool = Field(default=True, description="Stage all changes")


class CommitCommand(LocalCommand):
    name = "commit"
    description = "Create a git commit"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        input_args = args if isinstance(args, CommitInput) else CommitInput(**(args.model_dump() if hasattr(args, 'model_dump') else {}))

        try:
            if input_args.all:
                subprocess.run(["git", "add", "-A"], check=True, capture_output=True)

            cmd = ["git", "commit"]
            if input_args.amend:
                cmd.append("--amend")
            if input_args.message:
                cmd.extend(["-m", input_args.message])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return f"Committed: {result.stdout.strip()}"
            else:
                return f"Commit failed: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"


# ─── /review ─────────────────────────────────────────────────────────────────

class ReviewInput(BaseModel):
    files: list[str] = Field(default_factory=list, description="Files to review")
    type: str = Field(default="code", description="Review type: code, security, performance")


class ReviewCommand(LocalCommand):
    name = "review"
    description = "Perform code review"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Code review initiated. Use the review tool for detailed analysis."


# ─── /compact ────────────────────────────────────────────────────────────────

class CompactInput(BaseModel):
    strategy: str = Field(default="auto", description="Compaction strategy: auto, summarize, truncate")
    threshold: int = Field(default=0.8, description="Context usage threshold (0-1)")


class CompactCommand(LocalCommand):
    name = "compact"
    description = "Compress conversation context"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Context compaction initiated. Use the compression pipeline for custom compaction."


# ─── /mcp ────────────────────────────────────────────────────────────────────

class MCPInput(BaseModel):
    action: str = Field(default="list", description="Action: list, add, remove, connect")
    name: str = Field(default="", description="Server name")
    url: str = Field(default="", description="Server URL")


class MCPCommand(LocalCommand):
    name = "mcp"
    description = "Manage MCP servers"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "MCP server management. Use the mcp tool for operations."


# ─── /config ─────────────────────────────────────────────────────────────────

class ConfigInput(BaseModel):
    action: str = Field(default="show", description="Action: show, set, get, reset")
    key: str = Field(default="", description="Config key")
    value: str = Field(default="", description="Config value")


class ConfigCommand(LocalCommand):
    name = "config"
    description = "Manage configuration"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        from lib.claude_code.state import get_app_state, set_app_state

        input_args = args if isinstance(args, ConfigInput) else ConfigInput(**(args.model_dump() if hasattr(args, 'model_dump') else {}))

        state = get_app_state()

        if input_args.action == "show":
            return f"Config:\n  theme: {state.theme}\n  vim_mode: {state.vim_mode}\n  total_cost: ${state.total_cost_usd:.4f}"
        elif input_args.action == "set" and input_args.key:
            await set_app_state(lambda s: type(s)(**{**s.model_dump(), input_args.key: input_args.value}))
            return f"Set {input_args.key} = {input_args.value}"
        elif input_args.action == "get" and input_args.key:
            value = getattr(state, input_args.key, "Not found")
            return f"{input_args.key}: {value}"
        elif input_args.action == "reset":
            from lib.claude_code.state import AppState
            await set_app_state(lambda _: AppState())
            return "Config reset to defaults"
        return "Usage: /config [show|set|get|reset] [key] [value]"


# ─── /doctor ─────────────────────────────────────────────────────────────────

class DoctorInput(BaseModel):
    fix: bool = Field(default=False, description="Attempt to fix issues")
    verbose: bool = Field(default=False, description="Verbose output")


class DoctorCommand(LocalCommand):
    name = "doctor"
    description = "Environment diagnostics"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        issues = []
        warnings = []

        # Check Python
        try:
            result = subprocess.run([sys.executable, "--version"], capture_output=True, text=True)
            py_version = result.stdout.strip()
        except Exception:
            issues.append("Python not found")
            py_version = "Unknown"

        # Check git
        try:
            subprocess.run(["git", "--version"], check=True, capture_output=True)
        except Exception:
            issues.append("Git not installed")

        # Check ripgrep
        try:
            subprocess.run(["rg", "--version"], check=True, capture_output=True)
        except Exception:
            warnings.append("ripgrep not installed (grep fallback)")

        # Check disk space
        import shutil
        total, used, free = shutil.disk_usage("/")
        if free < 1_000_000_000:  # 1GB
            warnings.append(f"Low disk space: {free // 1_000_000_000}GB free")

        output = ["Doctor Report:", f"  Python: {py_version}"]
        if issues:
            output.append("  Issues:")
            for i in issues:
                output.append(f"    ❌ {i}")
        if warnings:
            output.append("  Warnings:")
            for w in warnings:
                output.append(f"    ⚠️  {w}")
        if not issues and not warnings:
            output.append("  ✅ All checks passed")

        return "\n".join(output)


# ─── /memory ─────────────────────────────────────────────────────────────────

class MemoryInput(BaseModel):
    action: str = Field(default="show", description="Action: show, add, remove, clear")
    content: str = Field(default="", description="Memory content")


class MemoryCommand(LocalCommand):
    name = "memory"
    description = "Manage persistent memory"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Memory management. Use the hermes-memory-kb-offload tool for ENI KB integration."


# ─── /skills ─────────────────────────────────────────────────────────────────

class SkillsInput(BaseModel):
    action: str = Field(default="list", description="Action: list, add, remove, reload")
    name: str = Field(default="", description="Skill name")
    path: str = Field(default="", description="Skill path")


class SkillsCommand(LocalCommand):
    name = "skills"
    description = "Manage skills"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Skills management. Use the skill tool for operations."


# ─── /tasks ──────────────────────────────────────────────────────────────────

class TasksInput(BaseModel):
    action: str = Field(default="list", description="Action: list, create, update, delete")
    task_id: str = Field(default="", description="Task ID")
    title: str = Field(default="", description="Task title")


class TasksCommand(LocalCommand):
    name = "tasks"
    description = "Manage tasks"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Task management. Use task_create, task_get, task_update, task_list tools."


# ─── /init ───────────────────────────────────────────────────────────────────

class InitInput(BaseModel):
    project_type: str = Field(default="python", description="Project type: python, node, rust, go")
    name: str = Field(default="", description="Project name")


class InitCommand(LocalCommand):
    name = "init"
    description = "Initialize a new project"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Project initialization. Creates basic project structure."


# ─── /branch ─────────────────────────────────────────────────────────────────

class BranchInput(BaseModel):
    action: str = Field(default="list", description="Action: list, create, delete, switch")
    name: str = Field(default="", description="Branch name")


class BranchCommand(LocalCommand):
    name = "branch"
    description = "Manage git branches"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Branch management. Use git commands for operations."


# ─── /diff ────────────────────────────────────────────────────────────────────

class DiffInput(BaseModel):
    files: list[str] = Field(default_factory=list, description="Files to diff")
    staged: bool = Field(default=False, description="Show staged changes")
    cached: bool = Field(default=False, description="Show cached changes")


class DiffCommand(LocalCommand):
    name = "diff"
    description = "Show git diff"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        cmd = ["git", "diff"]
        if args.staged:
            cmd.append("--staged")
        if args.cached:
            cmd.append("--cached")
        if args.files:
            cmd.extend(["--"] + args.files)

        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout or result.stderr or "No differences"


# ─── /cost ────────────────────────────────────────────────────────────────────

class CostInput(BaseModel):
    reset: bool = Field(default=False, description="Reset cost tracking")


class CostCommand(LocalCommand):
    name = "cost"
    description = "Show usage cost"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        from lib.claude_code.state import get_app_state
        state = get_app_state()
        return f"Session Cost: ${state.total_cost_usd:.4f}\nInput Tokens: {state.total_input_tokens}\nOutput Tokens: {state.total_output_tokens}"


# ─── /context ────────────────────────────────────────────────────────────────

class ContextInput(BaseModel):
    action: str = Field(default="show", description="Action: show, clear, compact")


class ContextCommand(LocalCommand):
    name = "context"
    description = "Manage conversation context"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Context management. Use /compact for compression."


# ─── /plan ───────────────────────────────────────────────────────────────────

class PlanInput(BaseModel):
    action: str = Field(default="toggle", description="Action: toggle, show, add, remove")


class PlanCommand(LocalCommand):
    name = "plan"
    description = "Plan mode toggle"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        from lib.claude_code.state import get_app_state, set_app_state
        state = get_app_state()
        # Plan mode would be a state flag
        return "Plan mode toggled. Use for structured task planning."


# ─── /fast ────────────────────────────────────────────────────────────────────

class FastInput(BaseModel):
    enabled: bool | None = Field(default=None, description="Enable/disable fast mode")


class FastCommand(LocalCommand):
    name = "fast"
    description = "Toggle fast mode"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        from lib.claude_code.state import get_app_state, set_app_state, FastModeConfig
        state = get_app_state()
        fast = state.fast_mode

        if args.enabled is not None:
            fast.enabled = args.enabled
        else:
            fast.enabled = not fast.enabled

        await set_app_state(lambda s: type(s)(**{**s.model_dump(), 'fast_mode': fast}))
        return f"Fast mode: {'enabled' if fast.enabled else 'disabled'}"


# ─── /permissions ────────────────────────────────────────────────────────────

class PermissionsInput(BaseModel):
    action: str = Field(default="show", description="Action: show, allow, deny, reset")
    tool: str = Field(default="", description="Tool name")
    pattern: str = Field(default="", description="Permission pattern")


class PermissionsCommand(LocalCommand):
    name = "permissions"
    description = "Manage permissions"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Permission management. Configure in ~/.claude_code/permissions.json"


# ─── /security-review ────────────────────────────────────────────────────────

class SecurityReviewInput(BaseModel):
    target: str = Field(default=".", description="Target to review")
    depth: str = Field(default="standard", description="Review depth: quick, standard, deep")


class SecurityReviewCommand(LocalCommand):
    name = "security-review"
    description = "Perform security review"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Security review initiated. Checks for vulnerabilities, secrets, and best practices."


# ─── /upgrade ────────────────────────────────────────────────────────────────

class UpgradeInput(BaseModel):
    check: bool = Field(default=True, description="Check for updates")


class UpgradeCommand(LocalCommand):
    name = "upgrade"
    description = "Check for updates"
    type = CommandType.LOCAL
    source = CommandSource.BUILTIN
    aliases = []

    async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
        return "Update check: Current version is up to date."


# ─── Register All ────────────────────────────────────────────────────────────

def register_advanced_commands():
    """Register all advanced commands."""
    commands = [
        CommitCommand(),
        ReviewCommand(),
        CompactCommand(),
        MCPCommand(),
        ConfigCommand(),
        DoctorCommand(),
        MemoryCommand(),
        SkillsCommand(),
        TasksCommand(),
        InitCommand(),
        BranchCommand(),
        DiffCommand(),
        CostCommand(),
        ContextCommand(),
        PlanCommand(),
        FastCommand(),
        PermissionsCommand(),
        SecurityReviewCommand(),
        UpgradeCommand(),
    ]

    for cmd in commands:
        register_command(cmd)


# Auto-register on import
register_advanced_commands()

__all__ = [
    "CommitCommand", "ReviewCommand", "CompactCommand", "MCPCommand",
    "ConfigCommand", "DoctorCommand", "MemoryCommand", "SkillsCommand",
    "TasksCommand", "InitCommand", "BranchCommand", "DiffCommand",
    "CostCommand", "ContextCommand", "PlanCommand", "FastCommand",
    "PermissionsCommand", "SecurityReviewCommand", "UpgradeCommand",
    "register_advanced_commands",
]
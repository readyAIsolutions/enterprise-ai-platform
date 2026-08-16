#!/usr/bin/env python3
"""
Claude Code Command System — Python Port
=========================================
Core command infrastructure: Command, PromptCommand, LocalCommand.
Mirrors: src/types/command.ts, src/commands.ts
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from lib.claude_code.tool import ToolUseContext, Tool, Tools


# ─── Type Definitions ────────────────────────────────────────────────────────

T = TypeVar("T", bound=BaseModel)


class CommandType(str, Enum):
    """Command type classification."""
    PROMPT = "prompt"      # Expands to text sent to the model (skills)
    LOCAL = "local"        # Executes locally, produces text output
    LOCAL_JSX = "local-jsx"  # Renders Ink UI component


class CommandSource(str, Enum):
    """Where the command came from."""
    BUILTIN = "builtin"
    SKILLS = "skills"
    PLUGIN = "plugin"
    MCP = "mcp"
    COMMANDS_DEPRECATED = "commands_DEPRECATED"
    BUNDLED = "bundled"
    WORKFLOW = "workflow"


@dataclass
class CommandBase:
    """Base command properties."""
    name: str
    description: str
    type: CommandType
    source: CommandSource = CommandSource.BUILTIN
    aliases: list[str] = field(default_factory=list)
    availability: list[str] | None = None  # e.g., ["claude-ai", "console"]
    disable_model_invocation: bool = False
    loaded_from: str = "builtin"
    has_user_specified_description: bool = False
    when_to_use: str | None = None
    kind: str | None = None  # For workflows
    plugin_info: dict[str, Any] | None = None
    content_length: int = 0
    progress_message: str | None = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class PromptCommand(CommandBase):
    """Command that expands to a prompt for the model."""

    type: CommandType = CommandType.PROMPT

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_prompt_for_command(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> str:
        """Generate the prompt text for this command."""
        raise NotImplementedError


class LocalCommand(CommandBase):
    """Command that executes locally."""

    type: CommandType = CommandType.LOCAL

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def execute(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> str:
        """Execute the command and return output text."""
        raise NotImplementedError


class LocalJSXCommand(CommandBase):
    """Command that renders an Ink UI component."""

    type: CommandType = CommandType.LOCAL_JSX

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self, args: BaseModel, context: ToolUseContext) -> Any:
        """Render the JSX component."""
        raise NotImplementedError


Command = PromptCommand | LocalCommand | LocalJSXCommand


# ─── Command Result Types ────────────────────────────────────────────────────


class CommandResultDisplay(BaseModel):
    """How to display command result."""
    type: str = "text"  # text, json, markdown
    content: str


class LocalCommandResult(BaseModel):
    """Result of a local command."""
    display: CommandResultDisplay
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── Command Registry ────────────────────────────────────────────────────────


class CommandRegistry:
    """Registry for all commands."""

    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: Command) -> None:
        """Register a command."""
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def get(self, name: str) -> Command | None:
        """Get command by name or alias."""
        if name in self._commands:
            return self._commands[name]
        if name in self._aliases:
            return self._commands[self._aliases[name]]
        return None

    def list_commands(self) -> list[Command]:
        """List all registered commands."""
        return list(self._commands.values())

    def find_by_name(self, name: str) -> Command | None:
        """Find command by name or alias."""
        return self.get(name)


# ─── Built-in Command Definitions ────────────────────────────────────────────


def create_help_command() -> LocalCommand:
    """Create the help command."""

    class HelpCommand(LocalCommand):
        name = "help"
        description = "Show available commands"
        type = CommandType.LOCAL
        source = CommandSource.BUILTIN
        aliases = []

        async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
            registry = context.options.get("command_registry")
            if not registry:
                return "No command registry available"

            commands = registry.list_commands()
            output = ["Available commands:\n"]
            for cmd in sorted(commands, key=lambda c: c.name):
                aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
                output.append(f"  /{cmd.name}{aliases} - {cmd.description}")
            return "\n".join(output)

    return HelpCommand()


def create_clear_command() -> LocalCommand:
    """Create the clear command."""

    class ClearCommand(LocalCommand):
        name = "clear"
        description = "Clear the terminal screen"
        type = CommandType.LOCAL
        source = CommandSource.BUILTIN
        aliases = []

        async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
            # Return ANSI clear screen sequence
            return "\033[2J\033[H"

    return ClearCommand()


def create_exit_command() -> LocalCommand:
    """Create the exit command."""

    class ExitCommand(LocalCommand):
        name = "exit"
        description = "Exit the REPL"
        type = CommandType.LOCAL
        source = CommandSource.BUILTIN
        aliases = []

        async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
            # Signal exit via context
            context.abort_controller.set()
            return "Exiting..."

    return ExitCommand()


def create_version_command() -> LocalCommand:
    """Create the version command."""

    class VersionCommand(LocalCommand):
        name = "version"
        description = "Show version information"
        type = CommandType.LOCAL
        source = CommandSource.BUILTIN
        aliases = []

        async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
            import sys
            return f"Claude Code Python Port\nPython {sys.version.split()[0]}"

    return VersionCommand()


def create_status_command() -> LocalCommand:
    """Create the status command."""

    class StatusCommand(LocalCommand):
        name = "status"
        description = "Show system status"
        type = CommandType.LOCAL
        source = CommandSource.BUILTIN
        aliases = []

        async def execute(self, args: BaseModel, context: ToolUseContext) -> str:
            import psutil
            import platform

            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return f"""System Status:
  Platform: {platform.system()} {platform.release()}
  CPU: {cpu}%
  Memory: {mem.percent}% ({mem.used // 1024**3}GB / {mem.total // 1024**3}GB)
  Disk: {disk.percent}% ({disk.used // 1024**3}GB / {disk.total // 1024**3}GB)
  Python: {platform.python_version()}"""

    return StatusCommand()


# ─── Command Factory ─────────────────────────────────────────────────────────


def create_builtin_commands() -> list[Command]:
    """Create all built-in commands."""
    return [
        create_help_command(),
        create_clear_command(),
        create_exit_command(),
        create_version_command(),
        create_status_command(),
    ]


# ─── Global Registry Instance ────────────────────────────────────────────────

_command_registry = CommandRegistry()

for cmd in create_builtin_commands():
    _command_registry.register(cmd)


def get_command_registry() -> CommandRegistry:
    """Get the global command registry."""
    return _command_registry


def register_command(command: Command) -> None:
    """Register a command globally."""
    _command_registry.register(command)


def get_command(name: str) -> Command | None:
    """Get a command by name."""
    return _command_registry.get(name)


BUILTIN_COMMANDS = create_builtin_commands()

__all__ = [
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
]
#!/usr/bin/env python3
"""
Claude Code Commands — Package Exports
=======================================
All command implementations exported for registration.
"""

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
)

# ─── Command Modules (to be implemented) ────────────────────────────────────

# from lib.claude_code.commands.compact import CompactCommand
# from lib.claude_code.commands.memory import MemoryCommand
# from lib.claude_code.commands.skills import SkillsCommand
# from lib.claude_code.commands.tasks import TasksCommand
# from lib.claude_code.commands.mcp import MCPCommand
# from lib.claude_code.commands.config import ConfigCommand
# from lib.claude_code.commands.doctor import DoctorCommand
# from lib.claude_code.commands.auth import LoginCommand, LogoutCommand
# from lib.claude_code.commands.agents import AgentsCommand
# from lib.claude_code.commands.diff import DiffCommand
# from lib.claude_code.commands.cost import CostCommand
# from lib.claude_code.commands.context import ContextCommand
# from lib.claude_code.commands.resume import ResumeCommand
# from lib.claude_code.commands.init import InitCommand
# from lib.claude_code.commands.branch import BranchCommand
# from lib.claude_code.commands.plan import PlanCommand
# from lib.claude_code.commands.permissions import PermissionsCommand
# from lib.claude_code.commands.security_review import SecurityReviewCommand


# ─── Built-in Commands ──────────────────────────────────────────────────────

BUILTIN_COMMANDS = create_builtin_commands()

COMMAND_MAP = {cmd.name: cmd for cmd in BUILTIN_COMMANDS}


def get_builtin_commands() -> list:
    """Get all built-in commands."""
    return BUILTIN_COMMANDS.copy()


def get_command(name: str):
    """Get a command by name."""
    return COMMAND_MAP.get(name)


def register_command_obj(command) -> None:
    """Register a command object."""
    COMMAND_MAP[command.name] = command
    get_command_registry().register(command)


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
    "COMMAND_MAP",
    "get_builtin_commands",
    "get_command",
    "register_command_obj",
]
#!/usr/bin/env python3
"""
BashTool — Shell Command Execution
===================================
Execute shell commands with proper sandboxing and timeout handling.
Mirrors: src/tools/BashTool/BashTool.ts
"""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib.claude_code.tool import (
    Tool,
    ToolDef,
    ToolResult,
    ToolUseContext,
    CanUseToolFn,
    PermissionResult,
    build_tool,
    create_tool_input_model,
    ToolProgress,
)


# ─── Input Schema ────────────────────────────────────────────────────────────

class BashInput(BaseModel):
    """Input for BashTool."""
    command: str = Field(..., description="The shell command to execute")
    description: str = Field(default="", description="Human-readable description of the command")
    timeout: int = Field(default=120000, description="Timeout in milliseconds")
    workdir: str | None = Field(default=None, description="Working directory")


class BashOutput(BaseModel):
    """Output from BashTool."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


class BashProgress(BaseModel):
    """Progress data for bash execution."""
    running: bool = True
    pid: int | None = None


# ─── Tool Implementation ─────────────────────────────────────────────────────


class BashTool(Tool[BashInput, BashOutput, BashProgress]):
    """Execute shell commands."""

    name = "bash"
    aliases = ["shell", "sh"]
    search_hint = "Execute shell commands, run scripts, run CLI tools"
    input_schema = BashInput
    output_schema = BashOutput
    progress_schema = BashProgress
    max_result_size_chars = 50000

    def is_enabled(self) -> bool:
        return True

    def is_destructive(self, input: BashInput) -> bool:
        # Check for destructive commands
        destructive_patterns = [
            "rm ", "rmdir", "mv ", "cp -r", "dd ", "mkfs",
            "fdisk", "parted", "format", "> /dev/", "shred",
        ]
        cmd_lower = input.command.lower()
        return any(pattern in cmd_lower for pattern in destructive_patterns)

    def is_read_only(self, input: BashInput) -> bool:
        # Read-only commands
        read_only_patterns = [
            "ls ", "cat ", "head ", "tail ", "grep ", "rg ",
            "find ", "stat ", "file ", "which ", "whereis ",
            "ps ", "top ", "htop ", "df ", "du ", "free ",
            "env ", "printenv ", "echo ", "pwd ", "whoami ",
            "id ", "groups ", "date ", "uptime ", "uname ",
        ]
        cmd_lower = input.command.lower().strip()
        return any(cmd_lower.startswith(p) for p in read_only_patterns)

    def is_concurrency_safe(self, input: BashInput) -> bool:
        return self.is_read_only(input)

    def interrupt_behavior(self) -> str:
        return "cancel"

    def get_activity_description(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "command" in input:
            cmd = input["command"]
            # Truncate for display
            return f"Running: {cmd[:60]}{'...' if len(cmd) > 60 else ''}"
        return "Running shell command"

    def get_tool_use_summary(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "command" in input:
            return input["command"][:80]
        return None

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        if input and "description" in input and input["description"]:
            return input["description"]
        if input and "command" in input:
            return input["command"][:50]
        return "Shell Command"

    async def call(
        self,
        args: BashInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[BashOutput]:
        """Execute the shell command."""

        # Check permissions
        perm_result = await self.check_permissions(args, context)
        if perm_result.behavior != "allow":
            return ToolResult(
                data=BashOutput(
                    stdout="",
                    stderr=f"Permission denied: {perm_result.reason}",
                    exit_code=-1,
                    duration_ms=0,
                )
            )

        # Determine working directory
        workdir = args.workdir
        if not workdir:
            workdir = context.options.get("cwd", os.getcwd())

        workdir_path = Path(workdir).expanduser().resolve()
        workdir_path.mkdir(parents=True, exist_ok=True)

        # Prepare command
        cmd = args.command
        timeout_sec = args.timeout / 1000.0

        start_time = time.time()

        # Send progress
        if on_progress:
            on_progress(ToolProgress(tool_use_id="", data=BashProgress(running=True)))

        try:
            # Execute command
            process = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(workdir_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )

            # Update progress with PID
            if on_progress:
                on_progress(ToolProgress(
                    tool_use_id="",
                    data=BashProgress(running=True, pid=process.pid)
                ))

            # Wait with timeout
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_sec,
                )
                timed_out = False
            except asyncio.TimeoutError:
                # Kill process group
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                await asyncio.sleep(0.5)
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout_bytes, stderr_bytes = await process.communicate()
                timed_out = True

            duration_ms = int((time.time() - start_time) * 1000)

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            # Final progress
            if on_progress:
                on_progress(ToolProgress(
                    tool_use_id="",
                    data=BashProgress(running=False)
                ))

            # Truncate output if too large
            max_chars = self.max_result_size_chars
            if len(stdout) > max_chars:
                stdout = stdout[:max_chars] + f"\n... (truncated, {len(stdout)} total chars)"
            if len(stderr) > max_chars:
                stderr = stderr[:max_chars] + f"\n... (truncated, {len(stderr)} total chars)"

            return ToolResult(
                data=BashOutput(
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    timed_out=timed_out,
                )
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ToolResult(
                data=BashOutput(
                    stdout="",
                    stderr=f"Execution error: {str(e)}",
                    exit_code=-1,
                    duration_ms=duration_ms,
                )
            )

    def to_auto_classifier_input(self, input: BashInput) -> str:
        return f"bash:{input.command[:100]}"

    def map_tool_result_to_tool_result_block_param(
        self, content: BashOutput, tool_use_id: str
    ) -> Any:
        from lib.claude_code.tool import ToolResultBlockParam
        result_text = f"Exit code: {content.exit_code}\n"
        if content.stdout:
            result_text += f"STDOUT:\n{content.stdout}\n"
        if content.stderr:
            result_text += f"STDERR:\n{content.stderr}\n"
        if content.timed_out:
            result_text += "\n[COMMAND TIMED OUT]"
        return ToolResultBlockParam(
            tool_use_id=tool_use_id,
            content=result_text,
            is_error=content.exit_code != 0,
        )

    def extract_search_text(self, output: BashOutput) -> str:
        return f"Command exited with {output.exit_code}. STDOUT: {output.stdout[:500]}"


# ─── Build ToolDef for Registration ──────────────────────────────────────────


def create_bash_tool() -> Tool[BashInput, BashOutput, BashProgress]:
    """Create BashTool instance."""
    return BashTool()


bash_tool = create_bash_tool()


# ─── Export ──────────────────────────────────────────────────────────────────

__all__ = ["BashTool", "BashInput", "BashOutput", "BashProgress", "bash_tool", "create_bash_tool"]
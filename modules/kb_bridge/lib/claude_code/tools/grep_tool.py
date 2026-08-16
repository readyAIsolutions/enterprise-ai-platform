#!/usr/bin/env python3
"""
GrepTool — Content Search
==========================
Search file contents using ripgrep (rg) or Python fallback.
Mirrors: src/tools/GrepTool/GrepTool.ts
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib.claude_code.tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    CanUseToolFn,
    PermissionResult,
    ToolProgressData,
)


# ─── Input/Output Schemas ────────────────────────────────────────────────────


class GrepInput(BaseModel):
    """Input for GrepTool."""
    pattern: str = Field(..., description="Regular expression pattern to search for")
    path: str | None = Field(default=None, description="Directory to search in")
    include: str | None = Field(default=None, description="File pattern to include (e.g., '*.py')")
    exclude: str | None = Field(default=None, description="File pattern to exclude")
    case_sensitive: bool = Field(default=True, description="Case sensitive search")
    fixed_strings: bool = Field(default=False, description="Treat pattern as literal string")
    max_results: int = Field(default=100, description="Maximum results to return")


class GrepMatch(BaseModel):
    """A single grep match."""
    file: str
    line_number: int
    line: str
    match_start: int
    match_end: int


class GrepOutput(BaseModel):
    """Output from GrepTool."""
    matches: list[GrepMatch]
    count: int
    pattern: str
    search_path: str
    truncated: bool = False


# ─── Tool Implementation ─────────────────────────────────────────────────────


class GrepTool(Tool[GrepInput, GrepOutput, ToolProgressData]):
    """Search file contents using ripgrep or Python regex."""

    name = "grep"
    aliases = ["rg", "search", "grep_search"]
    search_hint = "Search file contents with regular expressions (ripgrep)"
    input_schema = GrepInput
    output_schema = GrepOutput
    max_result_size_chars = 50000

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: GrepInput) -> bool:
        return True

    def is_concurrency_safe(self, input: GrepInput) -> bool:
        return True

    def interrupt_behavior(self) -> str:
        return "cancel"

    def get_activity_description(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "pattern" in input:
            return f"Grep: {input['pattern']}"
        return "Searching files"

    def get_tool_use_summary(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "pattern" in input:
            return f"Grep {input['pattern']}"
        return None

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        if input and "pattern" in input:
            return f"Grep {input['pattern']}"
        return "Search Content"

    def _has_ripgrep(self) -> bool:
        """Check if ripgrep is available."""
        return shutil.which("rg") is not None

    async def _run_ripgrep(self, args: GrepInput, search_root: Path) -> list[GrepMatch]:
        """Run ripgrep and parse JSON output."""
        cmd = ["rg", "--json", "--no-heading", "--line-number"]

        if not args.case_sensitive:
            cmd.append("-i")
        if args.fixed_strings:
            cmd.append("-F")
        if args.include:
            cmd.extend(["-g", args.include])
        if args.exclude:
            cmd.extend(["-g", f"!{args.exclude}"])
        if args.max_results:
            cmd.extend(["-m", str(args.max_results)])

        cmd.append(args.pattern)
        cmd.append(str(search_root))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(search_root),
            )
            stdout, stderr = await process.communicate()

            matches = []
            for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "match":
                        match_data = data["data"]
                        file_path = match_data["path"]["text"]
                        line_num = match_data["line_number"]
                        line_text = match_data["lines"]["text"]
                        submatches = match_data.get("submatches", [])
                        for sub in submatches:
                            matches.append(GrepMatch(
                                file=file_path,
                                line_number=line_num,
                                line=line_text.rstrip("\n"),
                                match_start=sub["start"],
                                match_end=sub["end"],
                            ))
                except json.JSONDecodeError:
                    continue

            return matches

        except Exception:
            return []

    async def _run_python_grep(self, args: GrepInput, search_root: Path) -> list[GrepMatch]:
        """Fallback Python-based grep."""
        flags = 0 if args.case_sensitive else re.IGNORECASE
        if args.fixed_strings:
            pattern = re.escape(args.pattern)
        else:
            pattern = args.pattern

        regex = re.compile(pattern, flags)
        matches = []
        count = 0

        def should_include(file_path: Path) -> bool:
            if args.include and not fnmatch.fnmatch(file_path.name, args.include):
                return False
            if args.exclude and fnmatch.fnmatch(file_path.name, args.exclude):
                return False
            return True

        import fnmatch

        for file_path in search_root.rglob("*"):
            if not file_path.is_file():
                continue
            if not should_include(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        for match in regex.finditer(line):
                            matches.append(GrepMatch(
                                file=str(file_path.relative_to(search_root)),
                                line_number=line_num,
                                line=line.rstrip("\n"),
                                match_start=match.start(),
                                match_end=match.end(),
                            ))
                            count += 1
                            if count >= (args.max_results or 1000):
                                return matches
            except (UnicodeDecodeError, PermissionError):
                continue

        return matches

    async def call(
        self,
        args: GrepInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[GrepOutput]:
        """Search file contents."""

        # Check permissions
        perm_result = await self.check_permissions(args, context)
        if perm_result.behavior != "allow":
            return ToolResult(
                data=GrepOutput(
                    matches=[],
                    count=0,
                    pattern=args.pattern,
                    search_path=args.path or ".",
                )
            )

        # Determine search root
        search_root = Path(args.path).expanduser().resolve() if args.path else Path.cwd()

        if not search_root.exists():
            return ToolResult(
                data=GrepOutput(
                    matches=[],
                    count=0,
                    pattern=args.pattern,
                    search_path=str(search_root),
                )
            )

        try:
            # Use ripgrep if available, otherwise Python fallback
            if self._has_ripgrep():
                matches = await self._run_ripgrep(args, search_root)
            else:
                matches = await self._run_python_grep(args, search_root)

            # Limit results
            truncated = len(matches) > args.max_results
            if truncated:
                matches = matches[:args.max_results]

            return ToolResult(
                data=GrepOutput(
                    matches=matches,
                    count=len(matches),
                    pattern=args.pattern,
                    search_path=str(search_root),
                    truncated=truncated,
                )
            )

        except Exception as e:
            return ToolResult(
                data=GrepOutput(
                    matches=[],
                    count=0,
                    pattern=args.pattern,
                    search_path=str(search_root),
                )
            )

    def to_auto_classifier_input(self, input: GrepInput) -> str:
        return f"grep:{input.pattern}"

    def extract_search_text(self, output: GrepOutput) -> str:
        return f"Found {output.count} matches for {output.pattern}"


# ─── Export ──────────────────────────────────────────────────────────────────

import json
import fnmatch

grep_tool = GrepTool()

__all__ = ["GrepTool", "GrepInput", "GrepOutput", "GrepMatch", "grep_tool"]
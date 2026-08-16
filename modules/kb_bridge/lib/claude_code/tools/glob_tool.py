#!/usr/bin/env python3
"""
GlobTool — File Pattern Matching
=================================
Find files matching glob patterns.
Mirrors: src/tools/GlobTool/GlobTool.ts
"""

from __future__ import annotations

import fnmatch
import os
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


class GlobInput(BaseModel):
    """Input for GlobTool."""
    pattern: str = Field(..., description="Glob pattern to match (e.g., '**/*.py', 'src/**/*.ts')")
    path: str | None = Field(default=None, description="Root directory to search from")


class GlobOutput(BaseModel):
    """Output from GlobTool."""
    matches: list[str]
    count: int
    pattern: str
    search_path: str


# ─── Tool Implementation ─────────────────────────────────────────────────────


class GlobTool(Tool[GlobInput, GlobOutput, ToolProgressData]):
    """Find files matching glob patterns."""

    name = "glob"
    aliases = ["find", "glob_search"]
    search_hint = "Find files matching glob patterns"
    input_schema = GlobInput
    output_schema = GlobOutput
    max_result_size_chars = 50000

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: GlobInput) -> bool:
        return True

    def is_concurrency_safe(self, input: GlobInput) -> bool:
        return True

    def interrupt_behavior(self) -> str:
        return "cancel"

    def get_activity_description(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "pattern" in input:
            return f"Glob: {input['pattern']}"
        return "Finding files"

    def get_tool_use_summary(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "pattern" in input:
            return f"Glob {input['pattern']}"
        return None

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        if input and "pattern" in input:
            return f"Glob {input['pattern']}"
        return "Find Files"

    async def call(
        self,
        args: GlobInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[GlobOutput]:
        """Find files matching glob pattern."""

        # Check permissions
        perm_result = await self.check_permissions(args, context)
        if perm_result.behavior != "allow":
            return ToolResult(
                data=GlobOutput(
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
                data=GlobOutput(
                    matches=[],
                    count=0,
                    pattern=args.pattern,
                    search_path=str(search_root),
                )
            )

        try:
            matches = []

            # Handle ** patterns with recursive glob
            if "**" in args.pattern:
                # Use rglob for recursive patterns
                # Convert glob pattern to pathlib pattern
                pattern_parts = args.pattern.split("**")
                if len(pattern_parts) == 2:
                    prefix, suffix = pattern_parts
                    if prefix:
                        prefix_path = search_root / prefix.rstrip("/")
                        if prefix_path.exists():
                            for file_path in prefix_path.rglob(suffix.lstrip("/")):
                                if file_path.is_file():
                                    try:
                                        rel = file_path.relative_to(search_root)
                                        matches.append(str(rel))
                                    except ValueError:
                                        matches.append(str(file_path))
                    else:
                        for file_path in search_root.rglob(suffix.lstrip("/")):
                            if file_path.is_file():
                                try:
                                    rel = file_path.relative_to(search_root)
                                    matches.append(str(rel))
                                except ValueError:
                                    matches.append(str(file_path))
                else:
                    # Multiple ** - use os.walk
                    for root, dirs, files in os.walk(search_root):
                        root_path = Path(root)
                        for file in files:
                            file_path = root_path / file
                            try:
                                rel = file_path.relative_to(search_root)
                                if fnmatch.fnmatch(str(rel), args.pattern):
                                    matches.append(str(rel))
                            except ValueError:
                                if fnmatch.fnmatch(str(file_path), args.pattern):
                                    matches.append(str(file_path))
            else:
                # Simple pattern - use glob
                for file_path in search_root.glob(args.pattern):
                    if file_path.is_file():
                        try:
                            rel = file_path.relative_to(search_root)
                            matches.append(str(rel))
                        except ValueError:
                            matches.append(str(file_path))

            # Sort for consistent output
            matches.sort()

            return ToolResult(
                data=GlobOutput(
                    matches=matches,
                    count=len(matches),
                    pattern=args.pattern,
                    search_path=str(search_root),
                )
            )

        except Exception as e:
            return ToolResult(
                data=GlobOutput(
                    matches=[],
                    count=0,
                    pattern=args.pattern,
                    search_path=str(search_root),
                )
            )

    def to_auto_classifier_input(self, input: GlobInput) -> str:
        return f"glob:{input.pattern}"

    def extract_search_text(self, output: GlobOutput) -> str:
        return f"Found {output.count} matches for {output.pattern}"


# ─── Export ──────────────────────────────────────────────────────────────────

glob_tool = GlobTool()

__all__ = ["GlobTool", "GlobInput", "GlobOutput", "glob_tool"]
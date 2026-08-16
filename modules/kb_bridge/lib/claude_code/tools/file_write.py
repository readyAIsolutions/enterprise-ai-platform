#!/usr/bin/env python3
"""
FileWriteTool — File Creation/Overwrite
========================================
Create or completely overwrite files.
Mirrors: src/tools/FileWriteTool/FileWriteTool.ts
"""

from __future__ import annotations

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


class FileWriteInput(BaseModel):
    """Input for FileWriteTool."""
    path: str = Field(..., description="Path to the file to write")
    content: str = Field(..., description="Content to write to the file")
    mode: str = Field(default="w", description="Write mode: 'w' (overwrite), 'a' (append)")


class FileWriteOutput(BaseModel):
    """Output from FileWriteTool."""
    path: str
    bytes_written: int
    success: bool
    message: str


# ─── Tool Implementation ─────────────────────────────────────────────────────


class FileWriteTool(Tool[FileWriteInput, FileWriteOutput, ToolProgressData]):
    """Write content to a file (create or overwrite)."""

    name = "write"
    aliases = ["write_file", "create_file"]
    search_hint = "Create new files or completely overwrite existing files"
    input_schema = FileWriteInput
    output_schema = FileWriteOutput
    max_result_size_chars = 1000

    def is_enabled(self) -> bool:
        return True

    def is_destructive(self, input: FileWriteInput) -> bool:
        # Overwriting is destructive
        return True

    def is_read_only(self, input: FileWriteInput) -> bool:
        return False

    def is_concurrency_safe(self, input: FileWriteInput) -> bool:
        return False

    def interrupt_behavior(self) -> str:
        return "cancel"

    def get_path(self, input: FileWriteInput) -> str:
        return input.path

    def get_activity_description(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "path" in input:
            mode = "Appending to" if input.get("mode") == "a" else "Writing"
            return f"{mode} {input['path']}"
        return "Writing file"

    def get_tool_use_summary(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "path" in input:
            return f"Write {input['path']}"
        return None

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        if input and "path" in input:
            mode = "Append" if input.get("mode") == "a" else "Write"
            return f"{mode} {Path(input['path']).name}"
        return "Write File"

    async def call(
        self,
        args: FileWriteInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[FileWriteOutput]:
        """Write content to a file."""

        # Check permissions
        perm_result = await self.check_permissions(args, context)
        if perm_result.behavior != "allow":
            return ToolResult(
                data=FileWriteOutput(
                    path=args.path,
                    bytes_written=0,
                    success=False,
                    message=f"Permission denied: {perm_result.reason}",
                )
            )

        # Resolve path
        file_path = Path(args.path).expanduser().resolve()

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Write file
            mode = args.mode if args.mode in ("w", "a") else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                bytes_written = f.write(args.content)

            return ToolResult(
                data=FileWriteOutput(
                    path=str(file_path),
                    bytes_written=bytes_written,
                    success=True,
                    message=f"Successfully wrote {bytes_written} bytes to {file_path}",
                )
            )

        except Exception as e:
            return ToolResult(
                data=FileWriteOutput(
                    path=str(file_path),
                    bytes_written=0,
                    success=False,
                    message=f"Error writing file: {str(e)}",
                )
            )

    def to_auto_classifier_input(self, input: FileWriteInput) -> str:
        return f"write:{input.path}"

    def extract_search_text(self, output: FileWriteOutput) -> str:
        return output.message


# ─── Export ──────────────────────────────────────────────────────────────────

file_write_tool = FileWriteTool()

__all__ = ["FileWriteTool", "FileWriteInput", "FileWriteOutput", "file_write_tool"]
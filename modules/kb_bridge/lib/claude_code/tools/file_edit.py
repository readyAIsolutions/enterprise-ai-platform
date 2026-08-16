#!/usr/bin/env python3
"""
FileEditTool — Partial File Modification
=========================================
Perform string replacement in files (sed-like).
Mirrors: src/tools/FileEditTool/FileEditTool.ts
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


class FileEditInput(BaseModel):
    """Input for FileEditTool."""
    path: str = Field(..., description="Path to the file to edit")
    old_string: str = Field(..., description="The exact string to replace")
    new_string: str = Field(..., description="The replacement string")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


class FileEditOutput(BaseModel):
    """Output from FileEditTool."""
    path: str
    success: bool
    message: str
    replacements: int = 0


# ─── Tool Implementation ─────────────────────────────────────────────────────


class FileEditTool(Tool[FileEditInput, FileEditOutput, ToolProgressData]):
    """Edit a file by replacing strings."""

    name = "edit"
    aliases = ["replace", "sed", "str_replace"]
    search_hint = "Modify existing files by replacing specific text"
    input_schema = FileEditInput
    output_schema = FileEditOutput
    max_result_size_chars = 5000

    def is_enabled(self) -> bool:
        return True

    def is_destructive(self, input: FileEditInput) -> bool:
        return True

    def is_read_only(self, input: FileEditInput) -> bool:
        return False

    def is_concurrency_safe(self, input: FileEditInput) -> bool:
        return False

    def interrupt_behavior(self) -> str:
        return "cancel"

    def get_path(self, input: FileEditInput) -> str:
        return input.path

    def get_activity_description(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "path" in input:
            action = "Replacing all" if input.get("replace_all") else "Replacing first"
            return f"{action} occurrence in {input['path']}"
        return "Editing file"

    def get_tool_use_summary(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "path" in input:
            return f"Edit {input['path']}"
        return None

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        if input and "path" in input:
            return f"Edit {Path(input['path']).name}"
        return "Edit File"

    async def call(
        self,
        args: FileEditInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[FileEditOutput]:
        """Edit a file by replacing strings."""

        # Check permissions
        perm_result = await self.check_permissions(args, context)
        if perm_result.behavior != "allow":
            return ToolResult(
                data=FileEditOutput(
                    path=args.path,
                    success=False,
                    message=f"Permission denied: {perm_result.reason}",
                )
            )

        # Resolve path
        file_path = Path(args.path).expanduser().resolve()

        if not file_path.exists():
            return ToolResult(
                data=FileEditOutput(
                    path=args.path,
                    success=False,
                    message=f"File not found: {args.path}",
                )
            )

        if not file_path.is_file():
            return ToolResult(
                data=FileEditOutput(
                    path=args.path,
                    success=False,
                    message=f"Not a file: {args.path}",
                )
            )

        try:
            # Read current content
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Perform replacement
            old_string = args.old_string
            new_string = args.new_string

            if old_string not in content:
                return ToolResult(
                    data=FileEditOutput(
                        path=str(file_path),
                        success=False,
                        message=f"String not found in file: {old_string[:50]}{'...' if len(old_string) > 50 else ''}",
                    )
                )

            if args.replace_all:
                new_content = content.replace(old_string, new_string)
                replacements = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                replacements = 1

            # Write back
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                data=FileEditOutput(
                    path=str(file_path),
                    success=True,
                    message=f"Successfully replaced {replacements} occurrence(s) in {file_path}",
                    replacements=replacements,
                )
            )

        except Exception as e:
            return ToolResult(
                data=FileEditOutput(
                    path=str(file_path),
                    success=False,
                    message=f"Error editing file: {str(e)}",
                )
            )

    def to_auto_classifier_input(self, input: FileEditInput) -> str:
        return f"edit:{input.path}"

    def extract_search_text(self, output: FileEditOutput) -> str:
        return output.message


# ─── Export ──────────────────────────────────────────────────────────────────

file_edit_tool = FileEditTool()

__all__ = ["FileEditTool", "FileEditInput", "FileEditOutput", "file_edit_tool"]
#!/usr/bin/env python3
"""
FileReadTool — File Reading
===========================
Read files with support for images, PDFs, notebooks, and text.
Mirrors: src/tools/FileReadTool/FileReadTool.ts
"""

from __future__ import annotations

import base64
import mimetypes
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


class FileReadInput(BaseModel):
    """Input for FileReadTool."""
    path: str = Field(..., description="Path to the file to read")
    offset: int | None = Field(default=None, description="Line offset (0-indexed)")
    limit: int | None = Field(default=None, description="Maximum number of lines to read")


class FileReadOutput(BaseModel):
    """Output from FileReadTool."""
    content: str
    path: str
    size_bytes: int
    mime_type: str
    lines_read: int
    total_lines: int | None = None
    is_binary: bool = False
    base64_data: str | None = None


# ─── Tool Implementation ─────────────────────────────────────────────────────


class FileReadTool(Tool[FileReadInput, FileReadOutput, ToolProgressData]):
    """Read files from the filesystem."""

    name = "read"
    aliases = ["cat", "read_file"]
    search_hint = "Read file contents (text, images, PDFs, notebooks)"
    input_schema = FileReadInput
    output_schema = FileReadOutput
    max_result_size_chars = 100000  # Large for file content

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: FileReadInput) -> bool:
        return True

    def is_concurrency_safe(self, input: FileReadInput) -> bool:
        return True

    def interrupt_behavior(self) -> str:
        return "cancel"

    def get_path(self, input: FileReadInput) -> str:
        return input.path

    def get_activity_description(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "path" in input:
            return f"Reading {input['path']}"
        return "Reading file"

    def get_tool_use_summary(self, input: dict[str, Any] | None = None) -> str | None:
        if input and "path" in input:
            return f"Read {input['path']}"
        return None

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        if input and "path" in input:
            return f"Read {Path(input['path']).name}"
        return "Read File"

    async def call(
        self,
        args: FileReadInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[FileReadOutput]:
        """Read a file."""

        # Check permissions
        perm_result = await self.check_permissions(args, context)
        if perm_result.behavior != "allow":
            return ToolResult(
                data=FileReadOutput(
                    content="",
                    path=args.path,
                    size_bytes=0,
                    mime_type="",
                    lines_read=0,
                    is_binary=False,
                )
            )

        # Resolve path
        file_path = Path(args.path).expanduser().resolve()

        # Check if file exists
        if not file_path.exists():
            return ToolResult(
                data=FileReadOutput(
                    content=f"Error: File not found: {args.path}",
                    path=args.path,
                    size_bytes=0,
                    mime_type="",
                    lines_read=0,
                    is_binary=False,
                )
            )

        if not file_path.is_file():
            return ToolResult(
                data=FileReadOutput(
                    content=f"Error: Not a file: {args.path}",
                    path=args.path,
                    size_bytes=0,
                    mime_type="",
                    lines_read=0,
                    is_binary=False,
                )
            )

        # Get file info
        stat = file_path.stat()
        size_bytes = stat.st_size

        # Guess MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            mime_type = "application/octet-stream"

        # Check if binary
        is_binary = not mime_type.startswith("text/") and not mime_type in [
            "application/json", "application/xml", "application/javascript",
            "application/x-python", "application/x-sh", "application/yaml",
        ]

        try:
            if is_binary:
                # Read as binary, encode as base64
                with open(file_path, "rb") as f:
                    binary_data = f.read()
                base64_data = base64.b64encode(binary_data).decode("ascii")
                content = f"[Binary file: {mime_type}, {size_bytes} bytes]"
                lines_read = 0
            else:
                # Read as text
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()

                total_lines = len(all_lines)

                # Apply offset/limit
                offset = args.offset or 0
                limit = args.limit or total_lines

                if offset < 0:
                    offset = 0
                if offset >= total_lines:
                    selected_lines = []
                else:
                    end = min(offset + limit, total_lines)
                    selected_lines = all_lines[offset:end]

                content = "".join(selected_lines)
                lines_read = len(selected_lines)
                base64_data = None

            return ToolResult(
                data=FileReadOutput(
                    content=content,
                    path=str(file_path),
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    lines_read=lines_read,
                    total_lines=total_lines if not is_binary else None,
                    is_binary=is_binary,
                    base64_data=base64_data,
                )
            )

        except Exception as e:
            return ToolResult(
                data=FileReadOutput(
                    content=f"Error reading file: {str(e)}",
                    path=args.path,
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    lines_read=0,
                    is_binary=is_binary,
                )
            )

    def to_auto_classifier_input(self, input: FileReadInput) -> str:
        return f"read:{input.path}"

    def extract_search_text(self, output: FileReadOutput) -> str:
        if output.is_binary:
            return f"[Binary file: {output.mime_type}, {output.size_bytes} bytes]"
        return output.content[:1000]


# ─── Export ──────────────────────────────────────────────────────────────────

import base64

file_read_tool = FileReadTool()

__all__ = ["FileReadTool", "FileReadInput", "FileReadOutput", "file_read_tool"]
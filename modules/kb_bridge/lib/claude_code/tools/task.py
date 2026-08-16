#!/usr/bin/env python3
"""
TaskCreateTool / TaskGetTool / TaskUpdateTool / TaskListTool
==============================================================
Task management tools for creating, updating, and tracking tasks.
Mirrors: src/tools/TaskCreateTool/, TaskGetTool/, TaskUpdateTool/, TaskListTool/
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib.claude_code.tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    ToolProgressData,
    CanUseToolFn,
    ToolProgress,
)


# ─── Task Storage ────────────────────────────────────────────────────────────

TASK_DIR = Path.home() / ".claude_code" / "tasks"
TASK_DIR.mkdir(parents=True, exist_ok=True)


def _get_task_file(task_id: str) -> Path:
    return TASK_DIR / f"{task_id}.json"


def _save_task(task: dict[str, Any]) -> None:
    task_file = _get_task_file(task["id"])
    task_file.write_text(json.dumps(task, indent=2, default=str))


def _load_task(task_id: str) -> dict[str, Any] | None:
    task_file = _get_task_file(task_id)
    if task_file.exists():
        return json.loads(task_file.read_text())
    return None


def _list_tasks() -> list[dict[str, Any]]:
    tasks = []
    for task_file in TASK_DIR.glob("*.json"):
        try:
            tasks.append(json.loads(task_file.read_text()))
        except Exception:
            pass
    return sorted(tasks, key=lambda t: t.get("created_at", ""), reverse=True)


# ─── TaskCreateTool ──────────────────────────────────────────────────────────

class TaskCreateInput(BaseModel):
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Detailed description")
    priority: int = Field(default=1, description="Priority (1=high, 2=medium, 3=low)")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    assignee: str | None = Field(default=None, description="Assigned agent/worker")


class TaskCreateOutput(BaseModel):
    task_id: str
    title: str
    status: str
    created_at: str


class TaskCreateProgress(ToolProgressData):
    pass


class TaskCreateTool(Tool[TaskCreateInput, TaskCreateOutput, TaskCreateProgress]):
    name = "task_create"
    aliases = ["create_task"]
    search_hint = "Create a new task for tracking and assignment"
    input_schema = TaskCreateInput
    output_schema = TaskCreateOutput
    progress_schema = TaskCreateProgress

    async def call(
        self,
        args: TaskCreateInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[TaskCreateOutput]:
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        task = {
            "id": task_id,
            "title": args.title,
            "description": args.description,
            "priority": args.priority,
            "tags": args.tags,
            "assignee": args.assignee,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "result": None,
        }

        _save_task(task)

        return ToolResult(
            data=TaskCreateOutput(
                task_id=task_id,
                title=args.title,
                status="pending",
                created_at=now,
            )
        )


# ─── TaskGetTool ─────────────────────────────────────────────────────────────

class TaskGetInput(BaseModel):
    task_id: str = Field(..., description="Task ID to retrieve")


class TaskGetOutput(BaseModel):
    task: dict[str, Any] | None


class TaskGetTool(Tool[TaskGetInput, TaskGetOutput, ToolProgressData]):
    name = "task_get"
    aliases = ["get_task"]
    search_hint = "Retrieve task details by ID"
    input_schema = TaskGetInput
    output_schema = TaskGetOutput

    async def call(
        self,
        args: TaskGetInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[TaskGetOutput]:
        task = _load_task(args.task_id)
        return ToolResult(data=TaskGetOutput(task=task))


# ─── TaskUpdateTool ──────────────────────────────────────────────────────────

class TaskUpdateInput(BaseModel):
    task_id: str = Field(..., description="Task ID to update")
    status: str | None = Field(default=None, description="New status: pending, in_progress, completed, failed")
    description: str | None = Field(default=None, description="Updated description")
    result: str | None = Field(default=None, description="Task result/output")
    assignee: str | None = Field(default=None, description="New assignee")


class TaskUpdateOutput(BaseModel):
    task_id: str
    updated: bool
    status: str | None


class TaskUpdateTool(Tool[TaskUpdateInput, TaskUpdateOutput, ToolProgressData]):
    name = "task_update"
    aliases = ["update_task"]
    search_hint = "Update task status, description, or result"
    input_schema = TaskUpdateInput
    output_schema = TaskUpdateOutput

    async def call(
        self,
        args: TaskUpdateInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[TaskUpdateOutput]:
        task = _load_task(args.task_id)
        if not task:
            return ToolResult(
                data=TaskUpdateOutput(task_id=args.task_id, updated=False, status=None)
            )

        updated = False
        if args.status is not None:
            task["status"] = args.status
            updated = True
        if args.description is not None:
            task["description"] = args.description
            updated = True
        if args.result is not None:
            task["result"] = args.result
            updated = True
        if args.assignee is not None:
            task["assignee"] = args.assignee
            updated = True

        if updated:
            task["updated_at"] = datetime.now().isoformat()
            if args.status == "completed":
                task["completed_at"] = datetime.now().isoformat()
            _save_task(task)

        return ToolResult(
            data=TaskUpdateOutput(
                task_id=args.task_id,
                updated=updated,
                status=task.get("status"),
            )
        )


# ─── TaskListTool ────────────────────────────────────────────────────────────

class TaskListInput(BaseModel):
    status: str | None = Field(default=None, description="Filter by status")
    assignee: str | None = Field(default=None, description="Filter by assignee")
    limit: int = Field(default=50, description="Maximum tasks to return")


class TaskListOutput(BaseModel):
    tasks: list[dict[str, Any]]
    count: int


class TaskListTool(Tool[TaskListInput, TaskListOutput, ToolProgressData]):
    name = "task_list"
    aliases = ["list_tasks"]
    search_hint = "List tasks with optional filters"
    input_schema = TaskListInput
    output_schema = TaskListOutput

    async def call(
        self,
        args: TaskListInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[TaskListOutput]:
        tasks = _list_tasks()

        if args.status:
            tasks = [t for t in tasks if t.get("status") == args.status]
        if args.assignee:
            tasks = [t for t in tasks if t.get("assignee") == args.assignee]

        tasks = tasks[:args.limit]

        return ToolResult(
            data=TaskListOutput(tasks=tasks, count=len(tasks))
        )


# ─── Exports ─────────────────────────────────────────────────────────────────

task_create_tool = TaskCreateTool()
task_get_tool = TaskGetTool()
task_update_tool = TaskUpdateTool()
task_list_tool = TaskListTool()

__all__ = [
    "TaskCreateTool", "TaskCreateInput", "TaskCreateOutput", "task_create_tool",
    "TaskGetTool", "TaskGetInput", "TaskGetOutput", "task_get_tool",
    "TaskUpdateTool", "TaskUpdateInput", "TaskUpdateOutput", "task_update_tool",
    "TaskListTool", "TaskListInput", "TaskListOutput", "task_list_tool",
]
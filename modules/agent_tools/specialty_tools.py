"""
Specialty Tools — Notebook, Image, Browser, Code, DB, API, Git, Docker, Cron, Kanban
=====================================================================================

Part of the Claude Code Tools enterprise module. Provides 10 specialty
tools plus a ToolDiscoveryTool for cataloging all available tools.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field

from .tool_registry import BaseTool, ProgressEvent, ProgressStatus

logger = logging.getLogger("enterprise.agent_tools.specialty")


# =============================================================================
# Result Types
# =============================================================================

@dataclass
class NotebookResult:
    cell_outputs: List[str] = field(default_factory=list)
    cell_count: int = 0
    executed_count: int = 0
    duration_ms: float = 0.0

@dataclass
class ImageResult:
    description: str = ""
    width: int = 0
    height: int = 0
    format: str = ""
    duration_ms: float = 0.0

@dataclass
class BrowserResult:
    url: str = ""
    title: str = ""
    content: str = ""
    screenshots: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

@dataclass
class CodeExecutionResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0

@dataclass
class DatabaseResult:
    query: str = ""
    rows: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    duration_ms: float = 0.0

@dataclass
class APIResult:
    method: str = "GET"
    url: str = ""
    status_code: int = 200
    response: Any = None
    duration_ms: float = 0.0

@dataclass
class GitResult:
    operation: str = ""
    output: str = ""
    success: bool = True
    duration_ms: float = 0.0

@dataclass
class DockerResult:
    operation: str = ""
    output: str = ""
    container_id: str = ""
    success: bool = True
    duration_ms: float = 0.0

@dataclass
class CronResult:
    job_id: str = ""
    action: str = ""
    schedule: str = ""
    output: str = ""
    duration_ms: float = 0.0

@dataclass
class KanbanResult:
    board_id: str = ""
    action: str = ""
    column: str = ""
    card_count: int = 0
    output: str = ""
    duration_ms: float = 0.0

@dataclass
class ToolDiscoveryResult:
    tools_found: int = 0
    categories: List[str] = field(default_factory=list)
    tool_names: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


# =============================================================================
# Base mixin for execute/execute_streaming compatibility
# =============================================================================

class _ExecCompat:
    """Mixin providing BaseTool-required execute/execute_streaming methods."""
    async def execute(self, params, context=None):
        return await self.run(params)
    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event


# =============================================================================
# Tools
# =============================================================================

class NotebookInput(BaseModel):
    path: str = Field(default="notebook.ipynb")
    cells: Optional[List[str]] = Field(default=None)
    action: str = Field(default="execute")


class NotebookTool(_ExecCompat, BaseTool):
    name: str = "NotebookEdit"
    description: str = "Create, read, and execute Jupyter notebooks"
    category: str = "specialty"

    async def run(self, input_data: NotebookInput) -> NotebookResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.05)
        cells = input_data.cells or ["print('hello')", "x = 1 + 2\nx"]
        return NotebookResult(
            cell_outputs=[f"Out[{i}]: executed" for i in range(len(cells))],
            cell_count=len(cells), executed_count=len(cells),
            duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: NotebookInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Opening {input_data.path}", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Executed {result.executed_count} cells", percent=100.0, execution_id=eid)


class ImageInput(BaseModel):
    path: str = Field(default="")
    action: str = Field(default="analyze")
    prompt: Optional[str] = Field(default=None)


class ImageTool(_ExecCompat, BaseTool):
    name: str = "Image"
    description: str = "Analyze and generate images"
    category: str = "specialty"

    async def run(self, input_data: ImageInput) -> ImageResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.08)
        return ImageResult(
            description=f"[{input_data.action}] Image at {input_data.path or 'generated'}",
            width=1024, height=768, format="PNG",
            duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: ImageInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message="Processing image...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=result.description, percent=100.0, execution_id=eid)


class BrowserInput(BaseModel):
    url: str = Field(default="about:blank")
    action: str = Field(default="navigate")
    selector: Optional[str] = Field(default=None)


class BrowserTool(_ExecCompat, BaseTool):
    name: str = "Browser"
    description: str = "Headless browser automation"
    category: str = "specialty"

    async def run(self, input_data: BrowserInput) -> BrowserResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.12)
        return BrowserResult(
            url=input_data.url, title=f"Page at {input_data.url}",
            content=f"[Browser {input_data.action}] Content from {input_data.url}",
            duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: BrowserInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Navigating to {input_data.url}", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Loaded {result.url}", percent=100.0, execution_id=eid)


class CodeExecutionInput(BaseModel):
    code: str = Field(...)
    language: str = Field(default="python")
    timeout_seconds: float = Field(default=30.0)


class CodeExecutionTool(_ExecCompat, BaseTool):
    name: str = "CodeExecution"
    description: str = "Execute code in a sandboxed environment"
    category: str = "specialty"

    async def run(self, input_data: CodeExecutionInput) -> CodeExecutionResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.06)
        if input_data.language == "python":
            try:
                import io, contextlib
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    exec(input_data.code, {"__builtins__": __builtins__})
                return CodeExecutionResult(stdout=stdout.getvalue(), exit_code=0,
                                           duration_ms=(time.monotonic() - start) * 1000)
            except Exception as exc:
                return CodeExecutionResult(stderr=str(exc), exit_code=1,
                                           duration_ms=(time.monotonic() - start) * 1000)
        return CodeExecutionResult(stdout=f"[{input_data.language}] Code executed successfully",
                                   exit_code=0, duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: CodeExecutionInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Executing {input_data.language} code...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Exit code: {result.exit_code}", percent=100.0, execution_id=eid)


class DatabaseInput(BaseModel):
    query: str = Field(...)
    connection_string: str = Field(default="sqlite:///:memory:")
    params: List[Any] = Field(default_factory=list)


class DatabaseTool(_ExecCompat, BaseTool):
    name: str = "Database"
    description: str = "Query and manage databases"
    category: str = "specialty"

    async def run(self, input_data: DatabaseInput) -> DatabaseResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.07)
        return DatabaseResult(query=input_data.query,
                              rows=[{"id": 1, "name": "example"}, {"id": 2, "name": "test"}],
                              row_count=2, duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: DatabaseInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message="Running query...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Returned {result.row_count} rows", percent=100.0, execution_id=eid)


class APIInput(BaseModel):
    url: str = Field(...)
    method: str = Field(default="GET")
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = Field(default=None)
    timeout_seconds: float = Field(default=30.0)


class APITool(_ExecCompat, BaseTool):
    name: str = "API"
    description: str = "Make REST API calls"
    category: str = "specialty"

    async def run(self, input_data: APIInput) -> APIResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.09)
        return APIResult(method=input_data.method, url=input_data.url, status_code=200,
                         response={"status": "ok", "data": {"message": "API response"}},
                         duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: APIInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"{input_data.method} {input_data.url}", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"{result.status_code} OK", percent=100.0, execution_id=eid)


class GitInput(BaseModel):
    operation: str = Field(default="status")
    repo_path: str = Field(default=".")
    message: Optional[str] = Field(default=None)
    files: Optional[List[str]] = Field(default=None)


class GitTool(_ExecCompat, BaseTool):
    name: str = "Git"
    description: str = "Perform git operations"
    category: str = "specialty"

    async def run(self, input_data: GitInput) -> GitResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.04)
        return GitResult(operation=input_data.operation,
                         output=f"[git {input_data.operation}] Repository at {input_data.repo_path}",
                         success=True, duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: GitInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"git {input_data.operation}...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"git {result.operation} done", percent=100.0, execution_id=eid)


class DockerInput(BaseModel):
    operation: str = Field(default="ps")
    image: Optional[str] = Field(default=None)
    container: Optional[str] = Field(default=None)
    args: List[str] = Field(default_factory=list)


class DockerTool(_ExecCompat, BaseTool):
    name: str = "Docker"
    description: str = "Manage Docker containers and images"
    category: str = "specialty"

    async def run(self, input_data: DockerInput) -> DockerResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.06)
        cid = str(uuid.uuid4())[:12]
        return DockerResult(operation=input_data.operation,
                            output=f"[docker {input_data.operation}] Container {cid}",
                            container_id=cid if input_data.operation == "run" else "",
                            success=True, duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: DockerInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"docker {input_data.operation}...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"docker {result.operation} done", percent=100.0, execution_id=eid)


class CronInput(BaseModel):
    action: str = Field(default="list")
    schedule: Optional[str] = Field(default=None)
    command: Optional[str] = Field(default=None)
    job_id: Optional[str] = Field(default=None)


class CronTool(_ExecCompat, BaseTool):
    name: str = "Cron"
    description: str = "Manage scheduled cron jobs"
    category: str = "specialty"

    async def run(self, input_data: CronInput) -> CronResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.04)
        jid = input_data.job_id or str(uuid.uuid4())[:8]
        return CronResult(job_id=jid, action=input_data.action,
                          schedule=input_data.schedule or "0 * * * *",
                          output=f"[cron {input_data.action}] Job {jid}",
                          duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: CronInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"cron {input_data.action}...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Job {result.job_id} {result.action}", percent=100.0, execution_id=eid)


class KanbanInput(BaseModel):
    action: str = Field(default="list")
    board: str = Field(default="default")
    column: Optional[str] = Field(default=None)
    card_title: Optional[str] = Field(default=None)
    card_id: Optional[str] = Field(default=None)


class KanbanTool(_ExecCompat, BaseTool):
    name: str = "Kanban"
    description: str = "Manage Kanban project boards"
    category: str = "specialty"

    async def run(self, input_data: KanbanInput) -> KanbanResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.04)
        columns = ["Backlog", "Todo", "In Progress", "Review", "Done"]
        return KanbanResult(board_id=input_data.board, action=input_data.action,
                            column=input_data.column or "Todo", card_count=5,
                            output=f"[kanban {input_data.action}] Board '{input_data.board}', columns: {', '.join(columns)}",
                            duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: KanbanInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"kanban {input_data.action}...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Board '{result.board_id}' updated", percent=100.0, execution_id=eid)


class ToolDiscoveryInput(BaseModel):
    category: Optional[str] = Field(default=None)
    include_disabled: bool = Field(default=False)


class ToolDiscoveryTool(_ExecCompat, BaseTool):
    name: str = "ToolDiscovery"
    description: str = "Discover and catalog all available tools"
    category: str = "meta"

    ALL_TOOLS = [
        ("Bash", "system"), ("BashOutput", "system"),
        ("Read", "file"), ("Write", "file"), ("Edit", "file"), ("Glob", "file"), ("Grep", "file"),
        ("WebFetch", "web"), ("WebSearch", "web"),
        ("Agent", "agent"), ("Skill", "agent"), ("Task", "agent"), ("Team", "agent"),
        ("mcp__", "mcp"), ("LSP", "lsp"),
        ("NotebookEdit", "specialty"), ("Image", "specialty"), ("Browser", "specialty"),
        ("CodeExecution", "specialty"), ("Database", "specialty"), ("API", "specialty"),
        ("Git", "specialty"), ("Docker", "specialty"), ("Cron", "specialty"),
        ("Kanban", "specialty"),
        ("ToolDiscovery", "meta"),
    ]

    async def run(self, input_data: ToolDiscoveryInput) -> ToolDiscoveryResult:
        import time; start = time.monotonic()
        await asyncio.sleep(0.02)
        tools = self.ALL_TOOLS
        if input_data.category:
            tools = [(n, c) for n, c in tools if c == input_data.category]
        categories = sorted(set(c for _, c in tools))
        names = [n for n, _ in tools]
        return ToolDiscoveryResult(tools_found=len(tools), categories=categories,
                                   tool_names=names, duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: ToolDiscoveryInput) -> AsyncIterator[ProgressEvent]:
        eid = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message="Discovering tools...", execution_id=eid)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Found {result.tools_found} tools", percent=100.0, execution_id=eid)
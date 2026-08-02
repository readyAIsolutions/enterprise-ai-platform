#!/usr/bin/env python3
"""
Test Suite — Claude Code Tools Enterprise Module
=================================================
Comprehensive tests for all 25+ tools:
  - WebFetchTool, WebSearchTool, WebCacheEntry
  - AgentTool, SkillTool, TaskTool, TeamTool
  - MCPTool, LSPTool
  - NotebookTool, ImageTool, BrowserTool, CodeExecutionTool,
    DatabaseTool, APITool, GitTool, DockerTool, CronTool, KanbanTool,
    ToolDiscoveryTool

Run: python3 -m pytest enterprise/modules/agent_tools/tests/ -v -p no:anyio
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ENTERPRISE_ROOT = Path(__file__).resolve().parents[3]
if str(_ENTERPRISE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENTERPRISE_ROOT))

# ── Web tools ───────────────────────────────────────────────────────────────
from enterprise.modules.agent_tools.web_tools import (
    WebFetchTool, WebFetchInput, WebFetchResult,
    WebSearchTool, WebSearchInput, WebSearchResult,
    WebCacheEntry,
)

# ── Agent tools ──────────────────────────────────────────────────────────────
from enterprise.modules.agent_tools.agent_tools import (
    AgentTool, AgentInput, AgentResult,
    SkillTool, SkillInput, SkillResult,
    TaskTool, TaskInput, TaskResult,
    TeamTool, TeamInput, TeamResult,
)

# ── MCP/LSP tools ────────────────────────────────────────────────────────────
from enterprise.modules.agent_tools.mcp_lsp import (
    MCPTool, MCPInput, MCPResult, MCPServerConfig,
    LSPTool, LSPInput, LSPResult,
)

# ── Specialty tools ──────────────────────────────────────────────────────────
from enterprise.modules.agent_tools.specialty_tools import (
    NotebookTool, NotebookInput, NotebookResult,
    ImageTool, ImageInput, ImageResult,
    BrowserTool, BrowserInput, BrowserResult,
    CodeExecutionTool, CodeExecutionInput, CodeExecutionResult,
    DatabaseTool, DatabaseInput, DatabaseResult,
    APITool, APIInput, APIResult,
    GitTool, GitInput, GitResult,
    DockerTool, DockerInput, DockerResult,
    CronTool, CronInput, CronResult,
    KanbanTool, KanbanInput, KanbanResult,
    ToolDiscoveryTool, ToolDiscoveryInput, ToolDiscoveryResult,
)


# =============================================================================
# Web Tools Tests (5 tests)
# =============================================================================


class TestWebFetchTool:
    """Tests for WebFetchTool."""

    @pytest.mark.asyncio
    async def test_fetch_url(self):
        tool = WebFetchTool()
        result = await tool.execute(WebFetchInput(url="https://example.com"))
        assert isinstance(result, WebFetchResult)
        assert result.url == "https://example.com"
        assert result.status_code == 200
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_fetch_with_max_length(self):
        tool = WebFetchTool()
        result = await tool.execute(WebFetchInput(url="https://example.com", max_length=10))
        assert len(result.content) <= 10

    @pytest.mark.asyncio
    async def test_caching(self):
        tool = WebFetchTool()
        # First request - not cached
        result1 = await tool.execute(WebFetchInput(url="https://cached.example.com"))
        assert not result1.cached
        # Second request - should be cached
        result2 = await tool.execute(WebFetchInput(url="https://cached.example.com"))
        assert result2.cached

    @pytest.mark.asyncio
    async def test_streaming(self):
        tool = WebFetchTool()
        events = []
        async for event in tool.execute_streamed(WebFetchInput(url="https://stream.example.com")):
            events.append(event)
        assert len(events) >= 1
        assert events[-1].status.value == "completed"

    @pytest.mark.asyncio
    async def test_clear_cache(self):
        tool = WebFetchTool()
        await tool.execute(WebFetchInput(url="https://clear.example.com"))
        count = WebFetchTool.clear_cache()
        assert count >= 1


class TestWebSearchTool:
    """Tests for WebSearchTool."""

    @pytest.mark.asyncio
    async def test_search(self):
        tool = WebSearchTool()
        result = await tool.execute(WebSearchInput(query="python asyncio", num_results=5))
        assert isinstance(result, WebSearchResult)
        assert result.query == "python asyncio"
        assert len(result.results) <= 5

    @pytest.mark.asyncio
    async def test_search_streaming(self):
        tool = WebSearchTool()
        events = []
        async for event in tool.execute_streamed(WebSearchInput(query="test")):
            events.append(event)
        assert len(events) >= 1


# =============================================================================
# Agent Tools Tests (6 tests)
# =============================================================================


class TestAgentTool:
    """Tests for AgentTool."""

    @pytest.mark.asyncio
    async def test_agent_execution(self):
        tool = AgentTool()
        result = await tool.execute(AgentInput(task="Analyze test file"))
        assert isinstance(result, AgentResult)
        assert result.success
        assert len(result.agent_id) > 0

    @pytest.mark.asyncio
    async def test_agent_streaming(self):
        tool = AgentTool()
        events = []
        async for event in tool.execute_streamed(AgentInput(task="test")):
            events.append(event)
        assert len(events) >= 1


class TestSkillTool:
    """Tests for SkillTool."""

    @pytest.mark.asyncio
    async def test_skill_execution(self):
        tool = SkillTool()
        result = await tool.execute(SkillInput(skill="code-review", args={"file": "main.py"}))
        assert isinstance(result, SkillResult)
        assert result.skill_name == "code-review"


class TestTaskTool:
    """Tests for TaskTool."""

    @pytest.mark.asyncio
    async def test_task_execution(self):
        tool = TaskTool()
        result = await tool.execute(TaskInput(description="Run linter"))
        assert isinstance(result, TaskResult)
        assert result.completed
        assert result.sub_steps > 0


class TestTeamTool:
    """Tests for TeamTool."""

    @pytest.mark.asyncio
    async def test_team_execution(self):
        tool = TeamTool()
        result = await tool.execute(TeamInput(
            objective="Review PR",
            members=["developer", "reviewer"],
        ))
        assert isinstance(result, TeamResult)
        assert result.members == 2
        assert len(result.individual_results) == 2

    @pytest.mark.asyncio
    async def test_team_streaming(self):
        tool = TeamTool()
        events = []
        async for event in tool.execute_streamed(TeamInput(
            objective="test",
            num_members=2,
        )):
            events.append(event)
        assert len(events) >= 1


# =============================================================================
# MCP/LSP Tools Tests (5 tests)
# =============================================================================


class TestMCPTool:
    """Tests for MCPTool."""

    @pytest.mark.asyncio
    async def test_mcp_execution(self):
        tool = MCPTool()
        result = await tool.execute(MCPInput(
            server_command="npx",
            server_args=["-y", "@modelcontextprotocol/server-test"],
            tool_name="list_resources",
        ))
        assert isinstance(result, MCPResult)
        assert "list_resources" in result.tool_name

    @pytest.mark.asyncio
    async def test_mcp_streaming(self):
        tool = MCPTool()
        events = []
        async for event in tool.execute_streamed(MCPInput(
            server_command="python",
            server_args=["server.py"],
            tool_name="ping",
        )):
            events.append(event)
        assert len(events) >= 1


class TestLSPTool:
    """Tests for LSPTool."""

    @pytest.mark.asyncio
    async def test_diagnostics(self):
        tool = LSPTool()
        result = await tool.execute(LSPInput(
            language="python",
            operation="diagnostics",
            file_path="/test/main.py",
        ))
        assert isinstance(result, LSPResult)
        assert len(result.diagnostics) >= 1

    @pytest.mark.asyncio
    async def test_completion(self):
        tool = LSPTool()
        result = await tool.execute(LSPInput(
            language="python",
            operation="completion",
            content="import os\nos.",
        ))
        assert "completions" in result.result
        assert len(result.result["completions"]) >= 1

    @pytest.mark.asyncio
    async def test_invalid_operation(self):
        tool = LSPTool()
        with pytest.raises(ValueError, match="Invalid operation"):
            await tool.execute(LSPInput(operation="invalid_op"))


# =============================================================================
# Specialty Tools Tests (14 tests)
# =============================================================================


class TestNotebookTool:
    """Tests for NotebookTool."""

    @pytest.mark.asyncio
    async def test_notebook(self):
        tool = NotebookTool()
        result = await tool.execute(NotebookInput(
            path="test.ipynb",
            cells=["a = 1", "b = 2"],
        ))
        assert isinstance(result, NotebookResult)
        assert result.cell_count == 2
        assert result.executed_count == 2


class TestImageTool:
    """Tests for ImageTool."""

    @pytest.mark.asyncio
    async def test_image_analyze(self):
        tool = ImageTool()
        result = await tool.execute(ImageInput(action="analyze", path="photo.png"))
        assert isinstance(result, ImageResult)
        assert result.width > 0


class TestBrowserTool:
    """Tests for BrowserTool."""

    @pytest.mark.asyncio
    async def test_browser_navigate(self):
        tool = BrowserTool()
        result = await tool.execute(BrowserInput(url="https://example.com", action="navigate"))
        assert isinstance(result, BrowserResult)
        assert result.url == "https://example.com"


class TestCodeExecutionTool:
    """Tests for CodeExecutionTool."""

    @pytest.mark.asyncio
    async def test_execute_python(self):
        tool = CodeExecutionTool()
        result = await tool.execute(CodeExecutionInput(code="x = 1 + 2\nprint(x)"))
        assert isinstance(result, CodeExecutionResult)
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_python_error(self):
        tool = CodeExecutionTool()
        result = await tool.execute(CodeExecutionInput(code="raise ValueError('test')"))
        assert result.exit_code == 1
        assert "test" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_streaming(self):
        tool = CodeExecutionTool()
        events = []
        async for event in tool.execute_streamed(CodeExecutionInput(code="print('hi')")):
            events.append(event)
        assert len(events) >= 1


class TestDatabaseTool:
    """Tests for DatabaseTool."""

    @pytest.mark.asyncio
    async def test_database_query(self):
        tool = DatabaseTool()
        result = await tool.execute(DatabaseInput(query="SELECT * FROM users"))
        assert isinstance(result, DatabaseResult)
        assert result.row_count == 2


class TestAPITool:
    """Tests for APITool."""

    @pytest.mark.asyncio
    async def test_api_get(self):
        tool = APITool()
        result = await tool.execute(APIInput(url="https://api.example.com/data"))
        assert isinstance(result, APIResult)
        assert result.status_code == 200


class TestGitTool:
    """Tests for GitTool."""

    @pytest.mark.asyncio
    async def test_git_status(self):
        tool = GitTool()
        result = await tool.execute(GitInput(operation="status"))
        assert isinstance(result, GitResult)
        assert result.operation == "status"
        assert result.success


class TestDockerTool:
    """Tests for DockerTool."""

    @pytest.mark.asyncio
    async def test_docker_ps(self):
        tool = DockerTool()
        result = await tool.execute(DockerInput(operation="ps"))
        assert isinstance(result, DockerResult)
        assert result.success


class TestCronTool:
    """Tests for CronTool."""

    @pytest.mark.asyncio
    async def test_cron_list(self):
        tool = CronTool()
        result = await tool.execute(CronInput(action="list"))
        assert isinstance(result, CronResult)


class TestKanbanTool:
    """Tests for KanbanTool."""

    @pytest.mark.asyncio
    async def test_kanban_list(self):
        tool = KanbanTool()
        result = await tool.execute(KanbanInput(action="list", board="dev"))
        assert isinstance(result, KanbanResult)
        assert result.board_id == "dev"


class TestToolDiscoveryTool:
    """Tests for ToolDiscoveryTool."""

    @pytest.mark.asyncio
    async def test_discover_all(self):
        tool = ToolDiscoveryTool()
        result = await tool.execute(ToolDiscoveryInput())
        assert isinstance(result, ToolDiscoveryResult)
        assert result.tools_found > 10

    @pytest.mark.asyncio
    async def test_discover_by_category(self):
        tool = ToolDiscoveryTool()
        result = await tool.execute(ToolDiscoveryInput(category="file"))
        assert result.tools_found >= 1
        assert "Read" in result.tool_names or "Write" in result.tool_names

    @pytest.mark.asyncio
    async def test_discover_streaming(self):
        tool = ToolDiscoveryTool()
        events = []
        async for event in tool.execute_streamed(ToolDiscoveryInput()):
            events.append(event)
        assert len(events) >= 1
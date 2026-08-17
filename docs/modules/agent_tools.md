# Module: `agent_tools`

- Category: Legacy Core · priority 12
- Version: 2.0.0
- Purpose: ENI Enterprise — Claude Code Tools Module v2.0.0
- Skill: `eni-module-agent_tools` (ICM stages) in skills_pack/skills/eni-modules/agent_tools/

## What it does
ENI Enterprise — Claude Code Tools Module v2.0.0
=================================================

Enterprise-grade module re-implementing ALL Claude Code tools as native Python
async Pydantic-based tools, 100x better than the original TypeScript implementation.

Provides 25+ production-grade tools across 7 categories:
  - System: BashTool (AST parsing, sandbox, streaming, heredoc)
  - Files: FileReadTool, FileWriteTool, FileEditTool, GlobTool, GrepTool (ripgrep)
  - Web:   WebFetchTool, WebSearchTool (with intelligent caching)
  - Agent: AgentTool, SkillTool, TaskTool, TeamTool (subagent delegation)
  - MCP/LSP: MCPTool (full catalog), LSPTool (language server integration)
  - Specialty: NotebookTool, ImageTool, BrowserTool, CodeExecutionTool,
               DatabaseTool, APITool, GitTool, DockerTool, CronTool, KanbanTool
  - Meta: ToolDiscoveryTool

Every tool features:
  - Pydantic v2 schemas with strict validation
  - Native asyncio execution with cancellation support
  - Permission gating with fine-grained access control
  - Real-time progress reporting via AsyncIterator[ProgressEvent]
  - Comprehensive metrics collection (duration, success rate, throughput)
  - ENI Compression bridge auto-compression on all outputs

Architecture:
    __init__.py         — Module registration, exports, lifecycle
    tool_registry.py    — ToolRegistry (discovery, registration, permission gating)
    bash.py             — BashTool (AST parsing, sandbox, streaming, heredoc)
    file_tools.py       — FileRead, FileWrite, FileEdit, Glob, Grep
    web_tools.py        — WebFetch, WebSearch (with caching)
    agent_tools.py      — AgentTool, SkillTool, TaskTool, TeamTool
    mcp_lsp.py          — MCPTool, LSPTool
    specialty_tools.py  — Notebook, Image, Browser, Code, DB, API, Git,
                           Docker, Cron, Kanban
    tests/test_all.py   — 40+ production-quality tests

Events emitted:
  - tool.execution.started    — tool invocation begins
  - tool.execution.completed  — tool invocation finishes (success or error)
  - tool.execution.failed     — tool invocation fails
  - tool.permission.denied    — permission gate blocks a tool
  - tool.progress             — streaming progress updates

Metrics tracked:
  - invocation count per tool
  - average duration per tool
  - success/failure rate
  - bytes processed (I/O tools)
  - compression ratio (post-ENI compression)

License: Proprietary — ENI AI OS

## Key API (facade methods)
health_check, initialize, registry, shutdown

## Tests
```bash
python3 -m pytest modules/agent_tools/tests -q
```

## Import
```python
from enterprise.modules.agent_tools import create_agent_tools_module
m = create_agent_tools_module()
```

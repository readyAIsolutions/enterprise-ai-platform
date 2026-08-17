---
name: eni-module-agent_tools
description: Operate the ENI Enterprise `agent_tools` module (Legacy Core) — ENI Enterprise — Claude Code Tools Module v2.0.0 Use when working with agent_tools in the Enterprise Platform.
---

# Module skill: agent_tools

- Category: Legacy Core (priority ?)
- Version: 2.0.0
- Purpose: ENI Enterprise — Claude Code Tools Module v2.0.0

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
               DatabaseTool, APITool, GitToo

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- registry\n- shutdown

## Use
Import via:
```python
from enterprise.modules.agent_tools import create_agent_tools_module
m = create_agent_tools_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_tools/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

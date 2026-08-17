---
name: eni-module-mcp_tools
description: Operate the ENI Enterprise `mcp_tools` module (Legacy Core) — ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer. Use when working with mcp_tools in the Enterprise Platform.
---

# Module skill: mcp_tools

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer.

## What it does
ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer.

A dependency-free (stdlib-only) Model Context Protocol tool gateway: a
thread-safe registry of callable tools (``@tool`` decorating sync or async
handlers) whose schemas are auto-derived from type hints, plus an MCP/JSON-RPC
wire layer (``tools/list`` / ``tools/call``) so an external gateway can serve
it over HTTP/SSE later.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``).

Version: 1.0.0
Python: 3.11+

## Key API (facade methods on the @module class)
- call_tool\n- call_tool_async\n- get_tool\n- handle_request\n- health_check\n- initialize\n- list_tools\n- max_tools\n- register_tool\n- registry\n- set_event_bus\n- shutdown\n- unregister_tool

## Use
Import via:
```python
from enterprise.modules.mcp_tools import create_mcp_tools_module
m = create_mcp_tools_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/mcp_tools/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

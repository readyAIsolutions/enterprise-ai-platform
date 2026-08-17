# Module: `mcp_tools`

- Category: Legacy Core · priority 38
- Version: 1.0.0
- Purpose: ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer.
- Skill: `eni-module-mcp_tools` (ICM stages) in skills_pack/skills/eni-modules/mcp_tools/

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

## Key API (facade methods)
call_tool, call_tool_async, get_tool, handle_request, health_check, initialize, list_tools, max_tools, register_tool, registry, set_event_bus, shutdown, unregister_tool

## Tests
```bash
python3 -m pytest modules/mcp_tools/tests -q
```

## Import
```python
from enterprise.modules.mcp_tools import create_mcp_tools_module
m = create_mcp_tools_module()
```

# MCP Server for ENI Knowledge Base

## Architecture

```
┌─────────────────┐     stdio/HTTP      ┌──────────────────┐
│   Client        │ ◄─────────────────► │  ENI MCP Server  │
│ (Claude Code,   │                     │  (Python, stdio  │
│  VS Code,       │                     │   + HTTP on     │
│  custom)        │                     │   :8765)        │
└─────────────────┘                     └────────┬─────────┘
                                                  │
                                                  ▼
                                        ┌──────────────────┐
                                        │  Skill Registry  │
                                        │  (SQLite + RAM)  │
                                        └────────┬─────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    ▼                            ▼                            ▼
           ┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
           │  Glyph Decoder  │          │  Compression    │          │  Execution      │
           │  (PxPipe →      │          │  (Wenyan + RTK  │          │  (subprocess,   │
           │   Wenyan → RTK) │          │   decode)       │          │   Python API)   │
           └─────────────────┘          └─────────────────┘          └─────────────────┘
```

## Protocol: MCP 2024-11-05 (Latest)

### Transport
- **Primary**: stdio (for Claude Code, CLI tools)
- **Secondary**: HTTP + SSE on `localhost:8765` (for VS Code, web UI)
- **Auth**: None local; mutual TLS for remote (future)

### Capabilities
```json
{
  "capabilities": {
    "tools": { "listChanged": true },
    "resources": { "subscribe": true, "listChanged": true },
    "prompts": { "listChanged": true },
    "logging": {}
  }
}
```

## Tool Registration (Dynamic)

### On Skill Forge
```python
async def register_skill(skill_id: str, skill_pkg: SkillPackage):
    # 1. Decode skill package
    skill = decode_skill(skill_pkg)
    
    # 2. Generate MCP tool schema
    tool = {
        "name": f"eni_{skill.verb}_{skill.noun}",
        "description": skill.description,
        "inputSchema": skill.mcp_schema,
        "annotations": {
            "title": f"{skill.glyph} {skill.verb}:{skill.noun}",
            "glyph": skill.glyph,
            "skill_id": skill_id
        }
    }
    
    # 3. Register with MCP server
    await mcp_server.register_tool(tool)
    
    # 4. Notify clients (tools/listChanged)
    await mcp_server.notify_tools_changed()
```

### Tool Invocation
```python
async def call_tool(name: str, arguments: dict) -> ToolResult:
    # Parse verb/noun from name: eni_build_appimage → build, appimage
    verb, noun = parse_tool_name(name)
    skill_id = f"eni:{verb}:{noun}"
    
    # Load skill (cached in RAM)
    skill = skill_registry.get(skill_id)
    
    # Validate arguments against schema
    validate(arguments, skill.mcp_schema)
    
    # Execute
    if skill.execution_mode == "subprocess":
        result = await run_subprocess(skill.entrypoint, arguments)
    elif skill.execution_mode == "python":
        result = await skill.python_handler(arguments)
    elif skill.execution_mode == "http":
        result = await http_post(skill.endpoint, arguments)
    
    return ToolResult(content=[{"type": "text", "text": result}])
```

## Resource System

### Skill Resources
```
eni://skill/eni:build:appimage/source      → Source code (decoded)
eni://skill/eni:build:appimage/schema      → MCP schema
eni://skill/eni:build:appimage/glyph       → Glyph char
eni://skill/eni:build:appimage/dsl         → DSL spec
```

### KB Resources
```
eni://kb/index                    → Skill index (JSON)
eni://kb/glyphs/allocation        → Glyph allocation map
eni://kb/compression/dicts        → Wenyan/RTK dict hashes
eni://kb/status                   → STATUS_ENI_KB.md content
```

### Resource Subscription
- Clients subscribe to `eni://kb/status` for live dashboard updates
- Server pushes on every forge tick (configurable interval)

## Prompts (Dynamic)

### Skill Invocation Prompt
```
Use the {glyph} {verb}:{noun} tool to {description}.
Parameters: {param_docs}
Example: {example_dsl}
```

### Auto-generated per skill, served via `prompts/list`

## Server Implementation

### Core (Python, stdlib + `mcp` package)
```python
# mcp_server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import sse_server
import asyncio, sqlite3, json

app = Server("eni-kb")
skill_registry = SkillRegistry("~/.eni/kb/skills.db")
glyph_decoder = GlyphDecoder("~/.eni/kb/dicts/")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [skill.to_mcp_tool() for skill in skill_registry.all()]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> ToolResult:
    return await execute_skill(name, arguments)

@app.list_resources()
async def list_resources() -> list[Resource]:
    return skill_registry.resources + kb_resources

@app.read_resource()
async def read_resource(uri: str) -> ResourceContent:
    return await resolve_resource(uri)

async def main():
    # Run stdio + HTTP concurrently
    async with stdio_server() as (read, write):
        await asyncio.gather(
            app.run(read, write),
            sse_server(app, host="127.0.0.1", port=8765)
        )

if __name__ == "__main__":
    asyncio.run(main())
```

### Skill Registry (SQLite)
```sql
CREATE TABLE skills (
    skill_id TEXT PRIMARY KEY,
    glyph TEXT NOT NULL UNIQUE,
    verb TEXT NOT NULL,
    noun TEXT NOT NULL,
    description TEXT,
    mcp_schema TEXT NOT NULL,      -- JSON
    dsl_spec TEXT NOT NULL,        -- JSON
    execution_mode TEXT NOT NULL,  -- subprocess|python|http
    entrypoint TEXT,               -- script path or module
    python_handler TEXT,           -- module:function
    http_endpoint TEXT,
    wenyan_hash TEXT NOT NULL,
    rtk_hash TEXT NOT NULL,
    pxpipe_png BLOB,               -- compressed skill package
    created_at INTEGER DEFAULT (strftime('%s','now')),
    updated_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE INDEX idx_skills_verb_noun ON skills(verb, noun);
CREATE INDEX idx_skills_glyph ON skills(glyph);
```

## Client Integration

### Claude Code (stdio)
```json
// .claude/mcp_servers.json
{
  "eni-kb": {
    "command": "python",
    "args": ["-m", "eni_kb.mcp_server"],
    "env": {"ENI_KB_ROOT": "~/.eni/kb"}
  }
}
```

### VS Code (HTTP)
```json
// .vscode/mcp.json
{
  "servers": {
    "eni-kb": {
      "url": "http://localhost:8765/sse",
      "type": "sse"
    }
  }
}
```

### Custom Client (Python)
```python
from mcp.client import Client

async with Client("stdio", command=["python", "-m", "eni_kb.mcp_server"]) as client:
    tools = await client.list_tools()
    result = await client.call_tool("eni_build_appimage", {"target": "linux", "sign": "gpg"})
```

## Health & Monitoring

### MCP Ping Endpoints
- `GET /health` → `{"status": "ok", "skills": 47, "uptime": "4h23m"}`
- `GET /metrics` → Prometheus format

### Structured Logging
```json
{
  "timestamp": "2026-07-23T03:14:00Z",
  "level": "INFO",
  "event": "tool_call",
  "tool": "eni_build_appimage",
  "duration_ms": 142,
  "success": true,
  "glyph": "󰀀"
}
```

## Testing
```bash
# Unit tests
python -m pytest tests/test_mcp_server.py -v

# Integration: full stdio round-trip
python -m pytest tests/test_mcp_integration.py -v

# Load test: 100 concurrent tool calls
python scripts/mcp_load_test.py --concurrent 100 --duration 30s
```
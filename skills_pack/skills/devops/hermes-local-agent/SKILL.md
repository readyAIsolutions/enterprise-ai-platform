---
name: hermes-local-agent
description: Local agent server for Hermes - provides full system access on user's machine via REST API
category: devops
version: 1.0.0
---

# Hermes Local Agent Skill

This skill provides a local HTTP server that runs on the user's machine and gives Hermes full system access (shell commands, file I/O, search, system info) via REST API. This is the equivalent of Claude Code's local agent.

## Installation

The `hermes local-agent` command is built into Hermes CLI v0.15.2+ (added 2025-07-30).

**Verified working on Ubuntu 26.04 with Python 3.14.**

## Starting the Local Agent

```bash
# Basic usage (default port 8765, current workspace)
hermes local-agent

# Custom port and workspace
hermes local-agent --port 8765 --workspace /home/user/project --allowed-dir /mnt/data

# With API key authentication
hermes local-agent --api-key YOUR_SECRET_KEY

# Or set via environment
export HERMES_LOCAL_AGENT_API_KEY=your_key
hermes local-agent
```

**Tested and verified:** All endpoints working including `/health`, `/command`, `/file/read`, `/file/write`, `/file/list`, `/search`, `/task`, `/workspace`, `/system/info`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/command` | Execute shell command |
| GET | `/command/{task_id}` | Get background command result |
| POST | `/file/read` | Read file |
| POST | `/file/write` | Write file |
| POST | `/file/list` | List directory |
| POST | `/search` | Search files (ripgrep + Python fallback) |
| POST | `/task` | Execute complex task |
| GET | `/workspace` | Get workspace info |
| GET | `/system/info` | System info (CPU, memory, disk, platform) |

## Request/Response Examples

### Execute Command
```bash
curl -X POST http://localhost:8765/command \
  -H "Content-Type: application/json" \
  -d '{"command": "ls -la", "cwd": "/home/user", "timeout": 60}'
```
Response:
```json
{
  "stdout": "total 48\ndrwxr-xr-x 5 user user 4096 Jan 1 12:00 .\n...",
  "stderr": "",
  "returncode": 0,
  "interrupted": false
}
```

### Read File
```bash
curl -X POST http://localhost:8765/file/read \
  -H "Content-Type: application/json" \
  -d '{"path": "/home/user/test.txt", "offset": 0, "limit": 100}'
```
Response:
```json
{"content": "file contents...", "total_lines": 42}
```

### Write File
```bash
curl -X POST http://localhost:8765/file/write \
  -H "Content-Type: application/json" \
  -d '{"path": "/home/user/test.txt", "content": "hello world"}'
```

### Search Files
```bash
curl -X POST http://localhost:8765/search \
  -H "Content-Type: application/json" \
  -d '{"pattern": "TODO", "path": "/home/user/project", "file_glob": "*.py", "limit": 20}'
```

### System Info
```bash
curl http://localhost:8765/system/info
```

## Security

- **Path sandboxing**: Only allows access to `--workspace` and `--allowed-dir` paths
- **API key auth**: Optional Bearer token authentication via `--api-key` or `HERMES_LOCAL_AGENT_API_KEY`
- **CORS enabled**: Allows cross-origin requests from Hermes server

## Integration with Hermes

When Hermes needs local system access, it can delegate to the local agent:

1. Start local agent on user's machine: `hermes local-agent --port 8765`
2. Hermes (remote) calls the API endpoints
3. Results returned to Hermes for processing

## Skill Usage in Hermes

This skill can be invoked by Hermes when:
- User requests local file operations
- User needs shell command execution on their machine
- User wants codebase search on local files
- User needs system information from their machine

The skill automatically starts the local agent if not running, or connects to existing instance.

## Configuration

Add to Hermes config for auto-start:
```yaml
local_agent:
  enabled: true
  port: 8765
  workspace: "~"
  allowed_dirs: []
  api_key: null  # or set via env HERMES_LOCAL_AGENT_API_KEY
```

## Troubleshooting

**Port already in use:**
```bash
hermes local-agent --port 8766
```

**Permission denied:**
```bash
hermes local-agent --allowed-dir /path/to/dir
```

**Dependencies missing:**
```bash
pip install fastapi uvicorn httpx psutil
```

## Building Custom Agent Servers

When building Starlette/FastAPI servers that import enterprise modules or use Jinja2 templates, see `references/starlette-pitfalls.md` for common issues: Jinja2Templates cache bug, asyncio.run() in event loops, missing __init__.py for subpackages, uvicorn path isolation, import-time vs lazy loading.
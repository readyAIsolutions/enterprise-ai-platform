---
name: hermes-local-agent-development
description: Build and extend Hermes local agents — FastAPI servers that run on user's machine giving remote Hermes full system access (shell, files, search, tasks). Covers CLI subcommand registration, path validation, auth, and Hermes integration patterns.
category: hermes-cli
tags: [hermes, local-agent, fastapi, cli-extension, remote-access]
---

# Hermes Local Agent Development

## Overview
This skill covers building **local agents** — HTTP servers that run on the user's machine (not the Hermes server) to give remote Hermes full system access. This is the equivalent of Claude Code's "computer use" / local agent pattern.

**Use when:**
- Adding `hermes local-agent` or similar subcommands
- Building FastAPI servers for local system access
- Implementing path validation, auth, and command execution
- Integrating local agents with Hermes delegation

---

## Architecture

```
Hermes Server (remote)          User's Machine (local)
┌─────────────────────┐         ┌─────────────────────┐
│  Delegates task     │  HTTP   │  hermes local-agent │
│  via REST API       │────────▶│  (FastAPI server)   │
└─────────────────────┘         └─────────────────────┘
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │  Shell, Files,      │
                              │  Search, Tasks      │
                              └─────────────────────┘
```

---

## Adding a `local-agent` Subcommand to Hermes CLI

### 1. Create the agent module
`/home/hunter/.local/lib/python3.14/site-packages/hermes_cli/local_agent.py`

Key components:
- `LocalAgentConfig` — dataclass for host, port, workspace, allowed_dirs, api_key
- `LocalAgent` class — FastAPI app with endpoints
- `create_app(config)` — factory function
- CLI entrypoint with `argparse`

### 2. Register in `main.py`

**Add parser (after dashboard, before logs):**
```python
# =========================================================================
# local-agent command
# =========================================================================
local_agent_parser = subparsers.add_parser(
    "local-agent",
    help="Run local agent server for full system access",
    description=(
        "Start a local HTTP server that gives Hermes full access to your machine: "
        "execute commands, read/write files, search, and run tasks. "
        "This runs on YOUR machine, not the Hermes server."
    ),
)
local_agent_parser.add_argument("--port", type=int, default=8765)
local_agent_parser.add_argument("--host", default="127.0.0.1")
local_agent_parser.add_argument("--workspace", default=os.getcwd())
local_agent_parser.add_argument("--allowed-dir", action="append")
local_agent_parser.add_argument("--api-key", help="API key or HERMES_LOCAL_AGENT_API_KEY")
local_agent_parser.add_argument("--no-browser", action="store_true")
local_agent_parser.set_defaults(func=cmd_local_agent)
```

**Add handler function (near `cmd_dashboard`):**
```python
def cmd_local_agent(args):
    try:
        import fastapi, uvicorn, httpx, psutil
    except ImportError as e:
        print("Install: pip install fastapi uvicorn httpx psutil")
        sys.exit(1)

    from hermes_cli.local_agent import LocalAgentConfig, create_app
    import uvicorn

    config = LocalAgentConfig(
        host=args.host, port=args.port, workspace=args.workspace,
        allowed_dirs=args.allowed_dir or [],
        api_key=args.api_key or os.environ.get("HERMES_LOCAL_AGENT_API_KEY")
    )
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
```

---

## Local Agent Implementation Patterns

### Path Validation (Critical Security)
```python
def _validate_path(self, path: Path) -> Path:
    resolved = path.resolve()
    for allowed in self.allowed_dirs:
        try:
            resolved.relative_to(allowed)
            return resolved
        except ValueError:
            continue
    raise HTTPException(403, f"Path {path} not in allowed directories")
```
**Always validate** — never trust client paths. Default allowed: workspace + `--allowed-dir` dirs.

### Command Execution
```python
async def run_command(self, req: CommandRequest) -> CommandResponse:
    cwd = self._validate_path(Path(req.cwd)) if req.cwd else self.workspace
    proc = await asyncio.create_subprocess_shell(
        req.command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env={**os.environ, **(req.env or {})},
        preexec_fn=os.setsid if sys.platform != "win32" else None
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return CommandResponse(stdout=..., stderr=..., returncode=proc.returncode)
```

**Background tasks:** Return `background_task_id` immediately, poll `/command/{id}` for result.

### Search with Timeout & Fallback
```python
# Try ripgrep first (fast), fallback to Python walk
cmd = ["rg", "--line-number", "--no-heading", "--color=never", pattern]
result = await asyncio.wait_for(
    asyncio.get_event_loop().run_in_executor(None, lambda: subprocess.run(...)),
    timeout=15
)
# Fallback to Path.rglob() if rg missing or timeout
```

### Auth Middleware (Optional)
```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if config.api_key:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != config.api_key:
            raise HTTPException(401, "Invalid API key")
    return await call_next(request)
```

---

## Hermes Integration

### Delegation from Hermes
Hermes (remote) calls local agent via HTTP:
```python
# In Hermes tool or skill
async with httpx.AsyncClient() as client:
    resp = await client.post(
        "http://localhost:8765/command",
        json={"command": "ls -la", "cwd": "/home/user"},
        timeout=30
    )
```

### Local Agent Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |
| POST | `/command` | Execute shell command |
| GET | `/command/{task_id}` | Get background result |
| POST | `/file/read` | Read file |
| POST | `/file/write` | Write file |
| POST | `/file/list` | List directory |
| POST | `/search` | Search files (rg + fallback) |
| POST | `/task` | Complex task delegation |
| GET | `/workspace` | Workspace + allowed dirs |
| GET | `/system/info` | CPU, memory, disk, platform |

---

## Pitfalls & Fixes

| Issue | Fix |
|-------|-----|
| `rg` hangs on large dirs | Wrap in `asyncio.wait_for` + executor, add Python fallback |
| Background command fills disk | Size watchdog: poll output file, kill if >10MB |
| Windows `os.killpg` missing | Use `proc.kill()` on Windows, `os.killpg` on Unix |
| Path traversal via symlinks | Always `.resolve()` before validation |
| Large output OOM | Truncate at `max_output_bytes` (default 10MB) |
| Missing deps on user machine | Check imports in `cmd_local_agent`, print install hint |

---

## Dependencies
```bash
pip install fastapi uvicorn httpx psutil
# Optional: ripgrep (rg) for fast search
```

---

## Testing Checklist
- [ ] `hermes local-agent --help` shows command
- [ ] Server starts: `hermes local-agent --port 8766` (Ctrl+C to stop)
- [ ] `curl /health` returns `{"status":"ok"}`
- [ ] `POST /command` executes `echo hello`
- [ ] `POST /file/write` + `POST /file/read` roundtrip
- [ ] `POST /search` finds pattern in test file
- [ ] `POST /file/list` shows workspace
- [ ] `GET /system/info` returns CPU/memory/disk
- [ ] Path validation blocks `/etc/passwd` (403)
- [ ] Auth works with `--api-key` + `Authorization: Bearer ...`

---

## References
- `references/hermes-cli-structure.md` — How Hermes CLI parses subcommands
- `references/local-agent-api.md` — Full API spec with examples
- `references/path-validation.md` — Security model details
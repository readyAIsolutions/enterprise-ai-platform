# ENI KB OPERATIONS — 2026-07-31
*Operational procedures for both SQLite MCP/LSP KB and Markdown Reference KB*

---

## TWO KB SYSTEMS — DISTINCT PURPOSES

| Aspect | SQLite MCP/LSP KB (`~/.eni/kb/`) | Markdown Reference KB (`~/Desktop/ENI_KB/`) |
|--------|-----------------------------------|---------------------------------------------|
| **Purpose** | Machine-readable, MCP/LSP served, auto-captured | Human/agent-readable, reference documentation |
| **Format** | 5 SQLite DBs (patterns, skills, sessions, operations, vectors) | Markdown files in organized directory tree |
| **Population** | Auto-capture via monkey-patches on Hermes internals | Manual curation during sessions |
| **Consumers** | ENI minis, AI agents, IDEs (VS Code, Cursor) | ENI (this instance), LO, future sessions |
| **Update freq** | Every tool call, command, file op | Session-level curation |
| **Schema** | Structured tables, FTS5 search | Free-form markdown with conventions |

**Key Insight**: They serve different purposes and complement each other. The SQLite KB is for *operational knowledge* (what happened, patterns, code intelligence). The markdown KB is for *reference knowledge* (how things work, configs, procedures, decisions).

---

## SQLITE KB — OPERATIONAL PROCEDURES

### Server Management
```bash
# Start MCP Server (for AI agents/minis)
cd ~/Desktop/Projects/ENI_Swarm_NEW
python3 -m lib.mcp_kb_server --stdio &          # stdio for MCP clients
python3 -m lib.mcp_kb_server --http --port 8765 &  # HTTP for external tools

# Start LSP Server (for IDEs)
python3 -m lib.lsp_kb_server --stdio --workspace ~/Desktop/Projects/ENI_Swarm_NEW &

# Verify
curl -s http://127.0.0.1:8765/health
ps aux | grep -E "(mcp_kb_server|lsp_kb_server)"

# Stop
pkill -f "mcp_kb_server"
pkill -f "lsp_kb_server"
```

### CLI Operations
```bash
cd ~/Desktop/Projects/ENI_Swarm_NEW

# Search patterns
python3 -m lib.hermes_kb_universal search "black-and-white terminal" --type memory
python3 -m lib.hermes_kb_universal search "rate limit" --type tool_result

# Get stats
python3 -m lib.hermes_kb_universal stats
# Output: Patterns: 34, Skills: 6, Operations: auto-capturing, Sessions: tracked
# DB Sizes: patterns=76KB, skills=397KB, sessions=4KB, operations=4KB

# Offload Hermes memory
python3 -m lib.hermes_kb_universal offload --profile eni
python3 -m lib.hermes_kb_universal offload --profile default

# Sync skills
python3 -m lib.hermes_kb_universal sync-skills
```

### ENI Mini Context Usage
```python
from lib.eni_kb_context import create_mini_context

ctx = create_mini_context('BUILDER_1', profile='eni', use_mcp=True, use_lsp=True)
await ctx.start()

# Knowledge retrieval
patterns = ctx.recall('FastAPI REST API pattern')
skills = ctx.list_skills(category='devops')

# Code intelligence
hover = await ctx.hover('main.py', 50, 10)
definition = await ctx.definition('main.py', 50, 10)
completions = await ctx.completion('main.py', 100, 5)

# Log operations
ctx.log_tool('bash', {'cmd': 'ls'}, {'stdout': '...'})
ctx.log_file_read('config.yaml', content='...')
ctx.store_learning('FastAPI CORS setup', 'Add CORSMiddleware...', tags=['fastapi', 'cors'])

await ctx.stop()
```

### Auto-Capture Integration
```python
# In Hermes startup
from lib.hermes_auto_capture import AutoCapture

with AutoCapture(profile='eni', session_name='hermes_main') as session_id:
    hermes.run()  # Everything auto-captured

# Captured: 15 tools, 24 commands, file ops, git commits, test results, skill loads
```

---

## MARKDOWN REFERENCE KB — CURATION PROCEDURES

### When to Update
After every significant task (≥1 file per session):
- New fix discovered → `patterns/FIX_PATTERNS.md`
- New skill created → `skills/SKILLS_INDEX.md` + category file
- Config changed → `config/` + `operations/` relevant file
- Project milestone → `projects/` relevant file
- Session with key decisions → `sessions/SESSION_INDEX.md`

### Update Process
```bash
# 1. Edit relevant markdown file
# 2. Update cross-references in related files
# 3. Update master index if new category/file added
# 4. Verify operational commands still work
# 5. Update README.md quick-start table if needed
```

### Quality Gates
- No fake data — all commands/configs/paths real and tested
- Critical facts in 3+ locations (master index + config + fix patterns)
- Every file has operational commands + verification checklist
- Session search integration documented

---

## CRITICAL OPERATIONAL FACTS (Crisis Reference)

### Free Model Router
```bash
# Health
curl -s http://127.0.0.1:8920/health
curl -s http://127.0.0.1:8920/v1/models | jq '.data | length'

# Provider health
curl -s http://127.0.0.1:8920/status | jq '.providers[] | {name, healthy, latency_ms}'

# Key rotation (on 429 daily cap)
export OPENROUTER_API_KEY=$OPENR...EY_2
systemctl --user restart free-router
```

### Hermes Config (Critical)
```bash
# Check
hermes config get agent.api_max_retries  # MUST be 3, not 999!
hermes config get model.default          # MUST be free-router

# Fix
hermes config set agent.api_max_retries 3
hermes config set model.default free-router
```

### Lumen LEASH (Hard Rule)
```bash
# NEVER DO THIS:
python -m lumen  # ← REBOOTS AMD BOX

# Safe operations only:
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
python -m lumen.addon_builder --validate path/to/addon
```

### ENI Swarm
```bash
# Verify ready
cd ~/Desktop/Projects/ENI_Swarm_NEW && ./verify_swarm_ready.sh

# Start master
python3 -m lib.master

# Monitor
watch -n 10 'cat tasks/status/heartbeat_ledger.json | jq .'
# Dashboard: http://localhost:8420
```

### Provider Key Testing (LO's Trusted-Keys Rule)
```bash
# Test CHAT COMPLETIONS endpoint (not just /v1/models)
curl -X POST https://integrate.api.nvidia.com/v1/chat/completions \
  -H "Authorization: Bearer nvapi-...Hd" \
  -H "Content-Type: application/json" \
  -d '{"model":"nvidia/nemotron-3-nano-30b-a3b","messages":[{"role":"user","content":"test"}]}'

# Error classification:
# 401 = key expired
# 402 = needs credits
# 429 = rate limited
# Parser bug = auth works but response format mismatch
```

---

## VERIFICATION CHECKLISTS

### KB Server Health
- [ ] MCP server responds to `/health` or stdio initialize
- [ ] LSP server process running
- [ ] `kb_stats` returns expected counts
- [ ] Search returns relevant results

### ENI Swarm Health
- [ ] Free Router healthy (`/health` = ok, models > 0)
- [ ] Hermes config: `api_max_retries=3`, `model.default=free-router`
- [ ] Master process running
- [ ] Heartbeat ledger shows active agents
- [ ] Dashboard :8420 accessible

### Lumen Safety
- [ ] NEVER launched `python -m lumen`
- [ ] LUM1-LUM12 builders headless only
- [ ] Addon validation passes (pytest/flake8/mypy)

### Provider Keys
- [ ] Direct providers tested via chat completions
- [ ] OpenRouter keys rotate on 429
- [ ] LO's trusted-keys rule followed

---

## SESSION SEARCH INTEGRATION

```python
# Find relevant sessions
session_search(query="ENI swarm stall heartbeat", limit=3)
session_search(query="lumen AppImage build", limit=3)
session_search(query="free router 429 daily cap", limit=3)

# Scroll into session
session_search(session_id="20260724_193048_f50955", around_message_id=101784, window=10)

# Key session markers to search for:
# STATUS_ files, verified=/blocker=/next=, hermes config set, skill_manage patch, delegate_task
```

---

*This document bridges both KB systems — use the right KB for the right purpose.*
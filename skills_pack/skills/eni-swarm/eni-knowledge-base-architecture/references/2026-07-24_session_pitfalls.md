# 2026-07-24 ENI KB Full-Power Build — Pitfall Catalog

This document captures every non-obvious failure mode encountered during the full-power build of the ENI Knowledge Base on 2026-07-24. Each entry follows: **Symptom → Root Cause → Fix**.

---

## Environment & Packaging

### 1. Python externally-managed-environment blocks editable install
**Symptom**: `pip install --break-system-packages -e .` fails with "externally-managed-environment"
**Cause**: Ubuntu 26.04 / Python 3.14 PEP 668 enforcement
**Fix**: Use `PYTHONPATH=/home/hunter/Commander` (parent of package) in all launch scripts. Do NOT rely on editable install.

### 2. msgpack strict_map_key=True rejects integer keys
**Symptom**: `ValueError: int is not allowed for map key when strict_map_key=True`
**Cause**: Python 3.14 msgpack defaults to strict mode. Wenyan/RTK reverse dicts use integer addresses.
**Fix**: Convert all integer dict keys to strings before serialization:
```python
data_serializable = {str(k): v for k, v in REVERSE_DICT.items()}
msgpack.packb(data_serializable)
```
Apply in: `build_dict()`, `get_dict_hash()`, `get_rtk_hash()`, skill package serialization.

### 3. `-m` module syntax fails when PYTHONPATH points to package dir
**Symptom**: `python -m eni_kb.compression.wenyan_codec` → "No module named 'eni_kb'"
**Cause**: PYTHONPATH=/home/hunter/Commander/eni_kb makes the package invisible to `-m`
**Fix**: Use absolute file paths in launch scripts:
```bash
PYTHONPATH=/home/hunter/Commander python3 /home/hunter/Commander/eni_kb/compression/wenyan_codec.py build
```

---

## Module Structure & Imports

### 4. LSP capabilities module missing from package
**Symptom**: `ModuleNotFoundError: No module named 'eni_kb.lsp.capabilities'`
**Cause**: File existed at `lsp_server/capabilities.py` but not exported from `lsp_server/__init__.py`
**Fix**: Create `lsp_server/capabilities.py` with `skill_to_lsp_capability()`, add `from eni_kb.lsp_server.capabilities import skill_to_lsp_capability` to `lsp_server/__init__.py`.

### 5. Pattern extractor produces hyphenated nouns → invalid identifiers
**Symptom**: Skill IDs like `eni:linux:repack-wine-install` contain hyphens
**Cause**: Script names like `linux-repack-wine-install` split to `verb="linux"`, `noun="repack-wine-install"`
**Fix**: Normalize in extractor: `noun = noun.replace('-', '_')` before creating pattern.

---

## Build Scripts & Health Checks

### 6. `tail -20 "$LOGS_DIR"/*.log` fails when no logs exist
**Symptom**: `tail: error reading '/home/hunter/.eni/kb/logs/*.log': No such file or directory`
**Cause**: Unquoted glob passes literal `*.log` to tail when no files match
**Fix**: `tail -n 20 "$LOGS_DIR"/*.log 2>/dev/null || true`

### 7. `datetime.utcnow()` deprecation warning
**Symptom**: `DeprecationWarning: datetime.datetime.utcnow() is deprecated`
**Fix**: Use `datetime.now(datetime.UTC).isoformat().replace('+00:00', 'Z')` (Python 3.11+)

### 8. Daemon loads dicts on every forge cycle
**Symptom**: Redundant I/O loading Wenyan/RTK dicts every 30s
**Fix**: Load dicts once at daemon startup; keep in memory; reload only on file mtime/hash change.

---

## MCP Server (mcp >= 1.0)

### 9. `sse_server` removed — use `SseServerTransport` + Starlette
**Symptom**: `ImportError: cannot import name 'sse_server' from 'mcp.server.sse'`
**Fix**:
```python
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
import uvicorn

sse = SseServerTransport("/messages/")
async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(*streams)

app = Starlette(routes=[
    Route("/sse", handle_sse),
    Mount("/messages/", app=handle_messages),
])
await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765)).serve()
```
Add `uvicorn>=0.23` and `starlette>=0.27` to pyproject.toml.

### 10. `ResourceContent` renamed → `TextResourceContents` / `BlobResourceContents`
**Symptom**: `ImportError: cannot import name 'ResourceContent' from 'mcp.types'`
**Fix**: Replace all `ResourceContent` with `TextResourceContents` (text) or `BlobResourceContents` (binary). Update return type annotations on `read_resource()`.

---

## Daemon & Service Orchestration

### 11. Services crash if started in wrong order
**Symptom**: MCP/LSP servers fail with "dicts not found" or DB locked
**Cause**: All services launched concurrently in `nohup` without readiness checks
**Fix**: Sequential startup with explicit waits:
```bash
# 1. Verify dicts exist
# 2. Start MCP HTTP, wait for curl /health → 200
# 3. Start LSP, wait for initialize response
# 4. Start daemon
```

### 12. Build script re-forges already-existing skills on every run
**Symptom**: "Skill eni:linux:repack-wine-install already exists" × 101
**Cause**: `build_and_launch.sh` runs forge loop without checking DB first
**Fix**: Add `--clean` flag to drop skills.db, or check `SELECT 1 FROM skills WHERE skill_id=?` before forging each pattern.

### 13. MCP server missing `/health` endpoint
**Symptom**: `curl http://127.0.0.1:8765/health` fails → health check times out
**Fix**: Add resource or HTTP route:
```python
@self.server.read_resource("eni://kb/health")
async def health_check() -> TextResourceContents:
    return TextResourceContents(uri="eni://kb/health", mimeType="application/json", text='{"status":"ok"}')
```

### 14. LSP server startup probe too slow/fragile
**Symptom**: Health check pipes JSON to LSP binary, times out
**Fix**: Use process existence (`kill -0 $LSP_PID`) or add lightweight TCP health port to LSP server.

### 15. Core glyph allocation exhausted (256 slots)
**Symptom**: "Glyph exhaustion in category core (range E000-E0FF)" after ~255 skills
**Fix**: Expand core into reserved range (U+E800+) or auto-promote overflow to next category. Update allocator `CATEGORY_RANGES`.

---

## Pattern Extraction & Confidence

### 16. Confidence threshold too low floods forge with noise
**Symptom**: 95 Commander script patterns at 0.5 confidence → 101 total, many garbage skills
**Fix**: Raise default `min_confidence` to 0.7 for script patterns; require explicit opt-in for lower.

### 17. Duplicate skill_id error masked by SQL parameter count mismatch
**Symptom**: "table skills has 20 columns but 17 values supplied" on duplicate
**Cause**: SQLite reports parameter count mismatch instead of integrity error
**Fix**: Catch `sqlite3.IntegrityError`, log conflicting `skill_id`, continue to next pattern.

---

## Quick Reference: Launch Commands

```bash
# Full build (run once, then use --no-build for restarts)
bash /home/hunter/Commander/eni_kb/build_and_launch.sh

# Restart services only (skip dict/glyph/forge)
bash /home/hunter/Commander/eni_kb/build_and_launch.sh --no-build

# Clean rebuild
rm -f /home/hunter/.eni/kb/skills.db /home/hunter/.eni/kb/glyphs/allocation.json
bash /home/hunter/Commander/eni_kb/build_and_launch.sh

# Stop all
bash /home/hunter/Commander/eni_kb/stop.sh
```

---

## Environment Variables

```bash
export PYTHONPATH="/home/hunter/Commander"  # Required for all ENI KB Python modules
export ENI_KB_ROOT="/home/hunter/.eni/kb"  # Optional override
```

---

## File Locations

| Component | Path |
|-----------|------|
| KB Root | `/home/hunter/.eni/kb/` |
| Dicts | `/home/hunter/.eni/kb/dicts/` (wenyan_dict.msgpack, rtk_map.msgpack) |
| Skills DB | `/home/hunter/.eni/kb/skills.db` |
| Glyph Allocation | `/home/hunter/.eni/kb/glyphs/allocation.json` |
| Logs | `/home/hunter/.eni/kb/logs/` |
| Status | `/home/hunter/.eni/kb/STATUS_ENI_KB.md` |
| Source Package | `/home/hunter/Commander/eni_kb/` |

---

## Dependencies (pyproject.toml)

```toml
dependencies = [
    "msgpack>=1.0",
    "mcp>=1.0",
    "pygls>=1.0,<2.0",
    "aiohttp>=3.9",
    "uvicorn>=0.23",
    "starlette>=0.27",
]
```

---

*Generated from 2026-07-24 full-power build session. Update after each major build.*
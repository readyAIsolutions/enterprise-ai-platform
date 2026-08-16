# Session Notes: Masterchief → Demiurge Marketing Rename

**Date**: 2026-07-24  
**Project**: `/home/hunter/Desktop/Demiurge Marketing`  
**Scope**: Full project rename (package, imports, config, env, DB, CLI, n8n, tests, docs)

## Patterns Encountered

### 1. Package & Import Rename
- Directory: `masterchief/` → `demiurge_mkt/`
- PyPI name: `masterchief` → `demiurge_mkt` (underscores for package, hyphens for distribution)
- CLI command: `masterchief` → `demiurge_mkt`
- Imports: `from masterchief.config` → `from demiurge_mkt.config`

### 2. Config Files
- `config/masterchief.yaml` → `config/demiurge_mkt.yaml`
- `config/masterchief.example.yaml` → `config/demiurge_mkt.example.yaml`
- Config loader default path in `config.py`: updated `user_path` default

### 3. Environment Variables
- Prefix: `MASTERCHIEF_` → `DEMIURGE_MKT_`
- All 50+ env vars in `.env`, `.env.example`, config loader `secret_map`, `_env_override()`

### 4. Database Schema References
- PostgreSQL schema: `masterchief` → `demiurge_mkt`
- Connection URL: `postgresql://masterchief:***@localhost:5432/masterchief` → `postgresql://demiurge_mkt:***@localhost:5432/demiurge_mkt`
- SQL in n8n workflows: 19 JSON files with `masterchief.prospects`, `masterchief.bookings`, etc.

### 5. n8n Workflow JSON (19 files)
- Database queries: `FROM masterchief.table` → `FROM demiurge_mkt.table`
- Webhook paths: `/masterchief/...` → `/demiurge_mkt/...`
- Workflow tags: `"masterchief"` → `"demiurge_mkt"`
- Auth headers: `MASTERCHIEF_JWT_TOKEN` → `DEMIURGE_MKT_JWT_TOKEN`

### 6. Python Class Names (Critical)
**Automated replace broke PascalCase:**
- `DemiurgeMarketingConfig` → `Demiurge MarketingConfig` (SPACE INSERTED!)
- `DemiurgeMarketingAgent` → `Demiurge MarketingAgent`
- Had to manually patch: `config.py`, `agent.py`, `cli.py`, `models/router.py`, `voice/provider.py`, `messaging/telegram_bot.py`, `messaging/command_parser.py`, `scripts/health_check.py`

### 7. Test Files (7 files)
Type hints broken: `Demiurge MarketingConfig` → `DemiurgeMarketingConfig`
- `tests/conftest.py`, `tests/test_agent.py`, `tests/test_config.py`, `tests/test_smoke.py`

### 8. Server Scripts
- `app/serve.py`: imports, env vars, config loader
- `admin/serve.py`: minimal (just branding)
- `bots/run_client_bot.py`: imports, env vars
- `bots/client_bot.py`: imports, env vars, branding
- `scripts/health_check.py`: imports

### 9. Documentation
- `STATUS_MASTERCHIEF.md` → `STATUS_DEMIURGE_MKT.md`
- Launch commands updated in status file

## Replacement Patterns That Worked

```python
# Order matters - do package rename first, then these:
replacements = [
    # 1. Imports (most critical)
    (r"from masterchief\.", "from demiurge_mkt."),
    (r"import masterchief\.", "import demiurge_mkt."),
    (r"masterchief\.", "demiurge_mkt."),  # catches remaining attribute access
    
    # 2. Config files
    (r"masterchief\.yaml", "demiurge_mkt.yaml"),
    (r"masterchief\.example\.yaml", "demiurge_mkt.example.yaml"),
    
    # 3. Env vars
    (r"MASTERCHIEF_", "DEMIURGE_MKT_"),
    
    # 4. Database schema (in SQL/JSON)
    (r"masterchief\.", "demiurge_mkt."),
    
    # 5. String literals
    (r"'masterchief'", "'demiurge_mkt'"),
    (r'"masterchief"', '"demiurge_mkt"'),
    
    # 6. Paths
    (r"masterchief/", "demiurge_mkt/"),
]
```

## Verification Commands Run

```bash
# 1. Reinstall
pip install -e .

# 2. CLI works
demiurge_mkt version
demiurge_mkt config-check

# 3. Servers start
timeout 5 demiurge_mkt serve
timeout 5 python app/serve.py
timeout 5 python admin/serve.py

# 4. Tests collect (0 import errors)
pytest --collect-only

# 5. No old references remain
grep -r "masterchief" --include="*.py" --include="*.yaml" --include="*.json" . | grep -v ".venv" | grep -v "__pycache__"
```

## Time Breakdown
- Discovery & inventory: 5 min
- Directory rename & pyproject.toml: 3 min
- Automated batch replace (68 files): 2 min
- Config file rename: 1 min
- Manual PascalCase class fixes (8 files): 5 min
- Test file fixes (4 files): 3 min
- Verification & test run: 5 min
- **Total: ~24 minutes**

## Key Lesson
**Always fix PascalCase class names BEFORE running tests.** The automated `oldname.` → `newname.` replacement inserts spaces in `OldNameClass` → `NewName Class` because the regex matches the dot after the class name in `OldNameClass.method()`. Use word boundaries or do class names manually.
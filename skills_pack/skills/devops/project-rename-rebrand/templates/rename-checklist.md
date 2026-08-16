# Project Rename Verification Checklist

**Project**: _______________  **Old Name**: _______________  **New Name**: _______________  **Date**: _______________

## Pre-Rename Inventory
- [ ] Package directory: `oldname/` exists
- [ ] pyproject.toml: name, scripts, package find
- [ ] Config files: `config/oldname.yaml`, `config/oldname.example.yaml`
- [ ] Env prefix: `OLDNAME_` in config loader, .env, .env.example
- [ ] Database schema: `oldname.` in SQL/JSON
- [ ] CLI command: `oldname` in `[project.scripts]`
- [ ] Test imports: `from oldname.*` in tests/
- [ ] Docs/Status files referencing old name

## Rename Execution
- [ ] 1. `mv oldname newname` (package directory)
- [ ] 2. pyproject.toml updated (name, scripts, include)
- [ ] 3. Batch replace: imports, config refs, env prefix, DB schema
- [ ] 4. Config files renamed: `oldname.yaml` → `newname.yaml`
- [ ] 5. Config loader default path updated
- [ ] 6. .env / .env.example updated (prefix + comments)
- [ ] 7. n8n workflow JSON SQL updated
- [ ] 8. Server scripts, CLI, entry points updated
- [ ] 9. Test files fixed (type hints, class names)
- [ ] 10. Status/docs files renamed/updated

## Post-Rename Verification

### Installation
- [ ] `pip install -e .` succeeds
- [ ] Package imports: `from newname.config import ...` works

### CLI
- [ ] `newname version` → prints version
- [ ] `newname config-check` → loads config from `config/newname.yaml`
- [ ] `newname serve` → starts without import errors
- [ ] `newname migrate` → runs (if DB configured)
- [ ] `newname test` → collects tests

### Servers
- [ ] `python app/serve.py` → starts on :8000
- [ ] `python admin/serve.py` → starts on :8200
- [ ] `python bots/run_client_bot.py` → starts (if token set)

### Tests
- [ ] `pytest --collect-only` → 0 import errors
- [ ] `pytest tests/ -x` → core tests pass (pre-existing failures OK)

### Config & Env
- [ ] `config/newname.yaml` loads as user config
- [ ] `DEMIURGE_MKT_` (new prefix) env vars recognized
- [ ] No `OLDNAME_` references in source (grep check)

### Database
- [ ] Schema references use `newname.` in all SQL
- [ ] Migration scripts updated

### Cleanup
- [ ] No `oldname` directory remains
- [ ] No `oldname.yaml` in config/
- [ ] No `OLDNAME_` in .env, .env.example
- [ ] No `from oldname` imports in any .py
- [ ] `grep -r "oldname" . --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.git` → 0 results in source

## Sign-Off
- [ ] All verification items pass
- [ ] Known pre-existing test failures documented
- [ ] Team notified of new CLI command name

**Verified by**: _______________  **Date**: _______________
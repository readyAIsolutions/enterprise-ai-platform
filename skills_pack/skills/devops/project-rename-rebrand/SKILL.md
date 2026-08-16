---
name: project-rename-rebrand
description: Systematic rename/rebrand of a Python project across all file types — package name, imports, config files, env vars, database schemas, CLI entry points, and test references.
trigger: User requests renaming a project (e.g., "rename everything from X to Y", "rebrand this project")
---

# Project Rename / Rebrand — Systematic Codebase Renaming

## When to Use
User asks to rename a project comprehensively — changing package name, imports, config files, environment variables, database references, CLI commands, and all internal references.

## Prerequisites
- Project uses a consistent naming pattern (package name, env prefix, DB schema all derive from same base name)
- Python project with standard structure (pyproject.toml, src/ or package/ dir, tests/, config/)

## Procedure

### 1. Discovery & Inventory
```bash
# Find all files referencing the old name
grep -r "oldname" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.json" --include="*.toml" --include="*.env*" --include="*.html" --include="*.js" --include="*.css" --include="*.sh" .
# Exclude .venv/, __pycache__/, .git/, build/, dist/
```

**Key patterns to track:**
- Package directory name
- `pyproject.toml`: `name`, `scripts`, `tool.setuptools.packages.find.include`
- Python imports: `from oldname.*`, `import oldname.*`
- Config filenames: `oldname.yaml`, `oldname.example.yaml`
- Env var prefix: `OLDNAME_` → `NEWNAME_`
- Database schema: `oldname.table` in SQL (often in n8n JSON workflows)
- CLI entry point name
- Status/docs files referencing old name

### 2. Execute Rename in Order

| Step | Action | Tool |
|------|--------|------|
| 1 | Rename package directory | `mv oldname newname` |
| 2 | Update `pyproject.toml` (name, scripts, package find) | `patch` |
| 3 | Batch-replace imports & references in all code/config | `execute_code` with regex |
| 4 | Rename config files | `mv config/oldname.yaml config/newname.yaml` |
| 5 | Update env var prefix in config loader & all files | `execute_code` |
| 6 | Update database schema references (SQL in JSON) | `execute_code` |
| 7 | Update server scripts, CLI, entry points | `patch` per file |
| 8 | Fix any syntax errors from automated replacement | Manual `patch` |
| 9 | Reinstall package & verify | `pip install -e .` |
| 10 | Run tests to catch regressions | `pytest` |

### 3. Regex Replacement Patterns (Python)

```python
replacements = [
    # Imports
    (r"from oldname\.", "from newname."),
    (r"import oldname\.", "import newname."),
    (r"oldname\.", "newname."),
    # Config files
    (r"oldname\.yaml", "newname.yaml"),
    (r"oldname\.example\.yaml", "newname.example.yaml"),
    # Env vars
    (r"OLDNAME_", "NEWNAME_"),
    # Database schemas
    (r"oldname\.", "newname."),
    # String literals
    (r"'oldname'", "'newname'"),
    (r'"oldname"', '"newname"'),
]
```

### 4. Common Pitfalls & Fixes

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Automated replace breaks PascalCase class names | `Demiurge MarketingConfig` (space inserted in `DemiurgeMarketingConfig`) | Manually patch all occurrences: `DemiurgeMarketingConfig`, `DemiurgeMarketingAgent` |
| Env var prefix in comments/docs missed | `.env` comments still show old prefix (`# MASTERCHIEF_...`) | Run replacement on `.env`, `.env.example`, and all docs |
| Database URLs with credentials | `postgresql://masterchief:***@localhost:5432/masterchief` | Replace both user and DB name in URL pattern |
| n8n workflow JSON SQL queries | `FROM masterchief.prospects` in 19 JSON files | Include JSON files in replacement sweep; update workflow tags too |
| Test fixtures using old config class | `Demiurge MarketingConfig` in type hints across 7 test files | Fix all test files after main replacement before running pytest |
| CLI entry point not updated | `masterchief` command not found | Update `pyproject.toml` `[project.scripts]` and `[tool.setuptools.packages.find]` |
| Config loader default path hardcoded | Still looks for `config/masterchief.yaml` | Update `load_config()` default `user_path` in `config.py` |
| Secret map in config loader uses old prefix | `_secret("MASTERCHIEF_API_KEY")` fails | Update `secret_map` dict in `_resolve_secrets()` |
| Status/docs files reference old name | `STATUS_MASTERCHIEF.md`, launch commands in docs | Rename status file, update all launch paths in docs |

### 5. Verification Checklist

- [ ] `pip install -e .` succeeds
- [ ] New CLI command works: `newname version`, `newname config-check`
- [ ] Servers start: `python app/serve.py`, `python admin/serve.py`
- [ ] Tests collect without import errors: `pytest --collect-only`
- [ ] Config loads from new YAML: `config/newname.yaml`
- [ ] Env vars use new prefix: `NEWNAME_*`
- [ ] No `oldname` references remain in source (grep check)

## References
- `references/rename-patterns.md` — Common naming patterns and their mappings
- `references/regex-cookbook.md` — Battle-tested regex for each file type

## Templates
- `templates/rename-checklist.md` — Printable checklist for manual verification
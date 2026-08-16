# Regex Cookbook for Project Renaming

## Python Files (.py)

### Imports
```python
# from oldname.module import X
re.sub(r'\bfrom\s+oldname\.', 'from newname.', content)

# import oldname.module
re.sub(r'\bimport\s+oldname\.', 'import newname.', content)

# oldname.something (attribute access)
re.sub(r'\boldname\.', 'newname.', content)
```

### Type Hints & Class References
```python
# Optional[OldNameConfig]
re.sub(r'\bOldName([A-Z]\w*)', r'NewName\1', content)  # PascalCase classes

# oldname_config (snake_case vars)
re.sub(r'\boldname_', 'newname_', content)
```

### Strings & Comments
```python
# "oldname" or 'oldname' as string literal
re.sub(r'[\'"\']oldname[\'"\']', lambda m: m.group(0).replace('oldname', 'newname'), content)

# oldname.yaml
re.sub(r'oldname\.ya?ml', 'newname.yaml', content)
```

## Config Files (.yaml, .yml)

```yaml
# Keys and values
re.sub(r'\boldname:', 'newname:', content)  # YAML keys
re.sub(r'oldname\.yaml', 'newname.yaml', content)
re.sub(r'oldname\.example\.yaml', 'newname.example.yaml', content)
```

## Environment Files (.env, .env.example)

```bash
# OLDNAME_VAR=value
re.sub(r'\bOLDNAME_', 'NEWNAME_', content)

# Comments: # OLDNAME_VAR=...
re.sub(r'#\s*OLDNAME_', '# NEWNAME_', content)
```

## TOML Files (pyproject.toml)

```toml
# name = "oldname"
re.sub(r'name\s*=\s*"oldname"', 'name = "newname"', content)

# oldname = "oldname.cli:main"
re.sub(r'\boldname\s*=', 'newname =', content)  # careful: only in scripts section

# include = ["oldname*"]
re.sub(r'include\s*=\s*\[([^\]]*)oldname\*', r'include = [\1newname*', content)
```

## JSON Files (n8n workflows, package.json, etc.)

```json
# Database schema references: "FROM oldname.table"
re.sub(r'(["\'])oldname\.', r'\1newname.', content)

# Package name
re.sub(r'"name"\s*:\s*"oldname"', '"name": "newname"', content)

# Paths: "oldname/workflow.json"
re.sub(r'"oldname/', '"newname/', content)
```

## SQL (in JSON or .sql files)

```sql
-- Table references
re.sub(r'\boldname\.', 'newname.', content)

-- CREATE SCHEMA oldname
re.sub(r'CREATE SCHEMA\s+oldname\b', 'CREATE SCHEMA newname', content, flags=re.IGNORECASE)

-- postgresql://oldname:***@host/oldname
re.sub(r'//oldname:([^@]+)@([^/]+)/oldname', r'//newname:\1@\2/newname', content)
```

## Shell Scripts (.sh)

```bash
# Commands: oldname serve
re.sub(r'\boldname\s', 'newname ', content)

# Paths: ./oldname/script.py
re.sub(r'oldname/', 'newname/', content)

# Env: export OLDNAME_VAR
re.sub(r'\bOLDNAME_', 'NEWNAME_', content)
```

## HTML/JS/CSS (Frontend)

```html
<!-- Text content -->
re.sub(r'>oldname<', '>newname<', content)

<!-- Paths: /oldname/ or oldname.js -->
re.sub(r'["\'/]oldname/', r'\1newname/', content)

<!-- CSS classes: .oldname-card -->
re.sub(r'\.oldname-', '.newname-', content)
```

## Safety Tips

1. **Always test first**: Run with `re.findall()` to preview matches
2. **Use word boundaries**: `\b` prevents partial matches
3. **Process in order**: Directory rename → config files → code → tests → docs
4. **Verify with grep**: `grep -r "oldname" --include="*.py" . | grep -v ".venv" | grep -v "__pycache__"`
5. **Check PascalCase separately**: Class names need different regex than snake_case
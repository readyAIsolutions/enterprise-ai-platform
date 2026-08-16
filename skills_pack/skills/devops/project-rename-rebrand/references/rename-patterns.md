# Common Naming Patterns in Python Projects

When renaming a project, these patterns typically all derive from the base name:

## Base Name → Derived Forms

| Base | Package Dir | PyPI Name | Env Prefix | DB Schema | Config File | CLI Command |
|------|-------------|-----------|------------|-----------|-------------|-------------|
| `myapp` | `myapp/` | `myapp` | `MYAPP_` | `myapp` | `myapp.yaml` | `myapp` |
| `my-app` | `my_app/` | `my-app` | `MYAPP_` | `myapp` | `my_app.yaml` | `my-app` |
| `MyApp` | `myapp/` | `myapp` | `MYAPP_` | `myapp` | `myapp.yaml` | `myapp` |
| `super_tool` | `super_tool/` | `super-tool` | `SUPER_TOOL_` | `super_tool` | `super_tool.yaml` | `super_tool` |

## Transformation Rules

- **Package/import name**: lowercase, underscores → `my_app`
- **PyPI/distribution name**: lowercase, hyphens → `my-app`
- **Env var prefix**: UPPERCASE, underscores → `MYAPP_`
- **Database schema**: lowercase, underscores → `myapp`
- **Config file**: lowercase, underscores + `.yaml` → `myapp.yaml`
- **CLI command**: matches PyPI name typically → `my-app`

## Files to Check Per Pattern

### Package/Import Name (`myapp`)
- Directory: `myapp/`
- Imports: `from myapp.config import ...`, `import myapp.models`
- pyproject.toml: `name = "myapp"`, `include = ["myapp*"]`
- `__init__.py` version/exports

### Env Prefix (`MYAPP_`)
- Config loader: `prefix = "MYAPP_"`
- Secret map keys: `"MYAPP_API_KEY"`
- `.env` / `.env.example` files
- Documentation/comments

### Database Schema (`myapp`)
- SQL in code: `FROM myapp.prospects`
- n8n workflow JSON: `"query": "SELECT * FROM myapp.bookings"`
- Migration files
- Repository layer queries

### Config File (`myapp.yaml`)
- Config loader default path
- `.gitignore` entry
- Documentation references

### CLI Command (`myapp`)
- pyproject.toml `[project.scripts]`: `myapp = "myapp.cli:main"`
- Shell aliases/completions
- README usage examples
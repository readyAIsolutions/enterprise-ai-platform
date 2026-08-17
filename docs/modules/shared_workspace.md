# Module: `shared_workspace`

- Category: Agent Workflow · priority 2
- Version: 1.0.0
- Purpose: Live multi-editor workspace: lock, merge-safe write, history, redact-before-share.
- Skill: `eni-module-shared_workspace` (ICM stages) in skills_pack/skills/eni-modules/shared_workspace/

## What it does
Shared Workspace module — live multi-editor collaboration (from transcript).

Implements the shared, live, versioned workspace described in the pulled
"Multiplayer AI" transcript: concurrent multi-editor writes with lock + merge
safety, an append-only queryable session history, and siloed/redact-before-share
handling for private values.

## Key API (facade methods)
health_check, history, initialize, list, lock, query, read, shutdown, unlock, write

## Tests
```bash
python3 -m pytest modules/shared_workspace/tests -q
```

## Import
```python
from enterprise.modules.shared_workspace import create_shared_workspace_module
m = create_shared_workspace_module()
```

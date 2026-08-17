# Module: `kb_bridge`

- Category: Legacy Core · priority 29
- Version: 1.0.0
- Purpose: ENI Knowledge Base OS Module
- Skill: `eni-module-kb_bridge` (ICM stages) in skills_pack/skills/eni-modules/kb_bridge/

## What it does
ENI Knowledge Base OS Module

Enterprise-grade wrapper around Hermes KB Universal, providing
structured CRUD, search, vector search, metrics, and health checks
as a registered Platform Kernel module.

Exports:
  ENIKBModule        — @module-decorated Module subclass
  KnowledgeBaseBridge — Full KB wrapper with event publishing
  KBHealthCheck      — DB connectivity health verification

Version: 1.0.0
Python: 3.10+

## Key API (facade methods)
bridge, health_check, health_checker, initialize, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/kb_bridge/tests -q
```

## Import
```python
from enterprise.modules.kb_bridge import create_kb_bridge_module
m = create_kb_bridge_module()
```

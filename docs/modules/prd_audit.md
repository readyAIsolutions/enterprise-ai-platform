# Module: `prd_audit`

- Category: Legacy Core · priority 47
- Version: 1.0.0
- Purpose: prd_audit — PRD-gated build workflow: write the PRD, audit it with a second
- Skill: `eni-module-prd_audit` (ICM stages) in skills_pack/skills/eni-modules/prd_audit/

## What it does
prd_audit — PRD-gated build workflow: write the PRD, audit it with a second
instance, then gate execution until it clears a threshold. Grounded in
JEVanClief's "I'm Building a Custom Front End for Claude Code" (J2GLzkaUrBc).

## Key API (facade methods)
audit, audit_markdown, gate, gate_document, gate_markdown, health_check, initialize, parse_prd, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/prd_audit/tests -q
```

## Import
```python
from enterprise.modules.prd_audit import create_prd_audit_module
m = create_prd_audit_module()
```

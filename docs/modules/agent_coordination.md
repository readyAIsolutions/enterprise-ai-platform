# Module: `agent_coordination`

- Category: Legacy Core · priority 7
- Version: 1.0.0
- Purpose: Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling,
- Skill: `eni-module-agent_coordination` (ICM stages) in skills_pack/skills/eni-modules/agent_coordination/

## What it does
Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling,
shared knowledge, conflict resolution, verification, and fault tolerance.

Version: 1.0.0

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/agent_coordination/tests -q
```

## Import
```python
from enterprise.modules.agent_coordination import create_agent_coordination_module
m = create_agent_coordination_module()
```

# Module: `production_agent_hardening`

- Category: Build Quality · priority 3
- Version: 1.0.0
- Purpose: Demo->production hardening linter across 8 scored dimensions + systems loops.
- Skill: `eni-module-production_agent_hardening` (ICM stages) in skills_pack/skills/eni-modules/production_agent_hardening/

## What it does
Production Agent Hardening module — ship a demo agent that survives production.

Implements the production-readiness lessons from two pulled JE Van Clief
transcripts:

  * "Two Engineers on Why Your Agent Demo Will Not Survive Production"
    — observability ("understand how things are running"), error handling,
      retries, secrets, cost bounds, and the "demo trap" of canned/hardcoded
      behavior that does not generalize.

  * "Systems Thinking for People Who Build With AI"
    — a systems lens (feedback loops, coupling, emergent behavior) on why
      ~95% of agentic AI initiatives never make real-world impact (as cited
      from MIT Project Nanda), and how to reason about the whole system
      rather than only the happy path.

Export surface:
  * harden_spec — score an agent spec across hardening dimensions.
  * run_readiness_check — CI-grade production gate.
  * systems_feedback_loop — feedback-loop / coupling analysis.

## Key API (facade methods)
harden, health_check, initialize, readiness, shutdown, systems

## Tests
```bash
python3 -m pytest modules/production_agent_hardening/tests -q
```

## Import
```python
from enterprise.modules.production_agent_hardening import create_production_agent_hardening_module
m = create_production_agent_hardening_module()
```

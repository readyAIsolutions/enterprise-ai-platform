# Module: `production_hardening`

- Category: Build Quality · priority 3
- Version: 1.0.0
- Purpose: Operational hardening checks for shipping an agent into production.
- Skill: `eni-module-production_hardening` (ICM stages) in skills_pack/skills/eni-modules/production_hardening/

## What it does
Production Hardening module — production-readiness for ML / agent systems.

Grounded in the real pulled JE Van Clief transcript
"data/transcripts/JEVanClief/ezRtp6K6zwE.md" — "Two Engineers on Why Your
Agent Demo Will Not Survive Production" — a 57-minute NLP Logix interview
with Anton Corner (Director of Data & AI Engineering) and Ryan Nent
(Software Engineer).  The episode's thesis is that a demo and a sustained
production system live under different constraints: the invisible 80% of
the work (governance, monitoring, runtime, databases, monitoring tooling)
is what makes a system operate reliably, and shipping a one-off demo
over-enthusiastically is exactly how production fails.

Export surface:
  * ProductionReadinessRule / ReadinessReport / SystemProfile — data model.
  * assess() / assess_answers() — readiness scoring & gating.
  * Run-assurance helpers: check_deterministic_output, detect_drift,
    circuit_breaker_state, retry_plan, human_escalation_required.
  * ProductionHardeningModule — the ENI platform Module wrapper.
  * create_production_hardening_module(config) — factory used by the platform.

## Key API (facade methods)
assess, assess_answers, breaker, categories, check_determinism, check_drift, escalation, health_check, initialize, retry, rules, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/production_hardening/tests -q
```

## Import
```python
from enterprise.modules.production_hardening import create_production_hardening_module
m = create_production_hardening_module()
```

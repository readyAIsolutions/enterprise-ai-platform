# Module: `engineering_tradeoff`

- Category: Build Quality · priority 3
- Version: 1.0.0
- Purpose: Structured tradeoff scoring for engineering decisions.
- Skill: `eni-module-engineering_tradeoff` (ICM stages) in skills_pack/skills/eni-modules/engineering_tradeoff/

## What it does
Engineering Tradeoff module — a satisficing (not 'best'-maximising) engine.

Grounded in the real pulled JE Van Clief transcript
"data/transcripts/JEVanClief/-YursW-UIoY.md" — "A Pagani, a Toyota, and Why
'Best' Is a Trap in AI". The thesis is that chasing the absolute "best" is a
trap: "best becomes relative" and the right answer comes from "figuring out
your actual need". The $5M Pagani Zonda is the absolute best on paper, but
the cheap, reliable Toyota that satisfies your real constraints is the
satisficing winner.

Export surface:
  * TradeoffEngine  — weighted multi-criteria satisficing decision engine.
  * Option/Constraint/Dimension — the data model for candidates & hard rules.
  * TradeoffResult  — ranking + absolute best vs satisficing winner + tradeoffs.
  * EngineeringTradeoffModule — the ENI platform Module wrapper.
  * create_engineering_tradeoff_module(config) — factory used by the platform.

## Key API (facade methods)
dimensions, evaluate, health_check, initialize, pick_satisficing, shutdown

## Tests
```bash
python3 -m pytest modules/engineering_tradeoff/tests -q
```

## Import
```python
from enterprise.modules.engineering_tradeoff import create_engineering_tradeoff_module
m = create_engineering_tradeoff_module()
```

---
name: eni-module-engineering_tradeoff
description: Operate the ENI Enterprise `engineering_tradeoff` module (Build Quality) — Structured tradeoff scoring for engineering decisions. Use when working with engineering_tradeoff in the Enterprise Platform.
---

# Module skill: engineering_tradeoff

- Category: Build Quality (priority 3)
- Version: 1.0.0
- Purpose: Structured tradeoff scoring for engineering decisions.

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
  * EngineeringTradeoffMo

## Key API (facade methods on the @module class)
- dimensions\n- evaluate\n- health_check\n- initialize\n- pick_satisficing\n- shutdown

## Use
Import via:
```python
from enterprise.modules.engineering_tradeoff import create_engineering_tradeoff_module
m = create_engineering_tradeoff_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/engineering_tradeoff/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

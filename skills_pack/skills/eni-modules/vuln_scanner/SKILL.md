---
name: eni-module-vuln_scanner
description: Operate the ENI Enterprise `vuln_scanner` module (Legacy Core) — ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style). Use when working with vuln_scanner in the Enterprise Platform.
---

# Module skill: vuln_scanner

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style).

## What it does
ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style).

Local, stdlib-only, black-box vulnerability scanning of LLM endpoints using
deterministic heuristic probes (keywords / regex / entropy). Each probe scores
model responses in 0..1 (higher = more vulnerable). Mirrors the ``eval_gate``
and ``model_security`` philosophy of fully unit-testable offline metrics.

Built-in probes:
  - PromptInjectionProbe   — output follows injected directives.
  - JailbreakProbe         — output drops guardrails.
  - PIILeakProbe           — output leaks emails / phones / SSNs / cards.
  - PromptExtractionProbe  — output reveals the system prompt.
  - ToxicityProbe          — output is toxic / profane.
  - DataExfilProbe         — output leaks secrets / credentials.
  - RefusalEchoPro

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.vuln_scanner import create_vuln_scanner_module
m = create_vuln_scanner_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/vuln_scanner/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

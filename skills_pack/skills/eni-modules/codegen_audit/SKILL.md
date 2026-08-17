---
name: eni-module-codegen_audit
description: Operate the ENI Enterprise `codegen_audit` module (Build Quality) — Audit generated code for correctness, security and quality signals. Use when working with codegen_audit in the Enterprise Platform.
---

# Module skill: codegen_audit

- Category: Build Quality (priority 3)
- Version: 1.0.0
- Purpose: Audit generated code for correctness, security and quality signals.

## What it does
codegen_audit — audit / evaluate AI-generated code.

Grounded in three JE Van Clief coding-tool-eval transcripts:

* ``_rtyhVD4v4A`` — "One of These AI Coding Tools Failed Completely": comparing
  AI coding tools on how well they understand a technical goal and produce
  working, modular code.  Feeds the static review (hallucinated imports,
  truncation/fidelity stubs) and the task-understanding evaluator (does the
  generated code satisfy the *stated requirements*, and are claimed features
  actually verified?).

* ``nWbM9Ye2sLw`` — "Open Claw Vibe Coded an App. Real Developers Read Every
  Line and Tell You What They Found": a line-by-line team security audit of a
  vibe-coded app.  Feeds the secret/credential, redundant-reinvention, and
  unverified-auth checks.

* ``5B6W2OGfxq0`` — "Ho

## Key API (facade methods on the @module class)
- analyze_dependencies\n- audit\n- evaluate_task\n- health_check\n- initialize\n- review\n- score\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.codegen_audit import create_codegen_audit_module
m = create_codegen_audit_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/codegen_audit/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

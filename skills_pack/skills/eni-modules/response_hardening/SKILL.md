---
name: eni-module-response_hardening
description: Operate the ENI Enterprise `response_hardening` module (Legacy Core) — ENI Response Hardening module. Use when working with response_hardening in the Enterprise Platform.
---

# Module skill: response_hardening

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Response Hardening module.

## What it does
ENI Response Hardening module.

Detects and repairs the Hermes agent output-length / truncation ceilings so long
outputs never dead-end on "Response truncated due to output length limit".

WHY THIS EXISTS
---------------
Hermes's agent/conversation_loop.py bounds truncation recovery with fixed retry
caps, the worst being `truncated_tool_call_retries < 1`: a tool call (e.g. a huge
delegate_task arguments JSON) that gets cut off at the model's output ceiling was
retried ONCE then hard-refused with "Response truncated due to output length
limit". This module raises every cap to 8 and injects a completion-gating prompt
for truncated tool calls so the model resumes the cut JSON instead of re-issuing
the same oversized call and re-dead-locking.

audit() -> inspect current values. repair() -> app

## Key API (facade methods on the @module class)
- apply_repair\n- get_audit\n- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.response_hardening import create_response_hardening_module
m = create_response_hardening_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/response_hardening/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

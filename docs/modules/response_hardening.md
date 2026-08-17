# Module: `response_hardening`

- Category: Legacy Core · priority 54
- Version: 1.0.0
- Purpose: ENI Response Hardening module.
- Skill: `eni-module-response_hardening` (ICM stages) in skills_pack/skills/eni-modules/response_hardening/

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

audit() -> inspect current values. repair() -> apply the fix (idempotent, backups
the original, refuses invalid syntax).

Version: 1.0.0

## Key API (facade methods)
apply_repair, get_audit, health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/response_hardening/tests -q
```

## Import
```python
from enterprise.modules.response_hardening import create_response_hardening_module
m = create_response_hardening_module()
```

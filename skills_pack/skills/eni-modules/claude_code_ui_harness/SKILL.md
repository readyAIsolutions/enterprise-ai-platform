---
name: eni-module-claude_code_ui_harness
description: Operate the ENI Enterprise `claude_code_ui_harness` module (Legacy Core) — Claude Code UI Harness — Enterprise Module wrapper. Use when working with claude_code_ui_harness in the Enterprise Platform.
---

# Module skill: claude_code_ui_harness

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Claude Code UI Harness — Enterprise Module wrapper.

## What it does
Claude Code UI Harness — Enterprise Module wrapper.

Grounded in the real pulled JE Van Clief transcript
``data/transcripts/JEVanClief/J2GLzkaUrBc.md`` — "I'm Building a Custom Front
End for Claude Code (Here's the Plan)". The transcript's plan is a custom
front-end UI to *control* Claude Code and *monitor / observe how the agents
are working*, tracking usage to favor the Anthropic subscription (vs raw API
cost), presenting the workspace as folders / a mind map / a web map, and
driving the build through a phased *PRD markdown* (early -> late) that a
second Claude can audit before being dropped into the workspace for Claude
Code to read and implement.

Export surface:
  * ClaudeCodeUiHarness   — network-free facade tying the workflow together.
  * SessionManager/ClaudeSession — control & ob

## Key API (facade methods on the @module class)
- audit_prd\n- build_prd\n- health_check\n- initialize\n- observe\n- render_prd\n- set_event_bus\n- shutdown\n- start_session\n- track_usage\n- usage_summary\n- view

## Use
Import via:
```python
from enterprise.modules.claude_code_ui_harness import create_claude_code_ui_harness_module
m = create_claude_code_ui_harness_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/claude_code_ui_harness/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

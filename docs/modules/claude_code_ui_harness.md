# Module: `claude_code_ui_harness`

- Category: Legacy Core · priority 17
- Version: 1.0.0
- Purpose: Claude Code UI Harness — Enterprise Module wrapper.
- Skill: `eni-module-claude_code_ui_harness` (ICM stages) in skills_pack/skills/eni-modules/claude_code_ui_harness/

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
  * SessionManager/ClaudeSession — control & observe Claude Code sessions.
  * UsageTracker/UsageRecord — usage tracking (subscription vs API savings).
  * WorkspaceNavigator/WorkspaceNode — folders / mind map / web map views.
  * PrdBuilder/PrdDocument/PlanPhase/PrdAuditor/AuditFinding — phased PRD + audit.
  * ClaudeCodeUiHarnessModule — ENI platform Module wrapper.
  * create_claude_code_ui_harness_module(config) — factory for the platform.

## Key API (facade methods)
audit_prd, build_prd, health_check, initialize, observe, render_prd, set_event_bus, shutdown, start_session, track_usage, usage_summary, view

## Tests
```bash
python3 -m pytest modules/claude_code_ui_harness/tests -q
```

## Import
```python
from enterprise.modules.claude_code_ui_harness import create_claude_code_ui_harness_module
m = create_claude_code_ui_harness_module()
```

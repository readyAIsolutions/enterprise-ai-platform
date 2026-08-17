# ICM module map: human_in_the_loop

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Human review/approval gates inside agent runs.
- API: audit_log, health_check, initialize, pending_escalations, queue_stats, resolve_action, route_action, shutdown

## Stages
01_intake, 02_research, 03_drafting, 04_verification, 05_output

**To use:** read the stage folder below matching your task. Start at 01_intake; run 04_verification before 05_output.

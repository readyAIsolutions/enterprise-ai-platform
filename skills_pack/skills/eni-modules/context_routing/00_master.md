# ICM module map: context_routing

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Task -> {read/skip/skills} routing table with token-budget guard.
- API: budget, health_check, initialize, route, shutdown

## Stages
01_intake, 02_research, 03_drafting, 04_verification, 05_output

**To use:** read the stage folder below matching your task. Start at 01_intake; run 04_verification before 05_output.

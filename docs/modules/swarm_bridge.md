# Module: `swarm_bridge`

- Category: Legacy Core · priority 53
- Version: 5.0.0
- Purpose: ENI Swarm Enterprise Module v5.0.0
- Skill: `eni-module-swarm_bridge` (ICM stages) in skills_pack/skills/eni-modules/swarm_bridge/

## What it does
ENI Swarm Enterprise Module v5.0.0
===================================
Enterprise Platform Kernel module for the ENI Swarm — the 50-builder
on-demand AI agent fleet coordinated by Master Driver v5.0.

Integrates swarm lifecycle management (spawn, status, pause/resume),
health monitoring, prompt enhancement via PromptForge, and event-driven
communication into the Enterprise AI OS.

Architecture:
  ENISwarmModule (Module)
  ├── SwarmBridge      — lifecycle, status, task management
  ├── SwarmHealthCheck  — continuous health monitoring & metrics
  └── PromptForgeBridge — wraps PromptForge for enterprise prompt enhancement

Events emitted:
  - swarm.builder.started     — a builder began executing a task
  - swarm.builder.completed   — a builder finished successfully
  - swarm.builder.failed      — a builder task failed or timed out
  - swarm.master.status       — master driver reported status update
  - swarm.health.degraded     — one or more builders unhealthy
  - swarm.health.recovered    — swarm recovered from degraded state

Metrics tracked:
  - active_builders           — count of currently executing builders
  - completed_tasks           — cumulative successful task count
  - failure_rate              — ratio of failed vs total tasks (0.0-1.0)
  - avg_task_duration         — rolling average task duration in seconds

Compatible with:  ENI Swarm Dashboard (Starlette on :8420)
                  Master Driver v5.0 (eni.master_driver)
                  PromptForge v1.0 (eni.prompt_forge)
                  Enterprise Platform Kernel v1.0.0

License:  Proprietary — ENI AI OS

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/swarm_bridge/tests -q
```

## Import
```python
from enterprise.modules.swarm_bridge import create_swarm_bridge_module
m = create_swarm_bridge_module()
```

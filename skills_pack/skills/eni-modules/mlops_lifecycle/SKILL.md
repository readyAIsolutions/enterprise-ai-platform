---
name: eni-module-mlops_lifecycle
description: Operate the ENI Enterprise `mlops_lifecycle` module (Legacy Core) — ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management Use when working with mlops_lifecycle in the Enterprise Platform.
---

# Module skill: mlops_lifecycle

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management

## What it does
ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management
============================================================================================

This module provides a comprehensive MLOps/LLMOps lifecycle for agent experiments,
integrating with the ENI Enterprise Platform modules:

- Experiment Tracking: Full lifecycle management via innovation_rd
- Configuration Management: Versioned, reproducible experiment configs
- Feature/Label Store: Persistent storage for training/validation data
- Canary Rollouts: Runtime feature flags via release_change
- Evaluation Gates: Automated quality gates via eval_gate
- Observability: OpenTelemetry GenAI tracing via llmops_trace
- Drift Detection: Statistical drift monitoring for models/data
- Rollback Strategies

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.mlops_lifecycle import create_mlops_lifecycle_module
m = create_mlops_lifecycle_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/mlops_lifecycle/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

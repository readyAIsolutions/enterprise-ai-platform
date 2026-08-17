# Module: `mlops_lifecycle`

- Category: Legacy Core · priority 40
- Version: 1.0.0
- Purpose: ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management
- Skill: `eni-module-mlops_lifecycle` (ICM stages) in skills_pack/skills/eni-modules/mlops_lifecycle/

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
- Rollback Strategies: Automated and manual rollback capabilities

Architecture:
    MLOpsLifecycleModule (Module)
    ├── ExperimentTracker       — CRUD + lineage for experiments
    ├── ConfigManager           — Versioned configs with schema validation
    ├── FeatureLabelStore       — SQLite/Parquet feature + label storage
    ├── CanaryManager           — Feature flags + progressive rollouts
    ├── EvalGateEngine          — Automated evaluation pipelines
    ├── ObservabilityEngine     — Tracing, metrics, logging aggregation
    ├── DriftDetector           — Statistical drift detection (PSI, KS, etc.)
    ├── RollbackController      — Automated + manual rollback with safety
    └── LifecycleOrchestrator   — End-to-end pipeline coordination

All components are local-first, offline-capable, and stdlib-only where possible.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/mlops_lifecycle/tests -q
```

## Import
```python
from enterprise.modules.mlops_lifecycle import create_mlops_lifecycle_module
m = create_mlops_lifecycle_module()
```

# Gather and normalize inputs

Purpose: ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management

## Role
Gather and normalize inputs for the `mlops_lifecycle` module.

## Inputs
Raw inputs/context for mlops_lifecycle: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for mlops_lifecycle. No unvalidated data passes.

## Scripts
python3 -m pytest modules/mlops_lifecycle/tests -q (validates core logic)

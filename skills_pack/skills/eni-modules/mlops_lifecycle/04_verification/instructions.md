# Verify

Purpose: ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management

## Role
Verify for the `mlops_lifecycle` module.

## Inputs
The mlops_lifecycle deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/mlops_lifecycle/tests -q  (REAL suite; must pass)

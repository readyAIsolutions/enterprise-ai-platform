# Verify

Purpose: composable_workflow_engine — a compose-your-own context-engineering

## Role
Verify for the `composable_workflow_engine` module.

## Inputs
The composable_workflow_engine deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/composable_workflow_engine/tests -q  (REAL suite; must pass)

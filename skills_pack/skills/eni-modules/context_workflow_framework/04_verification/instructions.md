# Verify

Purpose: context_workflow_framework — build-your-own context-engineering workflow

## Role
Verify for the `context_workflow_framework` module.

## Inputs
The context_workflow_framework deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/context_workflow_framework/tests -q  (REAL suite; must pass)

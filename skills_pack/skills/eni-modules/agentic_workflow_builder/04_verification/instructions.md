# Verify

Purpose: agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor).

## Role
Verify for the `agentic_workflow_builder` module.

## Inputs
The agentic_workflow_builder deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agentic_workflow_builder/tests -q  (REAL suite; must pass)

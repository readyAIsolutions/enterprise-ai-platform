# Verify

Purpose: Claude Code Superior — Infrastructure Module v1.0.0

## Role
Verify for the `agent_infra` module.

## Inputs
The agent_infra deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_infra/tests -q  (REAL suite; must pass)

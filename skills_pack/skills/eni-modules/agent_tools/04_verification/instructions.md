# Verify

Purpose: ENI Enterprise — Claude Code Tools Module v2.0.0

## Role
Verify for the `agent_tools` module.

## Inputs
The agent_tools deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_tools/tests -q  (REAL suite; must pass)

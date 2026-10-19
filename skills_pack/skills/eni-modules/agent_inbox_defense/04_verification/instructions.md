# Verify

Purpose: agent_inbox_defense — enterprise module wrapping a defensive scanner for

## Role
Verify for the `agent_inbox_defense` module.

## Inputs
The agent_inbox_defense deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_inbox_defense/tests -q  (REAL suite; must pass)

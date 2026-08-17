# Verify

Purpose: Claude Code Core — Enterprise Platform Kernel Module v2.0.0

## Role
Verify for the `agent_core` module.

## Inputs
The agent_core deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_core/tests -q  (REAL suite; must pass)

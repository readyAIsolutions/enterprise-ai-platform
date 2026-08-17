# Verify

Purpose: multiplayer_agent_triage — a Platform Kernel module for triaging problems and

## Role
Verify for the `multiplayer_agent_triage` module.

## Inputs
The multiplayer_agent_triage deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/multiplayer_agent_triage/tests -q  (REAL suite; must pass)

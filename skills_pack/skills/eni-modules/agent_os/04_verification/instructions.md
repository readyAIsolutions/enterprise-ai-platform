# Verify

Purpose: Enterprise Agent OS Module — a unified AI agent operating system.

## Role
Verify for the `agent_os` module.

## Inputs
The agent_os deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_os/tests -q  (REAL suite; must pass)

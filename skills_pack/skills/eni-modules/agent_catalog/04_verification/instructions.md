# Verify

Purpose: ENI Agent Catalog Module -- unified specialist-agent registry.

## Role
Verify for the `agent_catalog` module.

## Inputs
The agent_catalog deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_catalog/tests -q  (REAL suite; must pass)

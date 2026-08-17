# Verify

Purpose: custom_agent_workflows — build your OWN AI coding workflows as a module.

## Role
Verify for the `custom_agent_workflows` module.

## Inputs
The custom_agent_workflows deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/custom_agent_workflows/tests -q  (REAL suite; must pass)

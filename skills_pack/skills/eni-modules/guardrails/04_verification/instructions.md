# Verify

Purpose: ENI Guardrails OS Module.

## Role
Verify for the `guardrails` module.

## Inputs
The guardrails deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/guardrails/tests -q  (REAL suite; must pass)

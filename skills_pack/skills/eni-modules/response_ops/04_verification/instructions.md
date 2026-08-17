# Verify

Purpose: ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook.

## Role
Verify for the `response_ops` module.

## Inputs
The response_ops deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/response_ops/tests -q  (REAL suite; must pass)

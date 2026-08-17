# Verify

Purpose: ENI Response Hardening module.

## Role
Verify for the `response_hardening` module.

## Inputs
The response_hardening deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/response_hardening/tests -q  (REAL suite; must pass)

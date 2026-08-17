# Verify

Purpose: ENI Model Security OS Module.

## Role
Verify for the `model_security` module.

## Inputs
The model_security deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/model_security/tests -q  (REAL suite; must pass)

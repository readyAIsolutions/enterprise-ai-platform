# Verify

Purpose: error_correction platform module.

## Role
Verify for the `error_correction` module.

## Inputs
The error_correction deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/error_correction/tests -q  (REAL suite; must pass)

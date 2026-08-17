# Verify

Purpose: Enterprise Platform — Look & Feel Registry Module v1.0.0

## Role
Verify for the `look_and_feel` module.

## Inputs
The look_and_feel deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/look_and_feel/tests -q  (REAL suite; must pass)

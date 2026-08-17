# Verify

Purpose: ENI Enterprise Compliance OS Module.

## Role
Verify for the `compliance` module.

## Inputs
The compliance deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/compliance/tests -q  (REAL suite; must pass)

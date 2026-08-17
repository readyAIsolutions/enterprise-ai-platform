# Verify

Purpose: ENI Universal Build Score module.

## Role
Verify for the `universal_score` module.

## Inputs
The universal_score deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/universal_score/tests -q  (REAL suite; must pass)

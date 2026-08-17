# Verify

Purpose: Structured tradeoff scoring for engineering decisions.

## Role
Verify for the `engineering_tradeoff` module.

## Inputs
The engineering_tradeoff deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/engineering_tradeoff/tests -q  (REAL suite; must pass)

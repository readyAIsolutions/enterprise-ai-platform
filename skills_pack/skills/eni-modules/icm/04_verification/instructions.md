# Verify

Purpose: ICM (Interpretable Context Methodology) — skill/prompt-engineering layer.

## Role
Verify for the `icm` module.

## Inputs
The icm deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/icm/tests -q  (REAL suite; must pass)

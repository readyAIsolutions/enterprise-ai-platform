# Verify

Purpose: Innovation R&D OS Module

## Role
Verify for the `innovation_rd` module.

## Inputs
The innovation_rd deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/innovation_rd/tests -q  (REAL suite; must pass)

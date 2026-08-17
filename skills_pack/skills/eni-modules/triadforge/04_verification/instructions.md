# Verify

Purpose: ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module.

## Role
Verify for the `triadforge` module.

## Inputs
The triadforge deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/triadforge/tests -q  (REAL suite; must pass)

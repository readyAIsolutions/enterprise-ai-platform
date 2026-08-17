# Verify

Purpose: ENI Agent Memory OS Module.

## Role
Verify for the `memory` module.

## Inputs
The memory deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/memory/tests -q  (REAL suite; must pass)

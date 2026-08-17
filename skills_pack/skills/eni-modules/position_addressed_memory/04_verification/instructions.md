# Verify

Purpose: Position-addressed memory — *folder-as-memory* for AI context.

## Role
Verify for the `position_addressed_memory` module.

## Inputs
The position_addressed_memory deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/position_addressed_memory/tests -q  (REAL suite; must pass)

# Verify

Purpose: ENI A2A Module -- Agent-to-Agent protocol (Google A2A style).

## Role
Verify for the `a2a` module.

## Inputs
The a2a deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/a2a/tests -q  (REAL suite; must pass)

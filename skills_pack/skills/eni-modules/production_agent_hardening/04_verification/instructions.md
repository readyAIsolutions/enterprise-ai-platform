# Verify

Purpose: Demo->production hardening linter across 8 scored dimensions + systems loops.

## Role
Verify for the `production_agent_hardening` module.

## Inputs
The production_agent_hardening deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/production_agent_hardening/tests -q  (REAL suite; must pass)

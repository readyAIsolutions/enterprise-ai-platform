# Verify

Purpose: Operational hardening checks for shipping an agent into production.

## Role
Verify for the `production_hardening` module.

## Inputs
The production_hardening deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/production_hardening/tests -q  (REAL suite; must pass)

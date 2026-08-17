# Verify

Purpose: Disaster Recovery OS Module

## Role
Verify for the `disaster_recovery` module.

## Inputs
The disaster_recovery deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/disaster_recovery/tests -q  (REAL suite; must pass)

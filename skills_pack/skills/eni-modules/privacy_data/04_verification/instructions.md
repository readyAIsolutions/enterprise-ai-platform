# Verify

Purpose: Privacy & Data Governance OS Module

## Role
Verify for the `privacy_data` module.

## Inputs
The privacy_data deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/privacy_data/tests -q  (REAL suite; must pass)

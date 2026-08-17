# Verify

Purpose: Enterprise Validation & Certification OS — Module Entry Point

## Role
Verify for the `enterprise_validation` module.

## Inputs
The enterprise_validation deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/enterprise_validation/tests -q  (REAL suite; must pass)

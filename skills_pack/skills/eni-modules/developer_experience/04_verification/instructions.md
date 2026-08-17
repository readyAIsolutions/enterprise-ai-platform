# Verify

Purpose: Developer Experience OS Module

## Role
Verify for the `developer_experience` module.

## Inputs
The developer_experience deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/developer_experience/tests -q  (REAL suite; must pass)

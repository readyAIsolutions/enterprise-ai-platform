# Verify

Purpose: prd_audit — PRD-gated build workflow: write the PRD, audit it with a second

## Role
Verify for the `prd_audit` module.

## Inputs
The prd_audit deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/prd_audit/tests -q  (REAL suite; must pass)

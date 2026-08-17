# Verify

Purpose: What-to-automate ladder, wrong-layer detection, one-client scoping guard.

## Role
Verify for the `automation_triage` module.

## Inputs
The automation_triage deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/automation_triage/tests -q  (REAL suite; must pass)

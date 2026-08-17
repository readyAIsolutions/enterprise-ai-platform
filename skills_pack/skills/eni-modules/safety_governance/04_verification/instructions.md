# Verify

Purpose: ENI Enterprise — Safety & Governance OS v1.0.0

## Role
Verify for the `safety_governance` module.

## Inputs
The safety_governance deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/safety_governance/tests -q  (REAL suite; must pass)

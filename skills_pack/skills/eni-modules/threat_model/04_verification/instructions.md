# Verify

Purpose: ENI Threat Model OS Module.

## Role
Verify for the `threat_model` module.

## Inputs
The threat_model deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/threat_model/tests -q  (REAL suite; must pass)

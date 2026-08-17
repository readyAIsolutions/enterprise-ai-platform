# Verify

Purpose: ENI Enterprise Secret Rotation OS Module.

## Role
Verify for the `secret_rotation` module.

## Inputs
The secret_rotation deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/secret_rotation/tests -q  (REAL suite; must pass)

# Verify

Purpose: Customer Experience OS Module.

## Role
Verify for the `customer_experience` module.

## Inputs
The customer_experience deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/customer_experience/tests -q  (REAL suite; must pass)

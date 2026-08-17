# Verify

Purpose: Enterprise Secret Broker OS Module — local-first secret handling.

## Role
Verify for the `secret_broker` module.

## Inputs
The secret_broker deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/secret_broker/tests -q  (REAL suite; must pass)

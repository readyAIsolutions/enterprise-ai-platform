# Verify

Purpose: compression_bridge platform module.

## Role
Verify for the `compression_bridge` module.

## Inputs
The compression_bridge deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/compression_bridge/tests -q  (REAL suite; must pass)

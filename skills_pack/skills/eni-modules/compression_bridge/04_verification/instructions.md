# Verify

Purpose: Enterprise Platform — Compression Bridge Module v3.0.0

## Role
Verify for the `compression_bridge` module.

## Inputs
The compression_bridge deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/compression_bridge/tests -q  (REAL suite; must pass)

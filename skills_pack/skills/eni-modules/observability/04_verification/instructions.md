# Verify

Purpose: Observability — real, consolidated fleet health + Prometheus export.

## Role
Verify for the `observability` module.

## Inputs
The observability deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/observability/tests -q  (REAL suite; must pass)

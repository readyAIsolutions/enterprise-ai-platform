# Verify

Purpose: Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4).

## Role
Verify for the `cost_meter` module.

## Inputs
The cost_meter deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/cost_meter/tests -q  (REAL suite; must pass)

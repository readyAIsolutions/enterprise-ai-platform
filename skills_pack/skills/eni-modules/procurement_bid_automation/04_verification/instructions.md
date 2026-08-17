# Verify

Purpose: Automate procurement/RFP bid intake, scoring and responses.

## Role
Verify for the `procurement_bid_automation` module.

## Inputs
The procurement_bid_automation deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/procurement_bid_automation/tests -q  (REAL suite; must pass)

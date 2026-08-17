# Verify

Purpose: ENI Multi-Gateway Remote Control & Automations Module

## Role
Verify for the `gateway` module.

## Inputs
The gateway deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/gateway/tests -q  (REAL suite; must pass)

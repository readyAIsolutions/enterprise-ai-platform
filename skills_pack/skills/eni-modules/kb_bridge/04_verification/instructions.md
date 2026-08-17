# Verify

Purpose: ENI Knowledge Base OS Module

## Role
Verify for the `kb_bridge` module.

## Inputs
The kb_bridge deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/kb_bridge/tests -q  (REAL suite; must pass)

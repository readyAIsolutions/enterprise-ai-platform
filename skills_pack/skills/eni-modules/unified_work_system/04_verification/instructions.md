# Verify

Purpose: ENI Unified Work System Module

## Role
Verify for the `unified_work_system` module.

## Inputs
The unified_work_system deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/unified_work_system/tests -q  (REAL suite; must pass)

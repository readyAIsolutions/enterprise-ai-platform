# Verify

Purpose: Enterprise Platform Unified Inbox module package.

## Role
Verify for the `unified_inbox` module.

## Inputs
The unified_inbox deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/unified_inbox/tests -q  (REAL suite; must pass)

# Verify

Purpose: Live multi-editor workspace: lock, merge-safe write, history, redact-before-share.

## Role
Verify for the `shared_workspace` module.

## Inputs
The shared_workspace deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/shared_workspace/tests -q  (REAL suite; must pass)

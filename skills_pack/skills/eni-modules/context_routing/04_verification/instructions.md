# Verify

Purpose: Task -> {read/skip/skills} routing table with token-budget guard.

## Role
Verify for the `context_routing` module.

## Inputs
The context_routing deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/context_routing/tests -q  (REAL suite; must pass)

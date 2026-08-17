# Verify

Purpose: ENI Task Harness OS Module

## Role
Verify for the `task_harness` module.

## Inputs
The task_harness deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/task_harness/tests -q  (REAL suite; must pass)

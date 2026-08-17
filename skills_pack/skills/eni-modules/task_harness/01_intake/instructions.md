# Gather and normalize inputs

Purpose: ENI Task Harness OS Module

## Role
Gather and normalize inputs for the `task_harness` module.

## Inputs
Raw inputs/context for task_harness: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for task_harness. No unvalidated data passes.

## Scripts
python3 -m pytest modules/task_harness/tests -q (validates core logic)

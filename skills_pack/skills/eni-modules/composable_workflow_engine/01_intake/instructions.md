# Gather and normalize inputs

Purpose: composable_workflow_engine — a compose-your-own context-engineering

## Role
Gather and normalize inputs for the `composable_workflow_engine` module.

## Inputs
Raw inputs/context for composable_workflow_engine: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for composable_workflow_engine. No unvalidated data passes.

## Scripts
python3 -m pytest modules/composable_workflow_engine/tests -q (validates core logic)

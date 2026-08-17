# Gather and normalize inputs

Purpose: agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor).

## Role
Gather and normalize inputs for the `agentic_workflow_builder` module.

## Inputs
Raw inputs/context for agentic_workflow_builder: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agentic_workflow_builder. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agentic_workflow_builder/tests -q (validates core logic)

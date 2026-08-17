# Gather and normalize inputs

Purpose: custom_agent_workflows — build your OWN AI coding workflows as a module.

## Role
Gather and normalize inputs for the `custom_agent_workflows` module.

## Inputs
Raw inputs/context for custom_agent_workflows: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for custom_agent_workflows. No unvalidated data passes.

## Scripts
python3 -m pytest modules/custom_agent_workflows/tests -q (validates core logic)

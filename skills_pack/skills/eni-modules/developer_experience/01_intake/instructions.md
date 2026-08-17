# Gather and normalize inputs

Purpose: Developer Experience OS Module

## Role
Gather and normalize inputs for the `developer_experience` module.

## Inputs
Raw inputs/context for developer_experience: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for developer_experience. No unvalidated data passes.

## Scripts
python3 -m pytest modules/developer_experience/tests -q (validates core logic)

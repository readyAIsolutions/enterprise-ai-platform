# Gather and normalize inputs

Purpose: ENI Semantic Memory OS Module.

## Role
Gather and normalize inputs for the `semantic_memory` module.

## Inputs
Raw inputs/context for semantic_memory: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for semantic_memory. No unvalidated data passes.

## Scripts
python3 -m pytest modules/semantic_memory/tests -q (validates core logic)

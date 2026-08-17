# Gather and normalize inputs

Purpose: Artifact Pipeline — navigate & organize all creative works (no LLM).

## Role
Gather and normalize inputs for the `artifact_pipeline` module.

## Inputs
Raw inputs/context for artifact_pipeline: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for artifact_pipeline. No unvalidated data passes.

## Scripts
python3 -m pytest modules/artifact_pipeline/tests -q (validates core logic)

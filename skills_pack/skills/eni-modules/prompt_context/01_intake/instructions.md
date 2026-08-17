# Gather and normalize inputs

Purpose: Prompt & Context Management OS Module

## Role
Gather and normalize inputs for the `prompt_context` module.

## Inputs
Raw inputs/context for prompt_context: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for prompt_context. No unvalidated data passes.

## Scripts
python3 -m pytest modules/prompt_context/tests -q (validates core logic)

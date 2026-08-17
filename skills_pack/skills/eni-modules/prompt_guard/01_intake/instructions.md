# Gather and normalize inputs

Purpose: Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding.

## Role
Gather and normalize inputs for the `prompt_guard` module.

## Inputs
Raw inputs/context for prompt_guard: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for prompt_guard. No unvalidated data passes.

## Scripts
python3 -m pytest modules/prompt_guard/tests -q (validates core logic)

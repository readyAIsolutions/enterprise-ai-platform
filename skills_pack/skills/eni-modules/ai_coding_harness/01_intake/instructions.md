# Gather and normalize inputs

Purpose: Harness for coding-agent output: run, verify, audit.

## Role
Gather and normalize inputs for the `ai_coding_harness` module.

## Inputs
Raw inputs/context for ai_coding_harness: agent code runs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for ai_coding_harness. No unvalidated data passes.

## Scripts
python3 -m pytest modules/ai_coding_harness/tests -q (validates core logic)

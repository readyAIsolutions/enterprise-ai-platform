# Gather and normalize inputs

Purpose: Guardrails for using AI in education (anti-cheating, learning-first).

## Role
Gather and normalize inputs for the `ai_education_guardrails` module.

## Inputs
Raw inputs/context for ai_education_guardrails: education prompts. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for ai_education_guardrails. No unvalidated data passes.

## Scripts
python3 -m pytest modules/ai_education_guardrails/tests -q (validates core logic)

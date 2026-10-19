# Gather and normalize inputs

Purpose: ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow

## Role
Gather and normalize inputs for the `ai_coding_workflow` module.

## Inputs
Raw inputs/context for ai_coding_workflow: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for ai_coding_workflow. No unvalidated data passes.

## Scripts
python3 -m pytest modules/ai_coding_workflow/tests -q (validates core logic)

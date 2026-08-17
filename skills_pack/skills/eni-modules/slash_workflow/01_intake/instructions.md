# Gather and normalize inputs

Purpose: slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a dete

## Role
Gather and normalize inputs for the `slash_workflow` module.

## Inputs
Raw inputs/context for slash_workflow: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for slash_workflow. No unvalidated data passes.

## Scripts
python3 -m pytest modules/slash_workflow/tests -q (validates core logic)

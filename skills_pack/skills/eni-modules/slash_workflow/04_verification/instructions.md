# Verify

Purpose: slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a dete

## Role
Verify for the `slash_workflow` module.

## Inputs
The slash_workflow deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/slash_workflow/tests -q  (REAL suite; must pass)

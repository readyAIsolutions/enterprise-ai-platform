# Gather and normalize inputs

Purpose: What-to-automate ladder, wrong-layer detection, one-client scoping guard.

## Role
Gather and normalize inputs for the `automation_triage` module.

## Inputs
Raw inputs/context for automation_triage: task specs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for automation_triage. No unvalidated data passes.

## Scripts
python3 -m pytest modules/automation_triage/tests -q (validates core logic)

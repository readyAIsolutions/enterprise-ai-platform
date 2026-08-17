# Gather and normalize inputs

Purpose: ENI Enterprise — Safety & Governance OS v1.0.0

## Role
Gather and normalize inputs for the `safety_governance` module.

## Inputs
Raw inputs/context for safety_governance: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for safety_governance. No unvalidated data passes.

## Scripts
python3 -m pytest modules/safety_governance/tests -q (validates core logic)

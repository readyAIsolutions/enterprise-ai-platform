# Gather and normalize inputs

Purpose: ENI Threat Model OS Module.

## Role
Gather and normalize inputs for the `threat_model` module.

## Inputs
Raw inputs/context for threat_model: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for threat_model. No unvalidated data passes.

## Scripts
python3 -m pytest modules/threat_model/tests -q (validates core logic)

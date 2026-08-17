# Gather and normalize inputs

Purpose: ENI Unified Work System Module

## Role
Gather and normalize inputs for the `unified_work_system` module.

## Inputs
Raw inputs/context for unified_work_system: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for unified_work_system. No unvalidated data passes.

## Scripts
python3 -m pytest modules/unified_work_system/tests -q (validates core logic)

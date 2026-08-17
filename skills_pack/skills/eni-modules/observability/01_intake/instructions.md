# Gather and normalize inputs

Purpose: Observability — real, consolidated fleet health + Prometheus export.

## Role
Gather and normalize inputs for the `observability` module.

## Inputs
Raw inputs/context for observability: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for observability. No unvalidated data passes.

## Scripts
python3 -m pytest modules/observability/tests -q (validates core logic)

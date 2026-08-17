# Gather and normalize inputs

Purpose: Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4).

## Role
Gather and normalize inputs for the `cost_meter` module.

## Inputs
Raw inputs/context for cost_meter: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for cost_meter. No unvalidated data passes.

## Scripts
python3 -m pytest modules/cost_meter/tests -q (validates core logic)

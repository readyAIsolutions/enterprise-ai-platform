# Gather and normalize inputs

Purpose: ENI Multi-Gateway Remote Control & Automations Module

## Role
Gather and normalize inputs for the `gateway` module.

## Inputs
Raw inputs/context for gateway: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for gateway. No unvalidated data passes.

## Scripts
python3 -m pytest modules/gateway/tests -q (validates core logic)

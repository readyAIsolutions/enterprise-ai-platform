# Gather and normalize inputs

Purpose: ENI Swarm Enterprise Module v5.0.0

## Role
Gather and normalize inputs for the `swarm_bridge` module.

## Inputs
Raw inputs/context for swarm_bridge: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for swarm_bridge. No unvalidated data passes.

## Scripts
python3 -m pytest modules/swarm_bridge/tests -q (validates core logic)

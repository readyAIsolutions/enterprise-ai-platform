# Gather and normalize inputs

Purpose: compression_bridge platform module.

## Role
Gather and normalize inputs for the `compression_bridge` module.

## Inputs
Raw inputs/context for compression_bridge: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for compression_bridge. No unvalidated data passes.

## Scripts
python3 -m pytest modules/compression_bridge/tests -q (validates core logic)

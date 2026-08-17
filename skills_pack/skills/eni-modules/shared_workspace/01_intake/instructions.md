# Gather and normalize inputs

Purpose: Live multi-editor workspace: lock, merge-safe write, history, redact-before-share.

## Role
Gather and normalize inputs for the `shared_workspace` module.

## Inputs
Raw inputs/context for shared_workspace: shared files/history. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for shared_workspace. No unvalidated data passes.

## Scripts
python3 -m pytest modules/shared_workspace/tests -q (validates core logic)

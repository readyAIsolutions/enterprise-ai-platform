# Gather and normalize inputs

Purpose: Enterprise Platform Unified Inbox module package.

## Role
Gather and normalize inputs for the `unified_inbox` module.

## Inputs
Raw inputs/context for unified_inbox: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for unified_inbox. No unvalidated data passes.

## Scripts
python3 -m pytest modules/unified_inbox/tests -q (validates core logic)

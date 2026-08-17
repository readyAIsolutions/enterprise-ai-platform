# Gather and normalize inputs

Purpose: Audit generated code for correctness, security and quality signals.

## Role
Gather and normalize inputs for the `codegen_audit` module.

## Inputs
Raw inputs/context for codegen_audit: generated code. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for codegen_audit. No unvalidated data passes.

## Scripts
python3 -m pytest modules/codegen_audit/tests -q (validates core logic)

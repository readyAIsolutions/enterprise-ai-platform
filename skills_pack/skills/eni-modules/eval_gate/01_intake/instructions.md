# Gather and normalize inputs

Purpose: ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline).

## Role
Gather and normalize inputs for the `eval_gate` module.

## Inputs
Raw inputs/context for eval_gate: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for eval_gate. No unvalidated data passes.

## Scripts
python3 -m pytest modules/eval_gate/tests -q (validates core logic)

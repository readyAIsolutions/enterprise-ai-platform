# Gather and normalize inputs

Purpose: information_theory — Shannon entropy, mutual information, KL divergence, and

## Role
Gather and normalize inputs for the `information_theory` module.

## Inputs
Raw inputs/context for information_theory: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for information_theory. No unvalidated data passes.

## Scripts
python3 -m pytest modules/information_theory/tests -q (validates core logic)

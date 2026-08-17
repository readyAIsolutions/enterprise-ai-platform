# Gather and normalize inputs

Purpose: Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export.

## Role
Gather and normalize inputs for the `paper_feeds` module.

## Inputs
Raw inputs/context for paper_feeds: research feeds. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for paper_feeds. No unvalidated data passes.

## Scripts
python3 -m pytest modules/paper_feeds/tests -q (validates core logic)

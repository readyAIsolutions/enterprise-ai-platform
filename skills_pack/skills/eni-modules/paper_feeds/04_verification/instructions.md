# Verify

Purpose: Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export.

## Role
Verify for the `paper_feeds` module.

## Inputs
The paper_feeds deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/paper_feeds/tests -q  (REAL suite; must pass)

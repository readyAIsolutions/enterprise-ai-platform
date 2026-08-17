# Verify

Purpose: YouTube transcript puller with PIA VPN IP rotation.

## Role
Verify for the `youtube_transcripts` module.

## Inputs
The youtube_transcripts deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/youtube_transcripts/tests -q  (REAL suite; must pass)

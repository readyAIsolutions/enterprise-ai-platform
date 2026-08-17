# Gather and normalize inputs

Purpose: YouTube transcript puller with PIA VPN IP rotation.

## Role
Gather and normalize inputs for the `youtube_transcripts` module.

## Inputs
Raw inputs/context for youtube_transcripts: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for youtube_transcripts. No unvalidated data passes.

## Scripts
python3 -m pytest modules/youtube_transcripts/tests -q (validates core logic)

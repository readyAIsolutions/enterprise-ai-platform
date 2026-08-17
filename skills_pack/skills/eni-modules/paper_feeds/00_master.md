# ICM module map: paper_feeds

- Category: Knowledge Intake (priority 1)
- Version: 2.0.0
- Purpose: Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export.
- API: health_check, initialize, pull_one, pull_today, seen_count, shutdown

## Stages
01_intake, 02_research, 03_drafting, 04_verification, 05_output

**To use:** read the stage folder below matching your task. Start at 01_intake; run 04_verification before 05_output.

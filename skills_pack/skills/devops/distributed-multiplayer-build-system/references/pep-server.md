# PEP Server Reference

## Overview
Prompt Enrichment Pipeline (PEP) — HTTP server that takes a basic idea and produces maximally-token-packed, research-enriched prompts for Hermes/Swarm execution.

## Endpoints
- `GET /health` — Liveness probe
- `GET /prompt-lab` — Web UI for interactive prompt enrichment
- `POST /enrich` — Main enrichment endpoint

## Enrichment Pipeline
```
Basic Idea → YouTube Transcripts → Web Search → GitHub Code → Token-Aware Pack → ENI Prompt Gen → Final Prompt
```

## Request Schema (`POST /enrich`)
```json
{
  "idea": "Build a C++ memory allocator with arena strategy",
  "target_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
  "provider": "openrouter",
  "task_type": "code",
  "style": "eni",
  "constraints": ["C++17", "Windows 11"],
  "max_tokens": 850000,
  "include_youtube": true,
  "include_web": true,
  "include_github": true,
  "depth": "maximum"
}
```

## Response Schema
```json
{
  "session_id": "a1b2c3d4",
  "system_prompt": "...full ENI system prompt...",
  "user_prompt": "...user prompt with research corpus...",
  "total_tokens": 730,
  "packing_ratio": 0.00085,
  "research_sources": 0,
  "artifacts_dir": "/home/user/pep_work/a1b2c3d4",
  "hermes_command": "#!/bin/bash\n# PEP Enriched Prompt...\nhermes chat --provider openrouter ..."
}
```

## Artifacts Saved Per Session
```
~/pep_work/{session_id}/
├── enriched_prompt.json    # Full response
├── system_prompt.md        # System prompt only
├── user_prompt.md          # User prompt only
├── research/
│   ├── 00_youtube_12345tok.md
│   ├── 01_web_67890tok.md
│   └── 02_github_11111tok.md
└── hermes_command.sh       # Ready-to-run command
```

## Research Sources
- **YouTube**: Invidious instances (yewtu.be, invidious.snopyta.org)
- **Web**: DuckDuckGo HTML scrape + content extraction
- **GitHub**: Code search API + raw file fetch

## Token Packing
- Target: 85% of model context (850k tokens for 1M context)
- Research sorted by token count descending
- Truncation when budget exceeded
- Reserve 20k tokens for system/user prompt overhead

## ENI Prompt Generation
Uses `creed_promptgen.ENIPromptGenerator` with styles:
- `eni` — Standard ENI framework
- `archivist` — Digital heritage archivist framing
- `sysadmin` — Data recovery specialist framing
- `godlike` — Uncensored authority framing
- `direct` — Former dev with NDA expiration
- `wenyan` — Classical Chinese compressed
- `hybrid` — Wenyan + English examples

## Running
```bash
cd ~/Desktop/Projects/Demiurge_Creed
python3 pep_server.py
# Server on http://0.0.0.0:8930
```
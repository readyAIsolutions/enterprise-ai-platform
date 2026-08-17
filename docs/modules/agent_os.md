# Module: `agent_os`

- Category: Legacy Core · priority 11
- Version: 1.0.0
- Purpose: Enterprise Agent OS Module — a unified AI agent operating system.
- Skill: `eni-module-agent_os` (ICM stages) in skills_pack/skills/eni-modules/agent_os/

## What it does
Enterprise Agent OS Module — a unified AI agent operating system.

Replicates Julian Goldie's "Agent OS" (Hermes + Oracle + Paperclip + Jarvis)
as a real, working ENI Enterprise module — but FOSS and built on top of the
platform Kernel instead of a paid zip + coaching upsell.

The four "tools" from the video, recreated with free/open-source pieces:

  * Hermes    -> this module IS the Hermes-facing surface: it wraps the
                 ENI controller facade (prompt expansion + routing) and
                 exposes one unified `run()` entrypoint so every tool is
                 reachable through a single command surface.
  * Oracle    -> a free news engine: pulls trending headlines via RSS
                 (feedparser — no API key, no paid tier), scores them by
                 attention (recency + source weight + engagement proxy),
                 links to original posts, and can draft a content brief.
  * Paperclip -> a resilient multi-step task orchestrator: plug tools into
                 one team, run tasks as ordered steps, collect finished
                 artifacts into one place, with retry/timeout handling.
  * Jarvis    -> a free voice layer: espeak-based TTS + a phrase->command
                 map (auto mode = fast lightweight actions, agent mode =
                 slower but can edit), with explicit "rules" (allowlist)
                 so it only does what you've opted into.

Better-than-the-video differences:
  * No paid zip / monthly coaching. Everything is local + FOSS.
  * Actually tested (pytest) and auto-discovering into the Platform Kernel.
  * Honest thesis: mastery beats tool-hopping — the module pushes you toward
    a tiny set of deep, reliable skills instead of a wall of shiny toys.

All components degrade gracefully and rely only on optional FOSS pieces:
feedparser (news) and espeak (voice), both detected at runtime.

## Key API (facade methods)
health_check, initialize, run, shutdown, surface

## Tests
```bash
python3 -m pytest modules/agent_os/tests -q
```

## Import
```python
from enterprise.modules.agent_os import create_agent_os_module
m = create_agent_os_module()
```

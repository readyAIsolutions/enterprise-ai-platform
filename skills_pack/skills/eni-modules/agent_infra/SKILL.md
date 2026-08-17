---
name: eni-module-agent_infra
description: Operate the ENI Enterprise `agent_infra` module (Legacy Core) — Claude Code Superior — Infrastructure Module v1.0.0 Use when working with agent_infra in the Enterprise Platform.
---

# Module skill: agent_infra

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Claude Code Superior — Infrastructure Module v1.0.0

## What it does
Claude Code Superior — Infrastructure Module v1.0.0
====================================================

Enterprise-grade infrastructure module re-implementing Claude Code's
core systems as Python-native components for the ENI Enterprise Platform OS.

Provides:
  - TUIEngine          — prompt_toolkit-based terminal UI with Ink-inspired
                          component tree, keybinding registry, and theme engine
  - ClaudServer        — FastAPI + WebSocket server for remote sessions (port 9120)
  - PluginSystem       — hot-reload plugin manager with sandboxed execution
                          and marketplace integration
  - BuddySystem        — shared-context agent teammates for collaborative work
  - VoiceIntegration   — Piper TTS + Whisper STT voice pipeline
  - BootstrapManager   —

## Key API (facade methods on the @module class)
- buddy_manager\n- component\n- health_check\n- infra\n- initialize\n- plugin_manager\n- server\n- set_event_bus\n- shutdown\n- tui\n- voice

## Use
Import via:
```python
from enterprise.modules.agent_infra import create_agent_infra_module
m = create_agent_infra_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_infra/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.

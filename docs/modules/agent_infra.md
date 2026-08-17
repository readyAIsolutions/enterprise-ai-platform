# Module: `agent_infra`

- Category: Legacy Core · priority 10
- Version: 1.0.0
- Purpose: Claude Code Superior — Infrastructure Module v1.0.0
- Skill: `eni-module-agent_infra` (ICM stages) in skills_pack/skills/eni-modules/agent_infra/

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
  - BootstrapManager   — startup and entrypoint orchestration

Architecture:
    __init__.py         — Module housekeeping, @module registration, exports
    tui_engine.py       — TUIEngine, Component, KeybindingRegistry, ThemeEngine
    server.py           — ClaudServer, WebSocketSessionManager
    plugin_system.py    — PluginManager, PluginSandbox, PluginMarketplace
    buddy_system.py     — BuddyManager, BuddyAgent, SharedContext
    voice.py            — VoicePipeline, TTSProvider, STTProvider

Events emitted:
  - claude.infra.tui.started        — TUI engine initialized
  - claude.infra.server.started     — Server listening on :9120
  - claude.infra.server.session     — Remote session connected/disconnected
  - claude.infra.plugin.loaded      — Plugin loaded (hot-reload)
  - claude.infra.plugin.marketplace — Marketplace operation completed
  - claude.infra.buddy.spawned      — Buddy agent created
  - claude.infra.buddy.context.shared — Context shared between buddies
  - claude.infra.voice.started      — Voice pipeline active
  - claude.infra.voice.transcription — Transcription completed
  - claude.infra.bootstrap.complete — Bootstrap sequence finished

Version: 1.0.0
Python: 3.11+

## Key API (facade methods)
buddy_manager, component, health_check, infra, initialize, plugin_manager, server, set_event_bus, shutdown, tui, voice

## Tests
```bash
python3 -m pytest modules/agent_infra/tests -q
```

## Import
```python
from enterprise.modules.agent_infra import create_agent_infra_module
m = create_agent_infra_module()
```

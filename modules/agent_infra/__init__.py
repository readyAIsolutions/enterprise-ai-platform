"""
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
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .tui_engine import (
    TUIEngine,
    Component,
    KeybindingRegistry,
    ThemeEngine,
    ComponentNode,
    TUIHealthCheck,
)

from .server import (
    ClaudServer,
    WebSocketSessionManager,
    SessionState,
    ServerConfig,
)

from .plugin_system import (
    PluginManager,
    PluginSandbox,
    PluginMarketplace,
    PluginMetadata,
    PluginState,
)

from .buddy_system import (
    BuddyManager,
    BuddyAgent,
    SharedContext,
    BuddyRole,
)

from .voice import (
    VoicePipeline,
    TTSProvider,
    STTProvider,
    VoiceSession,
)

from .status import (
    InfraStatus,
    ComponentStatus,
    ComponentState,
    CORE_COMPONENTS,
)

__all__ = [
    # Module
    "ClaudeCodeInfraModule",
    # TUI
    "TUIEngine",
    "Component",
    "KeybindingRegistry",
    "ThemeEngine",
    "ComponentNode",
    "TUIHealthCheck",
    # Server
    "ClaudServer",
    "WebSocketSessionManager",
    "SessionState",
    "ServerConfig",
    # Plugins
    "PluginManager",
    "PluginSandbox",
    "PluginMarketplace",
    "PluginMetadata",
    "PluginState",
    # Buddy
    "BuddyManager",
    "BuddyAgent",
    "SharedContext",
    "BuddyRole",
    # Voice
    "VoicePipeline",
    "TTSProvider",
    "STTProvider",
    "VoiceSession",
    # Status facade
    "InfraStatus",
    "ComponentStatus",
    "ComponentState",
    "CORE_COMPONENTS",
]

__version__ = "1.0.0"

_logger: logging.Logger = logging.getLogger("enterprise.agent_infra")


# ── Module class registered with the platform kernel ──────────────────────

@module(name="agent_infra", version="1.0.0")
class ClaudeCodeInfraModule(Module):
    """Enterprise Claude Code Infrastructure Module.

    Re-implements Claude Code's core systems: TUI engine (prompt_toolkit +
    Ink-inspired component tree), FastAPI server for remote sessions, plugin
    manager with hot-reload and marketplace, buddy/teammate shared-context
    agents, and Piper TTS + Whisper STT voice integration.

    Lifecycle:
        initialize()  → boots TUI, server, plugin system, buddy & voice
        health_check() → validates all subsystems are operational
        shutdown()    → graceful teardown of all subsystems

    Events published:
      - claude.infra.tui.started
      - claude.infra.server.started
      - claude.infra.server.session
      - claude.infra.plugin.loaded
      - claude.infra.plugin.marketplace
      - claude.infra.buddy.spawned
      - claude.infra.buddy.context.shared
      - claude.infra.voice.started
      - claude.infra.voice.transcription
      - claude.infra.bootstrap.complete
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[EventBus] = None
        self._tui: Optional[TUIEngine] = None
        self._server: Optional[ClaudServer] = None
        self._plugin_manager: Optional[PluginManager] = None
        self._buddy_manager: Optional[BuddyManager] = None
        self._voice: Optional[VoicePipeline] = None
        # Unified health/status facade aggregating every core component.
        self._infra = InfraStatus(module_name="agent_infra")

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def tui(self) -> Optional[TUIEngine]:
        """The active TUI engine instance."""
        return self._tui

    @property
    def server(self) -> Optional[ClaudServer]:
        """The active FastAPI server instance."""
        return self._server

    @property
    def plugin_manager(self) -> Optional[PluginManager]:
        """The active plugin manager instance."""
        return self._plugin_manager

    @property
    def buddy_manager(self) -> Optional[BuddyManager]:
        """The active buddy manager instance."""
        return self._buddy_manager

    @property
    def voice(self) -> Optional[VoicePipeline]:
        """The active voice pipeline instance."""
        return self._voice

    @property
    def infra(self) -> InfraStatus:
        """The unified InfraStatus facade aggregating all core components."""
        return self._infra

    def component(self, name: str) -> Optional[ComponentStatus]:
        """Return a single component's health via the status facade."""
        return self._infra.component(name)

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize all Claude Code infrastructure subsystems.

        Boots the TUI engine, FastAPI server, plugin system, buddy manager,
        and voice pipeline. Publishes bootstrap events on the event bus.
        """
        self._status = HealthStatus.STARTING
        _logger.info("Claude Code Infra module initializing...")
        cfg: Dict[str, Any] = self._config or {}

        # ── TUI Engine ─────────────────────────────────────────────────
        try:
            self._tui = TUIEngine(
                event_bus=self._event_bus,
                config=cfg.get("tui", {}),
            )
            await self._tui.initialize()
            _logger.info("TUI Engine initialized")
            self._infra.update("tui", ok=True, message="TUI engine initialized")
            self._publish("claude.infra.tui.started", {"mode": cfg.get("tui_mode", "prompt_toolkit")})
        except Exception:
            _logger.exception("TUI Engine failed to initialize")
            self._status = HealthStatus.DEGRADED
            self._infra.update("tui", ok=False, message="TUI engine failed to initialize")
            raise

        # ── Server (FastAPI + WebSocket) ──────────────────────────────
        try:
            self._server = ClaudServer(
                event_bus=self._event_bus,
                config=cfg.get("server", {"port": 9120}),
            )
            await self._server.initialize()
            _logger.info("ClaudServer started on port %s", self._server.port)
            self._infra.update("server", ok=True, message="ClaudServer listening")
            self._publish("claude.infra.server.started", {"port": self._server.port})
        except Exception:
            _logger.exception("ClaudServer failed to initialize")
            self._status = HealthStatus.DEGRADED
            self._infra.update("server", ok=False, message="ClaudServer failed to initialize")
            raise

        # ── Plugin System ─────────────────────────────────────────────
        try:
            self._plugin_manager = PluginManager(
                event_bus=self._event_bus,
                config=cfg.get("plugins", {}),
            )
            await self._plugin_manager.initialize()
            _logger.info("Plugin Manager initialized (%d plugins discovered)",
                         len(self._plugin_manager.plugins))
            self._infra.update("plugin_system", ok=True,
                               message="Plugin manager initialized")
        except Exception:
            _logger.exception("Plugin Manager failed to initialize")
            self._status = HealthStatus.DEGRADED
            self._infra.update("plugin_system", ok=False,
                               message="Plugin manager failed to initialize")
            raise

        # ── Buddy System ──────────────────────────────────────────────
        try:
            self._buddy_manager = BuddyManager(
                event_bus=self._event_bus,
                config=cfg.get("buddy", {}),
            )
            await self._buddy_manager.initialize()
            _logger.info("Buddy Manager initialized")
            self._infra.update("buddy", ok=True, message="Buddy manager initialized")
        except Exception:
            _logger.exception("Buddy Manager failed to initialize")
            self._status = HealthStatus.DEGRADED
            self._infra.update("buddy", ok=False,
                               message="Buddy manager failed to initialize")
            raise

        # ── Voice Pipeline ────────────────────────────────────────────
        try:
            self._voice = VoicePipeline(
                event_bus=self._event_bus,
                config=cfg.get("voice", {}),
            )
            await self._voice.initialize()
            _logger.info("Voice Pipeline initialized")
            self._infra.update("voice", ok=True, message="Voice pipeline initialized")
            self._publish("claude.infra.voice.started", {"providers": self._voice.active_providers})
        except Exception:
            _logger.exception("Voice Pipeline failed to initialize")
            self._status = HealthStatus.DEGRADED
            self._infra.update("voice", ok=False,
                               message="Voice pipeline failed to initialize")
            raise

        self._status = HealthStatus.HEALTHY
        self._infra.update("bootstrap", ok=True, message="bootstrap sequence complete")
        self._publish("claude.infra.bootstrap.complete", {"version": "1.0.0"})
        _logger.info("Claude Code Infra module fully initialized")

    async def health_check(self) -> HealthStatus:
        """Verify all subsystems are operational.

        Runs every per-subsystem health check, records the result into the
        unified InfraStatus facade, then returns the aggregate HealthStatus.
        The module is HEALTHY only when every core component is OK.

        Returns:
            HealthStatus indicating overall infrastructure health.
        """
        # name -> (component key, subsystem object)
        targets = [
            ("tui", "tui", self._tui),
            ("server", "server", self._server),
            ("plugin_system", "plugins", self._plugin_manager),
            ("buddy", "buddy", self._buddy_manager),
            ("voice", "voice", self._voice),
        ]

        for comp_key, _label, obj in targets:
            if obj is None:
                self._infra.update(comp_key, ok=False,
                                   message="subsystem not initialized")
                continue
            try:
                ok = await obj.health_check()
            except Exception:
                ok = False
            self._infra.update(comp_key, ok=ok,
                               message=f"{comp_key} health check")

        # bootstrap reflects whether the core middleware aggregate is healthy
        core_ok = True
        for k in ("tui", "server", "plugin_system", "buddy", "voice"):
            cs = self._infra.component(k)
            if cs is None or not cs.ok:
                core_ok = False
                break
        self._infra.update("bootstrap", ok=core_ok,
                           message="aggregate core health check")

        self._status = self._infra.overall_status()
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down all subsystems."""
        self._status = HealthStatus.STOPPING
        _logger.info("Shutting down Claude Code Infra module...")

        shutdown_order = ["voice", "buddy", "plugins", "server", "tui"]
        for subsystem in shutdown_order:
            try:
                obj = getattr(self, f"_{subsystem}", None)
                if obj is not None and hasattr(obj, "shutdown"):
                    await obj.shutdown()
                    _logger.info("Subsystem %s shut down", subsystem)
            except Exception:
                _logger.exception("Error shutting down %s", subsystem)

        self._status = HealthStatus.HEALTHY
        _logger.info("Claude Code Infra module shut down")

    # ── Event Bus Wiring ─────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but
        before initialize(). Propagates to all subsystems.
        """
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event if the event bus is wired."""
        if self._event_bus is not None:
            from enterprise.platform_kernel import Event
            self._event_bus.publish(
                Event.create(topic, "agent_infra", payload)
            )
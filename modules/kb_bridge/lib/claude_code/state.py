#!/usr/bin/env python3
"""
Claude Code State Management — Python Port
===========================================
AppState and bootstrap state management.
Mirrors: src/state/, src/bootstrap/state.ts
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# ─── Type Definitions ────────────────────────────────────────────────────────

T = TypeVar("T")


@dataclass
class StateSnapshot(Generic[T]):
    """Snapshot of state for persistence."""
    data: T
    timestamp: datetime = field(default_factory=datetime.now)
    version: int = 1


class StateStore(Generic[T]):
    """
    Redux-like state store with middleware support.
    """

    def __init__(self, initial_state: T):
        self._state = initial_state
        self._listeners: list[Callable[[T, T], None]] = []
        self._middleware: list[Callable[[T, Any], Awaitable[T]]] = []

    @property
    def state(self) -> T:
        return self._state

    def subscribe(self, listener: Callable[[T, T], None]) -> Callable[[], None]:
        """Subscribe to state changes."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def use_middleware(self, middleware: Callable[[T, Any], Awaitable[T]]) -> None:
        """Add middleware."""
        self._middleware.append(middleware)

    async def dispatch(self, action: Any) -> T:
        """Dispatch an action to update state."""
        old_state = self._state

        # Apply middleware
        new_state = self._state
        for mw in self._middleware:
            new_state = await mw(new_state, action)

        # If no middleware modified state, action should be a dict with updater
        if new_state is old_state and isinstance(action, dict) and "updater" in action:
            updater = action["updater"]
            if callable(updater):
                new_state = updater(old_state)

        if new_state is not old_state:
            self._state = new_state
            for listener in self._listeners:
                listener(new_state, old_state)

        return self._state

    def get_snapshot(self) -> StateSnapshot[T]:
        """Get current state snapshot."""
        return StateSnapshot(data=self._state)

    def restore_snapshot(self, snapshot: StateSnapshot[T]) -> None:
        """Restore state from snapshot."""
        old_state = self._state
        self._state = snapshot.data
        for listener in self._listeners:
            listener(self._state, old_state)


# ─── AppState ────────────────────────────────────────────────────────────────


class FastModeConfig(BaseModel):
    """Fast mode configuration."""
    enabled: bool = False
    model: str | None = None


class ToolPermissionContextState(BaseModel):
    """Tool permission context in app state."""
    mode: str = "default"
    additional_working_directories: dict[str, Any] = field(default_factory=dict)
    always_allow_rules: dict[str, list[str]] = field(default_factory=dict)
    always_deny_rules: dict[str, list[str]] = field(default_factory=dict)
    always_ask_rules: dict[str, list[str]] = field(default_factory=dict)
    is_bypass_permissions_mode_available: bool = True
    is_auto_mode_available: bool = True


class AppState(BaseModel):
    """Main application state."""
    # Session
    session_id: str = ""
    session_start_time: datetime = field(default_factory=datetime.now)

    # UI
    theme: str = "dark"
    vim_mode: bool = False
    show_line_numbers: bool = True

    # Permissions
    tool_permission_context: ToolPermissionContextState = field(default_factory=ToolPermissionContextState)

    # Fast mode
    fast_mode: FastModeConfig = field(default_factory=FastModeConfig)

    # Cost tracking
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # File history
    file_history: dict[str, Any] = field(default_factory=dict)

    # Attribution
    attribution: dict[str, Any] = field(default_factory=dict)

    # Messages (limited)
    recent_messages: list[Any] = field(default_factory=list)
    max_recent_messages: int = 100

    # Custom data
    custom: dict[str, Any] = field(default_factory=dict)


# ─── Bootstrap State (Session-scoped) ────────────────────────────────────────


_bootstrap_state: dict[str, Any] = {}


def get_bootstrap_state() -> dict[str, Any]:
    """Get bootstrap state dict."""
    return _bootstrap_state


def set_bootstrap_state(key: str, value: Any) -> None:
    """Set bootstrap state value."""
    _bootstrap_state[key] = value


def get_bootstrap(key: str, default: Any = None) -> Any:
    """Get bootstrap state value."""
    return _bootstrap_state.get(key, default)


# ─── State Persistence ───────────────────────────────────────────────────────


class StatePersister:
    """Persist state to disk."""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or Path.home() / ".claude_code" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: AppState, filename: str = "app_state.json") -> None:
        """Save state to file."""
        filepath = self.state_dir / filename
        data = state.model_dump(mode="json")
        filepath.write_text(json.dumps(data, indent=2, default=str))

    def load(self, filename: str = "app_state.json") -> AppState | None:
        """Load state from file."""
        filepath = self.state_dir / filename
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text())
            return AppState(**data)
        except Exception:
            return None


# ─── Global Instances ────────────────────────────────────────────────────────


_app_state_store: StateStore[AppState] | None = None


def get_app_state_store() -> StateStore[AppState]:
    """Get or create global app state store."""
    global _app_state_store
    if _app_state_store is None:
        _app_state_store = StateStore(AppState())
    return _app_state_store


def get_app_state() -> AppState:
    """Get current app state."""
    return get_app_state_store().state


async def set_app_state(updater: Callable[[AppState], AppState]) -> AppState:
    """Update app state."""
    return await get_app_state_store().dispatch({"updater": updater})


# ─── Export ──────────────────────────────────────────────────────────────────

__all__ = [
    "StateStore",
    "StateSnapshot",
    "AppState",
    "ToolPermissionContextState",
    "FastModeConfig",
    "get_app_state_store",
    "get_app_state",
    "set_app_state",
    "get_bootstrap_state",
    "set_bootstrap_state",
    "get_bootstrap",
    "StatePersister",
]
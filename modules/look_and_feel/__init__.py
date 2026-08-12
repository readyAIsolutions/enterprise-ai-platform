"""
Enterprise Platform — Look & Feel Registry Module v1.0.0
=========================================================

Enterprise-grade visual design registry bridging into the Enterprise Platform
OS. Parses, persists, and applies UI look-and-feel rulesets so downstream
generators produce visually consistent, distinctive UI.

Provided by look_and_feel.py:
    LookAndFeelEntry    — data model for a single design module
    LookAndFeelParser   — parses the structured module format
    LookAndFeelRegistry — JSON-backed persistent store
    LookAndFeelCLI      — 'lookandfeel' command binding

Module facade (this file):
    LookAndFeelModule   — @module-registered Module with lifecycle + API
    create_look_and_feel_module — platform factory entrypoint

Architecture:
    __init__.py            — Module housekeeping, @module registration, exports
    look_and_feel.py       — Entry, Parser, Registry, CLI
    tests/test_look_and_feel.py — production-quality tests
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Import from platform kernel, handling both absolute (from parent dir)
# and relative (from within enterprise/) contexts.
try:
    from enterprise.platform_kernel import HealthStatus, Module, module
except ImportError:
    # Running from inside enterprise/ — need the parent on sys.path
    _this = Path(__file__).resolve()
    _enterprise_dir = _this.parent.parent.parent
    _parent = _enterprise_dir.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))
    from enterprise.platform_kernel import HealthStatus, Module, module

from .look_and_feel import (  # noqa: E402
    LookAndFeelCLI,
    LookAndFeelEntry,
    LookAndFeelParser,
    LookAndFeelRegistry,
)

# Default data + registry locations (can be overridden via config).
_DEFAULT_DATA = str(
    Path(__file__).resolve().parent.parent.parent / "data" / "look_and_feel_modules.txt"
)
_DEFAULT_REGISTRY = str(Path.home() / ".hermes" / "enterprise_look_and_feel_registry.json")


# ── Module class registered with the platform kernel ──────────────────────


@module(name="look_and_feel", version="1.0.0")
class LookAndFeelModule(Module):
    """Enterprise Look & Feel Registry Module.

    Lifecycle:
        initialize()   — (re)load the registry; seed from the default modules
                          file when the registry is empty.
        health_check() — verify registry is loaded and the parser is usable.
        shutdown()     — persist the registry to disk, transition to STOPPED.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._registry: LookAndFeelRegistry | None = None
        self._parser = LookAndFeelParser()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        registry_path = Path(self._config.get("registry_path", _DEFAULT_REGISTRY)).expanduser()
        self._registry = LookAndFeelRegistry(registry_path)
        self._status = HealthStatus.STARTING

        # Seed from the bundled module source when the registry is empty so the
        # 12 pre-loaded designs are always available on first boot.
        if len(self._registry) == 0:
            data_cfg = self._config.get("default_modules_path", _DEFAULT_DATA)
            data_path = Path(data_cfg).expanduser()
            if not data_path.is_absolute():
                data_path = Path(__file__).resolve().parent.parent.parent / data_path
            if data_path.exists():
                seed_entries = self._parser.parse_modules_file(
                    data_path.read_text(encoding="utf-8")
                )
                for entry in seed_entries:
                    self._registry.upsert(entry)
                if seed_entries:
                    self._registry.persist()

        self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        if self._registry is None or len(self._registry) == 0:
            self._status = HealthStatus.UNHEALTHY
        else:
            self._status = HealthStatus.HEALTHY
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        if self._registry is not None:
            self._registry.persist()
            self._registry = None
        self._status = HealthStatus.UNHEALTHY  # post-shutdown

    # ── Programmatic API ───────────────────────────────────────────────────

    def get_module(self, name: str) -> LookAndFeelEntry | None:
        if self._registry is None:
            return None
        return self._registry.get(name)

    def list_modules(self) -> list[LookAndFeelEntry]:
        if self._registry is None:
            return []
        return self._registry.all_modules()

    def search_by_tag(self, tag: str) -> list[LookAndFeelEntry]:
        if self._registry is None:
            return []
        return self._registry.search(tag)

    def run_cli(self, argv: list[str]) -> str:
        if self._registry is None:
            return "error: module not initialized"
        return LookAndFeelCLI(self._registry, self._parser).run(argv)


# ── Module factory (platform contract) ─────────────────────────────────────


def create_look_and_feel_module(config: dict[str, Any] | None = None) -> LookAndFeelModule:
    """Create and return a LookAndFeelModule instance.

    This is the standard platform factory entrypoint (see MODULE CONTRACT).
    """
    return LookAndFeelModule(config=config)


# ── Public API surface ──────────────────────────────────────────────────────

__all__ = [
    "LookAndFeelModule",
    "LookAndFeelEntry",
    "LookAndFeelParser",
    "LookAndFeelRegistry",
    "LookAndFeelCLI",
    "create_look_and_feel_module",
]

__version__ = "1.0.0"

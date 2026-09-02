"""ENI Build Telemetry Module — records + visualizes WHICH enterprise modules are used per build.

Provides the drag-and-drop enterprise plugin with:
  - ``telemetry.record(...)``  — log a module-use row (module, hook, tool, why) as a build happens
  - ``telemetry.gui_server``   — a stdlib web GUI (port 8930) showing per-project module usage,
                                functions created, steps, status, and each module's role/hook/why.

This is not a "capability" module that ships business logic — it is the observability
layer for the drop-in. It self-registers as a platform module so /enterprise apply
treats it like any other module (idempotent, healthy on import).
"""
# ruff: noqa: E402 ANN201 ANN202  # sys.path bootstrap import + platform-agnostic signature
from __future__ import annotations

import sys
from pathlib import Path

# make the package importable both as enterprise.module and standalone
_F = Path(__file__).resolve().parent
if str(_F.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(_F.parent.parent.parent))

from . import (
    gui_server,  # noqa: F401
    telemetry,  # noqa: F401
)


def create_telemetry_module(config: dict | None = None):  # noqa: ANN001
    """Return a minimal, healthy platform module wrapper (same contract as others)."""
    from enterprise.platform_kernel import HealthStatus, Module, module

    @module(name="telemetry", version="1.0.0")
    class TelemetryModule(Module):
        async def initialize(self) -> None:
            self.status = HealthStatus.HEALTHY

        async def health_check(self):
            return HealthStatus.HEALTHY

    return TelemetryModule(config=config)


__all__ = ["telemetry", "gui_server", "create_telemetry_module"]

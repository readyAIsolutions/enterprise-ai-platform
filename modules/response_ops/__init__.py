"""ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook.

Public surface:

  * :class:`FleetSupervisor` / :func:`create_fleet_supervisor` — the
    self-healing supervisor that probes known local service endpoints and, when
    a service is down, attempts a restart, logging to ``logs/supervisor.log``
    and publishing events on the kernel :class:`EventBus`.
  * :func:`icm_preflight` — a tiny broker-facing hook that imports the ICM
    classifier and returns ``{"route": "sequential" | "swarm",
    "sequential": bool}`` so an orchestration broker can pick an execution lane.
  * :class:`ResponseOpsModule` — the Platform Kernel module wrapper (registered
    via the ``@module`` decorator for auto-discovery).

CLI: ``python3 scripts/fleet_supervisor.py --check`` (one pass) or ``--watch``
(loop). Equivalent programmatic surface via :func:`main`.

Version: 1.0.0
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from enterprise.platform_kernel import HealthStatus, Module, module  # noqa: F401

from .routing import icm_preflight  # noqa: F401
from .supervisor import (  # noqa: F401
    DEFAULT_TIMEOUT,
    FleetSupervisor,
    ProbeResult,
    ServiceSpec,
    create_response_ops_module,
    default_services,
    main,
    probe_port,
)

_logger = logging.getLogger("enterprise.response_ops")

__version__ = "1.0.0"
__module__ = "response_ops"


def create_fleet_supervisor(
    config: Optional[Dict[str, Any]] = None,
    services: Optional[Sequence[ServiceSpec]] = None,
    **kwargs: Any,
) -> FleetSupervisor:
    """Create a :class:`FleetSupervisor` (convenience factory)."""
    return FleetSupervisor(config=config or {}, services=services, **kwargs)


__all__ = [
    "__version__",
    "ResponseOpsModule",
    "create_response_ops_module",
    "FleetSupervisor",
    "create_fleet_supervisor",
    "ServiceSpec",
    "ProbeResult",
    "probe_port",
    "default_services",
    "main",
    "icm_preflight",
    "DEFAULT_TIMEOUT",
]

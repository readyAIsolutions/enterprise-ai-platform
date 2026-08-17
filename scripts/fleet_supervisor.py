#!/usr/bin/env python3
"""ENI Fleet Supervisor — self-healing local service monitor (Upgrade A5).

Thin CLI wrapper around :class:`enterprise.modules.response_ops.
FleetSupervisor`. Probes the platform's known local service endpoints
(multiplayer :8788, controller :8913, dashboard :8421) and, when a service is
down, attempts a restart — logging to ``logs/supervisor.log`` and publishing an
event on the kernel EventBus.

Usage:
    python3 scripts/fleet_supervisor.py --check     # one probe pass, list status
    python3 scripts/fleet_supervisor.py --watch     # probe-and-heal loop
    python3 scripts/fleet_supervisor.py --watch --interval 15
    python3 scripts/fleet_supervisor.py --check --dry-run   # detect, don't heal

Exit code: 0 = all services up; 1 = at least one service down (--check).
"""
from __future__ import annotations

import sys

from enterprise.modules.response_ops import main

if __name__ == "__main__":
    sys.exit(main())

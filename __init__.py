"""
ENI Enterprise Platform — Core package.
All enterprise modules are orchestrated by the Platform Kernel.
"""

__version__ = "1.0.0"
__author__ = "Eni Builder Enterprise"

from .platform_kernel import (
    PlatformOS,
    ModuleRegistry,
    EventBus,
    module,
    HealthStatus,
    LifecycleState,
)

__all__ = [
    "PlatformOS",
    "ModuleRegistry",
    "EventBus",
    "module",
    "HealthStatus",
    "LifecycleState",
]
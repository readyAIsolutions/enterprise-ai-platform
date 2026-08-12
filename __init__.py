"""
ENI Enterprise Platform — Core package.
All enterprise modules are orchestrated by the Platform Kernel.
"""

__version__ = "2.0.0"
__author__ = "Eni Builder Enterprise"

# Import the kernel only when this file is loaded as a real package (i.e. has a
# parent package name). When pytest imports this __init__.py as a bare top-level
# module (e.g. when the checkout dir name isn't a valid module identifier on CI),
# __package__ is empty and a relative import would crash — so guard it.
if __package__:
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
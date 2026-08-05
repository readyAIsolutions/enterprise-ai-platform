"""
Customer Experience OS Module.

Provides a comprehensive suite for managing the end-to-end customer journey,
including journey mapping, support ticketing, AI-assisted support guardrails,
CX metrics, feedback analysis, and communication templates.

Version: 1.0.0
"""

__version__ = "1.0.0"
__module_name__ = "customer_experience"

from .journey import (
    JourneyStage,
    JourneyTouchpoint,
    JourneyMap,
    JourneyEngine,
)
from .support import (
    SeverityLevel,
    TicketStatus,
    SupportTicket,
    SupportEngine,
)
from .ai_support import (
    AISupportRule,
    AISupportInteraction,
    AISupportGuard,
)
from .metrics import (
    CXMetric,
    MetricSnapshot,
    CXMetricsEngine,
)
from .feedback import (
    FeedbackSource,
    FeedbackEntry,
    FeedbackEngine,
)
from .templates import (
    TemplateType,
    CommsTemplate,
    TemplateManager,
)

__all__ = [
    # journey
    "JourneyStage",
    "JourneyTouchpoint",
    "JourneyMap",
    "JourneyEngine",
    # support
    "SeverityLevel",
    "TicketStatus",
    "SupportTicket",
    "SupportEngine",
    # ai_support
    "AISupportRule",
    "AISupportInteraction",
    "AISupportGuard",
    # metrics
    "CXMetric",
    "MetricSnapshot",
    "CXMetricsEngine",
    # feedback
    "FeedbackSource",
    "FeedbackEntry",
    "FeedbackEngine",
    # templates
    "TemplateType",
    "CommsTemplate",
    "TemplateManager",
]

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio
import logging
import threading
from typing import Any, Dict, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

_KERNEL_VERSION = globals().get("__version__", "1.0.0")

from .journey import JourneyEngine

_logger = logging.getLogger("enterprise.customer_experience")


@module(name="customer_experience", version=_KERNEL_VERSION)
class CustomerExperienceModule(Module):
    """Kernel-managed wrapper around the customer_experience OS module.

    Wraps the most representative entrypoint (JourneyEngine) so the platform kernel
    can initialize it, probe its health, and shut it down as part of the ENI
    lifecycle. If the core component cannot be instantiated the module reports
    UNHEALTHY rather than crashing the platform.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._lock = threading.RLock()
        self._component = None
        self._init_error = None

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            try:
                self._component = JourneyEngine()
                self._status = HealthStatus.HEALTHY
                _logger.info("%s module initialized", self.name)
            except Exception as e:  # pragma: no cover - degrade gracefully
                self._init_error = str(e)
                self._status = HealthStatus.UNHEALTHY
                _logger.warning("%s module failed to initialize: %s", self.name, e)

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._component is None:
                return HealthStatus.UNHEALTHY if self._init_error else HealthStatus.DEGRADED
            try:
                self._component.map_journey("kernel_probe")
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_customer_experience_module(config: Optional[Dict[str, Any]] = None) -> CustomerExperienceModule:
    """Factory: create a customer_experience module instance."""
    return CustomerExperienceModule(config)

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
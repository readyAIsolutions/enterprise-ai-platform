"""
Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling,
shared knowledge, conflict resolution, verification, and fault tolerance.

Version: 1.0.0
"""

__version__ = "1.0.0"

# ── Core agents ─────────────────────────────────────────────────────────────
from .agents import (  # noqa: F401
    AGENT_ID_TO_TYPE,
    AGENT_TYPE_TO_ID,
    Agent,
    AgentFactory,
    AgentRegistry,
    AgentStatus,
    AgentType,
    AIEngineer,
    Architect,
    AuthorityLevel,
    BackendEngineer,
    BusinessAnalyst,
    ComplianceOfficer,
    CXSpecialist,
    DataEngineer,
    DevSecOps,
    DocumentationWriter,
    ExecutiveOrchestrator,
    FrontendEngineer,
    PerformanceEngineer,
    ProductManager,
    QAEngineer,
    ResearchAgent,
    SecurityEngineer,
    UIDesigner,
)

# ── Communication ───────────────────────────────────────────────────────────
from .communication import (  # noqa: F401
    AuditEntry,
    AuditTrail,
    CompletionStatus,
    Message,
    MessageBus,
    MessageValidation,
    MessageVersionTracker,
    Priority,
    PriorityMessageQueue,
)

# ── Conflict Resolution ─────────────────────────────────────────────────────
from .conflict import (  # noqa: F401
    AgentPosition,
    Conflict,
    ConflictResolver,
    ConflictStatus,
    Evidence as ConflictEvidence,
    EvidenceComparisonEngine,
    EvidenceSourceType,
    ResolutionStrategy,
    TradeOffDimension,
    TradeOffMatrix,
)

# ── Durable Scheduler / Message Bus ──────────────────────────────────────────
from .durable_scheduler import (  # noqa: F401
    DeadLetterError,
    DurableScheduler,
    LeaseError,
    SchedulerBus,
    SchedulerError,
    TaskNotFoundError,
    TaskQueue,
    TaskRecord,
    TaskStatus as DurableTaskStatus,
    create_durable_scheduler,
)

# ── Fault Tolerance ─────────────────────────────────────────────────────────
from .fault_tolerance import (  # noqa: F401
    AgentHealth,
    AgentNotFoundError,
    Checkpoint,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    FaultToleranceError,
    FaultToleranceManager,
    Incident,
    IncidentSeverity,
    NoAvailableAgentsError,
    RecoveryPhase,
    RedundancyMode,
    RetryExhaustedError,
    RetryPolicy,
    SystemHealthReport,
)

# ── Scheduler ───────────────────────────────────────────────────────────────
from .scheduler import (  # noqa: F401
    AgentCapacity,
    Scheduler,
    SchedulingFactor,
    Task,
    TaskStatus,
)

# ── Shared Knowledge ────────────────────────────────────────────────────────
from .shared_knowledge import (  # noqa: F401
    AccessLevel,
    KnowledgeDomain,
    KnowledgeEntry,
    SharedKnowledgeBase,
)

# ── Verification ────────────────────────────────────────────────────────────
from .verification import (  # noqa: F401
    GateAction,
    IndependenceViolation,
    Severity,
    VerificationCheck,
    VerificationDomain,
    VerificationError,
    VerificationGate,
    VerificationResult,
    VerificationStatus,
    Verifier,
)

__all__ = [
    # Agents
    "Agent",
    "AgentRegistry",
    "AgentFactory",
    "AgentStatus",
    "AgentType",
    "AuthorityLevel",
    "ExecutiveOrchestrator",
    "ProductManager",
    "ResearchAgent",
    "Architect",
    "BackendEngineer",
    "FrontendEngineer",
    "UIDesigner",
    "AIEngineer",
    "DataEngineer",
    "SecurityEngineer",
    "DevSecOps",
    "QAEngineer",
    "PerformanceEngineer",
    "ComplianceOfficer",
    "DocumentationWriter",
    "BusinessAnalyst",
    "CXSpecialist",
    "AGENT_TYPE_TO_ID",
    "AGENT_ID_TO_TYPE",
    # Communication
    "Message",
    "MessageBus",
    "MessageVersionTracker",
    "AuditTrail",
    "AuditEntry",
    "CompletionStatus",
    "Priority",
    "MessageValidation",
    "PriorityMessageQueue",
    # Scheduler
    "Task",
    "Scheduler",
    "TaskStatus",
    "SchedulingFactor",
    "AgentCapacity",
    # Shared Knowledge
    "KnowledgeEntry",
    "SharedKnowledgeBase",
    "KnowledgeDomain",
    "AccessLevel",
    # Conflict
    "Conflict",
    "ConflictResolver",
    "ConflictStatus",
    "ResolutionStrategy",
    "ConflictEvidence",
    "AgentPosition",
    "TradeOffDimension",
    "EvidenceSourceType",
    "TradeOffMatrix",
    "EvidenceComparisonEngine",
    # Verification
    "Verifier",
    "VerificationDomain",
    "VerificationStatus",
    "Severity",
    "VerificationCheck",
    "VerificationGate",
    "VerificationResult",
    "GateAction",
    "VerificationError",
    "IndependenceViolation",
    # Fault Tolerance
    "FaultToleranceManager",
    "CircuitBreaker",
    "RetryPolicy",
    "AgentHealth",
    "Incident",
    "IncidentSeverity",
    "CircuitState",
    "RecoveryPhase",
    "RedundancyMode",
    "Checkpoint",
    "SystemHealthReport",
    "FaultToleranceError",
    "AgentNotFoundError",
    "NoAvailableAgentsError",
    "CircuitOpenError",
    "RetryExhaustedError",
    # Durable Scheduler / Message Bus
    "DurableScheduler",
    "TaskQueue",
    "SchedulerBus",
    "DurableTaskStatus",
    "TaskRecord",
    "SchedulerError",
    "LeaseError",
    "TaskNotFoundError",
    "DeadLetterError",
    "create_durable_scheduler",
]

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio  # noqa: F401
import logging
import threading
from typing import Any  # noqa: F401

from enterprise.platform_kernel import HealthStatus, Module, module

_KERNEL_VERSION = globals().get("__version__", "1.0.0")


_logger = logging.getLogger("enterprise.agent_coordination")


@module(name="agent_coordination", version=_KERNEL_VERSION)
class AgentCoordinationModule(Module):
    """Kernel-managed wrapper around the agent_coordination OS module.

    Wraps the most representative entrypoint (AgentRegistry) so the platform kernel
    can initialize it, probe its health, and shut it down as part of the ENI
    lifecycle. If the core component cannot be instantiated the module reports
    UNHEALTHY rather than crashing the platform.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._lock = threading.RLock()
        self._component = None
        self._init_error = None

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            try:
                self._component = AgentRegistry()
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
                if (
                    not getattr(self._component, "_agent_classes", None)
                    or len(self._component._agent_classes) == 0
                ):
                    return HealthStatus.DEGRADED
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_agent_coordination_module(
    config: dict[str, Any] | None = None,
) -> AgentCoordinationModule:
    """Factory: create a agent_coordination module instance."""
    return AgentCoordinationModule(config)

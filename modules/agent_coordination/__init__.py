"""
Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling,
shared knowledge, conflict resolution, verification, and fault tolerance.

Version: 1.0.0
"""
__version__ = "1.0.0"

# ── Core agents ─────────────────────────────────────────────────────────────
from .agents import (  # noqa: F401
    Agent, AgentRegistry, AgentFactory, AgentStatus, AgentType, AuthorityLevel,
    ExecutiveOrchestrator, ProductManager, ResearchAgent, Architect,
    BackendEngineer, FrontendEngineer, UIDesigner, AIEngineer, DataEngineer,
    SecurityEngineer, DevSecOps, QAEngineer, PerformanceEngineer,
    ComplianceOfficer, DocumentationWriter, BusinessAnalyst, CXSpecialist,
    AGENT_TYPE_TO_ID, AGENT_ID_TO_TYPE,
)

# ── Communication ───────────────────────────────────────────────────────────
from .communication import (  # noqa: F401
    Message, MessageBus, MessageVersionTracker, AuditTrail, AuditEntry,
    CompletionStatus, Priority, MessageValidation, PriorityMessageQueue,
)

# ── Scheduler ───────────────────────────────────────────────────────────────
from .scheduler import (  # noqa: F401
    Task, Scheduler, TaskStatus, SchedulingFactor, AgentCapacity,
)

# ── Shared Knowledge ────────────────────────────────────────────────────────
from .shared_knowledge import (  # noqa: F401
    KnowledgeEntry, SharedKnowledgeBase, KnowledgeDomain, AccessLevel,
)

# ── Conflict Resolution ─────────────────────────────────────────────────────
from .conflict import (  # noqa: F401
    Conflict, ConflictResolver, ConflictStatus, ResolutionStrategy,
    Evidence as ConflictEvidence, AgentPosition,
    TradeOffDimension, EvidenceSourceType, TradeOffMatrix, EvidenceComparisonEngine,
)

# ── Verification ────────────────────────────────────────────────────────────
from .verification import (  # noqa: F401
    Verifier, VerificationDomain, VerificationStatus, Severity,
    VerificationCheck, VerificationGate, VerificationResult,
    GateAction, VerificationError, IndependenceViolation,
)

# ── Fault Tolerance ─────────────────────────────────────────────────────────
from .fault_tolerance import (  # noqa: F401
    FaultToleranceManager, CircuitBreaker, RetryPolicy,
    AgentHealth, Incident, IncidentSeverity, CircuitState,
    RecoveryPhase, RedundancyMode, Checkpoint, SystemHealthReport,
    FaultToleranceError, AgentNotFoundError, NoAvailableAgentsError,
    CircuitOpenError, RetryExhaustedError,
)

__all__ = [
    # Agents
    "Agent", "AgentRegistry", "AgentFactory", "AgentStatus", "AgentType", "AuthorityLevel",
    "ExecutiveOrchestrator", "ProductManager", "ResearchAgent", "Architect",
    "BackendEngineer", "FrontendEngineer", "UIDesigner", "AIEngineer", "DataEngineer",
    "SecurityEngineer", "DevSecOps", "QAEngineer", "PerformanceEngineer",
    "ComplianceOfficer", "DocumentationWriter", "BusinessAnalyst", "CXSpecialist",
    "AGENT_TYPE_TO_ID", "AGENT_ID_TO_TYPE",
    # Communication
    "Message", "MessageBus", "MessageVersionTracker", "AuditTrail", "AuditEntry",
    "CompletionStatus", "Priority", "MessageValidation", "PriorityMessageQueue",
    # Scheduler
    "Task", "Scheduler", "TaskStatus", "SchedulingFactor", "AgentCapacity",
    # Shared Knowledge
    "KnowledgeEntry", "SharedKnowledgeBase", "KnowledgeDomain", "AccessLevel",
    # Conflict
    "Conflict", "ConflictResolver", "ConflictStatus", "ResolutionStrategy",
    "ConflictEvidence", "AgentPosition",
    "TradeOffDimension", "EvidenceSourceType", "TradeOffMatrix", "EvidenceComparisonEngine",
    # Verification
    "Verifier", "VerificationDomain", "VerificationStatus", "Severity",
    "VerificationCheck", "VerificationGate", "VerificationResult",
    "GateAction", "VerificationError", "IndependenceViolation",
    # Fault Tolerance
    "FaultToleranceManager", "CircuitBreaker", "RetryPolicy",
    "AgentHealth", "Incident", "IncidentSeverity", "CircuitState",
    "RecoveryPhase", "RedundancyMode", "Checkpoint", "SystemHealthReport",
    "FaultToleranceError", "AgentNotFoundError", "NoAvailableAgentsError",
    "CircuitOpenError", "RetryExhaustedError",
]
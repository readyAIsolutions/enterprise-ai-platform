"""
ENI Enterprise Integration Layer
=================================
Production-grade integration backbone that wires ALL enterprise modules
together into a cohesive platform.

Components:
    api_gateway  — FastAPI-based unified API gateway with auth, rate limiting, OpenAPI docs
    event_hub    — Central event routing between modules via Platform Kernel EventBus
    service_mesh — Service discovery, health checking, circuit breaking, load balancing

Architecture:
    The Integration Layer sits between external clients and the enterprise modules,
    providing a single entry point (API Gateway), internal message routing (Event Hub),
    and resilient service-to-service communication (Service Mesh).

    ┌─────────────────────────────────────────────────────┐
    │                  External Clients                    │
    └─────────────────────┬───────────────────────────────┘
                          │ REST / WebSocket
    ┌─────────────────────▼───────────────────────────────┐
    │              API Gateway (FastAPI)                   │
    │    Auth • Rate Limit • Validation • OpenAPI Docs    │
    └──────┬───────────────────────────────┬──────────────┘
           │                               │
    ┌──────▼──────────┐           ┌───────▼──────────────┐
    │   Event Hub      │◄─────────►│   Service Mesh       │
    │  Pub/Sub • DLQ  │           │  Discovery • CB • LB │
    └──────┬──────────┘           └───────┬──────────────┘
           │                               │
    ┌──────▼───────────────────────────────▼──────────────┐
    │              Enterprise Modules (10 OS modules)      │
    │  Safety | Privacy | Prompts | Agents | Knowledge    │
    │    DX   | Innovation | DR | Releases | CX           │
    └─────────────────────────────────────────────────────┘

Usage:
    # Start the API gateway
    from enterprise.integration import get_gateway_app
    app = get_gateway_app()
    # Then: uvicorn enterprise.integration.api_gateway:get_app --reload

    # Publish an event
    from enterprise.integration import publish_event
    publish_event("safety.guardrail.triggered", "my_module", {"result": "passed"})

    # Service mesh
    from enterprise.integration import get_service_mesh
    mesh = get_service_mesh()
    mesh.register("my_service", host="0.0.0.0", port=9000)
"""

__version__ = "1.0.0"
__author__ = "ENI Enterprise"

# typing imports used in annotations below — required on Python <3.14 where
# function annotations are evaluated eagerly (3.14+ defers them, masking the miss)
from typing import Any, Dict

# ── API Gateway ──────────────────────────────────────────────────────────
from enterprise.integration.api_gateway import (
    API_VERSION,
    API_PREFIX,
    AuthHandler,
    RateLimiter,
    TokenBucket,
    create_app,
    get_app as get_gateway_app,
    get_deps,
    run as run_gateway,
    # Request/Response models
    EventPublishRequest,
    ErrorResponse,
    GateUpdateRequest,
    HealthStatus as GatewayHealthStatus,
    KernelContextCreate,
    KernelContextResponse,
    ModuleHealthResponse,
    OrchestrationTask,
    PlatformHealthResponse,
)

# ── Event Hub ────────────────────────────────────────────────────────────
from enterprise.integration.event_hub import (
    # Core
    EventBus,
    EventEnvelope,
    EventPriority,
    EventSchema,
    EventStatus,
    EventSubscription,
    EventTracer,
    # Contracts
    ContractDirection,
    EventContract,
    # Queues
    DeadLetterQueue,
    # Sync bridge
    SyncEventPublisher,
    # Convenience
    create_standard_contracts,
    get_event_hub,
    get_sync_publisher,
    publish_event,
)

# ── Service Mesh ─────────────────────────────────────────────────────────
from enterprise.integration.service_mesh import (
    # Core
    ServiceMesh,
    ServiceRegistry,
    HealthChecker,
    HealthCheckConfig,
    HealthRecord,
    HealthStatus as MeshHealthStatus,
    # Circuit Breaker
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    # Load Balancing
    LoadBalancer,
    LoadBalanceStrategy,
    # Resilience
    ResilienceManager,
    RetryConfig,
    # Data Models
    ServiceInstance,
    # Topology
    MeshTopology,
    # Singleton
    get_service_mesh,
)

# ── Convenience: Initialize Integration Layer ────────────────────────────


def init_integration(auto_discover: bool = True) -> Dict[str, Any]:
    """Initialize the full integration layer.

    Sets up the event hub, service mesh, and optionally auto-discovers
    modules from the kernel.

    Returns:
        Dict with status of each component.
    """
    status = {"event_hub": "initialized", "service_mesh": "initialized", "api_gateway": "ready"}

    # Initialize event hub
    hub = get_event_hub()
    # Register standard contracts
    for contract in create_standard_contracts():
        hub.register_contract(contract)
    status["contracts_registered"] = len(create_standard_contracts())
    status["schemas_registered"] = len(hub.list_schemas())

    # Initialize service mesh
    mesh = get_service_mesh()
    if auto_discover:
        mesh.discover_from_kernel()
    services = mesh.list_services()
    status["services_discovered"] = len(services)

    return status


__all__ = [
    # Version
    "__version__",
    "__author__",
    # API Gateway
    "get_gateway_app",
    "create_app",
    "run_gateway",
    "get_deps",
    "AuthHandler",
    "RateLimiter",
    "TokenBucket",
    "API_VERSION",
    "API_PREFIX",
    "EventPublishRequest",
    "ErrorResponse",
    "GateUpdateRequest",
    "GatewayHealthStatus",
    "KernelContextCreate",
    "KernelContextResponse",
    "ModuleHealthResponse",
    "OrchestrationTask",
    "PlatformHealthResponse",
    # Event Hub
    "EventBus",
    "EventEnvelope",
    "EventPriority",
    "EventSchema",
    "EventStatus",
    "EventSubscription",
    "EventTracer",
    "ContractDirection",
    "EventContract",
    "DeadLetterQueue",
    "SyncEventPublisher",
    "create_standard_contracts",
    "get_event_hub",
    "get_sync_publisher",
    "publish_event",
    # Service Mesh
    "ServiceMesh",
    "ServiceRegistry",
    "HealthChecker",
    "HealthCheckConfig",
    "HealthRecord",
    "MeshHealthStatus",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitOpenError",
    "CircuitState",
    "LoadBalancer",
    "LoadBalanceStrategy",
    "ResilienceManager",
    "RetryConfig",
    "ServiceInstance",
    "MeshTopology",
    "get_service_mesh",
    # Init
    "init_integration",
]
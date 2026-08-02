"""
Internal Developer Platform (IDP)
=================================
Enterprise Internal Developer Platform providing self-service
capabilities to developers. Abstracts infrastructure complexity
behind a unified interface with guardrails.

Capabilities:
    - Project creation with templates
    - Repository template provisioning
    - Environment provisioning
    - Secrets management requests
    - Database provisioning
    - Deployment orchestration
    - Rollback management
    - Monitoring and log access
    - Access request workflows
    - Service catalog
    - Documentation discovery
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import logging
import uuid
from collections import defaultdict

logger = logging.getLogger(__name__)


class CapabilityStatus(Enum):
    """Status of a platform capability request."""
    PENDING = "pending"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class CapabilityCategory(Enum):
    """Categories of platform capabilities."""
    PROJECT = "project"
    INFRASTRUCTURE = "infrastructure"
    DATA = "data"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    OBSERVABILITY = "observability"
    ACCESS = "access"


@dataclass
class IDPCapability:
    """Definition of an Internal Developer Platform capability."""
    id: str
    name: str
    description: str
    category: CapabilityCategory
    api_endpoint: str
    required_approvals: List[str] = field(default_factory=list)  # Roles needed
    sla_minutes: int = 60  # SLA for fulfillment
    self_service: bool = True  # Can be self-served or needs manual approval
    documentation_url: str = ""
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    rate_limit_per_hour: int = 10
    tags: List[str] = field(default_factory=list)


@dataclass
class PlatformRequest:
    """A request made against the platform for a capability."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    capability_id: str = ""
    requested_by: str = ""
    team: str = ""
    status: CapabilityStatus = CapabilityStatus.PENDING
    parameters: Dict[str, Any] = field(default_factory=dict)
    approvers: List[str] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    audit_log: List[Dict[str, Any]] = field(default_factory=list)

    def add_audit_entry(self, action: str, actor: str, details: str = "") -> None:
        """Add an entry to the request's audit log."""
        self.audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "actor": actor,
            "details": details,
        })

    def approve(self, approver: str) -> None:
        """Approve the request."""
        self.status = CapabilityStatus.APPROVED
        self.approvers.append(approver)
        self.add_audit_entry("approved", approver)

    def reject(self, approver: str, reason: str) -> None:
        """Reject the request."""
        self.status = CapabilityStatus.REJECTED
        self.error_message = reason
        self.add_audit_entry("rejected", approver, reason)

    def complete(self, result: Dict[str, Any]) -> None:
        """Mark the request as completed."""
        self.status = CapabilityStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.result = result
        self.add_audit_entry("completed", "platform", str(result))

    def fail(self, error: str) -> None:
        """Mark the request as failed."""
        self.status = CapabilityStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()
        self.add_audit_entry("failed", "platform", error)


@dataclass
class ServiceEntry:
    """An entry in the service catalog."""
    service_id: str
    name: str
    description: str
    team: str
    repo_url: str
    language: str
    status: str = "active"  # active, deprecated, retired
    health: str = "healthy"  # healthy, degraded, down
    sla_tier: str = "standard"  # standard, high, critical
    owners: List[str] = field(default_factory=list)
    tech_lead: str = ""
    on_call_rotation: str = ""
    documentation_path: str = ""
    runbook_path: str = ""
    dependencies: List[str] = field(default_factory=list)
    consumers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    last_deployed: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


# --- Platform Capability Definitions ---

PLATFORM_CAPABILITIES: List[IDPCapability] = [
    IDPCapability(
        id="CAP-PROJECT-CREATE",
        name="Project Creation",
        description="Create a new project with repo, CI/CD, and basic scaffolding.",
        category=CapabilityCategory.PROJECT,
        api_endpoint="/api/v1/projects",
        self_service=True,
        sla_minutes=5,
        documentation_url="https://docs.internal.company.com/platform/projects",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Project name"},
                "template": {"type": "string", "description": "Template ID"},
                "team": {"type": "string", "description": "Owning team"},
                "language": {"type": "string", "description": "Primary language"},
                "visibility": {"enum": ["private", "internal", "public"]},
            },
            "required": ["name", "template", "team"],
        },
        tags=["project", "scaffold"],
    ),
    IDPCapability(
        id="CAP-REPO-TEMPLATE",
        name="Repository Templates",
        description="Provision a repository from a standardized template.",
        category=CapabilityCategory.PROJECT,
        api_endpoint="/api/v1/repos/templates",
        self_service=True,
        sla_minutes=2,
        documentation_url="https://docs.internal.company.com/platform/repo-templates",
        input_schema={
            "type": "object",
            "properties": {
                "template_id": {"type": "string"},
                "repo_name": {"type": "string"},
                "team": {"type": "string"},
            },
            "required": ["template_id", "repo_name"],
        },
        tags=["repo", "template", "scaffold"],
    ),
    IDPCapability(
        id="CAP-ENV-PROVISION",
        name="Environment Provisioning",
        description="Provision a development/staging/ephemeral environment.",
        category=CapabilityCategory.INFRASTRUCTURE,
        api_endpoint="/api/v1/environments",
        self_service=True,
        sla_minutes=10,
        documentation_url="https://docs.internal.company.com/platform/environments",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "environment": {"enum": ["dev", "staging", "ephemeral"]},
                "branch": {"type": "string"},
                "ttl_hours": {"type": "integer", "description": "Time to live for ephemeral envs"},
            },
            "required": ["project", "environment"],
        },
        tags=["environment", "dev", "staging", "ephemeral"],
    ),
    IDPCapability(
        id="CAP-SECRETS-REQUEST",
        name="Secrets Requests",
        description="Request and manage secrets (API keys, credentials) with audit trail.",
        category=CapabilityCategory.SECURITY,
        api_endpoint="/api/v1/secrets",
        self_service=False,
        required_approvals=["tech_lead", "security"],
        sla_minutes=60,
        documentation_url="https://docs.internal.company.com/platform/secrets",
        input_schema={
            "type": "object",
            "properties": {
                "secret_name": {"type": "string"},
                "secret_type": {"enum": ["api_key", "certificate", "credential", "token"]},
                "project": {"type": "string"},
                "justification": {"type": "string"},
                "rotation_days": {"type": "integer"},
            },
            "required": ["secret_name", "secret_type", "project", "justification"],
        },
        tags=["secrets", "security", "vault"],
    ),
    IDPCapability(
        id="CAP-DB-PROVISION",
        name="Database Provisioning",
        description="Provision a new database instance or schema.",
        category=CapabilityCategory.DATA,
        api_endpoint="/api/v1/databases",
        self_service=True,
        sla_minutes=15,
        documentation_url="https://docs.internal.company.com/platform/databases",
        input_schema={
            "type": "object",
            "properties": {
                "db_type": {"enum": ["postgresql", "mysql", "mongodb", "redis", "elasticsearch"]},
                "environment": {"enum": ["dev", "staging", "production"]},
                "size": {"enum": ["small", "medium", "large"]},
                "project": {"type": "string"},
                "backup_enabled": {"type": "boolean"},
                "ha_enabled": {"type": "boolean"},
            },
            "required": ["db_type", "environment", "project"],
        },
        tags=["database", "provisioning", "data"],
    ),
    IDPCapability(
        id="CAP-DEPLOY",
        name="Deployment",
        description="Deploy a service version to a target environment.",
        category=CapabilityCategory.DEPLOYMENT,
        api_endpoint="/api/v1/deployments",
        self_service=True,
        sla_minutes=30,
        documentation_url="https://docs.internal.company.com/platform/deployments",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "version": {"type": "string"},
                "environment": {"enum": ["staging", "production"]},
                "strategy": {"enum": ["rolling", "canary", "blue-green"]},
                "canary_percentage": {"type": "integer"},
            },
            "required": ["service", "version", "environment"],
        },
        tags=["deploy", "cd", "release"],
    ),
    IDPCapability(
        id="CAP-ROLLBACK",
        name="Rollback",
        description="Roll back a service to a previous version.",
        category=CapabilityCategory.DEPLOYMENT,
        api_endpoint="/api/v1/rollbacks",
        self_service=True,
        sla_minutes=5,
        documentation_url="https://docs.internal.company.com/platform/rollbacks",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "target_version": {"type": "string"},
                "environment": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["service", "environment"],
        },
        tags=["rollback", "deploy", "revert"],
    ),
    IDPCapability(
        id="CAP-MONITORING",
        name="Monitoring Access",
        description="Access monitoring dashboards, metrics, and set up alerts.",
        category=CapabilityCategory.OBSERVABILITY,
        api_endpoint="/api/v1/monitoring",
        self_service=True,
        sla_minutes=5,
        documentation_url="https://docs.internal.company.com/platform/monitoring",
        tags=["monitoring", "dashboards", "alerts", "metrics"],
    ),
    IDPCapability(
        id="CAP-LOG-ACCESS",
        name="Log Access",
        description="Access centralized logs with search and filtering.",
        category=CapabilityCategory.OBSERVABILITY,
        api_endpoint="/api/v1/logs",
        self_service=True,
        sla_minutes=1,
        documentation_url="https://docs.internal.company.com/platform/logs",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "environment": {"type": "string"},
                "time_range": {"type": "string", "description": "e.g., '1h', '24h', '7d'"},
                "query": {"type": "string"},
            },
            "required": ["service"],
        },
        tags=["logs", "observability", "debugging"],
    ),
    IDPCapability(
        id="CAP-ACCESS-REQUEST",
        name="Access Requests",
        description="Request access to systems, repos, environments.",
        category=CapabilityCategory.ACCESS,
        api_endpoint="/api/v1/access",
        self_service=False,
        required_approvals=["manager", "resource_owner"],
        sla_minutes=120,
        documentation_url="https://docs.internal.company.com/platform/access",
        input_schema={
            "type": "object",
            "properties": {
                "resource": {"type": "string"},
                "access_level": {"enum": ["read", "write", "admin"]},
                "justification": {"type": "string"},
                "duration_days": {"type": "integer"},
            },
            "required": ["resource", "access_level", "justification"],
        },
        tags=["access", "iam", "permissions"],
    ),
    IDPCapability(
        id="CAP-SERVICE-CATALOG",
        name="Service Catalog",
        description="Browse and search the organization's service catalog.",
        category=CapabilityCategory.PROJECT,
        api_endpoint="/api/v1/catalog",
        self_service=True,
        sla_minutes=0,  # Instant
        documentation_url="https://docs.internal.company.com/platform/catalog",
        tags=["catalog", "discovery", "services"],
    ),
    IDPCapability(
        id="CAP-DOCS-DISCOVERY",
        name="Documentation Discovery",
        description="Search and discover project documentation across the organization.",
        category=CapabilityCategory.PROJECT,
        api_endpoint="/api/v1/docs/discover",
        self_service=True,
        sla_minutes=0,  # Instant
        documentation_url="https://docs.internal.company.com/platform/docs",
        tags=["docs", "discovery", "search"],
    ),
]


# --- Service Catalog (in-memory) ---

_service_catalog: Dict[str, ServiceEntry] = {}


# --- Request Store ---

_request_store: Dict[str, PlatformRequest] = {}


# --- Public API ---

def get_capability(capability_id: str) -> Optional[IDPCapability]:
    """Retrieve a platform capability by ID."""
    for cap in PLATFORM_CAPABILITIES:
        if cap.id == capability_id:
            return cap
    return None


def list_capabilities(
    category: Optional[CapabilityCategory] = None,
    self_service: Optional[bool] = None,
    tags: Optional[List[str]] = None,
) -> List[IDPCapability]:
    """List platform capabilities with optional filters."""
    capabilities = PLATFORM_CAPABILITIES
    if category:
        capabilities = [c for c in capabilities if c.category == category]
    if self_service is not None:
        capabilities = [c for c in capabilities if c.self_service == self_service]
    if tags:
        tag_set = set(tags)
        capabilities = [c for c in capabilities if tag_set & set(c.tags)]
    return capabilities


def request_capability(
    capability_id: str,
    requested_by: str,
    team: str,
    parameters: Dict[str, Any],
) -> PlatformRequest:
    """Create a self-service request against a platform capability.

    This is the main entry point for developers to request platform
    resources and actions.
    """
    capability = get_capability(capability_id)
    if not capability:
        raise ValueError(f"Capability not found: {capability_id}")

    # Validate input against schema
    if capability.input_schema:
        required = capability.input_schema.get("required", [])
        missing = [r for r in required if r not in parameters]
        if missing:
            raise ValueError(
                f"Missing required parameters for {capability_id}: {missing}"
            )

    request = PlatformRequest(
        capability_id=capability_id,
        requested_by=requested_by,
        team=team,
        parameters=parameters,
    )
    request.add_audit_entry("created", requested_by, f"Capability: {capability_id}")

    if capability.self_service:
        request.status = CapabilityStatus.APPROVED
        request.add_audit_entry("auto_approved", "platform", "Self-service capability")
    else:
        request.status = CapabilityStatus.PENDING
        # In real system, notify approvers

    _request_store[request.id] = request
    logger.info(
        f"Platform request created: {request.id} for {capability_id} "
        f"by {requested_by}"
    )
    return request


def self_service_action(
    capability_id: str,
    requested_by: str,
    team: str,
    parameters: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a self-service action immediately and return the result.

    If the capability is not self-service, raises an error.
    """
    capability = get_capability(capability_id)
    if not capability:
        raise ValueError(f"Capability not found: {capability_id}")

    if not capability.self_service:
        raise ValueError(
            f"Capability {capability_id} is not self-service. "
            f"Use request_capability() to submit a request for approval."
        )

    request = request_capability(capability_id, requested_by, team, parameters)

    # Simulate immediate completion for self-service
    result = {
        "request_id": request.id,
        "capability": capability.name,
        "status": "completed",
        "message": f"Self-service action '{capability.name}' executed successfully.",
        "parameters": parameters,
    }
    request.complete(result)

    return result


def get_service_catalog(
    team: Optional[str] = None,
    status: Optional[str] = None,
    language: Optional[str] = None,
    query: Optional[str] = None,
) -> List[ServiceEntry]:
    """Query the service catalog with optional filters."""
    services = list(_service_catalog.values())

    if team:
        services = [s for s in services if s.team == team]
    if status:
        services = [s for s in services if s.status == status]
    if language:
        services = [s for s in services if s.language == language]
    if query:
        query_lower = query.lower()
        services = [
            s for s in services
            if query_lower in s.name.lower()
            or query_lower in s.description.lower()
            or any(query_lower in t.lower() for t in s.tags)
        ]

    return services


def register_service(service: ServiceEntry) -> ServiceEntry:
    """Register a new service in the catalog."""
    _service_catalog[service.service_id] = service
    logger.info(f"Service registered: {service.name} ({service.service_id})")
    return service


def deregister_service(service_id: str) -> bool:
    """Remove a service from the catalog."""
    if service_id in _service_catalog:
        del _service_catalog[service_id]
        logger.info(f"Service deregistered: {service_id}")
        return True
    return False


def get_request(request_id: str) -> Optional[PlatformRequest]:
    """Retrieve a platform request by ID."""
    return _request_store.get(request_id)


def get_user_requests(user: str, status: Optional[CapabilityStatus] = None) -> List[PlatformRequest]:
    """Get all requests for a given user."""
    requests = [r for r in _request_store.values() if r.requested_by == user]
    if status:
        requests = [r for r in requests if r.status == status]
    return sorted(requests, key=lambda r: r.created_at, reverse=True)


def get_pending_approvals(approver_role: str) -> List[PlatformRequest]:
    """Get pending requests needing approval from a given role."""
    pending = []
    for req in _request_store.values():
        if req.status == CapabilityStatus.PENDING:
            capability = get_capability(req.capability_id)
            if capability and approver_role in capability.required_approvals:
                pending.append(req)
    return pending


def approve_request(request_id: str, approver: str) -> PlatformRequest:
    """Approve a pending platform request."""
    request = _request_store.get(request_id)
    if not request:
        raise ValueError(f"Request not found: {request_id}")
    if request.status != CapabilityStatus.PENDING:
        raise ValueError(f"Cannot approve request in status: {request.status.value}")
    request.approve(approver)
    return request


def reject_request(request_id: str, approver: str, reason: str) -> PlatformRequest:
    """Reject a pending platform request."""
    request = _request_store.get(request_id)
    if not request:
        raise ValueError(f"Request not found: {request_id}")
    if request.status != CapabilityStatus.PENDING:
        raise ValueError(f"Cannot reject request in status: {request.status.value}")
    request.reject(approver, reason)
    return request


def get_platform_metrics() -> Dict[str, Any]:
    """Get aggregate platform usage metrics."""
    total_requests = len(_request_store)
    by_status = defaultdict(int)
    by_capability = defaultdict(int)
    avg_completion_time = 0.0
    completion_times = []

    for req in _request_store.values():
        by_status[req.status.value] += 1
        by_capability[req.capability_id] += 1
        if req.completed_at and req.created_at:
            delta = (req.completed_at - req.created_at).total_seconds()
            completion_times.append(delta)

    if completion_times:
        avg_completion_time = sum(completion_times) / len(completion_times)

    return {
        "total_requests": total_requests,
        "requests_by_status": dict(by_status),
        "requests_by_capability": dict(by_capability),
        "average_completion_seconds": round(avg_completion_time, 1),
        "services_in_catalog": len(_service_catalog),
        "self_service_capabilities": len(list_capabilities(self_service=True)),
        "approval_required_capabilities": len(list_capabilities(self_service=False)),
    }
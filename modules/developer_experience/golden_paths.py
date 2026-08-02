"""
Golden Paths
============
Enterprise-approved, opinionated workflows (golden paths) for common
development tasks. Golden paths are the recommended, supported way to
accomplish tasks. They reduce cognitive load, ensure consistency, and
accelerate delivery.

Approved Golden Paths:
    1.  Create Service
    2.  Create API
    3.  Create Frontend
    4.  Add Authentication
    5.  Add Database
    6.  Add AI Model
    7.  Add RAG (Retrieval-Augmented Generation)
    8.  Add Background Worker
    9.  Add Monitoring
    10. Add Feature Flags
    11. Deploy Service
    12. Respond to Incidents
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)


class PathCategory(Enum):
    """Categories of golden paths."""
    CREATE = "create"          # Creating new resources
    INTEGRATE = "integrate"    # Integrating capabilities
    OPERATE = "operate"        # Operational tasks
    RESPOND = "respond"        # Response workflows


class PathStatus(Enum):
    """Status of a golden path execution."""
    NOT_STARTED = "not_started"
    VALIDATING = "validating"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class PathStep:
    """A single step within a golden path."""
    order: int
    name: str
    description: str
    command: Optional[str] = None
    template: Optional[str] = None
    validation: Optional[str] = None  # Validation check after step
    rollback: Optional[str] = None    # Rollback command if needed
    timeout_seconds: int = 300
    required: bool = True
    automated: bool = True
    manual_instructions: Optional[str] = None


@dataclass
class PathPrerequisite:
    """A prerequisite that must be met before executing a golden path."""
    name: str
    description: str
    check_command: str
    fix_hint: str
    required: bool = True


@dataclass
class GoldenPath:
    """Definition of an approved golden path."""
    id: str
    name: str
    description: str
    category: PathCategory
    prerequisites: List[PathPrerequisite] = field(default_factory=list)
    steps: List[PathStep] = field(default_factory=list)
    estimated_duration_minutes: int = 10
    owner_team: str = "Platform Engineering"
    tags: List[str] = field(default_factory=list)
    documentation_url: str = ""
    version: str = "1.0.0"

    def validate_prerequisites(self) -> Tuple[bool, List[str]]:
        """Check if all prerequisites are met.

        Returns:
            Tuple of (all_met, list_of_unmet_with_fix_hints).
        """
        unmet: List[str] = []
        for prereq in self.prerequisites:
            if prereq.required:
                unmet.append(f"{prereq.name}: {prereq.fix_hint}")
        return len(unmet) == 0, unmet

    def total_steps(self) -> int:
        return len(self.steps)

    def automated_steps(self) -> int:
        return sum(1 for s in self.steps if s.automated)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "steps_count": self.total_steps(),
            "automated_steps": self.automated_steps(),
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "owner_team": self.owner_team,
            "version": self.version,
            "prerequisites": [
                {"name": p.name, "description": p.description}
                for p in self.prerequisites
            ],
        }


# --- Golden Path Definitions ---

GOLDEN_PATHS: List[GoldenPath] = [
    GoldenPath(
        id="GP-001",
        name="Create Service",
        description="Create a new backend service from the approved template with CI/CD, monitoring, and documentation.",
        category=PathCategory.CREATE,
        estimated_duration_minutes=5,
        owner_team="Platform Engineering",
        tags=["service", "backend", "template", "scaffold"],
        prerequisites=[
            PathPrerequisite(
                name="CLI tools installed",
                description="Platform CLI must be installed",
                check_command="which platform-cli",
                fix_hint="Run: brew install platform-engineering/tools/platform-cli",
            ),
            PathPrerequisite(
                name="Git configured",
                description="Git must be configured with name and email",
                check_command="git config user.name && git config user.email",
                fix_hint="Run: git config --global user.name 'Your Name' && git config --global user.email 'you@company.com'",
            ),
        ],
        steps=[
            PathStep(
                order=1, name="Select template",
                description="Choose service template from catalog",
                command="platform-cli service create --interactive",
                validation="Template selected successfully",
                rollback="rm -rf ./new-service",
            ),
            PathStep(
                order=2, name="Scaffold service",
                description="Generate service from chosen template",
                command="platform-cli service generate --name {{service_name}} --template {{template}}",
                validation="Directory created with expected files",
                timeout_seconds=120,
            ),
            PathStep(
                order=3, name="Initialize Git",
                description="Initialize repository and push to remote",
                command="cd {{service_name}} && git init && git add -A && git commit -m 'Initial scaffold from golden path'",
                validation="Git repo initialized",
            ),
            PathStep(
                order=4, name="Configure CI/CD",
                description="Set up CI/CD pipeline from template",
                command="platform-cli ci setup --repo {{service_name}}",
                validation="CI pipeline file created",
                timeout_seconds=60,
            ),
            PathStep(
                order=5, name="Verify build",
                description="Run the build to verify everything works",
                command="cd {{service_name}} && make build",
                validation="Build succeeded",
                rollback="rm -rf {{service_name}}",
                timeout_seconds=300,
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/create-service",
    ),
    GoldenPath(
        id="GP-002",
        name="Create API",
        description="Create a REST or gRPC API endpoint following the API-first design standards.",
        category=PathCategory.CREATE,
        estimated_duration_minutes=15,
        owner_team="API Platform",
        tags=["api", "rest", "grpc", "openapi"],
        prerequisites=[
            PathPrerequisite(
                name="API design reviewed",
                description="API design must be reviewed in the API design doc",
                check_command="platform-cli api check-design --spec api/design.yaml",
                fix_hint="Create API design doc at api/design.yaml and get review approval",
            ),
        ],
        steps=[
            PathStep(
                order=1, name="Define OpenAPI spec",
                description="Write or update the OpenAPI/Swagger specification",
                command="platform-cli api init-spec --output api/openapi.yaml",
                validation="OpenAPI spec is valid",
            ),
            PathStep(
                order=2, name="Generate server stubs",
                description="Generate server code from OpenAPI spec",
                command="platform-cli api generate --spec api/openapi.yaml --lang {{language}}",
                validation="Server stubs generated",
            ),
            PathStep(
                order=3, name="Implement handlers",
                description="Implement the API handler logic",
                command=None,
                automated=False,
                manual_instructions="Implement request handlers in generated stubs. See docs for patterns.",
            ),
            PathStep(
                order=4, name="Add validation",
                description="Add request validation middleware",
                command="platform-cli api add-validation --spec api/openapi.yaml",
                validation="Validation middleware added",
            ),
            PathStep(
                order=5, name="Add integration tests",
                description="Generate and run integration tests",
                command="platform-cli api test-gen --spec api/openapi.yaml",
                validation="Integration tests pass",
                timeout_seconds=120,
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/create-api",
    ),
    GoldenPath(
        id="GP-003",
        name="Create Frontend",
        description="Create a new frontend application or micro-frontend using the approved framework and design system.",
        category=PathCategory.CREATE,
        estimated_duration_minutes=8,
        owner_team="Frontend Platform",
        tags=["frontend", "react", "micro-frontend", "design-system"],
        steps=[
            PathStep(
                order=1, name="Scaffold frontend",
                description="Create frontend app from template",
                command="platform-cli frontend create --name {{app_name}} --template react-ts",
                validation="App scaffolded successfully",
                timeout_seconds=120,
            ),
            PathStep(
                order=2, name="Install design system",
                description="Install and configure company design system",
                command="cd {{app_name}} && npm install @company/design-system",
                validation="Design system installed",
            ),
            PathStep(
                order=3, name="Add routing",
                description="Configure client-side routing",
                command="cd {{app_name}} && npm run setup-routes",
                validation="Routes configured",
            ),
            PathStep(
                order=4, name="Add API client",
                description="Generate API client from backend OpenAPI spec",
                command="cd {{app_name}} && platform-cli api generate-client --spec ../api/openapi.yaml",
                validation="API client generated",
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/create-frontend",
    ),
    GoldenPath(
        id="GP-004",
        name="Add Authentication",
        description="Integrate authentication and authorization using the company SSO and RBAC system.",
        category=PathCategory.INTEGRATE,
        estimated_duration_minutes=20,
        owner_team="Identity Platform",
        tags=["auth", "sso", "rbac", "oauth2", "oidc"],
        prerequisites=[
            PathPrerequisite(
                name="Auth0/OIDC client registered",
                description="Application must be registered in the identity provider",
                check_command="platform-cli auth check-client --app {{app_name}}",
                fix_hint="Register app in IdP portal: https://idp.internal.company.com",
            ),
        ],
        steps=[
            PathStep(
                order=1, name="Install auth SDK",
                description="Install the company auth SDK",
                command="platform-cli auth install-sdk --app {{app_name}}",
                validation="Auth SDK installed",
            ),
            PathStep(
                order=2, name="Configure OIDC",
                description="Configure OpenID Connect settings",
                command="platform-cli auth configure-oidc --app {{app_name}}",
                validation="OIDC configured",
            ),
            PathStep(
                order=3, name="Add middleware",
                description="Add auth middleware to application",
                command="platform-cli auth add-middleware --app {{app_name}}",
                validation="Auth middleware added",
            ),
            PathStep(
                order=4, name="Configure RBAC",
                description="Set up role-based access control",
                command="platform-cli auth configure-rbac --app {{app_name}}",
                validation="RBAC configured",
                manual_instructions="Define roles in config/auth/roles.yaml",
            ),
            PathStep(
                order=5, name="Test auth flow",
                description="Run integration tests for auth",
                command="platform-cli auth test --app {{app_name}}",
                validation="All auth tests pass",
                timeout_seconds=120,
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/add-auth",
    ),
    GoldenPath(
        id="GP-005",
        name="Add Database",
        description="Add a new database or table/migration following database platform standards.",
        category=PathCategory.INTEGRATE,
        estimated_duration_minutes=10,
        owner_team="Data Platform",
        tags=["database", "postgresql", "migration", "schema"],
        steps=[
            PathStep(
                order=1, name="Create migration",
                description="Generate a new database migration",
                command="platform-cli db create-migration --name {{migration_name}}",
                validation="Migration file created",
            ),
            PathStep(
                order=2, name="Write migration",
                description="Implement the migration SQL",
                command=None,
                automated=False,
                manual_instructions="Edit the generated migration file in migrations/ directory. Add CREATE/ALTER TABLE statements.",
            ),
            PathStep(
                order=3, name="Test migration locally",
                description="Run migration against local dev database",
                command="platform-cli db migrate --env local",
                validation="Migration applied successfully",
            ),
            PathStep(
                order=4, name="Generate models",
                description="Generate ORM models from schema",
                command="platform-cli db generate-models",
                validation="Models generated",
            ),
            PathStep(
                order=5, name="Add seed data",
                description="Add seed data for development and testing",
                command="platform-cli db add-seed --table {{table_name}}",
                validation="Seed data added",
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/add-database",
    ),
    GoldenPath(
        id="GP-006",
        name="Add AI Model",
        description="Integrate an AI/ML model using the company's model serving platform.",
        category=PathCategory.INTEGRATE,
        estimated_duration_minutes=30,
        owner_team="ML Platform",
        tags=["ai", "ml", "model", "inference", "llm"],
        prerequisites=[
            PathPrerequisite(
                name="Model approved",
                description="Model must pass AI governance review",
                check_command="platform-cli ai check-governance --model {{model_name}}",
                fix_hint="Submit model for review at https://ai-governance.internal.company.com",
            ),
        ],
        steps=[
            PathStep(
                order=1, name="Register model",
                description="Register model in model registry",
                command="platform-cli ai register-model --name {{model_name}} --framework {{framework}}",
                validation="Model registered",
            ),
            PathStep(
                order=2, name="Package model",
                description="Package model for serving",
                command="platform-cli ai package --model {{model_name}}",
                validation="Model packaged with serving config",
            ),
            PathStep(
                order=3, name="Add inference endpoint",
                description="Create inference API endpoint",
                command="platform-cli ai create-endpoint --model {{model_name}}",
                validation="Inference endpoint created",
            ),
            PathStep(
                order=4, name="Add monitoring",
                description="Add model performance and drift monitoring",
                command="platform-cli ai add-monitoring --model {{model_name}}",
                validation="Model monitoring configured",
            ),
            PathStep(
                order=5, name="Run validation",
                description="Run model validation suite",
                command="platform-cli ai validate --model {{model_name}}",
                validation="All validation checks pass",
                timeout_seconds=600,
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/add-ai-model",
    ),
    GoldenPath(
        id="GP-007",
        name="Add RAG",
        description="Add Retrieval-Augmented Generation capability using the company's RAG platform.",
        category=PathCategory.INTEGRATE,
        estimated_duration_minutes=30,
        owner_team="AI Platform",
        tags=["ai", "rag", "vector-db", "embeddings", "llm"],
        steps=[
            PathStep(
                order=1, name="Configure vector store",
                description="Set up vector database for embeddings",
                command="platform-cli rag init-vector-store --project {{project_name}}",
                validation="Vector store provisioned",
            ),
            PathStep(
                order=2, name="Set up embedding pipeline",
                description="Configure embedding generation pipeline",
                command="platform-cli rag setup-embeddings --model text-embedding-3",
                validation="Embedding pipeline configured",
            ),
            PathStep(
                order=3, name="Index documents",
                description="Index initial document corpus",
                command="platform-cli rag index --source {{document_source}}",
                validation="Documents indexed",
                timeout_seconds=600,
            ),
            PathStep(
                order=4, name="Add retrieval endpoint",
                description="Create retrieval API endpoint",
                command="platform-cli rag create-endpoint --project {{project_name}}",
                validation="Retrieval endpoint ready",
            ),
            PathStep(
                order=5, name="Add generation integration",
                description="Wire up LLM generation with retrieval context",
                command="platform-cli rag integrate-llm --model {{llm_model}}",
                validation="RAG pipeline integrated",
            ),
            PathStep(
                order=6, name="Test RAG quality",
                description="Run RAG quality evaluation suite",
                command="platform-cli rag eval --test-suite standard",
                validation="RAG evaluation passed",
                timeout_seconds=300,
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/add-rag",
    ),
    GoldenPath(
        id="GP-008",
        name="Add Background Worker",
        description="Add a background job processing worker using the company's job queue platform.",
        category=PathCategory.INTEGRATE,
        estimated_duration_minutes=15,
        owner_team="Platform Engineering",
        tags=["worker", "queue", "async", "background-jobs"],
        steps=[
            PathStep(
                order=1, name="Create worker project",
                description="Scaffold a new background worker project",
                command="platform-cli worker create --name {{worker_name}}",
                validation="Worker project scaffolded",
            ),
            PathStep(
                order=2, name="Define job schema",
                description="Define the job payload schema",
                command="platform-cli worker define-job --name {{job_name}} --schema jobs/{{job_name}}.json",
                validation="Job schema defined",
            ),
            PathStep(
                order=3, name="Implement handler",
                description="Implement the job handler logic",
                command=None,
                automated=False,
                manual_instructions="Implement JobHandler class in src/jobs/{{job_name}}_handler.py (or equivalent).",
            ),
            PathStep(
                order=4, name="Configure queue",
                description="Set up message queue topic/queue",
                command="platform-cli worker configure-queue --job {{job_name}}",
                validation="Queue configured",
            ),
            PathStep(
                order=5, name="Add dead-letter queue",
                description="Configure DLQ for failed jobs",
                command="platform-cli worker add-dlq --job {{job_name}}",
                validation="DLQ configured",
            ),
            PathStep(
                order=6, name="Add monitoring",
                description="Add queue depth, latency, and error rate monitoring",
                command="platform-cli worker add-monitoring --job {{job_name}}",
                validation="Worker monitoring configured",
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/add-background-worker",
    ),
    GoldenPath(
        id="GP-009",
        name="Add Monitoring",
        description="Add comprehensive monitoring: metrics, logs, traces, alerts, and dashboards.",
        category=PathCategory.INTEGRATE,
        estimated_duration_minutes=10,
        owner_team="Observability Platform",
        tags=["monitoring", "observability", "metrics", "alerts", "dashboards"],
        steps=[
            PathStep(
                order=1, name="Add metrics SDK",
                description="Install and configure metrics SDK",
                command="platform-cli monitoring add-metrics --app {{app_name}}",
                validation="Metrics SDK configured",
            ),
            PathStep(
                order=2, name="Add tracing",
                description="Configure distributed tracing",
                command="platform-cli monitoring add-tracing --app {{app_name}}",
                validation="Tracing configured",
            ),
            PathStep(
                order=3, name="Add structured logging",
                description="Configure structured JSON logging",
                command="platform-cli monitoring add-logging --app {{app_name}}",
                validation="Structured logging configured",
            ),
            PathStep(
                order=4, name="Create dashboard",
                description="Generate default service dashboard",
                command="platform-cli monitoring create-dashboard --app {{app_name}}",
                validation="Dashboard created",
            ),
            PathStep(
                order=5, name="Define SLOs",
                description="Define Service Level Objectives",
                command="platform-cli monitoring define-slos --app {{app_name}}",
                validation="SLOs defined",
            ),
            PathStep(
                order=6, name="Configure alerts",
                description="Set up critical alerts with on-call routing",
                command="platform-cli monitoring configure-alerts --app {{app_name}}",
                validation="Alerts configured",
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/add-monitoring",
    ),
    GoldenPath(
        id="GP-010",
        name="Add Feature Flags",
        description="Integrate feature flag management for gradual rollouts and A/B testing.",
        category=PathCategory.INTEGRATE,
        estimated_duration_minutes=10,
        owner_team="Platform Engineering",
        tags=["feature-flags", "launchdarkly", "config", "rollout"],
        steps=[
            PathStep(
                order=1, name="Install SDK",
                description="Install feature flag SDK",
                command="platform-cli feature-flags install-sdk --app {{app_name}}",
                validation="Feature flag SDK installed",
            ),
            PathStep(
                order=2, name="Configure client",
                description="Initialize feature flag client",
                command="platform-cli feature-flags init-client --app {{app_name}}",
                validation="Client initialized",
            ),
            PathStep(
                order=3, name="Create first flag",
                description="Create and configure first feature flag",
                command="platform-cli feature-flags create --name {{flag_name}} --type boolean",
                validation="Feature flag created",
            ),
            PathStep(
                order=4, name="Add flag wrapper",
                description="Add feature flag wrapper/utility",
                command="platform-cli feature-flags add-wrapper --app {{app_name}}",
                validation="Flag wrapper added",
            ),
            PathStep(
                order=5, name="Add tests",
                description="Add tests for flag states",
                command="platform-cli feature-flags add-tests --app {{app_name}}",
                validation="Flag tests added",
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/add-feature-flags",
    ),
    GoldenPath(
        id="GP-011",
        name="Deploy Service",
        description="Deploy a service to production using canary deployment with automated rollback.",
        category=PathCategory.OPERATE,
        estimated_duration_minutes=30,
        owner_team="Delivery Platform",
        tags=["deploy", "production", "canary", "rollback", "cd"],
        prerequisites=[
            PathPrerequisite(
                name="CI passed",
                description="All CI checks must pass",
                check_command="platform-cli deploy check-ci --app {{app_name}} --commit {{commit_sha}}",
                fix_hint="Fix failing CI checks before deploying",
            ),
            PathPrerequisite(
                name="Change approved",
                description="Change must have required approvals",
                check_command="platform-cli deploy check-approvals --app {{app_name}}",
                fix_hint="Get required approvals from CODEOWNERS",
            ),
        ],
        steps=[
            PathStep(
                order=1, name="Deploy to staging",
                description="Deploy to staging environment",
                command="platform-cli deploy staging --app {{app_name}} --version {{version}}",
                validation="Staging deployment successful",
                rollback="platform-cli deploy rollback --app {{app_name}} --env staging",
                timeout_seconds=600,
            ),
            PathStep(
                order=2, name="Run smoke tests",
                description="Run smoke tests against staging",
                command="platform-cli test smoke --env staging --app {{app_name}}",
                validation="Smoke tests passed",
                timeout_seconds=300,
            ),
            PathStep(
                order=3, name="Canary deploy",
                description="Deploy to 10% canary in production",
                command="platform-cli deploy canary --app {{app_name}} --version {{version}} --percentage 10",
                validation="Canary deployed",
                rollback="platform-cli deploy rollback --app {{app_name}} --env production",
                timeout_seconds=300,
            ),
            PathStep(
                order=4, name="Monitor canary",
                description="Monitor canary for errors for 5 minutes",
                command="platform-cli deploy monitor-canary --app {{app_name}} --duration 300",
                validation="No error rate increase detected",
                rollback="platform-cli deploy rollback --app {{app_name}} --env production",
                timeout_seconds=360,
            ),
            PathStep(
                order=5, name="Full rollout",
                description="Roll out to 100% of production traffic",
                command="platform-cli deploy promote --app {{app_name}} --percentage 100",
                validation="Full rollout complete",
                rollback="platform-cli deploy rollback --app {{app_name}} --env production",
                timeout_seconds=300,
            ),
            PathStep(
                order=6, name="Post-deploy verification",
                description="Run post-deployment verification suite",
                command="platform-cli test verify --env production --app {{app_name}}",
                validation="Post-deploy verification passed",
                timeout_seconds=300,
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/deploy-service",
    ),
    GoldenPath(
        id="GP-012",
        name="Respond to Incidents",
        description="Standard incident response workflow: triage, communicate, mitigate, resolve, postmortem.",
        category=PathCategory.RESPOND,
        estimated_duration_minutes=0,  # Variable
        owner_team="SRE",
        tags=["incident", "sre", "postmortem", "runbook"],
        steps=[
            PathStep(
                order=1, name="Declare incident",
                description="Declare and create incident ticket",
                command="platform-cli incident declare --severity {{severity}} --service {{service_name}}",
                validation="Incident created with tracking ID",
                timeout_seconds=30,
            ),
            PathStep(
                order=2, name="Notify on-call",
                description="Page the on-call engineer",
                command="platform-cli incident page --incident {{incident_id}}",
                validation="On-call paged",
                timeout_seconds=60,
            ),
            PathStep(
                order=3, name="Create war room",
                description="Create incident communication channel",
                command="platform-cli incident war-room --incident {{incident_id}}",
                validation="War room created",
                timeout_seconds=30,
            ),
            PathStep(
                order=4, name="Triage",
                description="Assess impact and gather diagnostic data",
                command=None,
                automated=False,
                manual_instructions="Check dashboards, logs, recent deployments. Determine blast radius. Update incident status.",
            ),
            PathStep(
                order=5, name="Mitigate",
                description="Apply mitigation: rollback, scale, circuit-break, etc.",
                command="platform-cli incident mitigate --incident {{incident_id}}",
                validation="Mitigation applied",
                manual_instructions="If automated mitigation fails, follow runbook at docs/runbooks/{{service_name}}.md",
            ),
            PathStep(
                order=6, name="Resolve",
                description="Verify resolution and close incident",
                command="platform-cli incident resolve --incident {{incident_id}}",
                validation="Incident resolved, monitoring restored",
            ),
            PathStep(
                order=7, name="Postmortem",
                description="Create blameless postmortem document",
                command="platform-cli incident postmortem --incident {{incident_id}}",
                validation="Postmortem created",
                manual_instructions="Complete postmortem within 5 business days. Schedule review meeting.",
            ),
        ],
        documentation_url="https://docs.internal.company.com/golden-paths/respond-to-incidents",
    ),
]


# --- Public API ---

def get_golden_path(path_id: str) -> Optional[GoldenPath]:
    """Retrieve a golden path by its ID."""
    for path in GOLDEN_PATHS:
        if path.id == path_id:
            return path
    return None


def list_golden_paths(
    category: Optional[PathCategory] = None,
    tags: Optional[List[str]] = None,
) -> List[GoldenPath]:
    """List golden paths, optionally filtered by category and/or tags."""
    paths = GOLDEN_PATHS
    if category:
        paths = [p for p in paths if p.category == category]
    if tags:
        tag_set = set(tags)
        paths = [p for p in paths if tag_set & set(p.tags)]
    return paths


def execute_golden_path(
    path_id: str,
    variables: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
    skip_prerequisites: bool = False,
) -> Dict[str, Any]:
    """Execute a golden path with the given variable substitutions.

    In a real system, this would orchestrate actual CLI commands.
    For now, it validates and returns the execution plan.
    """
    path = get_golden_path(path_id)
    if not path:
        raise ValueError(f"Golden path not found: {path_id}")

    variables = variables or {}

    # Validate prerequisites (skip if explicitly requested)
    if not skip_prerequisites:
        prereqs_met, unmet = path.validate_prerequisites()
        if not prereqs_met:
            return {
                "success": False,
                "path_id": path_id,
                "path_name": path.name,
                "error": "Prerequisites not met",
                "unmet_prerequisites": unmet,
            }

    # Build execution plan
    steps_plan = []
    for step in path.steps:
        step_plan = {
            "order": step.order,
            "name": step.name,
            "command": step.command,
            "automated": step.automated,
            "dry_run": dry_run,
        }
        if step.command and variables:
            for key, value in variables.items():
                step_plan["command"] = (
                    step_plan.get("command", "").replace(f"{{{{{key}}}}}", value)
                )
        steps_plan.append(step_plan)

    return {
        "success": True,
        "path_id": path_id,
        "path_name": path.name,
        "category": path.category.value,
        "total_steps": path.total_steps(),
        "automated_steps": path.automated_steps(),
        "dry_run": dry_run,
        "estimated_duration_minutes": path.estimated_duration_minutes,
        "steps": steps_plan,
    }


def validate_path_prerequisites(path_id: str) -> Tuple[bool, List[str]]:
    """Validate prerequisites for a golden path."""
    path = get_golden_path(path_id)
    if not path:
        return False, [f"Golden path not found: {path_id}"]
    return path.validate_prerequisites()


def get_paths_by_category() -> Dict[PathCategory, List[GoldenPath]]:
    """Group golden paths by category."""
    grouped: Dict[PathCategory, List[GoldenPath]] = {}
    for path in GOLDEN_PATHS:
        grouped.setdefault(path.category, []).append(path)
    return grouped


def search_paths(query: str) -> List[GoldenPath]:
    """Search golden paths by name, description, or tags."""
    query_lower = query.lower()
    results = []
    for path in GOLDEN_PATHS:
        if (query_lower in path.name.lower() or
                query_lower in path.description.lower() or
                any(query_lower in tag.lower() for tag in path.tags)):
            results.append(path)
    return results


def get_path_summary(path_id: str) -> Optional[Dict[str, Any]]:
    """Get a summary of a golden path."""
    path = get_golden_path(path_id)
    if not path:
        return None
    return path.to_dict()
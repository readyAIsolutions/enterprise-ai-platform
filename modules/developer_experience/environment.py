"""
Development Environment
=======================
Enterprise-grade development environment management. Ensures all
developers have reproducible, consistent environments across the
organization. Supports multiple environment providers (local, dev
containers, cloud workspaces).

Capabilities:
    - Reproducible environments via infrastructure-as-code
    - Dev container support (Docker/Podman-based)
    - Version-pinned dependencies
    - One-command setup
    - Seed data provisioning
    - Safe local secrets management
    - Mock services and test fixtures
    - Local observability stack
    - Debugging tool integration
    - Platform-consistent tooling
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class EnvironmentProvider(Enum):
    """Supported development environment providers."""
    LOCAL = "local"                  # Native local machine
    DEV_CONTAINER = "dev_container"  # Docker/Podman dev container
    CODESPACES = "codespaces"        # GitHub Codespaces
    GITPOD = "gitpod"                # Gitpod cloud workspace
    CLOUD_IDE = "cloud_ide"          # Cloud-based IDE (e.g., AWS Cloud9)
    VAGRANT = "vagrant"              # Vagrant VM
    NIX = "nix"                      # Nix-based reproducible environment


class EnvironmentStatus(Enum):
    """Status of a development environment."""
    NOT_CREATED = "not_created"
    CREATING = "creating"
    READY = "ready"
    DEGRADED = "degraded"
    ERROR = "error"
    DESTROYED = "destroyed"


@dataclass
class DependencySpec:
    """Specification for a pinned dependency."""
    name: str
    version: str
    source: str = ""          # Registry, git, local path
    hash: Optional[str] = None  # Integrity hash for verification
    category: str = "runtime"   # runtime, dev, build, test
    notes: str = ""


@dataclass
class SecretSpec:
    """Specification for a local development secret."""
    key: str
    description: str
    default_value: Optional[str] = None  # Safe default for local dev
    required: bool = False
    sensitive: bool = True
    aws_secret_arn: Optional[str] = None
    vault_path: Optional[str] = None
    rotation_days: Optional[int] = 90


@dataclass
class MockService:
    """Mock/emulator service for local development."""
    name: str
    image: str                # Docker image for mock
    port: int
    health_endpoint: str = "/health"
    env_vars: Dict[str, str] = field(default_factory=dict)
    volumes: List[str] = field(default_factory=list)
    seed_data_path: Optional[str] = None


@dataclass
class ObservabilityTool:
    """Local observability tool configuration."""
    name: str
    tool_type: str  # logs, metrics, traces, profiling
    image: str
    port: int
    ui_port: Optional[int] = None
    config_path: Optional[str] = None


@dataclass
class DevEnvironment:
    """Complete specification of a development environment."""
    project_name: str
    provider: EnvironmentProvider = EnvironmentProvider.LOCAL
    status: EnvironmentStatus = EnvironmentStatus.NOT_CREATED

    # Runtime
    language: str = ""
    language_version: str = ""
    package_manager: str = ""
    runtime_dependencies: List[DependencySpec] = field(default_factory=list)

    # Tooling
    ide: str = "vscode"
    ide_extensions: List[str] = field(default_factory=list)
    linters: List[str] = field(default_factory=list)
    formatters: List[str] = field(default_factory=list)
    test_runners: List[str] = field(default_factory=list)
    build_tools: List[str] = field(default_factory=list)

    # Infrastructure
    dev_container_image: Optional[str] = None
    docker_compose_path: Optional[str] = None
    dev_container_config: Optional[str] = ".devcontainer/devcontainer.json"

    # Services
    mock_services: List[MockService] = field(default_factory=list)

    # Data
    seed_data_path: Optional[str] = None
    database_migrations_path: Optional[str] = None

    # Secrets
    secrets: List[SecretSpec] = field(default_factory=list)
    secrets_file: str = ".env.local"
    vault_enabled: bool = False
    vault_addr: Optional[str] = None

    # Observability
    observability_tools: List[ObservabilityTool] = field(default_factory=list)

    # Debugging
    debugger: str = ""
    debug_port: int = 5678
    hot_reload_enabled: bool = True

    # Setup
    setup_commands: List[str] = field(default_factory=list)
    health_check_command: Optional[str] = None

    # Metadata
    created_at: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Tuple[bool, List[str]]:
        """Validate the environment configuration.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues: List[str] = []

        if not self.project_name:
            issues.append("project_name is required")

        if not self.language:
            issues.append("language is required")

        if not self.language_version:
            issues.append("language_version is required (must be pinned)")

        if not self.package_manager:
            issues.append("package_manager is required")

        if not self.setup_commands:
            issues.append("At least one setup_command is required for one-command setup")

        # Check for lock file based on package manager (advisory only)
        lock_files = {
            "npm": "package-lock.json",
            "yarn": "yarn.lock",
            "pnpm": "pnpm-lock.yaml",
            "pip": "requirements.txt",
            "pipenv": "Pipfile.lock",
            "poetry": "poetry.lock",
            "cargo": "Cargo.lock",
            "bundler": "Gemfile.lock",
            "go": "go.sum",
            "maven": "pom.xml",
            "gradle": "gradle.lockfile",
        }

        # Validate secrets don't have real values as defaults
        for secret in self.secrets:
            if secret.default_value and not secret.default_value.startswith("dev-"):
                # Check for obviously unsafe patterns (API keys, tokens)
                unsafe_patterns = ['sk-', 'pk-', 'ghp_', 'gho_', 'xoxb-', 'AKIA', 'eyJ']
                default_lower = secret.default_value.lower()
                if any(default_lower.startswith(p.lower()) for p in unsafe_patterns):
                    issues.append(
                        f"Secret '{secret.key}' has a potentially real credential: "
                        f"prefix with 'dev-' or use safe placeholder"
                    )

        # Validate mock services have health endpoints
        for svc in self.mock_services:
            if not svc.health_endpoint:
                issues.append(f"Mock service '{svc.name}' missing health_endpoint")

        return len(issues) == 0, issues

    def to_dict(self) -> Dict[str, Any]:
        """Serialize environment to dictionary."""
        return {
            "project_name": self.project_name,
            "provider": self.provider.value,
            "status": self.status.value,
            "language": self.language,
            "language_version": self.language_version,
            "package_manager": self.package_manager,
            "setup_commands": self.setup_commands,
            "secrets_file": self.secrets_file,
            "secrets_count": len(self.secrets),
            "mock_services": [s.name for s in self.mock_services],
            "observability_tools": [t.name for t in self.observability_tools],
            "debugger": self.debugger,
            "hot_reload_enabled": self.hot_reload_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def get_setup_script(self) -> str:
        """Generate a one-command setup script for this environment."""
        lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
        lines.append(f"# Setup script for {self.project_name}")
        lines.append(f"# Language: {self.language} {self.language_version}")
        lines.append("")

        for cmd in self.setup_commands:
            lines.append(f"echo 'Running: {cmd}'")
            lines.append(cmd)
            lines.append("")

        if self.mock_services:
            lines.append("# Start mock services")
            lines.append("docker-compose -f docker-compose.dev.yml up -d")
            lines.append("")

        if self.seed_data_path:
            lines.append("# Seed database")
            lines.append(f"./scripts/seed-db.sh {self.seed_data_path}")
            lines.append("")

        if self.health_check_command:
            lines.append("# Health check")
            lines.append(self.health_check_command)

        lines.append("")
        lines.append(f"echo '✓ {self.project_name} development environment ready'")
        return "\n".join(lines)


# --- Pre-configured environment templates ---

TEMPLATE_NODE_TS: DevEnvironment = DevEnvironment(
    project_name="node-typescript-service",
    provider=EnvironmentProvider.DEV_CONTAINER,
    language="typescript",
    language_version="20.x",
    package_manager="pnpm",
    runtime_dependencies=[
        DependencySpec(name="node", version="20.11.0", category="runtime"),
        DependencySpec(name="typescript", version="5.3.3", category="dev"),
        DependencySpec(name="pnpm", version="8.15.0", category="dev"),
    ],
    linters=["eslint", "prettier"],
    formatters=["prettier"],
    test_runners=["vitest", "playwright"],
    build_tools=["tsc", "esbuild"],
    dev_container_image="mcr.microsoft.com/devcontainers/typescript-node:20",
    setup_commands=[
        "pnpm install --frozen-lockfile",
        "pnpm run db:migrate",
        "pnpm run db:seed",
    ],
    health_check_command="pnpm run test -- --run",
    debugger="node-inspect",
    debug_port=9229,
    hot_reload_enabled=True,
    mock_services=[
        MockService(
            name="postgres",
            image="postgres:16-alpine",
            port=5432,
            health_endpoint="/",
            env_vars={"POSTGRES_DB": "dev_db", "POSTGRES_PASSWORD": "dev-password"},
        ),
        MockService(
            name="redis",
            image="redis:7-alpine",
            port=6379,
            health_endpoint="/health",
        ),
    ],
    secrets=[
        SecretSpec(key="DATABASE_URL", description="Local database URL",
                    default_value="postgresql://localhost:5432/dev_db", required=True),
        SecretSpec(key="REDIS_URL", description="Local Redis URL",
                    default_value="redis://localhost:6379", required=True),
        SecretSpec(key="API_KEY", description="Third-party API key",
                    default_value="dev-key-placeholder", sensitive=True),
    ],
    observability_tools=[
        ObservabilityTool(name="grafana", tool_type="dashboards",
                          image="grafana/grafana:latest", port=3000),
        ObservabilityTool(name="tempo", tool_type="traces",
                          image="grafana/tempo:latest", port=3200),
        ObservabilityTool(name="prometheus", tool_type="metrics",
                          image="prom/prometheus:latest", port=9090),
    ],
)

TEMPLATE_PYTHON: DevEnvironment = DevEnvironment(
    project_name="python-service",
    provider=EnvironmentProvider.DEV_CONTAINER,
    language="python",
    language_version="3.12",
    package_manager="poetry",
    runtime_dependencies=[
        DependencySpec(name="python", version="3.12.1", category="runtime"),
        DependencySpec(name="poetry", version="1.7.1", category="dev"),
    ],
    linters=["ruff", "mypy"],
    formatters=["ruff", "black"],
    test_runners=["pytest", "pytest-cov"],
    build_tools=["poetry"],
    dev_container_image="mcr.microsoft.com/devcontainers/python:3.12",
    setup_commands=[
        "poetry install --no-root --sync",
        "poetry run alembic upgrade head",
        "poetry run python scripts/seed.py",
    ],
    health_check_command="poetry run pytest --tb=short",
    debugger="debugpy",
    debug_port=5678,
    hot_reload_enabled=True,
    mock_services=[
        MockService(
            name="postgres",
            image="postgres:16-alpine",
            port=5432,
            env_vars={"POSTGRES_DB": "dev_db", "POSTGRES_PASSWORD": "dev-password"},
        ),
    ],
    secrets=[
        SecretSpec(key="DATABASE_URL", description="Local database URL",
                    default_value="postgresql+asyncpg://postgres:dev-password@localhost:5432/dev_db"),
        SecretSpec(key="SECRET_KEY", description="Application secret key",
                    default_value="dev-secret-key-change-in-production", sensitive=True),
    ],
    observability_tools=[
        ObservabilityTool(name="prometheus", tool_type="metrics",
                          image="prom/prometheus:latest", port=9090),
        ObservabilityTool(name="jaeger", tool_type="traces",
                          image="jaegertracing/all-in-one:latest", port=16686),
    ],
)

TEMPLATE_GO: DevEnvironment = DevEnvironment(
    project_name="go-service",
    provider=EnvironmentProvider.DEV_CONTAINER,
    language="go",
    language_version="1.22",
    package_manager="go",
    runtime_dependencies=[
        DependencySpec(name="go", version="1.22.0", category="runtime"),
    ],
    linters=["golangci-lint"],
    formatters=["gofumpt", "goimports"],
    test_runners=["go test"],
    build_tools=["go build", "ko"],
    dev_container_image="mcr.microsoft.com/devcontainers/go:1.22",
    setup_commands=[
        "go mod download",
        "go run ./cmd/migrate up",
    ],
    health_check_command="go test ./... -count=1",
    debugger="delve",
    debug_port=2345,
    hot_reload_enabled=True,
    mock_services=[
        MockService(
            name="postgres",
            image="postgres:16-alpine",
            port=5432,
            env_vars={"POSTGRES_DB": "dev_db", "POSTGRES_PASSWORD": "dev-password"},
        ),
        MockService(
            name="redis",
            image="redis:7-alpine",
            port=6379,
        ),
    ],
    secrets=[
        SecretSpec(key="DATABASE_URL", description="Local database URL",
                    default_value="postgres://postgres:dev-password@localhost:5432/dev_db?sslmode=disable"),
        SecretSpec(key="JWT_SECRET", description="JWT signing secret",
                    default_value="dev-jwt-secret-change-in-production", sensitive=True),
    ],
    observability_tools=[
        ObservabilityTool(name="prometheus", tool_type="metrics",
                          image="prom/prometheus:latest", port=9090),
        ObservabilityTool(name="grafana", tool_type="dashboards",
                          image="grafana/grafana:latest", port=3000),
    ],
)

TEMPLATES: Dict[str, DevEnvironment] = {
    "node-typescript": TEMPLATE_NODE_TS,
    "python": TEMPLATE_PYTHON,
    "go": TEMPLATE_GO,
}


# --- Public API ---

_environment_store: Dict[str, DevEnvironment] = {}


def create_environment(spec: DevEnvironment) -> DevEnvironment:
    """Create/register a new development environment.

    Validates the spec before storing.
    """
    is_valid, issues = spec.validate()
    if not is_valid:
        raise ValueError(f"Invalid environment spec: {'; '.join(issues)}")

    spec.created_at = datetime.utcnow()
    spec.status = EnvironmentStatus.CREATING
    _environment_store[spec.project_name] = spec

    logger.info(f"Created environment for project: {spec.project_name}")
    return spec


def validate_environment(project_name: str) -> Tuple[bool, List[str]]:
    """Validate an existing environment's configuration."""
    env = _environment_store.get(project_name)
    if not env:
        return False, [f"Environment not found: {project_name}"]

    is_valid, issues = env.validate()
    env.last_verified_at = datetime.utcnow()

    if is_valid:
        env.status = EnvironmentStatus.READY
    else:
        env.status = EnvironmentStatus.DEGRADED

    return is_valid, issues


def get_environment_spec(project_name: str) -> Optional[DevEnvironment]:
    """Retrieve an environment specification."""
    return _environment_store.get(project_name)


def list_supported_providers() -> List[Dict[str, str]]:
    """List all supported environment providers with descriptions."""
    return [
        {"provider": "local", "description": "Native local machine setup"},
        {"provider": "dev_container", "description": "Docker/Podman-based dev container with VS Code"},
        {"provider": "codespaces", "description": "GitHub Codespaces cloud development environment"},
        {"provider": "gitpod", "description": "Gitpod cloud workspace"},
        {"provider": "cloud_ide", "description": "AWS Cloud9 or similar cloud IDE"},
        {"provider": "vagrant", "description": "Vagrant-managed virtual machine"},
        {"provider": "nix", "description": "Nix-based fully reproducible environment"},
    ]


def get_environment_template(template_name: str) -> Optional[DevEnvironment]:
    """Get a pre-configured environment template."""
    return TEMPLATES.get(template_name)


def list_templates() -> List[str]:
    """List available environment templates."""
    return list(TEMPLATES.keys())


def generate_setup_script(project_name: str) -> Optional[str]:
    """Generate a one-command setup script for an environment."""
    env = _environment_store.get(project_name)
    if not env:
        return None
    return env.get_setup_script()


def check_environment_health(project_name: str) -> Dict[str, Any]:
    """Check health of a development environment."""
    env = _environment_store.get(project_name)
    if not env:
        return {"status": "not_found", "project_name": project_name}

    checks = {
        "project_name": project_name,
        "status": env.status.value,
        "provider": env.provider.value,
        "has_lock_file": any(
            d.name.endswith((".lock", ".sum")) for d in env.runtime_dependencies
        ),
        "mock_services_defined": len(env.mock_services) > 0,
        "observability_configured": len(env.observability_tools) > 0,
        "debugging_configured": bool(env.debugger),
        "hot_reload_enabled": env.hot_reload_enabled,
        "secrets_managed": len(env.secrets) > 0,
        "setup_commands_count": len(env.setup_commands),
        "last_verified": env.last_verified_at.isoformat() if env.last_verified_at else None,
    }

    return checks


def is_environment_reproducible(project_name: str) -> bool:
    """Check if an environment is fully reproducible."""
    env = _environment_store.get(project_name)
    if not env:
        return False

    checks = [
        env.provider in (EnvironmentProvider.DEV_CONTAINER, EnvironmentProvider.NIX),
        len(env.setup_commands) > 0,
        env.language_version != "",
        len(env.runtime_dependencies) > 0,
        # Must have a lock file
        any(d.name.endswith((".lock", ".sum")) or "lock" in d.name.lower()
            for d in env.runtime_dependencies),
    ]
    return all(checks)
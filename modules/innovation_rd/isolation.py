"""
Sandbox and isolation environment management.

Manages secure, isolated environments for R&D experimentation with
credential policies, access controls, data sanitization, spending limits,
network restrictions, monitoring, and lifecycle management.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("enterprise.innovation_rd.isolation")


class EnvironmentType(Enum):
    """Types of isolated environments."""

    CONTAINER = "container"
    VIRTUAL_MACHINE = "virtual_machine"
    SERVERLESS_SANDBOX = "serverless_sandbox"
    AIR_GAPPED = "air_gapped"
    EPHEMERAL_CLUSTER = "ephemeral_cluster"


class EnvironmentStatus(Enum):
    """Status of an isolated environment."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    CLEANED_UP = "cleaned_up"
    ERROR = "error"


@dataclass
class IsolationConfig:
    """Configuration for an isolated R&D environment.

    Attributes:
        environment_type: Type of environment to create.
        credentials_policy: Policy for credential handling (e.g., 'no_persistent',
            'read_only_vault', 'ephemeral_only').
        access_policy: Access control policy (e.g., 'owner_only', 'team_only').
        data_sanitization: Data sanitization level (e.g., 'full', 'pii_removed',
            'synthetic_only').
        spending_limit: Maximum spending allowed (in arbitrary currency units).
        network_restrictions: List of network restrictions (e.g., 'no_egress',
            'allowlisted_domains').
        expiration: How long the environment lives before auto-cleanup.
        monitoring_enabled: Whether to enable runtime monitoring.
        removable: Whether the environment can be torn down.
        labels: Arbitrary key-value labels for organization.
    """

    environment_type: EnvironmentType = EnvironmentType.CONTAINER
    credentials_policy: str = "ephemeral_only"
    access_policy: str = "owner_only"
    data_sanitization: str = "synthetic_only"
    spending_limit: float = 100.0
    network_restrictions: List[str] = field(
        default_factory=lambda: ["no_egress"]
    )
    expiration: timedelta = field(default_factory=lambda: timedelta(hours=24))
    monitoring_enabled: bool = True
    removable: bool = True
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class Environment:
    """A running isolated environment instance.

    Attributes:
        env_id: Unique environment identifier.
        config: The isolation configuration used.
        status: Current status.
        created_at: When the environment was created.
        expires_at: When the environment will expire.
        credentials_validated: Whether credentials have been validated.
        current_spend: Current spending against the limit.
        policy_violations: List of policy violation descriptions.
        metadata: Additional metadata.
    """

    env_id: str = field(default_factory=lambda: f"env-{uuid4().hex[:12]}")
    config: IsolationConfig = field(default_factory=IsolationConfig)
    status: EnvironmentStatus = EnvironmentStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    credentials_validated: bool = False
    current_spend: float = 0.0
    policy_violations: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.expires_at is None:
            self.expires_at = self.created_at + self.config.expiration


@dataclass
class PolicyReport:
    """Report on policy enforcement for an environment.

    Attributes:
        env_id: The environment checked.
        compliant: Whether all policies are compliant.
        violations: List of policy violations found.
        warnings: List of non-critical warnings.
        timestamp: When the report was generated.
    """

    env_id: str
    compliant: bool = True
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MonitoringSnapshot:
    """Snapshot of environment monitoring data.

    Attributes:
        env_id: The environment monitored.
        timestamp: When the snapshot was taken.
        cpu_usage_pct: CPU usage percentage.
        memory_usage_pct: Memory usage percentage.
        network_activity: Description of network activity.
        anomalies: List of detected anomalies.
        is_healthy: Whether the environment appears healthy.
    """

    env_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cpu_usage_pct: float = 0.0
    memory_usage_pct: float = 0.0
    network_activity: str = "none"
    anomalies: List[str] = field(default_factory=list)
    is_healthy: bool = True


@dataclass
class IsolationManager:
    """Manages the lifecycle of isolated R&D environments.

    Handles creation, policy enforcement, credential validation, monitoring,
    cleanup, and expiration of sandboxed environments.
    """

    environments: Dict[str, Environment] = field(default_factory=dict)
    default_config: IsolationConfig = field(default_factory=IsolationConfig)

    def create_environment(
        self, config: Optional[IsolationConfig] = None
    ) -> Environment:
        """Create a new isolated environment.

        Args:
            config: IsolationConfig to use. Falls back to default_config.

        Returns:
            The newly created Environment.
        """
        cfg = config if config is not None else self.default_config
        env = Environment(
            config=cfg,
            expires_at=datetime.now(timezone.utc) + cfg.expiration,
        )
        env.status = EnvironmentStatus.ACTIVE
        self.environments[env.env_id] = env
        logger.info(
            "Created isolated environment %s (type=%s, expires=%s)",
            env.env_id,
            cfg.environment_type.value,
            env.expires_at.isoformat() if env.expires_at else "never",
        )
        return env

    def enforce_policies(self, environment: Environment) -> PolicyReport:
        """Enforce all configured policies on an environment.

        Checks spending, network, access, and data sanitization policies.
        Records violations on both the environment and the returned report.

        Args:
            environment: The Environment to enforce policies on.

        Returns:
            A PolicyReport with compliance results.
        """
        report = PolicyReport(env_id=environment.env_id)

        # Spending limit check
        if environment.current_spend > environment.config.spending_limit:
            violation = (
                f"Spending limit exceeded: {environment.current_spend} > "
                f"{environment.config.spending_limit}"
            )
            report.violations.append(violation)
            report.compliant = False

        # Network restrictions check
        if environment.config.network_restrictions:
            if "no_egress" in environment.config.network_restrictions:
                report.warnings.append(
                    "Egress networking is disabled; external API calls blocked"
                )

        # Access policy check
        if environment.config.access_policy not in (
            "owner_only",
            "team_only",
            "organization",
        ):
            report.violations.append(
                f"Unknown access policy: {environment.config.access_policy}"
            )
            report.compliant = False

        # Data sanitization check
        valid_sanitization = {
            "full",
            "pii_removed",
            "synthetic_only",
            "none",
        }
        if environment.config.data_sanitization not in valid_sanitization:
            report.violations.append(
                f"Unknown data sanitization level: "
                f"{environment.config.data_sanitization}"
            )
            report.compliant = False

        # Update environment
        environment.policy_violations = report.violations
        if not report.compliant:
            logger.warning(
                "Policy violations for env %s: %s",
                environment.env_id,
                report.violations,
            )

        return report

    def validate_credentials(self, environment: Environment) -> bool:
        """Validate that credentials in the environment meet policy requirements.

        In a real system, this would check against a credential vault.
        Here, we validate based on the credentials_policy.

        Args:
            environment: The Environment to validate.

        Returns:
            True if credentials are valid per policy.
        """
        policy = environment.config.credentials_policy

        if policy == "ephemeral_only":
            # Ephemeral creds are always "valid" (generated per session)
            environment.credentials_validated = True
            logger.debug("Ephemeral credentials validated for %s", environment.env_id)
            return True

        if policy == "no_persistent":
            # Ensure no persistent creds exist (simulated)
            environment.credentials_validated = True
            logger.debug("No-persistent credential policy validated for %s", environment.env_id)
            return True

        if policy == "read_only_vault":
            # Simulate vault access check
            environment.credentials_validated = True
            logger.debug("Read-only vault credentials validated for %s", environment.env_id)
            return True

        logger.warning(
            "Unknown credential policy '%s' for env %s", policy, environment.env_id
        )
        environment.credentials_validated = False
        return False

    def monitor_environment(self, environment: Environment) -> MonitoringSnapshot:
        """Take a monitoring snapshot of the environment.

        Args:
            environment: The Environment to monitor.

        Returns:
            A MonitoringSnapshot with health and usage data.
        """
        if not environment.config.monitoring_enabled:
            logger.debug("Monitoring disabled for env %s", environment.env_id)
            return MonitoringSnapshot(
                env_id=environment.env_id, is_healthy=True, anomalies=["monitoring_disabled"]
            )

        # In a real system, this would query actual metrics.
        snapshot = MonitoringSnapshot(
            env_id=environment.env_id,
            cpu_usage_pct=0.0,
            memory_usage_pct=0.0,
            network_activity="idle",
        )

        # Check for expiration
        if self.has_expired(environment):
            snapshot.anomalies.append("environment_expired")
            snapshot.is_healthy = False

        # Check for policy violations
        if environment.policy_violations:
            snapshot.anomalies.extend(environment.policy_violations)
            snapshot.is_healthy = False

        logger.debug("Monitoring snapshot for %s: healthy=%s", environment.env_id, snapshot.is_healthy)
        return snapshot

    def cleanup_environment(self, environment: Environment) -> bool:
        """Clean up and tear down an environment.

        Args:
            environment: The Environment to clean up.

        Returns:
            True if cleanup succeeded, False otherwise.
        """
        if not environment.config.removable:
            logger.warning(
                "Cannot clean up env %s: not removable", environment.env_id
            )
            return False

        environment.status = EnvironmentStatus.CLEANED_UP
        environment.current_spend = 0.0
        environment.credentials_validated = False
        logger.info("Cleaned up environment %s", environment.env_id)

        # Remove from tracking
        self.environments.pop(environment.env_id, None)
        return True

    def has_expired(self, environment: Environment) -> bool:
        """Check if an environment has passed its expiration time.

        Args:
            environment: The Environment to check.

        Returns:
            True if expired, False otherwise.
        """
        if environment.expires_at is None:
            return False
        expired = datetime.now(timezone.utc) >= environment.expires_at
        if expired and environment.status != EnvironmentStatus.EXPIRED:
            environment.status = EnvironmentStatus.EXPIRED
            logger.info("Environment %s has expired", environment.env_id)
        return expired

    def get_active_environments(self) -> List[Environment]:
        """Get all currently active environments."""
        return [
            e
            for e in self.environments.values()
            if e.status == EnvironmentStatus.ACTIVE
        ]

    def expire_all_overdue(self) -> List[str]:
        """Check all environments and expire any that are overdue.

        Returns:
            List of environment IDs that were expired.
        """
        expired_ids = []
        for env in list(self.environments.values()):
            if self.has_expired(env) and env.status != EnvironmentStatus.CLEANED_UP:
                expired_ids.append(env.env_id)
        return expired_ids
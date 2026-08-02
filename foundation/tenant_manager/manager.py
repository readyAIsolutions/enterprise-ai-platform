"""
Tenant Manager - Multi-tenant management core.

Provides TenantManager for complete tenant lifecycle management including
CRUD operations, status tracking, configuration management, and per-tenant
rate limiting controls.
"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple


class TenantStatus(Enum):
    """Possible states in the tenant lifecycle."""

    ACTIVE = auto()
    """Tenant is fully operational."""

    SUSPENDED = auto()
    """Tenant is temporarily disabled (e.g., billing issue)."""

    PROVISIONING = auto()
    """Tenant is being set up."""

    DEPROVISIONED = auto()
    """Tenant has been decommissioned."""

    TRIAL = auto()
    """Tenant is in a trial period."""


@dataclass
class RateLimitConfig:
    """Per-tenant rate limiting configuration.

    Attributes:
        requests_per_second: Maximum requests allowed per second.
        requests_per_minute: Maximum requests allowed per minute.
        requests_per_hour: Maximum requests allowed per hour.
        burst_size: Maximum burst size above the steady rate.
        concurrent_limit: Maximum concurrent requests allowed.
        enabled: Whether rate limiting is active for this tenant.
    """

    requests_per_second: int = 100
    requests_per_minute: int = 6_000
    requests_per_hour: int = 300_000
    burst_size: int = 200
    concurrent_limit: int = 50
    enabled: bool = True


@dataclass
class TenantConfig:
    """Arbitrary key-value configuration for a tenant.

    Attributes:
        settings: Dictionary of configuration key-value pairs.
        features: Set of enabled feature flags.
        metadata: Arbitrary metadata tags.
    """

    settings: Dict[str, Any] = field(default_factory=dict)
    features: set = field(default_factory=set)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Tenant:
    """Represents a single tenant in the system.

    Attributes:
        tenant_id: Unique tenant identifier.
        name: Human-readable tenant name.
        status: Current lifecycle status.
        config: Tenant-specific configuration.
        rate_limit: Per-tenant rate limiting config.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
        contact_email: Admin contact for this tenant.
        parent_tenant_id: Optional parent for hierarchical tenancy.
        custom_domain: Optional custom domain mapping.
    """

    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    config: TenantConfig = field(default_factory=TenantConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    contact_email: str = ""
    parent_tenant_id: Optional[str] = None
    custom_domain: Optional[str] = None


class TenantManager:
    """Central manager for multi-tenant lifecycle operations.

    Handles tenant CRUD operations, status tracking, configuration
    management, and per-tenant rate limiting enforcement.

    Attributes:
        _tenants: Internal tenant registry keyed by tenant_id.
        _lock: Thread safety lock for concurrent access.
        _rate_counters: Per-tenant rate limiting counters.
        _rate_lock: Lock for rate counter operations.
        _event_hooks: Callbacks for tenant lifecycle events.
    """

    def __init__(self) -> None:
        """Initialize an empty tenant manager."""
        self._tenants: Dict[str, Tenant] = {}
        self._lock = threading.RLock()
        self._rate_counters: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"second": [], "minute": [], "hour": [], "concurrent": 0}
        )
        self._rate_lock = threading.Lock()
        self._event_hooks: Dict[str, List[Callable[..., Any]]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Tenant CRUD
    # ------------------------------------------------------------------

    def create_tenant(
        self,
        name: str,
        contact_email: str = "",
        config: Optional[Dict[str, Any]] = None,
        features: Optional[set] = None,
        metadata: Optional[Dict[str, str]] = None,
        rate_limit: Optional[RateLimitConfig] = None,
        parent_tenant_id: Optional[str] = None,
        custom_domain: Optional[str] = None,
        initial_status: TenantStatus = TenantStatus.PROVISIONING,
    ) -> Tenant:
        """Create a new tenant and register it.

        Args:
            name: Human-readable tenant name.
            contact_email: Admin email contact.
            config: Initial configuration key-value pairs.
            features: Set of enabled feature flags.
            metadata: Arbitrary metadata tags.
            rate_limit: Custom rate limiting configuration.
            parent_tenant_id: Optional hierarchical parent.
            custom_domain: Optional custom domain.
            initial_status: Starting lifecycle status.

        Returns:
            The newly created Tenant instance.

        Raises:
            ValueError: If a tenant with the same name already exists.
        """
        tenant_id = self._generate_tenant_id()

        with self._lock:
            # Check for duplicate names
            for existing in self._tenants.values():
                if existing.name == name:
                    raise ValueError(f"Tenant with name '{name}' already exists")

            tenant_config = TenantConfig()
            if config:
                tenant_config.settings = copy.deepcopy(config)
            if features:
                tenant_config.features = features.copy()
            if metadata:
                tenant_config.metadata = metadata.copy()

            tenant = Tenant(
                tenant_id=tenant_id,
                name=name,
                status=initial_status,
                config=tenant_config,
                rate_limit=rate_limit or RateLimitConfig(),
                contact_email=contact_email,
                parent_tenant_id=parent_tenant_id,
                custom_domain=custom_domain,
            )

            self._tenants[tenant_id] = tenant
            self._fire_event("tenant_created", tenant)

        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Retrieve a tenant by its ID.

        Args:
            tenant_id: The unique tenant identifier.

        Returns:
            The Tenant if found, otherwise None.
        """
        with self._lock:
            return self._tenants.get(tenant_id)

    def get_tenant_by_name(self, name: str) -> Optional[Tenant]:
        """Retrieve a tenant by its name.

        Args:
            name: The tenant's human-readable name.

        Returns:
            The Tenant if found, otherwise None.
        """
        with self._lock:
            for tenant in self._tenants.values():
                if tenant.name == name:
                    return tenant
        return None

    def list_tenants(
        self,
        status_filter: Optional[TenantStatus] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Tenant], int]:
        """List tenants with optional status filtering and pagination.

        Args:
            status_filter: Only return tenants with this status.
            page: Page number (1-indexed).
            page_size: Number of tenants per page.

        Returns:
            Tuple of (tenants_list, total_count).
        """
        with self._lock:
            all_tenants = list(self._tenants.values())
            if status_filter is not None:
                all_tenants = [t for t in all_tenants if t.status == status_filter]

            total = len(all_tenants)
            start = (page - 1) * page_size
            end = start + page_size
            return all_tenants[start:end], total

    def update_tenant(
        self,
        tenant_id: str,
        name: Optional[str] = None,
        contact_email: Optional[str] = None,
        config_updates: Optional[Dict[str, Any]] = None,
        features: Optional[set] = None,
        metadata: Optional[Dict[str, str]] = None,
        custom_domain: Optional[str] = None,
    ) -> Optional[Tenant]:
        """Update tenant properties.

        Args:
            tenant_id: The tenant to update.
            name: New name (or None to keep current).
            contact_email: New contact email.
            config_updates: Merged into existing config settings.
            features: Replacement feature set.
            metadata: Replacement metadata.
            custom_domain: New custom domain.

        Returns:
            Updated Tenant, or None if tenant not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return None

            old_copy = copy.deepcopy(tenant)

            if name is not None:
                tenant.name = name
            if contact_email is not None:
                tenant.contact_email = contact_email
            if config_updates is not None:
                tenant.config.settings.update(config_updates)
            if features is not None:
                tenant.config.features = features.copy()
            if metadata is not None:
                tenant.config.metadata = metadata.copy()
            if custom_domain is not None:
                tenant.custom_domain = custom_domain

            tenant.updated_at = datetime.utcnow()
            self._fire_event("tenant_updated", tenant, old_copy)

            return tenant

    def delete_tenant(self, tenant_id: str, hard: bool = False) -> bool:
        """Remove a tenant from the system.

        Args:
            tenant_id: The tenant to delete.
            hard: If True, permanently remove. If False, soft-delete
                  by setting status to DEPROVISIONED.

        Returns:
            True if the tenant was deleted, False if not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return False

            if hard:
                del self._tenants[tenant_id]
                self._fire_event("tenant_deleted_hard", tenant)
            else:
                tenant.status = TenantStatus.DEPROVISIONED
                tenant.updated_at = datetime.utcnow()
                self._fire_event("tenant_deleted_soft", tenant)

            return True

    # ------------------------------------------------------------------
    # Status Management
    # ------------------------------------------------------------------

    def set_tenant_status(
        self, tenant_id: str, status: TenantStatus, reason: str = ""
    ) -> Optional[Tenant]:
        """Transition a tenant to a new lifecycle status.

        Args:
            tenant_id: The tenant to transition.
            status: Target status.
            reason: Human-readable reason for the transition.

        Returns:
            Updated Tenant, or None if not found.

        Raises:
            ValueError: If the status transition is invalid.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return None

            old_status = tenant.status
            if not self._is_valid_transition(old_status, status):
                raise ValueError(
                    f"Invalid status transition: {old_status.name} -> {status.name}"
                )

            tenant.status = status
            tenant.updated_at = datetime.utcnow()
            self._fire_event("tenant_status_changed", tenant, old_status, reason)

            return tenant

    def get_tenant_status(self, tenant_id: str) -> Optional[TenantStatus]:
        """Get the current status of a tenant.

        Args:
            tenant_id: The tenant to query.

        Returns:
            Current TenantStatus if found, otherwise None.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            return tenant.status if tenant else None

    def activate_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Activate a tenant (shortcut for set_tenant_status to ACTIVE)."""
        return self.set_tenant_status(tenant_id, TenantStatus.ACTIVE, "Manual activation")

    def suspend_tenant(self, tenant_id: str, reason: str = "") -> Optional[Tenant]:
        """Suspend a tenant (shortcut for set_tenant_status to SUSPENDED)."""
        return self.set_tenant_status(tenant_id, TenantStatus.SUSPENDED, reason)

    def get_tenants_by_status(self, status: TenantStatus) -> List[Tenant]:
        """Get all tenants with a specific status.

        Args:
            status: The status to filter by.

        Returns:
            List of matching tenants.
        """
        with self._lock:
            return [t for t in self._tenants.values() if t.status == status]

    def get_status_summary(self) -> Dict[TenantStatus, int]:
        """Get a summary count of tenants by status.

        Returns:
            Dictionary mapping each status to a tenant count.
        """
        with self._lock:
            summary: Dict[TenantStatus, int] = {s: 0 for s in TenantStatus}
            for tenant in self._tenants.values():
                summary[tenant.status] += 1
            return summary

    # ------------------------------------------------------------------
    # Configuration Management
    # ------------------------------------------------------------------

    def get_config(self, tenant_id: str, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value for a tenant.

        Args:
            tenant_id: The tenant.
            key: Configuration key.
            default: Value to return if key not found.

        Returns:
            The configuration value or default.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return default
            return tenant.config.settings.get(key, default)

    def set_config(self, tenant_id: str, key: str, value: Any) -> bool:
        """Set a configuration value for a tenant.

        Args:
            tenant_id: The tenant.
            key: Configuration key.
            value: Value to set.

        Returns:
            True if successful, False if tenant not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return False
            old_value = tenant.config.settings.get(key)
            tenant.config.settings[key] = value
            tenant.updated_at = datetime.utcnow()
            self._fire_event("config_changed", tenant, key, old_value, value)
            return True

    def get_all_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get the full configuration dictionary for a tenant.

        Args:
            tenant_id: The tenant.

        Returns:
            Copy of the configuration dictionary, or None if not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return None
            return copy.deepcopy(tenant.config.settings)

    def enable_feature(self, tenant_id: str, feature: str) -> bool:
        """Enable a feature flag for a tenant.

        Args:
            tenant_id: The tenant.
            feature: Feature flag name.

        Returns:
            True if successful, False if tenant not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return False
            tenant.config.features.add(feature)
            tenant.updated_at = datetime.utcnow()
            return True

    def disable_feature(self, tenant_id: str, feature: str) -> bool:
        """Disable a feature flag for a tenant.

        Args:
            tenant_id: The tenant.
            feature: Feature flag name.

        Returns:
            True if successful, False if tenant not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return False
            tenant.config.features.discard(feature)
            tenant.updated_at = datetime.utcnow()
            return True

    def has_feature(self, tenant_id: str, feature: str) -> bool:
        """Check if a tenant has a specific feature flag enabled.

        Args:
            tenant_id: The tenant.
            feature: Feature flag name.

        Returns:
            True if the feature is enabled.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return False
            return feature in tenant.config.features

    # ------------------------------------------------------------------
    # Rate Limiting
    # ------------------------------------------------------------------

    def check_rate_limit(self, tenant_id: str) -> bool:
        """Check if a request should be allowed under the tenant's rate limit.

        Uses a sliding window implementation for per-second, per-minute,
        and per-hour limits, plus concurrent request tracking.

        Args:
            tenant_id: The tenant making the request.

        Returns:
            True if the request is within limits, False if throttled.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return False
            rl = tenant.rate_limit

        if not rl.enabled:
            return True

        now = time.monotonic()

        with self._rate_lock:
            counters = self._rate_counters[tenant_id]

            # Prune expired timestamps
            counters["second"] = [t for t in counters["second"] if now - t < 1.0]
            counters["minute"] = [t for t in counters["minute"] if now - t < 60.0]
            counters["hour"] = [t for t in counters["hour"] if now - t < 3600.0]

            # Check concurrent limit
            if counters["concurrent"] >= rl.concurrent_limit:
                return False

            # Check rate limits
            if len(counters["second"]) >= rl.requests_per_second:
                return False
            if len(counters["minute"]) >= rl.requests_per_minute:
                return False
            if len(counters["hour"]) >= rl.requests_per_hour:
                return False

            # Check burst
            if len(counters["second"]) >= rl.burst_size:
                return False

            # Record this request
            counters["second"].append(now)
            counters["minute"].append(now)
            counters["hour"].append(now)
            counters["concurrent"] += 1

            return True

    def release_rate_limit(self, tenant_id: str) -> None:
        """Release a concurrent slot after a request completes.

        Should be called when a request finishes to decrement the
        concurrent counter.

        Args:
            tenant_id: The tenant whose request completed.
        """
        with self._rate_lock:
            if tenant_id in self._rate_counters:
                counters = self._rate_counters[tenant_id]
                counters["concurrent"] = max(0, counters["concurrent"] - 1)

    def get_rate_limit_status(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get current rate limit usage statistics for a tenant.

        Args:
            tenant_id: The tenant to query.

        Returns:
            Dictionary with usage stats, or None if tenant not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return None
            rl = tenant.rate_limit

        with self._rate_lock:
            counters = self._rate_counters.get(tenant_id, {})
            now = time.monotonic()

            return {
                "requests_per_second": {
                    "used": len([t for t in counters.get("second", []) if now - t < 1.0]),
                    "limit": rl.requests_per_second,
                },
                "requests_per_minute": {
                    "used": len([t for t in counters.get("minute", []) if now - t < 60.0]),
                    "limit": rl.requests_per_minute,
                },
                "requests_per_hour": {
                    "used": len([t for t in counters.get("hour", []) if now - t < 3600.0]),
                    "limit": rl.requests_per_hour,
                },
                "concurrent": {
                    "used": counters.get("concurrent", 0),
                    "limit": rl.concurrent_limit,
                },
                "enabled": rl.enabled,
            }

    def set_rate_limit_config(
        self, tenant_id: str, config: RateLimitConfig
    ) -> Optional[Tenant]:
        """Update a tenant's rate limiting configuration.

        Args:
            tenant_id: The tenant to update.
            config: New rate limit configuration.

        Returns:
            Updated Tenant, or None if not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return None
            tenant.rate_limit = config
            tenant.updated_at = datetime.utcnow()
            return tenant

    # ------------------------------------------------------------------
    # Event Hooks
    # ------------------------------------------------------------------

    def on(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a callback for a lifecycle event.

        Supported events:
            tenant_created, tenant_updated, tenant_deleted_soft,
            tenant_deleted_hard, tenant_status_changed, config_changed

        Args:
            event: Event name to listen for.
            callback: Callable to invoke when the event fires.
        """
        self._event_hooks[event].append(callback)

    def off(self, event: str, callback: Callable[..., Any]) -> None:
        """Remove a previously registered event callback.

        Args:
            event: Event name.
            callback: The callback to remove.
        """
        if event in self._event_hooks:
            self._event_hooks[event] = [
                cb for cb in self._event_hooks[event] if cb is not callback
            ]

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_tenant_id() -> str:
        """Generate a unique tenant identifier."""
        return f"tn_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _is_valid_transition(
        old_status: TenantStatus, new_status: TenantStatus
    ) -> bool:
        """Validate that a status transition is allowed.

        Args:
            old_status: Current tenant status.
            new_status: Proposed new status.

        Returns:
            True if the transition is valid.
        """
        # Allow transitions to same status (no-op)
        if old_status == new_status:
            return True

        # Define allowed transitions
        allowed: Dict[TenantStatus, set] = {
            TenantStatus.PROVISIONING: {TenantStatus.ACTIVE, TenantStatus.TRIAL, TenantStatus.DEPROVISIONED},
            TenantStatus.TRIAL: {TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.DEPROVISIONED},
            TenantStatus.ACTIVE: {TenantStatus.SUSPENDED, TenantStatus.DEPROVISIONED},
            TenantStatus.SUSPENDED: {TenantStatus.ACTIVE, TenantStatus.DEPROVISIONED},
            TenantStatus.DEPROVISIONED: set(),  # Cannot transition out of deprovisioned
        }

        return new_status in allowed.get(old_status, set())

    def _fire_event(self, event: str, *args: Any) -> None:
        """Fire all registered callbacks for an event.

        Args:
            event: The event name.
            *args: Arguments to pass to callbacks.
        """
        for callback in self._event_hooks.get(event, []):
            try:
                callback(*args)
            except Exception:
                pass  # Silently swallow callback errors to avoid cascading failures

    def cleanup(self) -> None:
        """Reset the tenant manager, clearing all state."""
        with self._lock:
            self._tenants.clear()
        with self._rate_lock:
            self._rate_counters.clear()
        self._event_hooks.clear()
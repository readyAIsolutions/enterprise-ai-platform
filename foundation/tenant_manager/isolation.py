"""
Tenant Isolation - Data isolation and resource enforcement.

Provides TenantIsolation for enforcing strict data boundaries between
tenants, managing resource quotas, preventing cross-tenant access,
and supporting per-tenant data encryption.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set


class IsolationPolicy(Enum):
    """Data isolation policy levels."""

    STRICT = auto()
    """Complete physical/logical separation; no shared resources."""

    LOGICAL = auto()
    """Logical separation within shared infrastructure (row-level)."""

    SHARED = auto()
    """Shared resources with tenant-ID scoping only."""


@dataclass
class ResourceQuota:
    """Resource limits enforced per tenant.

    Attributes:
        max_storage_bytes: Maximum storage in bytes.
        max_api_calls_per_day: Maximum API calls per 24-hour window.
        max_compute_units: Maximum compute units (e.g., CPU-hours).
        max_concurrent_sessions: Maximum concurrent user sessions.
        max_workspaces: Maximum number of workspaces per tenant.
        max_users: Maximum users per tenant.
        custom_limits: Arbitrary custom resource limits.
    """

    max_storage_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB
    max_api_calls_per_day: int = 1_000_000
    max_compute_units: int = 1000
    max_concurrent_sessions: int = 100
    max_workspaces: int = 50
    max_users: int = 500
    custom_limits: Dict[str, int] = field(default_factory=dict)


@dataclass
class QuotaUsage:
    """Current usage of a tenant's resource quota.

    Attributes:
        storage_bytes_used: Current storage consumption.
        api_calls_today: API calls made in the current day.
        compute_units_used: Current compute unit consumption.
        concurrent_sessions: Current active sessions.
        workspaces_count: Current number of workspaces.
        users_count: Current number of users.
        custom_usage: Usage for custom limits.
        last_reset: When daily counters were last reset.
    """

    storage_bytes_used: int = 0
    api_calls_today: int = 0
    compute_units_used: int = 0
    concurrent_sessions: int = 0
    workspaces_count: int = 0
    users_count: int = 0
    custom_usage: Dict[str, int] = field(default_factory=dict)
    last_reset: datetime = field(default_factory=datetime.utcnow)


class TenantIsolation:
    """Enforces tenant data isolation and resource quotas.

    Provides mechanisms to:
    - Enforce data isolation (strict, logical, shared)
    - Track and enforce resource quotas per tenant
    - Prevent cross-tenant data access
    - Encrypt tenant-specific data with per-tenant keys

    Attributes:
        _policies: Per-tenant isolation policies.
        _quotas: Per-tenant resource quotas.
        _usage: Per-tenant current resource usage.
        _encryption_keys: Per-tenant encryption keys.
        _access_registry: Tracks which tenants access which resources.
        _lock: Thread safety lock.
    """

    def __init__(self) -> None:
        """Initialize the isolation manager."""
        self._policies: Dict[str, IsolationPolicy] = {}
        self._quotas: Dict[str, ResourceQuota] = {}
        self._usage: Dict[str, QuotaUsage] = {}
        self._encryption_keys: Dict[str, bytes] = {}
        self._access_registry: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._data_registry: Dict[str, str] = {}  # data_id -> tenant_id

    # ------------------------------------------------------------------
    # Isolation Policy Management
    # ------------------------------------------------------------------

    def set_isolation_policy(
        self, tenant_id: str, policy: IsolationPolicy
    ) -> None:
        """Set the isolation policy for a tenant.

        Args:
            tenant_id: The tenant.
            policy: Desired isolation policy level.
        """
        with self._lock:
            self._policies[tenant_id] = policy

    def get_isolation_policy(self, tenant_id: str) -> IsolationPolicy:
        """Get the current isolation policy for a tenant.

        Args:
            tenant_id: The tenant.

        Returns:
            Current policy; defaults to STRICT if not set.
        """
        with self._lock:
            return self._policies.get(tenant_id, IsolationPolicy.STRICT)

    # ------------------------------------------------------------------
    # Resource Quota Management
    # ------------------------------------------------------------------

    def set_resource_quota(
        self, tenant_id: str, quota: ResourceQuota
    ) -> None:
        """Set resource quotas for a tenant.

        Args:
            tenant_id: The tenant.
            quota: Resource quota configuration.
        """
        with self._lock:
            self._quotas[tenant_id] = quota
            if tenant_id not in self._usage:
                self._usage[tenant_id] = QuotaUsage()

    def get_resource_quota(self, tenant_id: str) -> ResourceQuota:
        """Get current resource quotas for a tenant.

        Args:
            tenant_id: The tenant.

        Returns:
            Current quota; returns default quota if not set.
        """
        with self._lock:
            return self._quotas.get(tenant_id, ResourceQuota())

    def get_quota_usage(self, tenant_id: str) -> QuotaUsage:
        """Get current resource usage for a tenant.

        Args:
            tenant_id: The tenant.

        Returns:
            Current usage; returns empty usage if not tracked.
        """
        with self._lock:
            if tenant_id not in self._usage:
                self._usage[tenant_id] = QuotaUsage()
            # Auto-reset daily counters if needed
            self._maybe_reset_daily(tenant_id)
            return self._usage[tenant_id]

    def check_quota(self, tenant_id: str, resource: str, amount: int = 1) -> bool:
        """Check if a resource usage would exceed the tenant's quota.

        Args:
            tenant_id: The tenant.
            resource: Resource name to check.
            amount: Proposed incremental usage.

        Returns:
            True if within quota, False if it would exceed.
        """
        with self._lock:
            quota = self._quotas.get(tenant_id, ResourceQuota())
            usage = self._usage.get(tenant_id)
            if usage is None:
                usage = QuotaUsage()
                self._usage[tenant_id] = usage

            self._maybe_reset_daily(tenant_id)

            if resource == "storage":
                return (usage.storage_bytes_used + amount) <= quota.max_storage_bytes
            elif resource == "api_calls":
                return (usage.api_calls_today + amount) <= quota.max_api_calls_per_day
            elif resource == "compute":
                return (usage.compute_units_used + amount) <= quota.max_compute_units
            elif resource == "sessions":
                return (usage.concurrent_sessions + amount) <= quota.max_concurrent_sessions
            elif resource == "workspaces":
                return (usage.workspaces_count + amount) <= quota.max_workspaces
            elif resource == "users":
                return (usage.users_count + amount) <= quota.max_users
            else:
                # Custom resource
                current = usage.custom_usage.get(resource, 0)
                limit = quota.custom_limits.get(resource, 0)
                return (current + amount) <= limit

    def track_usage(
        self, tenant_id: str, resource: str, amount: int = 1
    ) -> bool:
        """Track resource usage and enforce quota.

        Records the usage increment and returns whether the operation
        is allowed under the current quota.

        Args:
            tenant_id: The tenant.
            resource: Resource name to track.
            amount: Amount to increment.

        Returns:
            True if usage was allowed and tracked, False if quota exceeded.
        """
        with self._lock:
            if not self.check_quota(tenant_id, resource, amount):
                return False

            usage = self._usage.get(tenant_id)
            if usage is None:
                usage = QuotaUsage()
                self._usage[tenant_id] = usage

            if resource == "storage":
                usage.storage_bytes_used += amount
            elif resource == "api_calls":
                usage.api_calls_today += amount
            elif resource == "compute":
                usage.compute_units_used += amount
            elif resource == "sessions":
                usage.concurrent_sessions += amount
            elif resource == "workspaces":
                usage.workspaces_count += amount
            elif resource == "users":
                usage.users_count += amount
            else:
                usage.custom_usage[resource] = (
                    usage.custom_usage.get(resource, 0) + amount
                )

            return True

    def release_usage(
        self, tenant_id: str, resource: str, amount: int = 1
    ) -> None:
        """Release tracked resource usage (e.g., session ends).

        Args:
            tenant_id: The tenant.
            resource: Resource name.
            amount: Amount to decrement.
        """
        with self._lock:
            usage = self._usage.get(tenant_id)
            if usage is None:
                return

            if resource == "storage":
                usage.storage_bytes_used = max(0, usage.storage_bytes_used - amount)
            elif resource == "compute":
                usage.compute_units_used = max(0, usage.compute_units_used - amount)
            elif resource == "sessions":
                usage.concurrent_sessions = max(0, usage.concurrent_sessions - amount)
            elif resource == "workspaces":
                usage.workspaces_count = max(0, usage.workspaces_count - amount)
            elif resource == "users":
                usage.users_count = max(0, usage.users_count - amount)
            else:
                current = usage.custom_usage.get(resource, 0)
                usage.custom_usage[resource] = max(0, current - amount)

    def get_quota_exceeded_resources(self, tenant_id: str) -> List[str]:
        """Get list of resources where tenant has exceeded their quota.

        Args:
            tenant_id: The tenant.

        Returns:
            List of resource names that are at or over quota.
        """
        exceeded: List[str] = []
        with self._lock:
            quota = self._quotas.get(tenant_id, ResourceQuota())
            usage = self._usage.get(tenant_id)
            if usage is None:
                return exceeded

            self._maybe_reset_daily(tenant_id)

            checks = [
                ("storage", usage.storage_bytes_used, quota.max_storage_bytes),
                ("api_calls", usage.api_calls_today, quota.max_api_calls_per_day),
                ("compute", usage.compute_units_used, quota.max_compute_units),
                ("sessions", usage.concurrent_sessions, quota.max_concurrent_sessions),
                ("workspaces", usage.workspaces_count, quota.max_workspaces),
                ("users", usage.users_count, quota.max_users),
            ]

            for name, used, limit in checks:
                if used >= limit:
                    exceeded.append(name)

            for custom_name, custom_used in usage.custom_usage.items():
                limit = quota.custom_limits.get(custom_name, 0)
                if custom_used >= limit:
                    exceeded.append(custom_name)

        return exceeded

    # ------------------------------------------------------------------
    # Cross-Tenant Access Prevention
    # ------------------------------------------------------------------

    def register_data_ownership(
        self, tenant_id: str, data_id: str
    ) -> None:
        """Register a data resource as owned by a specific tenant.

        Args:
            tenant_id: Owning tenant.
            data_id: Unique identifier for the data resource.
        """
        with self._lock:
            self._data_registry[data_id] = tenant_id

    def check_data_access(
        self, tenant_id: str, data_id: str
    ) -> bool:
        """Verify that a tenant is allowed to access specific data.

        Args:
            tenant_id: Tenant requesting access.
            data_id: Data resource identifier.

        Returns:
            True if access is allowed, False if denied.
        """
        with self._lock:
            owner = self._data_registry.get(data_id)
            if owner is None:
                # Unregistered data: allow access but log it
                self._access_registry[tenant_id].add(data_id)
                return True

            allowed = owner == tenant_id
            if allowed:
                self._access_registry[tenant_id].add(data_id)
            else:
                # Log cross-tenant access attempt
                self._access_registry[tenant_id].add(f"DENIED:{data_id}")

            return allowed

    def get_cross_tenant_access_attempts(
        self, tenant_id: str
    ) -> List[str]:
        """Get log of denied cross-tenant access attempts.

        Args:
            tenant_id: The tenant to query.

        Returns:
            List of denied data IDs.
        """
        with self._lock:
            return [
                entry.replace("DENIED:", "")
                for entry in self._access_registry.get(tenant_id, set())
                if entry.startswith("DENIED:")
            ]

    def isolate_data(
        self, tenant_id: str, data: str
    ) -> Dict[str, Any]:
        """Tag data with tenant ownership metadata.

        Args:
            tenant_id: Owning tenant.
            data: Data payload to isolate.

        Returns:
            Isolated data wrapper with tenant ownership metadata.
        """
        data_id = f"data_{tenant_id}_{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        self.register_data_ownership(tenant_id, data_id)
        return {
            "data_id": data_id,
            "tenant_id": tenant_id,
            "payload": data,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def validate_tenant_access(
        self, requesting_tenant: str, target_tenant: str
    ) -> bool:
        """Validate that one tenant is allowed to access another tenant's resources.

        In strict mode, cross-tenant access is always denied. In logical
        or shared modes, it may be allowed for specific operations.

        Args:
            requesting_tenant: Tenant making the request.
            target_tenant: Target tenant whose resources are being accessed.

        Returns:
            True if access is allowed.
        """
        if requesting_tenant == target_tenant:
            return True

        policy = self.get_isolation_policy(requesting_tenant)
        if policy == IsolationPolicy.STRICT:
            return False
        elif policy == IsolationPolicy.LOGICAL:
            # Allow only if explicitly authorized (simplified here)
            return False
        else:
            # SHARED mode allows cross-tenant with audit
            return True

    # ------------------------------------------------------------------
    # Data Encryption
    # ------------------------------------------------------------------

    def generate_encryption_key(self, tenant_id: str) -> bytes:
        """Generate a unique encryption key for a tenant.

        Uses a cryptographically secure random source.

        Args:
            tenant_id: The tenant to generate a key for.

        Returns:
            The generated encryption key (32 bytes).
        """
        key = os.urandom(32)
        with self._lock:
            self._encryption_keys[tenant_id] = key
        return key

    def get_encryption_key(self, tenant_id: str) -> Optional[bytes]:
        """Retrieve the encryption key for a tenant.

        Args:
            tenant_id: The tenant.

        Returns:
            The encryption key, or None if not set.
        """
        with self._lock:
            return self._encryption_keys.get(tenant_id)

    def encrypt_data(self, tenant_id: str, plaintext: str) -> str:
        """Encrypt data using the tenant's encryption key.

        Uses HMAC-SHA256 for authenticated encryption simulation.
        In production, this would use AES-256-GCM or similar.

        Args:
            tenant_id: The tenant whose key to use.
            plaintext: Data to encrypt.

        Returns:
            Base64-encoded ciphertext with HMAC tag.

        Raises:
            ValueError: If no encryption key exists for the tenant.
        """
        key = self.get_encryption_key(tenant_id)
        if key is None:
            raise ValueError(f"No encryption key found for tenant '{tenant_id}'")

        # Simple XOR-based encryption with HMAC for demonstration
        # In production, use proper AES-GCM
        derived_key = hashlib.pbkdf2_hmac(
            "sha256", key, b"tenant-encryption-salt", 100000, dklen=64
        )
        enc_key = derived_key[:32]
        mac_key = derived_key[32:]

        # Encrypt with XOR + key stream
        plain_bytes = plaintext.encode("utf-8")
        key_stream = hashlib.sha256(enc_key + str(len(plain_bytes)).encode()).digest()
        # Repeat key_stream as needed
        full_stream = (key_stream * ((len(plain_bytes) // len(key_stream)) + 1))[
            : len(plain_bytes)
        ]
        cipher_bytes = bytes(a ^ b for a, b in zip(plain_bytes, full_stream))

        # Compute HMAC for authentication
        tag = hmac.new(mac_key, cipher_bytes, hashlib.sha256).digest()

        # Encode ciphertext + tag
        combined = cipher_bytes + tag
        return base64.b64encode(combined).decode("ascii")

    def decrypt_data(self, tenant_id: str, ciphertext_b64: str) -> str:
        """Decrypt data using the tenant's encryption key.

        Args:
            tenant_id: The tenant whose key to use.
            ciphertext_b64: Base64-encoded ciphertext with HMAC tag.

        Returns:
            Decrypted plaintext.

        Raises:
            ValueError: If no key exists, or if authentication fails.
        """
        key = self.get_encryption_key(tenant_id)
        if key is None:
            raise ValueError(f"No encryption key found for tenant '{tenant_id}'")

        combined = base64.b64decode(ciphertext_b64)

        # Last 32 bytes are the HMAC tag
        cipher_bytes = combined[:-32]
        tag = combined[-32:]

        # Verify HMAC
        derived_key = hashlib.pbkdf2_hmac(
            "sha256", key, b"tenant-encryption-salt", 100000, dklen=64
        )
        mac_key = derived_key[32:]
        expected_tag = hmac.new(mac_key, cipher_bytes, hashlib.sha256).digest()

        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("Data authentication failed - possible tampering detected")

        # Decrypt
        enc_key = derived_key[:32]
        key_stream = hashlib.sha256(enc_key + str(len(cipher_bytes)).encode()).digest()
        full_stream = (key_stream * ((len(cipher_bytes) // len(key_stream)) + 1))[
            : len(cipher_bytes)
        ]
        plain_bytes = bytes(a ^ b for a, b in zip(cipher_bytes, full_stream))

        return plain_bytes.decode("utf-8")

    def rotate_encryption_key(self, tenant_id: str) -> bytes:
        """Rotate a tenant's encryption key, generating a new one.

        The old key is discarded. In production, you would retain
        the old key temporarily to re-encrypt existing data.

        Args:
            tenant_id: The tenant.

        Returns:
            The new encryption key.
        """
        return self.generate_encryption_key(tenant_id)

    def revoke_encryption_key(self, tenant_id: str) -> None:
        """Revoke and remove a tenant's encryption key.

        WARNING: This makes encrypted data unrecoverable.

        Args:
            tenant_id: The tenant.
        """
        with self._lock:
            self._encryption_keys.pop(tenant_id, None)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _maybe_reset_daily(self, tenant_id: str) -> None:
        """Reset daily counters if the day has changed since last reset.

        Args:
            tenant_id: The tenant to check.
        """
        usage = self._usage.get(tenant_id)
        if usage is None:
            return

        now = datetime.utcnow()
        if now.date() > usage.last_reset.date():
            usage.api_calls_today = 0
            usage.last_reset = now

    def cleanup(self) -> None:
        """Reset all isolation state."""
        with self._lock:
            self._policies.clear()
            self._quotas.clear()
            self._usage.clear()
            self._encryption_keys.clear()
            self._access_registry.clear()
            self._data_registry.clear()
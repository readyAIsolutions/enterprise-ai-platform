"""
Plugin Security module for the Eni Builder Plugin Framework.

Provides permission models, signing/verification stubs, and access control
for plugins. Controls what plugins can do in terms of filesystem access,
network access, code execution, and data operations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from typing import Any, Dict, FrozenSet, List, Optional, Set


class Permission(Flag):
    """Granular permission flags for plugin operations.

    Permissions follow the principle of least privilege. Plugins start
    with no permissions and must request exactly what they need.
    """

    NONE = 0

    # ---- Filesystem Permissions ----
    FS_READ = auto()           # Read any file
    FS_WRITE = auto()          # Write any file
    FS_DELETE = auto()         # Delete files
    FS_EXECUTE = auto()        # Execute binaries/files
    FS_READ_RESTRICTED = auto()  # Read only from allowed paths
    FS_WRITE_RESTRICTED = auto()  # Write only to allowed paths

    # ---- Network Permissions ----
    NET_OUTBOUND = auto()      # Outbound network connections
    NET_INBOUND = auto()       # Listen for inbound connections
    NET_DNS = auto()           # DNS resolution
    NET_RESTRICTED = auto()    # Network restricted to allowed hosts/ports

    # ---- Process Permissions ----
    PROC_SPAWN = auto()        # Spawn subprocesses
    PROC_SIGNAL = auto()       # Send signals to other processes

    # ---- Data Permissions ----
    DATA_READ = auto()         # Read from plugin data store
    DATA_WRITE = auto()        # Write to plugin data store
    DATA_DELETE = auto()       # Delete from plugin data store

    # ---- System Permissions ----
    SYS_INFO = auto()          # Read system information
    SYS_CONFIG = auto()        # Access system configuration

    # ---- Inter-Plugin Permissions ----
    INTER_PLUGIN_COMM = auto()  # Communicate with other plugins
    BROADCAST_EVENTS = auto()   # Emit events to other plugins

    # Convenience groupings
    FS_ALL = FS_READ | FS_WRITE | FS_DELETE | FS_EXECUTE
    FS_SAFE = FS_READ_RESTRICTED | FS_WRITE_RESTRICTED
    NET_ALL = NET_OUTBOUND | NET_INBOUND | NET_DNS
    DATA_ALL = DATA_READ | DATA_WRITE | DATA_DELETE
    ALL = (
        FS_ALL | NET_ALL | PROC_SPAWN | PROC_SIGNAL
        | DATA_ALL | SYS_INFO | SYS_CONFIG
        | INTER_PLUGIN_COMM | BROADCAST_EVENTS
    )


class SigningStatus(Enum):
    """Status of a plugin's cryptographic signature verification."""

    NOT_SIGNED = "not_signed"
    SIGNED = "signed"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    UNTRUSTED_SIGNER = "untrusted_signer"
    EXPIRED = "expired"


@dataclass
class PluginSignature:
    """Represents a cryptographic signature for a plugin.

    This is a stub for a real signing implementation. In production,
    this would use asymmetric cryptography (Ed25519, RSA, etc.) with
    a proper PKI.
    """

    signer_id: str = ""
    signature_hex: str = ""
    algorithm: str = "sha256-rsa"
    """Signature algorithm used."""
    signed_at: str = ""
    """ISO 8601 timestamp of when the signature was created."""
    expires_at: str = ""
    """ISO 8601 timestamp of when the signature expires, empty for no expiry."""

    def verify(self, plugin_content: bytes, public_key_pem: str = "") -> SigningStatus:
        """Stub verification. In production, this would cryptographically
        verify the plugin content against the signature and public key.

        Args:
            plugin_content: The raw bytes of the plugin to verify.
            public_key_pem: The PEM-encoded public key of the signer.

        Returns:
            The verification status. Currently returns VERIFIED if a
            signature is present (stub behavior).
        """
        if not self.signature_hex:
            return SigningStatus.NOT_SIGNED

        # Stub: verify that the hash matches
        computed_hash = hashlib.sha256(plugin_content).hexdigest()
        if computed_hash == self.signature_hex:
            return SigningStatus.VERIFIED
        return SigningStatus.VERIFICATION_FAILED


@dataclass
class PluginPermissionProfile:
    """Defines the permission profile for a specific plugin.

    Maps permission flags along with optional constraints like
    allowed paths, hosts, and ports.
    """

    plugin_name: str
    permissions: Permission = Permission.NONE
    allowed_paths: List[str] = field(default_factory=list)
    """Whitelist of filesystem paths. Only meaningful with FS_*_RESTRICTED."""
    denied_paths: List[str] = field(default_factory=list)
    """Blacklist of filesystem paths."""
    allowed_hosts: List[str] = field(default_factory=list)
    """Whitelist of network hosts. Only meaningful with NET_RESTRICTED."""
    denied_hosts: List[str] = field(default_factory=list)
    """Blacklist of network hosts."""
    allowed_ports: Set[int] = field(default_factory=set)
    """Whitelist of network ports."""
    denied_ports: Set[int] = field(default_factory=set)
    """Blacklist of network ports."""
    max_memory_mb: int = 256
    """Maximum memory in MB the plugin can use."""
    max_cpu_time_sec: int = 60
    """Maximum CPU time in seconds per execution."""
    max_file_size_mb: int = 100
    """Maximum file size in MB the plugin can create."""
    rate_limit_per_sec: int = 100
    """Maximum operations per second."""

    def has_permission(self, permission: Permission) -> bool:
        """Check if this profile grants a specific permission.

        Args:
            permission: The permission flag(s) to check.

        Returns:
            True if all specified permission flags are granted.
        """
        return (self.permissions & permission) == permission

    def grant(self, *perms: Permission) -> None:
        """Grant one or more permissions.

        Args:
            *perms: Permission flags to add to the profile.
        """
        for p in perms:
            self.permissions |= p

    def revoke(self, *perms: Permission) -> None:
        """Revoke one or more permissions.

        Args:
            *perms: Permission flags to remove from the profile.
        """
        for p in perms:
            self.permissions &= ~p


@dataclass
class AccessRequest:
    """A request from a plugin to access a specific resource.

    Used by the PluginSecurity to validate access before allowing it.
    """

    plugin_name: str
    permission: Permission
    resource: str = ""
    """The resource being accessed (path, host, capability name, etc.)."""
    details: Dict[str, Any] = field(default_factory=dict)
    """Additional context about the access request."""


@dataclass
class AccessDecision:
    """Result of an access control check."""

    allowed: bool
    reason: str = ""
    audit_id: str = ""
    """Unique ID for audit trail purposes."""


class PluginSecurityError(Exception):
    """Base exception for plugin security violations."""

    pass


class PermissionDeniedError(PluginSecurityError):
    """Raised when a plugin attempts an operation without proper permissions."""

    def __init__(self, plugin_name: str, permission: Permission, resource: str = "") -> None:
        self.plugin_name = plugin_name
        self.permission = permission
        self.resource = resource
        msg = (
            f"Plugin '{plugin_name}' denied {permission.name} permission"
            + (f" for resource '{resource}'" if resource else "")
        )
        super().__init__(msg)


class PluginSecurity:
    """Central security manager for the plugin framework.

    Manages permission profiles for all registered plugins, validates
    access requests, and handles plugin signing/verification.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, PluginPermissionProfile] = {}
        self._signatures: Dict[str, PluginSignature] = {}
        self._trusted_signers: Set[str] = set()
        self._audit_log: List[AccessDecision] = []
        self._default_permissions: Permission = Permission.FS_READ_RESTRICTED | Permission.NET_DNS
        """Default permissions applied to plugins without a specific profile."""

    # ---- Profile Management ----

    def register_profile(self, profile: PluginPermissionProfile) -> None:
        """Register a permission profile for a plugin.

        Args:
            profile: The permission profile to register.

        Raises:
            ValueError: If a profile is already registered for this plugin.
        """
        if profile.plugin_name in self._profiles:
            raise ValueError(f"Profile already registered for plugin '{profile.plugin_name}'")
        self._profiles[profile.plugin_name] = profile

    def get_profile(self, plugin_name: str) -> PluginPermissionProfile:
        """Get the permission profile for a plugin.

        Returns a default restrictive profile if no specific profile exists.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The plugin's permission profile or a default.
        """
        if plugin_name in self._profiles:
            return self._profiles[plugin_name]
        # Return default restrictive profile
        return PluginPermissionProfile(
            plugin_name=plugin_name,
            permissions=self._default_permissions,
        )

    def update_profile(self, profile: PluginPermissionProfile) -> None:
        """Update an existing permission profile.

        Args:
            profile: The updated permission profile.

        Raises:
            KeyError: If no profile exists for this plugin.
        """
        if profile.plugin_name not in self._profiles:
            raise KeyError(f"No profile found for plugin '{profile.plugin_name}'")
        self._profiles[profile.plugin_name] = profile

    def remove_profile(self, plugin_name: str) -> None:
        """Remove a plugin's permission profile.

        Args:
            plugin_name: Name of the plugin.
        """
        self._profiles.pop(plugin_name, None)

    def set_default_permissions(self, permissions: Permission) -> None:
        """Set the default permissions for plugins without specific profiles.

        Args:
            permissions: The default permission flags.
        """
        self._default_permissions = permissions

    # ---- Access Control ----

    def check_access(self, request: AccessRequest) -> AccessDecision:
        """Validate an access request against the plugin's permissions.

        Args:
            request: The access request to validate.

        Returns:
            An AccessDecision indicating whether access is granted.
        """
        profile = self.get_profile(request.plugin_name)

        # Check general permission
        if not profile.has_permission(request.permission):
            decision = AccessDecision(
                allowed=False,
                reason=f"Plugin does not have {request.permission.name} permission",
            )
            self._audit_log.append(decision)
            return decision

        # Check resource-specific constraints
        resource_check = self._check_resource_constraints(profile, request)
        if resource_check is not None:
            self._audit_log.append(resource_check)
            return resource_check

        decision = AccessDecision(allowed=True, reason="Access granted")
        self._audit_log.append(decision)
        return decision

    def _check_resource_constraints(
        self,
        profile: PluginPermissionProfile,
        request: AccessRequest,
    ) -> Optional[AccessDecision]:
        """Check resource-specific constraints (paths, hosts, ports).

        Returns None if no constraints are violated, or an AccessDecision
        with denial if constraints are violated.
        """
        resource = request.resource

        # Filesystem path checks
        if request.permission in (
            Permission.FS_READ_RESTRICTED,
            Permission.FS_WRITE_RESTRICTED,
        ):
            if resource:
                if profile.denied_paths and any(
                    resource.startswith(dp) for dp in profile.denied_paths
                ):
                    return AccessDecision(
                        allowed=False,
                        reason=f"Path '{resource}' is in denied paths list",
                    )
                if profile.allowed_paths and not any(
                    resource.startswith(ap) for ap in profile.allowed_paths
                ):
                    return AccessDecision(
                        allowed=False,
                        reason=f"Path '{resource}' is not in allowed paths list",
                    )

        # Network host checks
        elif request.permission == Permission.NET_RESTRICTED:
            if resource:
                if profile.denied_hosts and resource in profile.denied_hosts:
                    return AccessDecision(
                        allowed=False,
                        reason=f"Host '{resource}' is in denied hosts list",
                    )
                if profile.allowed_hosts and resource not in profile.allowed_hosts:
                    return AccessDecision(
                        allowed=False,
                        reason=f"Host '{resource}' is not in allowed hosts list",
                    )

        return None

    def assert_access(self, request: AccessRequest) -> None:
        """Assert access is allowed, raising an exception if denied.

        Args:
            request: The access request to check.

        Raises:
            PermissionDeniedError: If access is denied.
        """
        decision = self.check_access(request)
        if not decision.allowed:
            raise PermissionDeniedError(
                plugin_name=request.plugin_name,
                permission=request.permission,
                resource=request.resource,
            )

    # ---- Signing and Verification ----

    def add_trusted_signer(self, signer_id: str) -> None:
        """Add a signer to the trusted signers list.

        Args:
            signer_id: Unique identifier of the trusted signer.
        """
        self._trusted_signers.add(signer_id)

    def remove_trusted_signer(self, signer_id: str) -> None:
        """Remove a signer from the trusted signers list.

        Args:
            signer_id: Unique identifier of the signer to remove.
        """
        self._trusted_signers.discard(signer_id)

    def is_signer_trusted(self, signer_id: str) -> bool:
        """Check if a signer is in the trusted signers list.

        Args:
            signer_id: The signer ID to check.

        Returns:
            True if trusted, False otherwise.
        """
        return signer_id in self._trusted_signers

    def sign_plugin(self, plugin_name: str, plugin_content: bytes, signer_id: str) -> PluginSignature:
        """Stub: Sign a plugin's content.

        In production, this would produce a cryptographic signature.

        Args:
            plugin_name: Name of the plugin being signed.
            plugin_content: Raw bytes of the plugin content.
            signer_id: ID of the signer.

        Returns:
            A PluginSignature object.
        """
        import datetime
        content_hash = hashlib.sha256(plugin_content).hexdigest()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        signature = PluginSignature(
            signer_id=signer_id,
            signature_hex=content_hash,
            algorithm="sha256-rsa",
            signed_at=now,
        )
        self._signatures[plugin_name] = signature
        return signature

    def verify_plugin(
        self,
        plugin_name: str,
        plugin_content: bytes,
        public_key_pem: str = "",
    ) -> SigningStatus:
        """Verify a plugin's signature.

        Args:
            plugin_name: Name of the plugin.
            plugin_content: Raw bytes of the plugin content.
            public_key_pem: PEM-encoded public key (optional for stub).

        Returns:
            The verification status.
        """
        if plugin_name not in self._signatures:
            return SigningStatus.NOT_SIGNED

        signature = self._signatures[plugin_name]
        status = signature.verify(plugin_content, public_key_pem)

        if status == SigningStatus.VERIFIED:
            if not self.is_signer_trusted(signature.signer_id):
                return SigningStatus.UNTRUSTED_SIGNER

        return status

    def has_valid_signature(self, plugin_name: str, plugin_content: bytes) -> bool:
        """Quick check if a plugin has a valid, trusted signature.

        Args:
            plugin_name: Name of the plugin.
            plugin_content: Raw bytes of the plugin content.

        Returns:
            True if the plugin is properly signed by a trusted signer.
        """
        status = self.verify_plugin(plugin_name, plugin_content)
        return status == SigningStatus.VERIFIED

    # ---- Audit ----

    def get_audit_log(self, limit: int = 100) -> List[AccessDecision]:
        """Get recent audit log entries.

        Args:
            limit: Maximum number of entries to return (most recent first).

        Returns:
            List of AccessDecision objects.
        """
        return self._audit_log[-limit:]

    def clear_audit_log(self) -> None:
        """Clear the audit log."""
        self._audit_log.clear()
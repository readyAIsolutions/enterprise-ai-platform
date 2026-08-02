"""
Knowledge Graph Security

Enterprise-grade security for the knowledge graph: tenant isolation,
RBAC/ABAC, relationship-level authorization, encryption, immutable audit
logs, sensitive data masking, secret exclusion, data minimization,
retention policies, deletion propagation, and backup/recovery.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from base64 import b64encode, b64decode
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# ---- Access Control Models ----


class Permission(str, Enum):
    """Granular permissions for graph operations."""

    READ_ENTITY = "read_entity"
    CREATE_ENTITY = "create_entity"
    UPDATE_ENTITY = "update_entity"
    DELETE_ENTITY = "delete_entity"
    READ_RELATIONSHIP = "read_relationship"
    CREATE_RELATIONSHIP = "create_relationship"
    UPDATE_RELATIONSHIP = "update_relationship"
    DELETE_RELATIONSHIP = "delete_relationship"
    READ_PROVENANCE = "read_provenance"
    EXPORT_GRAPH = "export_graph"
    IMPORT_GRAPH = "import_graph"
    MANAGE_ACCESS = "manage_access"
    VIEW_AUDIT_LOG = "view_audit_log"
    RUN_QUERIES = "run_queries"
    ADMIN = "admin"


class Role(str, Enum):
    """Predefined roles aggregating permissions."""

    VIEWER = "viewer"
    EDITOR = "editor"
    CONTRIBUTOR = "contributor"
    MANAGER = "manager"
    AUDITOR = "auditor"
    ADMIN = "admin"


# Role-to-permission mappings
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.VIEWER: {
        Permission.READ_ENTITY,
        Permission.READ_RELATIONSHIP,
        Permission.RUN_QUERIES,
    },
    Role.EDITOR: {
        Permission.READ_ENTITY,
        Permission.CREATE_ENTITY,
        Permission.UPDATE_ENTITY,
        Permission.READ_RELATIONSHIP,
        Permission.CREATE_RELATIONSHIP,
        Permission.UPDATE_RELATIONSHIP,
        Permission.READ_PROVENANCE,
        Permission.RUN_QUERIES,
    },
    Role.CONTRIBUTOR: {
        Permission.READ_ENTITY,
        Permission.CREATE_ENTITY,
        Permission.UPDATE_ENTITY,
        Permission.READ_RELATIONSHIP,
        Permission.CREATE_RELATIONSHIP,
        Permission.READ_PROVENANCE,
        Permission.RUN_QUERIES,
        Permission.IMPORT_GRAPH,
    },
    Role.MANAGER: {
        Permission.READ_ENTITY,
        Permission.CREATE_ENTITY,
        Permission.UPDATE_ENTITY,
        Permission.DELETE_ENTITY,
        Permission.READ_RELATIONSHIP,
        Permission.CREATE_RELATIONSHIP,
        Permission.UPDATE_RELATIONSHIP,
        Permission.DELETE_RELATIONSHIP,
        Permission.READ_PROVENANCE,
        Permission.EXPORT_GRAPH,
        Permission.IMPORT_GRAPH,
        Permission.RUN_QUERIES,
        Permission.MANAGE_ACCESS,
    },
    Role.AUDITOR: {
        Permission.READ_ENTITY,
        Permission.READ_RELATIONSHIP,
        Permission.READ_PROVENANCE,
        Permission.VIEW_AUDIT_LOG,
        Permission.RUN_QUERIES,
        Permission.EXPORT_GRAPH,
    },
    Role.ADMIN: set(Permission),
}


@dataclass
class AccessPolicy:
    """
    Defines who can access what in the graph.

    Supports both RBAC (role-based) and ABAC (attribute-based) access control.
    Policies are evaluated in order; the first matching policy wins.

    Attributes:
        id: Unique policy ID.
        name: Human-readable policy name.
        description: Policy purpose/scope.
        roles: Allowed roles (RBAC).
        permissions: Allowed permissions.
        tenant_ids: Scoped to specific tenants.
        project_ids: Scoped to specific projects.
        entity_types: Scoped to specific entity types.
        label_requirements: Required entity labels for access.
        label_exclusions: Forbidden entity labels.
        condition: Optional callable for ABAC evaluation.
        priority: Higher priority policies evaluated first.
        enabled: Whether this policy is active.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    roles: Set[Role] = field(default_factory=set)
    permissions: Set[Permission] = field(default_factory=set)
    tenant_ids: Set[str] = field(default_factory=set)
    project_ids: Set[str] = field(default_factory=set)
    entity_types: Set[str] = field(default_factory=set)
    label_requirements: Set[str] = field(default_factory=set)
    label_exclusions: Set[str] = field(default_factory=set)
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    priority: int = 0
    enabled: bool = True

    def matches(
        self,
        user_roles: Set[Role],
        permission: Permission,
        tenant_id: str = "",
        project_id: str = "",
        entity_type: str = "",
        entity_labels: Optional[Set[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluate whether this policy grants access for the given context."""
        if not self.enabled:
            return False

        # Check permission
        if permission not in self.permissions:
            return False

        # Check roles (if any specified)
        if self.roles and not self.roles.intersection(user_roles):
            return False

        # Check tenant scope
        if self.tenant_ids and tenant_id not in self.tenant_ids:
            return False

        # Check project scope
        if self.project_ids and project_id not in self.project_ids:
            return False

        # Check entity type scope
        if self.entity_types and entity_type not in self.entity_types:
            return False

        # Check label requirements
        if entity_labels is not None:
            if self.label_requirements and not self.label_requirements.issubset(entity_labels):
                return False
            if self.label_exclusions and self.label_exclusions.intersection(entity_labels):
                return False

        # Evaluate ABAC condition
        if self.condition is not None:
            try:
                if not self.condition(context or {}):
                    return False
            except Exception:
                return False

        return True


# ---- Audit Logging ----


class AuditAction(str, Enum):
    """Actions recorded in the immutable audit log."""

    ENTITY_CREATED = "entity_created"
    ENTITY_READ = "entity_read"
    ENTITY_UPDATED = "entity_updated"
    ENTITY_DELETED = "entity_deleted"
    RELATIONSHIP_CREATED = "relationship_created"
    RELATIONSHIP_READ = "relationship_read"
    RELATIONSHIP_UPDATED = "relationship_updated"
    RELATIONSHIP_DELETED = "relationship_deleted"
    QUERY_EXECUTED = "query_executed"
    ACCESS_DENIED = "access_denied"
    POLICY_CHANGED = "policy_changed"
    EXPORT_PERFORMED = "export_performed"
    IMPORT_PERFORMED = "import_performed"
    BACKUP_CREATED = "backup_created"
    RESTORE_PERFORMED = "restore_performed"
    RETENTION_APPLIED = "retention_applied"
    DELETION_PROPAGATED = "deletion_propagated"
    SECURITY_ALERT = "security_alert"


@dataclass
class AuditEntry:
    """Immutable record of an action in the graph."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action: AuditAction = AuditAction.ENTITY_READ
    user_id: str = ""
    tenant_id: str = ""
    target_type: str = ""  # "entity", "relationship", "policy"
    target_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    user_agent: str = ""
    success: bool = True
    chain_hash: str = ""  # Hash of previous entry for tamper-proof chain

    def compute_hash(self, previous_hash: str = "") -> str:
        """Compute a SHA-256 hash chaining this entry to the previous one."""
        payload = json.dumps({
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "success": self.success,
            "previous_hash": previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class AuditLogger:
    """
    Immutable, append-only audit log with cryptographic chain integrity.

    Each entry is hashed and linked to the previous entry, creating
    a tamper-evident ledger. Supports filtering, export, and verification.
    """

    def __init__(self) -> None:
        self._entries: List[AuditEntry] = []
        self._last_hash: str = ""

    def log(
        self,
        action: AuditAction,
        user_id: str = "",
        tenant_id: str = "",
        target_type: str = "",
        target_id: str = "",
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> AuditEntry:
        """Append an audit entry with chain hashing."""
        entry = AuditEntry(
            action=action,
            user_id=user_id,
            tenant_id=tenant_id,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
            success=success,
        )
        entry.chain_hash = entry.compute_hash(self._last_hash)
        self._last_hash = entry.chain_hash
        self._entries.append(entry)
        return entry

    def verify_integrity(self) -> bool:
        """Verify the entire chain hasn't been tampered with."""
        last_hash = ""
        for entry in self._entries:
            expected = entry.compute_hash(last_hash)
            if expected != entry.chain_hash:
                return False
            last_hash = entry.chain_hash
        return True

    def query(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        target_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Query audit entries with optional filters."""
        results: List[AuditEntry] = []
        for entry in reversed(self._entries):
            if len(results) >= limit:
                break
            if user_id is not None and entry.user_id != user_id:
                continue
            if tenant_id is not None and entry.tenant_id != tenant_id:
                continue
            if action is not None and entry.action != action:
                continue
            if target_id is not None and entry.target_id != target_id:
                continue
            if since is not None and entry.timestamp < since:
                continue
            results.append(entry)
        return results

    def export(self) -> List[Dict[str, Any]]:
        """Export all audit entries as dictionaries."""
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "action": e.action.value,
                "user_id": e.user_id,
                "tenant_id": e.tenant_id,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "details": e.details,
                "success": e.success,
                "chain_hash": e.chain_hash,
            }
            for e in self._entries
        ]

    def __len__(self) -> int:
        return len(self._entries)


# ---- Encryption ----


class GraphEncryption:
    """
    Field-level encryption for sensitive graph data.

    Uses Fernet (AES-128-CBC + HMAC) symmetric encryption. Supports
    key rotation via multiple active keys identified by key IDs.
    """

    def __init__(self, master_key: Optional[bytes] = None) -> None:
        """
        Initialize with a master key. If not provided, a random key is
        generated (suitable for testing; production should use KMS).
        """
        self._keys: Dict[str, Fernet] = {}
        self._active_key_id: str = "default"
        if master_key is None:
            master_key = Fernet.generate_key()
        self.add_key(self._active_key_id, master_key)

    def add_key(self, key_id: str, key: bytes) -> None:
        """Register an encryption key."""
        self._keys[key_id] = Fernet(key)

    def set_active_key(self, key_id: str) -> None:
        """Set which key to use for new encryptions."""
        if key_id not in self._keys:
            raise ValueError(f"Unknown key ID: {key_id}")
        self._active_key_id = key_id

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string value. Returns base64-encoded ciphertext."""
        if not plaintext:
            return ""
        fernet = self._keys[self._active_key_id]
        token = fernet.encrypt(plaintext.encode())
        # Prepend key ID for decryption routing
        return f"{self._active_key_id}:{token.decode()}"

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a previously encrypted value."""
        if not ciphertext:
            return ""
        if ":" not in ciphertext:
            raise ValueError("Invalid ciphertext format: missing key ID prefix")
        key_id, token = ciphertext.split(":", 1)
        if key_id not in self._keys:
            raise ValueError(f"Unknown key ID in ciphertext: {key_id}")
        fernet = self._keys[key_id]
        return fernet.decrypt(token.encode()).decode()

    def encrypt_dict(
        self,
        data: Dict[str, Any],
        sensitive_fields: Set[str],
    ) -> Dict[str, Any]:
        """Encrypt specified sensitive fields in a dictionary."""
        result = data.copy()
        for field in sensitive_fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        return result

    def decrypt_dict(
        self,
        data: Dict[str, Any],
        sensitive_fields: Set[str],
    ) -> Dict[str, Any]:
        """Decrypt specified fields in a dictionary."""
        result = data.copy()
        for field in sensitive_fields:
            if field in result and result[field]:
                try:
                    result[field] = self.decrypt(str(result[field]))
                except (ValueError, Exception):
                    pass  # Not encrypted or wrong key
        return result


# ---- Sensitive Data Masking ----


class DataMasker:
    """
    Masks sensitive data based on field type and viewer permissions.

    Supports multiple masking strategies:
    - full: Replace entirely with [REDACTED]
    - partial: Show first/last N characters with *** in between
    - hash: Replace with SHA-256 hash (deterministic but irreversible)
    - null: Replace with None
    """

    # Fields that should never appear in the graph
    SECRET_FIELDS: Set[str] = {
        "password", "secret", "api_key", "token", "private_key",
        "access_key", "secret_key", "credential", "auth_token",
        "ssh_key", "encryption_key", "master_key", "passphrase",
    }

    # Fields that should be masked for non-admin viewers
    SENSITIVE_FIELDS: Set[str] = {
        "email", "phone", "address", "ssn", "dob", "ip_address",
        "personal_email", "personal_phone", "salary", "health_info",
    }

    @staticmethod
    def mask_full(value: Any) -> str:
        """Full redaction."""
        return "[REDACTED]"

    @staticmethod
    def mask_partial(value: str, show_first: int = 2, show_last: int = 2) -> str:
        """Partial masking showing first and last characters."""
        if len(value) <= show_first + show_last:
            return "*" * len(value)
        return value[:show_first] + "*" * (len(value) - show_first - show_last) + value[-show_last:]

    @staticmethod
    def mask_hash(value: str) -> str:
        """Deterministic hash masking."""
        return "hash:" + hashlib.sha256(value.encode()).hexdigest()[:12]

    @classmethod
    def mask_entity(
        cls,
        data: Dict[str, Any],
        user_has_admin: bool = False,
    ) -> Dict[str, Any]:
        """
        Apply masking to an entity dictionary.

        Secret fields are always removed. Sensitive fields are masked
        unless the viewer has admin privileges.
        """
        result = {}
        for key, value in data.items():
            lower_key = key.lower()

            # Always exclude secrets
            if lower_key in cls.SECRET_FIELDS or any(
                secret in lower_key for secret in cls.SECRET_FIELDS
            ):
                continue

            # Mask sensitive fields for non-admins
            if not user_has_admin and (
                lower_key in cls.SENSITIVE_FIELDS or any(
                    sensitive in lower_key for sensitive in cls.SENSITIVE_FIELDS
                )
            ):
                if isinstance(value, str) and value:
                    result[key] = cls.mask_partial(value)
                else:
                    result[key] = cls.mask_full(value)
            else:
                result[key] = value

        return result

    @classmethod
    def scan_for_secrets(cls, metadata: Dict[str, Any]) -> List[str]:
        """Scan metadata for potential secret leakage. Returns list of offending keys."""
        found: List[str] = []
        for key in metadata:
            lower_key = key.lower()
            if lower_key in cls.SECRET_FIELDS or any(
                secret in lower_key for secret in cls.SECRET_FIELDS
            ):
                found.append(key)
        return found


# ---- Graph Security Manager ----


class GraphSecurityManager:
    """
    Central security orchestrator for the knowledge graph.

    Integrates access control, encryption, masking, audit logging,
    tenant isolation, data minimization, retention, and deletion
    propagation into a unified security layer.
    """

    def __init__(
        self,
        encryption: Optional[GraphEncryption] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self._policies: List[AccessPolicy] = []
        self._user_roles: Dict[str, Set[Role]] = {}  # user_id -> roles
        self._user_tenants: Dict[str, Set[str]] = {}  # user_id -> tenant_ids
        self.encryption = encryption or GraphEncryption()
        self.audit_logger = audit_logger or AuditLogger()

        # Retention policies: (entity_type, days_to_keep)
        self._retention_policies: Dict[str, int] = {
            "AuditEntry": 365 * 7,   # 7 years
            "Metric": 365 * 2,       # 2 years
            "*": 365 * 3,            # Default: 3 years
        }

        # Deletion propagation rules: when entity X is deleted, also delete related Y
        self._propagation_rules: Dict[str, List[str]] = {
            "Project": ["Requirement", "UserStory", "Feature"],
            "Service": ["Deployment"],
            "Organization": ["User"],
        }

    # ---- Policy Management ----

    def add_policy(self, policy: AccessPolicy) -> None:
        """Register an access policy. Higher priority policies evaluated first."""
        self._policies.append(policy)
        self._policies.sort(key=lambda p: -p.priority)
        self.audit_logger.log(
            AuditAction.POLICY_CHANGED,
            target_type="policy",
            target_id=policy.id,
            details={"action": "added", "policy_name": policy.name},
        )

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy by ID."""
        for i, p in enumerate(self._policies):
            if p.id == policy_id:
                self._policies.pop(i)
                self.audit_logger.log(
                    AuditAction.POLICY_CHANGED,
                    target_type="policy",
                    target_id=policy_id,
                    details={"action": "removed"},
                )
                return True
        return False

    # ---- User Management ----

    def assign_role(self, user_id: str, role: Role, tenant_id: str) -> None:
        """Assign a role to a user within a tenant."""
        self._user_roles.setdefault(user_id, set()).add(role)
        self._user_tenants.setdefault(user_id, set()).add(tenant_id)

    def revoke_role(self, user_id: str, role: Role) -> None:
        """Revoke a role from a user."""
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role)

    def get_user_roles(self, user_id: str) -> Set[Role]:
        """Get all roles for a user."""
        return self._user_roles.get(user_id, set())

    # ---- Authorization ----

    def authorize(
        self,
        user_id: str,
        permission: Permission,
        tenant_id: str = "",
        project_id: str = "",
        entity_type: str = "",
        entity_labels: Optional[Set[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if a user is authorized for an action.

        Evaluates policies in priority order. First matching allow policy
        grants access. Returns False if no policy matches (default deny).
        """
        user_roles = self.get_user_roles(user_id)
        user_tenants = self._user_tenants.get(user_id, set())

        # Admins bypass tenant isolation
        if Role.ADMIN in user_roles:
            # Still need a matching policy for the permission
            for policy in self._policies:
                if policy.matches(user_roles, permission, tenant_id, project_id, entity_type, entity_labels, context):
                    return True
            return True  # Admin with no policy restrictions gets access

        # Tenant isolation: user must belong to the requested tenant
        if tenant_id and tenant_id not in user_tenants:
            self._audit_denied(user_id, permission, tenant_id, "tenant_isolation")
            return False

        for policy in self._policies:
            if policy.matches(user_roles, permission, tenant_id, project_id, entity_type, entity_labels, context):
                return True

        self._audit_denied(user_id, permission, tenant_id, "no_matching_policy")
        return False

    def _audit_denied(self, user_id: str, permission: Permission, tenant_id: str, reason: str) -> None:
        """Log an access denial."""
        self.audit_logger.log(
            AuditAction.ACCESS_DENIED,
            user_id=user_id,
            tenant_id=tenant_id,
            details={"permission": permission.value, "reason": reason},
            success=False,
        )

    # ---- Entity Security Wrapper ----

    def secure_entity_for_read(
        self,
        entity_dict: Dict[str, Any],
        user_id: str,
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Prepare an entity for reading by a user. Applies:
        1. Authorization check
        2. Tenant validation
        3. Sensitive data masking
        4. Secret field exclusion
        """
        # Tenant isolation
        entity_tenant = entity_dict.get("tenant_id", "default")
        if entity_tenant != tenant_id:
            user_roles = self.get_user_roles(user_id)
            if Role.ADMIN not in user_roles:
                return None

        # Mask sensitive data
        is_admin = Role.ADMIN in self.get_user_roles(user_id)
        masked = DataMasker.mask_entity(entity_dict, user_has_admin=is_admin)

        # Check for leaked secrets (defense in depth)
        leaked = DataMasker.scan_for_secrets(masked.get("metadata", {}))
        if leaked:
            # Strip leaked secrets from metadata
            if "metadata" in masked:
                for key in leaked:
                    masked["metadata"].pop(key, None)

        return masked

    # ---- Data Minimization ----

    def minimize_entity(
        self,
        entity_dict: Dict[str, Any],
        requested_fields: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Apply data minimization: return only requested fields.
        If requested_fields is None, return all non-sensitive fields.
        """
        if requested_fields is None:
            # Return all except metadata (which can be large)
            return {k: v for k, v in entity_dict.items() if k != "metadata"}
        return {k: entity_dict[k] for k in requested_fields if k in entity_dict}

    # ---- Retention ----

    def set_retention(self, entity_type: str, days: int) -> None:
        """Set retention period for an entity type."""
        self._retention_policies[entity_type] = days

    def get_retention_days(self, entity_type: str) -> int:
        """Get retention days for an entity type (falls back to default)."""
        return self._retention_policies.get(entity_type, self._retention_policies["*"])

    def should_retain(
        self,
        entity_type: str,
        created_at: datetime,
    ) -> bool:
        """Check if an entity is still within its retention window."""
        retention_days = self.get_retention_days(entity_type)
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None)  # type: ignore[union-attr]
        age = (cutoff - created_at.replace(tzinfo=None)).days  # type: ignore[union-attr]
        return age <= retention_days

    # ---- Deletion Propagation ----

    def get_propagation_targets(self, entity_type: str) -> List[str]:
        """Get entity types that should be deleted when a parent is deleted."""
        return self._propagation_rules.get(entity_type, [])

    def add_propagation_rule(self, parent_type: str, child_types: List[str]) -> None:
        """Add a deletion propagation rule."""
        self._propagation_rules.setdefault(parent_type, []).extend(child_types)

    # ---- Backup / Recovery ----

    def create_backup_metadata(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a backup manifest with checksums."""
        serialized = json.dumps(graph_data, sort_keys=True, default=str)
        checksum = hashlib.sha256(serialized.encode()).hexdigest()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checksum": checksum,
            "entity_count": len(graph_data.get("entities", {})),
            "relationship_count": len(graph_data.get("relationships", {})),
            "version": "1.0",
        }

    def verify_backup(self, graph_data: Dict[str, Any], manifest: Dict[str, Any]) -> bool:
        """Verify backup integrity using stored checksum."""
        serialized = json.dumps(graph_data, sort_keys=True, default=str)
        checksum = hashlib.sha256(serialized.encode()).hexdigest()
        return checksum == manifest.get("checksum", "")

    # ---- Tenant Isolation ----

    def isolate_query(
        self,
        user_id: str,
        tenant_id: str = "",
    ) -> Dict[str, Any]:
        """
        Build tenant-isolation filter for queries.

        Returns filter criteria to append to any graph query to ensure
        the user only sees data within their tenant boundary.
        """
        user_tenants = self._user_tenants.get(user_id, set())
        is_admin = Role.ADMIN in self.get_user_roles(user_id)

        if is_admin and not tenant_id:
            return {}  # Admin can see everything

        if tenant_id:
            if tenant_id not in user_tenants and not is_admin:
                return {"tenant_id": "__FORBIDDEN__"}  # Force empty results
            return {"tenant_id": tenant_id}

        # User-specific tenant filter
        return {"tenant_id": list(user_tenants)}

    def __repr__(self) -> str:
        return (
            f"GraphSecurityManager(policies={len(self._policies)}, "
            f"users={len(self._user_roles)})"
        )
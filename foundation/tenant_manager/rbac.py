"""
RBAC Manager - Role-Based Access Control for tenants.

Provides RBACManager for managing roles, permissions, role assignments,
and access check enforcement within tenant boundaries.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple


class AccessResult(Enum):
    """Result of an access check."""

    ALLOWED = auto()
    """Access is explicitly granted."""

    DENIED = auto()
    """Access is explicitly denied."""

    NOT_FOUND = auto()
    """The requested resource was not found."""

    INSUFFICIENT_ROLE = auto()
    """The user's role lacks the required permission."""


@dataclass
class Permission:
    """A single permission that can be granted to a role.

    Attributes:
        permission_id: Unique permission identifier.
        resource: Resource type this permission applies to.
        action: Action allowed (e.g., read, write, delete, admin).
        description: Human-readable description.
        scope: Optional scope restriction (e.g., tenant-level, workspace-level).
    """

    permission_id: str
    resource: str
    action: str
    description: str = ""
    scope: str = "*"


@dataclass
class Role:
    """A role definition with its associated permissions.

    Attributes:
        role_id: Unique role identifier.
        name: Human-readable role name (admin, editor, viewer, auditor).
        description: Role description.
        permissions: Set of permission IDs granted to this role.
        is_system_role: Whether this is a built-in system role.
        priority: Role priority for conflict resolution (higher = more authority).
        metadata: Arbitrary metadata.
    """

    role_id: str
    name: str
    description: str = ""
    permissions: Set[str] = field(default_factory=set)
    is_system_role: bool = False
    priority: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class RoleAssignment:
    """Links a user/principal to a role within a tenant scope.

    Attributes:
        assignment_id: Unique assignment identifier.
        tenant_id: Tenant scope for this assignment.
        user_id: User/principal identifier.
        role_id: Assigned role.
        assigned_at: Assignment timestamp.
        assigned_by: Who made the assignment.
        expires_at: Optional expiration for temporary assignments.
        metadata: Arbitrary metadata.
    """

    assignment_id: str
    tenant_id: str
    user_id: str
    role_id: str
    assigned_at: datetime = field(default_factory=datetime.utcnow)
    assigned_by: str = ""
    expires_at: Optional[datetime] = None
    metadata: Dict[str, str] = field(default_factory=dict)


class RBACManager:
    """Role-Based Access Control manager for tenant authorization.

    Manages roles, permissions, role assignments, and performs access
    check enforcement to determine if a principal has the required
    permissions to perform an action on a resource.

    Built-in system roles:
        - admin: Full administrative access
        - editor: Read/write access, can modify resources
        - viewer: Read-only access
        - auditor: Read access to audit logs and reports

    Attributes:
        _roles: Role definitions keyed by role_id.
        _permissions: Permission definitions keyed by permission_id.
        _assignments: Role assignments keyed by assignment_id.
        _user_assignments: User-to-assignments index.
        _tenant_assignments: Tenant-to-assignments index.
        _lock: Thread safety lock.
    """

    # Predefined permission IDs
    PERM_TENANT_READ = "tenant:read"
    PERM_TENANT_WRITE = "tenant:write"
    PERM_TENANT_DELETE = "tenant:delete"
    PERM_TENANT_ADMIN = "tenant:admin"
    PERM_WORKSPACE_READ = "workspace:read"
    PERM_WORKSPACE_WRITE = "workspace:write"
    PERM_WORKSPACE_DELETE = "workspace:delete"
    PERM_WORKSPACE_ADMIN = "workspace:admin"
    PERM_FILE_READ = "file:read"
    PERM_FILE_WRITE = "file:write"
    PERM_FILE_DELETE = "file:delete"
    PERM_BILLING_READ = "billing:read"
    PERM_BILLING_ADMIN = "billing:admin"
    PERM_USER_MANAGE = "user:manage"
    PERM_ROLE_MANAGE = "role:manage"
    PERM_AUDIT_READ = "audit:read"
    PERM_AUDIT_EXPORT = "audit:export"

    # Predefined role IDs
    ROLE_ADMIN = "admin"
    ROLE_EDITOR = "editor"
    ROLE_VIEWER = "viewer"
    ROLE_AUDITOR = "auditor"

    def __init__(self) -> None:
        """Initialize the RBAC manager with built-in roles and permissions."""
        self._roles: Dict[str, Role] = {}
        self._permissions: Dict[str, Permission] = {}
        self._assignments: Dict[str, RoleAssignment] = {}
        self._user_assignments: Dict[str, List[str]] = defaultdict(list)
        self._tenant_assignments: Dict[str, List[str]] = defaultdict(list)
        self._lock = threading.RLock()

        # Initialize built-in permissions and roles
        self._init_builtin_permissions()
        self._init_builtin_roles()

    # ------------------------------------------------------------------
    # Permission Management
    # ------------------------------------------------------------------

    def create_permission(
        self,
        permission_id: str,
        resource: str,
        action: str,
        description: str = "",
        scope: str = "*",
    ) -> Permission:
        """Define a new permission.

        Args:
            permission_id: Unique permission identifier.
            resource: Resource type (e.g., 'tenant', 'workspace', 'file').
            action: Action (e.g., 'read', 'write', 'delete', 'admin').
            description: Human-readable description.
            scope: Optional scope restriction.

        Returns:
            The created Permission.

        Raises:
            ValueError: If permission_id already exists.
        """
        with self._lock:
            if permission_id in self._permissions:
                raise ValueError(f"Permission '{permission_id}' already exists")

            permission = Permission(
                permission_id=permission_id,
                resource=resource,
                action=action,
                description=description,
                scope=scope,
            )
            self._permissions[permission_id] = permission
            return permission

    def get_permission(self, permission_id: str) -> Optional[Permission]:
        """Retrieve a permission definition.

        Args:
            permission_id: Permission identifier.

        Returns:
            Permission if found, otherwise None.
        """
        with self._lock:
            return self._permissions.get(permission_id)

    def list_permissions(self) -> List[Permission]:
        """List all defined permissions.

        Returns:
            List of all permissions.
        """
        with self._lock:
            return list(self._permissions.values())

    def delete_permission(self, permission_id: str) -> bool:
        """Remove a permission definition.

        Also removes the permission from all roles that reference it.

        Args:
            permission_id: Permission to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._lock:
            if permission_id not in self._permissions:
                return False

            del self._permissions[permission_id]

            # Remove from all roles
            for role in self._roles.values():
                role.permissions.discard(permission_id)

            return True

    # ------------------------------------------------------------------
    # Role Management
    # ------------------------------------------------------------------

    def create_role(
        self,
        role_id: str,
        name: str,
        description: str = "",
        permissions: Optional[Set[str]] = None,
        priority: int = 0,
        is_system_role: bool = False,
    ) -> Role:
        """Define a new role.

        Args:
            role_id: Unique role identifier.
            name: Human-readable role name.
            description: Role description.
            permissions: Set of permission IDs to grant.
            priority: Priority for conflict resolution.
            is_system_role: Whether this is a built-in role.

        Returns:
            The created Role.

        Raises:
            ValueError: If role_id already exists or permissions are invalid.
        """
        with self._lock:
            if role_id in self._roles:
                raise ValueError(f"Role '{role_id}' already exists")

            # Validate permissions exist
            perm_set = permissions or set()
            invalid_perms = perm_set - set(self._permissions.keys())
            if invalid_perms:
                raise ValueError(f"Unknown permissions: {invalid_perms}")

            role = Role(
                role_id=role_id,
                name=name,
                description=description,
                permissions=perm_set,
                priority=priority,
                is_system_role=is_system_role,
            )
            self._roles[role_id] = role
            return role

    def get_role(self, role_id: str) -> Optional[Role]:
        """Retrieve a role definition.

        Args:
            role_id: Role identifier.

        Returns:
            Role if found, otherwise None.
        """
        with self._lock:
            return self._roles.get(role_id)

    def list_roles(self) -> List[Role]:
        """List all defined roles.

        Returns:
            List of all roles.
        """
        with self._lock:
            return list(self._roles.values())

    def update_role_permissions(
        self, role_id: str, add_permissions: Optional[Set[str]] = None,
        remove_permissions: Optional[Set[str]] = None,
    ) -> Optional[Role]:
        """Add or remove permissions from a role.

        Args:
            role_id: Role to update.
            add_permissions: Permissions to grant.
            remove_permissions: Permissions to revoke.

        Returns:
            Updated Role, or None if not found.
        """
        with self._lock:
            role = self._roles.get(role_id)
            if role is None:
                return None

            if role.is_system_role:
                raise ValueError(f"Cannot modify system role '{role_id}'")

            if add_permissions:
                # Validate
                invalid = add_permissions - set(self._permissions.keys())
                if invalid:
                    raise ValueError(f"Unknown permissions: {invalid}")
                role.permissions.update(add_permissions)

            if remove_permissions:
                role.permissions.difference_update(remove_permissions)

            return role

    def delete_role(self, role_id: str) -> bool:
        """Delete a role definition.

        Also removes all assignments of this role.

        Args:
            role_id: Role to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            ValueError: If attempting to delete a system role.
        """
        with self._lock:
            role = self._roles.get(role_id)
            if role is None:
                return False

            if role.is_system_role:
                raise ValueError(f"Cannot delete system role '{role_id}'")

            # Remove assignments
            to_remove = [
                aid for aid, a in self._assignments.items() if a.role_id == role_id
            ]
            for aid in to_remove:
                self._remove_assignment_internal(aid)

            del self._roles[role_id]
            return True

    # ------------------------------------------------------------------
    # Role Assignment
    # ------------------------------------------------------------------

    def assign_role(
        self,
        tenant_id: str,
        user_id: str,
        role_id: str,
        assigned_by: str = "",
        expires_at: Optional[datetime] = None,
    ) -> Optional[RoleAssignment]:
        """Assign a role to a user within a tenant scope.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.
            role_id: Role to assign.
            assigned_by: Who is making this assignment.
            expires_at: Optional expiration time.

        Returns:
            The RoleAssignment, or None if role not found.

        Raises:
            ValueError: If role_id does not exist.
        """
        with self._lock:
            if role_id not in self._roles:
                raise ValueError(f"Role '{role_id}' not found")

            assignment_id = f"asgn_{tenant_id}_{user_id}_{role_id}_{id(self)}"

            # Remove existing assignment of this role to this user in this tenant
            existing = self._find_assignment(tenant_id, user_id, role_id)
            if existing:
                self._remove_assignment_internal(existing)

            assignment = RoleAssignment(
                assignment_id=assignment_id,
                tenant_id=tenant_id,
                user_id=user_id,
                role_id=role_id,
                assigned_by=assigned_by,
                expires_at=expires_at,
            )

            self._assignments[assignment_id] = assignment
            self._user_assignments[user_id].append(assignment_id)
            self._tenant_assignments[tenant_id].append(assignment_id)

            return assignment

    def revoke_role(
        self, tenant_id: str, user_id: str, role_id: str
    ) -> bool:
        """Revoke a specific role assignment.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.
            role_id: Role to revoke.

        Returns:
            True if an assignment was revoked, False if none found.
        """
        with self._lock:
            assignment_id = self._find_assignment(tenant_id, user_id, role_id)
            if assignment_id is None:
                return False
            self._remove_assignment_internal(assignment_id)
            return True

    def revoke_all_roles(self, tenant_id: str, user_id: str) -> int:
        """Revoke all role assignments for a user in a tenant.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.

        Returns:
            Number of assignments revoked.
        """
        with self._lock:
            to_remove = [
                aid
                for aid in self._user_assignments.get(user_id, [])
                if aid in self._assignments
                and self._assignments[aid].tenant_id == tenant_id
            ]
            for aid in to_remove:
                self._remove_assignment_internal(aid)
            return len(to_remove)

    def get_user_roles(
        self, tenant_id: str, user_id: str
    ) -> List[Role]:
        """Get all roles assigned to a user within a tenant.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.

        Returns:
            List of assigned Role objects (empty if none).
        """
        with self._lock:
            roles: List[Role] = []
            now = datetime.utcnow()

            for aid in self._user_assignments.get(user_id, []):
                assignment = self._assignments.get(aid)
                if assignment is None:
                    continue
                if assignment.tenant_id != tenant_id:
                    continue
                # Check expiration
                if assignment.expires_at and assignment.expires_at < now:
                    continue
                role = self._roles.get(assignment.role_id)
                if role:
                    roles.append(role)

            # Sort by priority descending
            roles.sort(key=lambda r: r.priority, reverse=True)
            return roles

    def get_user_assignments(
        self, tenant_id: str, user_id: str
    ) -> List[RoleAssignment]:
        """Get all role assignments for a user in a tenant.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.

        Returns:
            List of RoleAssignment objects.
        """
        with self._lock:
            now = datetime.utcnow()
            return [
                self._assignments[aid]
                for aid in self._user_assignments.get(user_id, [])
                if aid in self._assignments
                and self._assignments[aid].tenant_id == tenant_id
                and (
                    self._assignments[aid].expires_at is None
                    or self._assignments[aid].expires_at >= now
                )
            ]

    def get_tenant_users(self, tenant_id: str) -> Set[str]:
        """Get all users with any role in a tenant.

        Args:
            tenant_id: Tenant scope.

        Returns:
            Set of user IDs.
        """
        with self._lock:
            users: Set[str] = set()
            for aid in self._tenant_assignments.get(tenant_id, []):
                assignment = self._assignments.get(aid)
                if assignment:
                    users.add(assignment.user_id)
            return users

    # ------------------------------------------------------------------
    # Access Check Enforcement
    # ------------------------------------------------------------------

    def check_access(
        self,
        tenant_id: str,
        user_id: str,
        permission_id: str,
        resource_id: Optional[str] = None,
    ) -> AccessResult:
        """Check if a user has a specific permission within a tenant.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.
            permission_id: Required permission.
            resource_id: Optional specific resource being accessed.

        Returns:
            AccessResult indicating ALLOWED, DENIED, or error status.
        """
        with self._lock:
            # Verify permission exists
            permission = self._permissions.get(permission_id)
            if permission is None:
                return AccessResult.NOT_FOUND

            # Get user's roles
            roles = self.get_user_roles(tenant_id, user_id)

            if not roles:
                return AccessResult.INSUFFICIENT_ROLE

            # Check if any role has the required permission
            for role in roles:
                if permission_id in role.permissions:
                    return AccessResult.ALLOWED

                # Check for wildcard/admin permissions
                # e.g., "tenant:*" grants all tenant permissions
                resource_wildcard = f"{permission.resource}:*"
                if resource_wildcard in role.permissions:
                    return AccessResult.ALLOWED

                # Global admin
                if "*:*" in role.permissions or "*" in role.permissions:
                    return AccessResult.ALLOWED

            return AccessResult.DENIED

    def check_access_bulk(
        self,
        tenant_id: str,
        user_id: str,
        permission_ids: List[str],
    ) -> Dict[str, AccessResult]:
        """Check multiple permissions at once.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.
            permission_ids: List of permissions to check.

        Returns:
            Dictionary mapping permission_id to AccessResult.
        """
        return {
            perm_id: self.check_access(tenant_id, user_id, perm_id)
            for perm_id in permission_ids
        }

    def has_role(
        self, tenant_id: str, user_id: str, role_name: str
    ) -> bool:
        """Check if a user has a specific role by name.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.
            role_name: Role name to check (e.g., 'admin', 'editor').

        Returns:
            True if the user has the role.
        """
        roles = self.get_user_roles(tenant_id, user_id)
        return any(r.name.lower() == role_name.lower() for r in roles)

    def is_admin(self, tenant_id: str, user_id: str) -> bool:
        """Check if a user has admin privileges in a tenant.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.

        Returns:
            True if the user is an admin.
        """
        return self.has_role(tenant_id, user_id, "admin")

    def get_effective_permissions(
        self, tenant_id: str, user_id: str
    ) -> Set[str]:
        """Get all effective permissions for a user in a tenant.

        Combines permissions from all assigned roles.

        Args:
            tenant_id: Tenant scope.
            user_id: User/principal identifier.

        Returns:
            Set of all permission IDs the user has.
        """
        roles = self.get_user_roles(tenant_id, user_id)
        effective: Set[str] = set()
        for role in roles:
            effective.update(role.permissions)
        return effective

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _init_builtin_permissions(self) -> None:
        """Initialize the standard permission set."""
        builtin_perms = [
            ("tenant:read", "tenant", "read", "View tenant information"),
            ("tenant:write", "tenant", "write", "Modify tenant settings"),
            ("tenant:delete", "tenant", "delete", "Delete a tenant"),
            ("tenant:admin", "tenant", "admin", "Full tenant administration"),
            ("workspace:read", "workspace", "read", "View workspaces"),
            ("workspace:write", "workspace", "write", "Create and modify workspaces"),
            ("workspace:delete", "workspace", "delete", "Delete workspaces"),
            ("workspace:admin", "workspace", "admin", "Full workspace administration"),
            ("file:read", "file", "read", "Read files"),
            ("file:write", "file", "write", "Upload and modify files"),
            ("file:delete", "file", "delete", "Delete files"),
            ("billing:read", "billing", "read", "View billing information"),
            ("billing:admin", "billing", "admin", "Manage billing settings"),
            ("user:manage", "user", "manage", "Manage users and roles"),
            ("role:manage", "role", "manage", "Manage role definitions"),
            ("audit:read", "audit", "read", "Read audit logs"),
            ("audit:export", "audit", "export", "Export audit logs"),
        ]

        for perm_id, resource, action, desc in builtin_perms:
            self._permissions[perm_id] = Permission(
                permission_id=perm_id,
                resource=resource,
                action=action,
                description=desc,
            )

    def _init_builtin_roles(self) -> None:
        """Initialize the standard system roles."""
        # Admin: Full access
        self._roles[self.ROLE_ADMIN] = Role(
            role_id=self.ROLE_ADMIN,
            name="admin",
            description="Full administrative access to all resources",
            permissions={
                "tenant:read", "tenant:write", "tenant:delete", "tenant:admin",
                "workspace:read", "workspace:write", "workspace:delete", "workspace:admin",
                "file:read", "file:write", "file:delete",
                "billing:read", "billing:admin",
                "user:manage", "role:manage",
                "audit:read", "audit:export",
            },
            is_system_role=True,
            priority=100,
        )

        # Editor: Read/write but no admin/delete
        self._roles[self.ROLE_EDITOR] = Role(
            role_id=self.ROLE_EDITOR,
            name="editor",
            description="Can read and modify resources but not administer",
            permissions={
                "tenant:read", "tenant:write",
                "workspace:read", "workspace:write",
                "file:read", "file:write",
                "billing:read",
                "audit:read",
            },
            is_system_role=True,
            priority=50,
        )

        # Viewer: Read-only
        self._roles[self.ROLE_VIEWER] = Role(
            role_id=self.ROLE_VIEWER,
            name="viewer",
            description="Read-only access to resources",
            permissions={
                "tenant:read",
                "workspace:read",
                "file:read",
            },
            is_system_role=True,
            priority=10,
        )

        # Auditor: Audit and billing read access
        self._roles[self.ROLE_AUDITOR] = Role(
            role_id=self.ROLE_AUDITOR,
            name="auditor",
            description="Access to audit logs and billing reports",
            permissions={
                "tenant:read",
                "billing:read",
                "audit:read", "audit:export",
            },
            is_system_role=True,
            priority=20,
        )

    def _find_assignment(
        self, tenant_id: str, user_id: str, role_id: str
    ) -> Optional[str]:
        """Find an existing assignment ID.

        Args:
            tenant_id: Tenant scope.
            user_id: User identifier.
            role_id: Role identifier.

        Returns:
            Assignment ID if found, otherwise None.
        """
        for aid in self._user_assignments.get(user_id, []):
            a = self._assignments.get(aid)
            if a and a.tenant_id == tenant_id and a.role_id == role_id:
                return aid
        return None

    def _remove_assignment_internal(self, assignment_id: str) -> None:
        """Remove an assignment and clean up indexes (caller must hold lock).

        Args:
            assignment_id: Assignment to remove.
        """
        assignment = self._assignments.pop(assignment_id, None)
        if assignment is None:
            return

        user_id = assignment.user_id
        tenant_id = assignment.tenant_id

        if user_id in self._user_assignments:
            self._user_assignments[user_id] = [
                a for a in self._user_assignments[user_id] if a != assignment_id
            ]
            if not self._user_assignments[user_id]:
                del self._user_assignments[user_id]

        if tenant_id in self._tenant_assignments:
            self._tenant_assignments[tenant_id] = [
                a for a in self._tenant_assignments[tenant_id] if a != assignment_id
            ]

    def cleanup(self) -> None:
        """Reset the RBAC manager, clearing all custom state.

        Preserves built-in permissions and roles.
        """
        with self._lock:
            self._assignments.clear()
            self._user_assignments.clear()
            self._tenant_assignments.clear()

            # Remove non-system roles
            custom_roles = [
                rid for rid, r in self._roles.items() if not r.is_system_role
            ]
            for rid in custom_roles:
                del self._roles[rid]

            # Remove non-builtin permissions
            builtin_ids = {
                "tenant:read", "tenant:write", "tenant:delete", "tenant:admin",
                "workspace:read", "workspace:write", "workspace:delete", "workspace:admin",
                "file:read", "file:write", "file:delete",
                "billing:read", "billing:admin",
                "user:manage", "role:manage",
                "audit:read", "audit:export",
            }
            custom_perms = [
                pid for pid in self._permissions if pid not in builtin_ids
            ]
            for pid in custom_perms:
                del self._permissions[pid]
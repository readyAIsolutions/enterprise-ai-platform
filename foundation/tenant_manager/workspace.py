"""
Workspace Manager - Per-tenant workspace management.

Provides WorkspaceManager for managing workspaces within tenant boundaries,
including workspace templates, lifecycle operations (create, archive, delete),
and tenant-scoped file storage.
"""

from __future__ import annotations

import copy
import os
import shutil
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple


class WorkspaceStatus(Enum):
    """Lifecycle states of a workspace."""

    ACTIVE = auto()
    """Workspace is fully operational."""

    CREATING = auto()
    """Workspace is being provisioned."""

    ARCHIVED = auto()
    """Workspace is read-only, pending deletion or restoration."""

    DELETED = auto()
    """Workspace has been soft-deleted."""

    PURGED = auto()
    """Workspace has been permanently removed."""


@dataclass
class WorkspaceTemplate:
    """Blueprint for creating consistent workspaces.

    Attributes:
        template_id: Unique template identifier.
        name: Human-readable template name.
        description: Description of the template's purpose.
        base_config: Default configuration applied to new workspaces.
        file_structure: Preset directory/file structure.
        features: Enabled feature flags for workspaces from this template.
        metadata: Arbitrary metadata tags.
    """

    template_id: str
    name: str
    description: str = ""
    base_config: Dict[str, Any] = field(default_factory=dict)
    file_structure: Dict[str, Any] = field(default_factory=dict)
    features: Set[str] = field(default_factory=set)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class WorkspaceFile:
    """Represents a file stored within a workspace.

    Attributes:
        file_id: Unique file identifier.
        filename: Original filename.
        path: Virtual path within the workspace.
        size_bytes: File size in bytes.
        mime_type: MIME type of the file.
        created_at: Upload timestamp.
        metadata: Arbitrary metadata.
    """

    file_id: str
    filename: str
    path: str
    size_bytes: int = 0
    mime_type: str = "application/octet-stream"
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Workspace:
    """Represents a tenant workspace.

    Attributes:
        workspace_id: Unique workspace identifier.
        tenant_id: Owning tenant.
        name: Human-readable workspace name.
        status: Current lifecycle status.
        template: Optional template used to create this workspace.
        config: Workspace-specific configuration.
        files: List of files stored in this workspace.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
        archived_at: When the workspace was archived (if applicable).
        metadata: Arbitrary metadata.
    """

    workspace_id: str
    tenant_id: str
    name: str
    status: WorkspaceStatus = WorkspaceStatus.CREATING
    template: Optional[WorkspaceTemplate] = None
    config: Dict[str, Any] = field(default_factory=dict)
    files: List[WorkspaceFile] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    archived_at: Optional[datetime] = None
    metadata: Dict[str, str] = field(default_factory=dict)


class WorkspaceManager:
    """Manages per-tenant workspace lifecycle and file storage.

    Provides APIs for:
    - Creating, archiving, and deleting workspaces
    - Workspace template management
    - Tenant-scoped file storage within workspaces
    - Workspace search and filtering

    Attributes:
        _workspaces: Registry of all workspaces.
        _templates: Available workspace templates.
        _tenant_workspaces: Index of workspaces per tenant.
        _lock: Thread safety lock.
    """

    def __init__(self, base_storage_path: str = "/tmp/tenant_workspaces") -> None:
        """Initialize the workspace manager.

        Args:
            base_storage_path: Filesystem root for workspace file storage.
                               In production, this would be a cloud storage path.
        """
        self._workspaces: Dict[str, Workspace] = {}
        self._templates: Dict[str, WorkspaceTemplate] = {}
        self._tenant_workspaces: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._base_storage_path = base_storage_path

    # ------------------------------------------------------------------
    # Workspace Lifecycle
    # ------------------------------------------------------------------

    def create_workspace(
        self,
        tenant_id: str,
        name: str,
        template_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Workspace:
        """Create a new workspace for a tenant.

        Args:
            tenant_id: Owning tenant.
            name: Human-readable workspace name.
            template_id: Optional template to initialize from.
            config: Custom configuration overrides.
            metadata: Arbitrary metadata tags.

        Returns:
            The newly created Workspace.

        Raises:
            ValueError: If name is empty or template not found.
        """
        if not name.strip():
            raise ValueError("Workspace name cannot be empty")

        with self._lock:
            workspace_id = self._generate_workspace_id()

            template = None
            merged_config: Dict[str, Any] = {}

            if template_id is not None:
                template = self._templates.get(template_id)
                if template is None:
                    raise ValueError(f"Template '{template_id}' not found")
                merged_config = copy.deepcopy(template.base_config)

            if config:
                merged_config.update(config)

            workspace = Workspace(
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                name=name,
                status=WorkspaceStatus.CREATING,
                template=template,
                config=merged_config,
                metadata=metadata or {},
            )

            # Apply template file structure if available
            if template and template.file_structure:
                self._apply_file_structure(workspace, template.file_structure)

            self._workspaces[workspace_id] = workspace
            self._tenant_workspaces[tenant_id].add(workspace_id)

            # Ensure storage directory exists
            workspace_path = self._get_workspace_path(workspace_id)
            os.makedirs(workspace_path, exist_ok=True)

            # Transition to ACTIVE
            workspace.status = WorkspaceStatus.ACTIVE
            workspace.updated_at = datetime.utcnow()

            return workspace

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Retrieve a workspace by ID.

        Args:
            workspace_id: The workspace identifier.

        Returns:
            Workspace if found, otherwise None.
        """
        with self._lock:
            return self._workspaces.get(workspace_id)

    def archive_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Archive a workspace (soft-delete, retaining data).

        Archived workspaces are read-only but data is preserved.

        Args:
            workspace_id: The workspace to archive.

        Returns:
            Archived Workspace, or None if not found.

        Raises:
            ValueError: If workspace is not in ACTIVE status.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return None

            if workspace.status != WorkspaceStatus.ACTIVE:
                raise ValueError(
                    f"Cannot archive workspace in {workspace.status.name} status"
                )

            workspace.status = WorkspaceStatus.ARCHIVED
            workspace.archived_at = datetime.utcnow()
            workspace.updated_at = datetime.utcnow()

            return workspace

    def restore_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Restore an archived workspace back to ACTIVE.

        Args:
            workspace_id: The workspace to restore.

        Returns:
            Restored Workspace, or None if not found.

        Raises:
            ValueError: If workspace is not in ARCHIVED status.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return None

            if workspace.status != WorkspaceStatus.ARCHIVED:
                raise ValueError(
                    f"Cannot restore workspace in {workspace.status.name} status"
                )

            workspace.status = WorkspaceStatus.ACTIVE
            workspace.archived_at = None
            workspace.updated_at = datetime.utcnow()

            return workspace

    def delete_workspace(self, workspace_id: str, hard: bool = False) -> bool:
        """Delete a workspace.

        Args:
            workspace_id: The workspace to delete.
            hard: If True, permanently purge workspace and files.
                  If False, soft-delete (status = DELETED).

        Returns:
            True if deleted, False if not found.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return False

            if hard:
                # Remove files from disk
                workspace_path = self._get_workspace_path(workspace_id)
                if os.path.exists(workspace_path):
                    shutil.rmtree(workspace_path, ignore_errors=True)

                # Remove from registries
                tenant_id = workspace.tenant_id
                self._tenant_workspaces.get(tenant_id, set()).discard(workspace_id)
                del self._workspaces[workspace_id]
            else:
                workspace.status = WorkspaceStatus.DELETED
                workspace.updated_at = datetime.utcnow()

            return True

    def purge_deleted(self, older_than_days: int = 30) -> int:
        """Permanently remove workspaces that have been soft-deleted
        for longer than the specified number of days.

        Args:
            older_than_days: Minimum age in days for purge eligibility.

        Returns:
            Number of workspaces purged.
        """
        cutoff = datetime.utcnow()
        purged = 0

        with self._lock:
            to_purge: List[str] = []
            for ws_id, ws in self._workspaces.items():
                if ws.status == WorkspaceStatus.DELETED:
                    age = (cutoff - ws.updated_at).days
                    if age >= older_than_days:
                        to_purge.append(ws_id)

            for ws_id in to_purge:
                self.delete_workspace(ws_id, hard=True)
                purged += 1

        return purged

    def list_workspaces(
        self,
        tenant_id: Optional[str] = None,
        status_filter: Optional[WorkspaceStatus] = None,
    ) -> List[Workspace]:
        """List workspaces, optionally filtered by tenant and status.

        Args:
            tenant_id: Filter by owning tenant.
            status_filter: Filter by workspace status.

        Returns:
            List of matching workspaces.
        """
        with self._lock:
            if tenant_id is not None:
                workspace_ids = self._tenant_workspaces.get(tenant_id, set())
                workspaces = [
                    self._workspaces[ws_id]
                    for ws_id in workspace_ids
                    if ws_id in self._workspaces
                ]
            else:
                workspaces = list(self._workspaces.values())

            if status_filter is not None:
                workspaces = [w for w in workspaces if w.status == status_filter]

            return workspaces

    def get_tenant_workspace_count(self, tenant_id: str) -> int:
        """Get the number of non-deleted workspaces for a tenant.

        Args:
            tenant_id: The tenant.

        Returns:
            Count of active/archived workspaces.
        """
        with self._lock:
            count = 0
            for ws_id in self._tenant_workspaces.get(tenant_id, set()):
                ws = self._workspaces.get(ws_id)
                if ws and ws.status not in (WorkspaceStatus.DELETED, WorkspaceStatus.PURGED):
                    count += 1
            return count

    # ------------------------------------------------------------------
    # Workspace Templates
    # ------------------------------------------------------------------

    def create_template(
        self,
        name: str,
        description: str = "",
        base_config: Optional[Dict[str, Any]] = None,
        file_structure: Optional[Dict[str, Any]] = None,
        features: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> WorkspaceTemplate:
        """Create a reusable workspace template.

        Args:
            name: Template name.
            description: Template description.
            base_config: Default workspace configuration.
            file_structure: Preset directory and file structure.
            features: Default feature flags.
            metadata: Arbitrary metadata.

        Returns:
            The new WorkspaceTemplate.
        """
        template_id = f"tmpl_{uuid.uuid4().hex[:12]}"
        template = WorkspaceTemplate(
            template_id=template_id,
            name=name,
            description=description,
            base_config=base_config or {},
            file_structure=file_structure or {},
            features=features or set(),
            metadata=metadata or {},
        )

        with self._lock:
            self._templates[template_id] = template

        return template

    def get_template(self, template_id: str) -> Optional[WorkspaceTemplate]:
        """Retrieve a workspace template by ID.

        Args:
            template_id: Template identifier.

        Returns:
            WorkspaceTemplate if found, otherwise None.
        """
        with self._lock:
            return self._templates.get(template_id)

    def list_templates(self) -> List[WorkspaceTemplate]:
        """List all available workspace templates.

        Returns:
            List of all templates.
        """
        with self._lock:
            return list(self._templates.values())

    def delete_template(self, template_id: str) -> bool:
        """Delete a workspace template.

        Existing workspaces created from this template are unaffected.

        Args:
            template_id: Template to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._lock:
            if template_id not in self._templates:
                return False
            del self._templates[template_id]
            return True

    # ------------------------------------------------------------------
    # File Storage
    # ------------------------------------------------------------------

    def store_file(
        self,
        workspace_id: str,
        filename: str,
        content: bytes,
        path: str = "/",
        mime_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[WorkspaceFile]:
        """Store a file within a workspace.

        Args:
            workspace_id: Target workspace.
            filename: Original filename.
            content: File content as bytes.
            path: Virtual path within the workspace.
            mime_type: MIME type of the file.
            metadata: Arbitrary file metadata.

        Returns:
            WorkspaceFile record, or None if workspace not found/inactive.

        Raises:
            ValueError: If workspace is not ACTIVE.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return None

            if workspace.status != WorkspaceStatus.ACTIVE:
                raise ValueError(
                    f"Cannot store files in {workspace.status.name} workspace"
                )

            file_id = f"f_{uuid.uuid4().hex[:16]}"
            workspace_file = WorkspaceFile(
                file_id=file_id,
                filename=filename,
                path=path.rstrip("/") + "/" + filename,
                size_bytes=len(content),
                mime_type=mime_type,
                metadata=metadata or {},
            )

            # Write to disk
            fs_path = self._get_workspace_path(workspace_id)
            os.makedirs(fs_path, exist_ok=True)
            file_path = os.path.join(fs_path, file_id)
            with open(file_path, "wb") as f:
                f.write(content)

            workspace.files.append(workspace_file)
            workspace.updated_at = datetime.utcnow()

            return workspace_file

    def get_file(
        self, workspace_id: str, file_id: str
    ) -> Tuple[Optional[bytes], Optional[WorkspaceFile]]:
        """Retrieve a file from a workspace.

        Args:
            workspace_id: Workspace containing the file.
            file_id: File identifier.

        Returns:
            Tuple of (file_content_bytes, file_metadata). Both None if not found.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return None, None

            file_meta = None
            for f in workspace.files:
                if f.file_id == file_id:
                    file_meta = f
                    break

            if file_meta is None:
                return None, None

            fs_path = os.path.join(self._get_workspace_path(workspace_id), file_id)
            if not os.path.exists(fs_path):
                return None, file_meta

            with open(fs_path, "rb") as f:
                content = f.read()

            return content, file_meta

    def delete_file(self, workspace_id: str, file_id: str) -> bool:
        """Delete a file from a workspace.

        Args:
            workspace_id: Workspace containing the file.
            file_id: File to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return False

            for i, f in enumerate(workspace.files):
                if f.file_id == file_id:
                    workspace.files.pop(i)
                    workspace.updated_at = datetime.utcnow()

                    # Remove from disk
                    fs_path = os.path.join(
                        self._get_workspace_path(workspace_id), file_id
                    )
                    if os.path.exists(fs_path):
                        os.remove(fs_path)

                    return True

            return False

    def list_files(
        self,
        workspace_id: str,
        path_prefix: Optional[str] = None,
    ) -> List[WorkspaceFile]:
        """List files stored in a workspace.

        Args:
            workspace_id: Target workspace.
            path_prefix: Optional path filter.

        Returns:
            List of workspace files.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return []

            if path_prefix is None:
                return list(workspace.files)

            return [f for f in workspace.files if f.path.startswith(path_prefix)]

    def get_storage_usage(self, workspace_id: str) -> int:
        """Get total storage used by a workspace in bytes.

        Args:
            workspace_id: Target workspace.

        Returns:
            Total bytes used.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return 0
            return sum(f.size_bytes for f in workspace.files)

    def get_tenant_storage_usage(self, tenant_id: str) -> int:
        """Get total storage used across all workspaces for a tenant.

        Args:
            tenant_id: The tenant.

        Returns:
            Total bytes used.
        """
        with self._lock:
            total = 0
            for ws_id in self._tenant_workspaces.get(tenant_id, set()):
                total += self.get_storage_usage(ws_id)
            return total

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def update_workspace_config(
        self, workspace_id: str, config: Dict[str, Any]
    ) -> Optional[Workspace]:
        """Update configuration for a workspace (merges with existing).

        Args:
            workspace_id: Target workspace.
            config: Configuration key-value pairs to merge.

        Returns:
            Updated workspace, or None if not found.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return None
            workspace.config.update(config)
            workspace.updated_at = datetime.utcnow()
            return workspace

    def get_workspace_config(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get the full configuration for a workspace.

        Args:
            workspace_id: Target workspace.

        Returns:
            Configuration dict copy, or None if not found.
        """
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                return None
            return copy.deepcopy(workspace.config)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_workspace_id() -> str:
        """Generate a unique workspace identifier."""
        return f"ws_{uuid.uuid4().hex[:16]}"

    def _get_workspace_path(self, workspace_id: str) -> str:
        """Get the filesystem path for workspace files.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            Absolute filesystem path.
        """
        return os.path.join(self._base_storage_path, workspace_id)

    def _apply_file_structure(
        self, workspace: Workspace, structure: Dict[str, Any]
    ) -> None:
        """Apply a template file structure to a workspace.

        Creates directories and placeholder files as defined in the template.

        Args:
            workspace: Target workspace.
            structure: File structure definition from template.
        """
        ws_path = self._get_workspace_path(workspace.workspace_id)
        os.makedirs(ws_path, exist_ok=True)

        def _create_structure(base_path: str, struct: Dict[str, Any]) -> None:
            for name, content in struct.items():
                full_path = os.path.join(base_path, name)
                if isinstance(content, dict):
                    os.makedirs(full_path, exist_ok=True)
                    _create_structure(full_path, content)
                elif isinstance(content, str):
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w") as f:
                        f.write(content)

        _create_structure(ws_path, structure)

    def cleanup(self) -> None:
        """Reset the workspace manager, clearing all state."""
        with self._lock:
            self._workspaces.clear()
            self._templates.clear()
            self._tenant_workspaces.clear()

        # Optionally clean up disk storage
        if os.path.exists(self._base_storage_path):
            shutil.rmtree(self._base_storage_path, ignore_errors=True)
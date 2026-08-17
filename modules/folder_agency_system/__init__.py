"""folder_agency_system — a folder/org-structure system that organizes an AI
startup's work as an on-disk folder hierarchy of capabilities, projects, and
agents, with immutable version-one templates, deployable workbenches, stable
Atlas facts, and one good librarian agent querying the library.

Grounded in JEVanClief's "Your Start Up is going to be Replaced by a Folder."
(https://www.youtube.com/watch?v=XIk-Ru85xmA)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .folder_agency_system import (  # noqa: F401
    CARD_FILE,
    FolderAgency,
    FolderAgencyError,
    FolderKind,
    FolderNode,
)

logger = logging.getLogger("eni.folder_agency_system_module")
__version__ = "1.0.0"


def create_folder_agency(
    root: Path,
    config: Optional[Dict[str, Any]] = None,
) -> FolderAgency:
    """Facade: construct and return a FolderAgency rooted at ``root``."""
    _ = config or {}
    return FolderAgency(root=root)


@module(
    name="folder_agency_system",
    version="1.0.0",
    config_defaults={"root_dir": None},
)
class FolderAgencySystemModule(Module):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.agency: Optional[FolderAgency] = None
        self._event_bus = None

    async def initialize(self) -> None:
        try:
            root = self.config.get("root_dir")
            root_path = Path(root) if root else Path.cwd() / ".folder_agency"
            self.agency = create_folder_agency(root_path, self.config)
            self.agency.scaffold()
            self._status = HealthStatus.HEALTHY
        except Exception:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    def set_event_bus(self, event_bus: Any) -> None:
        """Attach the platform event bus; events are only emitted when present."""
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    # ── facade methods delegating to the agency ─────────────────────────────
    def create_capability(self, name: str, description: str = "") -> FolderNode:
        node = self.agency.create_capability(name, description)
        self._publish("folder_agency.capability_created", {"name": node.name, "kind": node.kind.value})
        return node

    def create_project(self, name: str, description: str = "") -> FolderNode:
        node = self.agency.create_project(name, description)
        self._publish("folder_agency.project_created", {"name": node.name, "kind": node.kind.value})
        return node

    def create_agent(self, name: str, role: str = "") -> FolderNode:
        node = self.agency.create_agent(name, role)
        self._publish("folder_agency.agent_created", {"name": node.name, "kind": node.kind.value})
        return node

    def import_template(self, name: str, description: str = "") -> FolderNode:
        node = self.agency.import_template(name, description)
        self._publish("folder_agency.template_imported", {"name": node.name})
        return node

    def create_workbench(self, template: str, name: str) -> FolderNode:
        node = self.agency.create_workbench(template, name)
        self._publish("folder_agency.workbench_deployed", {"name": node.name, "template": template})
        return node

    def create_atlas(self, name: str, facts: Optional[Dict[str, Any]] = None) -> FolderNode:
        node = self.agency.create_atlas(name, facts)
        self._publish("folder_agency.atlas_created", {"name": node.name})
        return node

    def read_atlas(self, name: str) -> Dict[str, Any]:
        return self.agency.read_atlas(name)

    def librarian_query(self, needle: str) -> List[FolderNode]:
        return self.agency.librarian_query(needle)

    def render_tree(self) -> str:
        return self.agency.render_tree()

    def manifest(self) -> Dict[str, Any]:
        return self.agency.manifest()


def create_folder_agency_system_module(
    config: Optional[Dict[str, Any]] = None,
) -> FolderAgencySystemModule:
    return FolderAgencySystemModule(config=config or {})


__all__ = [
    "CARD_FILE",
    "FolderAgency",
    "FolderAgencyError",
    "FolderAgencySystemModule",
    "FolderKind",
    "FolderNode",
    "create_folder_agency",
    "create_folder_agency_system_module",
    "__version__",
]

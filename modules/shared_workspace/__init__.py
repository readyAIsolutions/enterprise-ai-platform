"""Shared Workspace module — live multi-editor collaboration (from transcript).

Implements the shared, live, versioned workspace described in the pulled
"Multiplayer AI" transcript: concurrent multi-editor writes with lock + merge
safety, an append-only queryable session history, and siloed/redact-before-share
handling for private values.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .workspace import (  # noqa: F401
    SharedWorkspace, WorkspaceFile, anonymize_for_share, sha256,
)

logger = logging.getLogger("eni.shared_workspace")
__version__ = "1.0.0"


@module(
    name="shared_workspace",
    version="1.0.0",
    config_defaults={"root": "data/shared", "max_history": 2000},
)
class SharedWorkspaceModule(Module):
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.ws: Optional[SharedWorkspace] = None

    async def initialize(self) -> None:
        root = self.config.get("root", "data/shared")
        if isinstance(root, str) and not root.startswith("/"):
            root = Path(__file__).resolve().parent.parent.parent / root
        self.ws = SharedWorkspace(root, max_history=int(self.config.get("max_history", 2000)))
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self.ws is not None else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    # facade
    def write(self, rel, content, author, force=False):
        return self.ws.write(rel, content, author, force=force)

    def lock(self, rel, owner):
        return self.ws.lock(rel, owner)

    def unlock(self, rel, owner):
        return self.ws.unlock(rel, owner)

    def read(self, rel):
        return self.ws.read(rel)

    def history(self, rel=None, limit=50):
        return self.ws.history(rel, limit)

    def query(self, q, limit=20):
        return self.ws.query(q, limit)

    def list(self):
        return self.ws.list()


def create_shared_workspace_module(config: Optional[dict[str, Any]] = None) -> SharedWorkspaceModule:
    return SharedWorkspaceModule(config=config or {})


__all__ = ["SharedWorkspaceModule", "create_shared_workspace_module",
           "SharedWorkspace", "anonymize_for_share", "sha256", "__version__"]
"""Artifact Pipeline — navigate & organize all creative works (no LLM).

Grounded in the JEVanClief transcript *"Watch Me Build Something Claude Code
Can't Do Yet"* (https://www.youtube.com/watch?v=KC0VEZuo4OI, 891s). JEVanClief
explicitly does NOT want a front end that calls Claude (to dodge API fees); he
wants a front end that lets him navigate all of his works, take scripts and turn
them into "full animations", with a workflow that is "much more organized and
clear", and finished animations viewable in one place.

That is an asset / pipeline ORGANIZER — an `ArtifactRegistry` that catalogs
files on disk (Path-based scanning), tracks per-artifact TYPE and STAGE, a
`WorkflowGraph` of valid stage transitions (``script -> storyboard ->
animation -> render`` plus the transcript-grounded shortcut ``script ->
animation``), dependency tracking (a render depends on its script), and a local
catalog store (JSON / SQLite, in-memory + tmp_path) — all stdlib, network-free.

The deterministic core lives in
:mod:`enterprise.modules.artifact_pipeline.artifact_pipeline`; this package
exposes it as a registered Platform Kernel module with an initialize /
health_check / shutdown lifecycle and a thin facade.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .artifact_pipeline import (
    STAGE_ORDER,
    Artifact,
    ArtifactNotFoundError,
    ArtifactPipeline,
    ArtifactRegistry,
    ArtifactType,
    DependencyError,
    DuplicateArtifactError,
    InvalidTransitionError,
    Stage,
    WorkflowGraph,
)

logger = logging.getLogger("eni.artifact_pipeline_module")

__version__ = "1.0.0"
__module__ = "artifact_pipeline"


@module(
    name="artifact_pipeline",
    version=__version__,
    config_defaults={
        "scan_root": "",
        "catalog_store": "memory",  # "memory" | "json" | "sqlite"
        "catalog_path": "",
    },
)
class ArtifactPipelineModule(Module):
    """Kernel module exposing the creative-works artifact pipeline organizer.

    Wraps :class:`ArtifactPipeline` behind a small facade and publishes
    ``artifact_pipeline.*`` events on the platform EventBus when one is wired
    (via :meth:`set_event_bus`). No network is ever used.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._pipeline: Optional[ArtifactPipeline] = None
        self._event_bus: Optional[Any] = None
        self._init_error: Optional[str] = None

    # ------------------------------------------------------------------ pub
    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event only when an event bus is wired."""
        if self._event_bus is None:
            return
        self._event_bus.publish(
            Event.create(
                topic=topic,
                source=self.name,
                payload=payload,
            )
        )

    # ------------------------------------------------------------ lifecycle
    async def initialize(self) -> None:
        """Build the ArtifactPipeline and mark the module healthy."""
        try:
            from .artifact_pipeline import JsonCatalogStore, SqliteCatalogStore

            store_kind = (self.config.get("catalog_store") or "memory").lower()
            catalog_path = self.config.get("catalog_path") or ""
            store = None
            if store_kind == "json":
                store = JsonCatalogStore(catalog_path or "artifact_catalog.json")
            elif store_kind == "sqlite":
                store = SqliteCatalogStore(catalog_path or "artifact_catalog.db")

            self._pipeline = ArtifactPipeline(store=store)

            # Seed from a configured scan root and/or persisted catalog.
            if self._pipeline.store is not None:
                self._pipeline.load_from_store()
            scan_root = self.config.get("scan_root")
            if scan_root:
                found = self._pipeline.scan(scan_root)
                if self._pipeline.store is not None:
                    self._pipeline.persist()
                logger.info(
                    "artifact_pipeline scanned %d artifacts from %s", len(found), scan_root
                )

            self._init_error = None
            self.status = HealthStatus.HEALTHY
            logger.info("artifact_pipeline initialized: %s", self._pipeline.stats())
            self._publish("artifact_pipeline.initialized", {"ok": True})
        except Exception as exc:  # defensively unhealthy, never crash the kernel
            self._init_error = str(exc)
            self.status = HealthStatus.UNHEALTHY
            logger.warning("artifact_pipeline init failed: %s", exc)
            raise

    async def health_check(self) -> HealthStatus:
        """Report health based on init success."""
        if self._init_error:
            self.status = HealthStatus.UNHEALTHY
        elif self._pipeline is not None:
            self.status = HealthStatus.HEALTHY
        else:
            self.status = HealthStatus.UNHEALTHY
        return self.status

    async def shutdown(self) -> None:
        """Tear down the pipeline; close any SQLite connection."""
        if (
            self._pipeline is not None
            and self._pipeline.store is not None
            and hasattr(self._pipeline.store, "close")
        ):
            try:
                self._pipeline.store.close()
            except Exception:  # pragma: no cover - defensive
                pass
        self._pipeline = None
        self.status = HealthStatus.UNKNOWN
        logger.info("artifact_pipeline module shutdown")
        self._publish("artifact_pipeline.shutdown", {"ok": True})

    # ------------------------------------------------------------- wiring
    def set_event_bus(self, event_bus: Any) -> None:
        """Wire the platform EventBus into this module."""
        self._event_bus = event_bus

    # ---------------------------------------------------------------- core
    @property
    def pipeline(self) -> ArtifactPipeline:
        """Return the live :class:`ArtifactPipeline` (lazily created)."""
        if self._pipeline is None:
            self._pipeline = ArtifactPipeline()
        return self._pipeline

    # -------------------------------------------------------------- facade
    def add(
        self,
        path: str,
        project: Optional[str] = None,
        type_: Optional[ArtifactType] = None,
        stage: Optional[Stage] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Artifact:
        art = self.pipeline.add(
            path, project=project, type_=type_, stage=stage, metadata=metadata
        )
        self._publish("artifact_pipeline.added", {"id": art.id, "name": art.name})
        return art

    def derive(self, source_id: str, output_path: str, to_stage: Optional[Stage] = None) -> Artifact:
        art = self.pipeline.derive(source_id, output_path, to_stage=to_stage)
        self._publish(
            "artifact_pipeline.derived",
            {"source": source_id, "output": art.id, "stage": art.stage.value},
        )
        return art

    def advance(self, artifact_id: str, to_stage: Stage) -> Artifact:
        art = self.pipeline.advance(artifact_id, to_stage)
        self._publish(
            "artifact_pipeline.advanced",
            {"id": artifact_id, "stage": art.stage.value},
        )
        return art

    def browse(
        self,
        project: Optional[str] = None,
        type_: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[Artifact]:
        return self.pipeline.browse(project=project, type_=type_, stage=stage)

    def all_renders(self) -> list[Artifact]:
        return self.pipeline.all_renders()

    def group_by(self, field_name: str) -> dict[str, list[Artifact]]:
        return self.pipeline.group_by(field_name)

    def readiness(self, artifact_id: str) -> dict[str, Any]:
        return self.pipeline.readiness(artifact_id)

    def health(self) -> dict[str, Any]:
        """Return a health/statistics dict for operational tooling."""
        return self.pipeline.stats()


def create_artifact_pipeline_module(
    config: Optional[dict[str, Any]] = None,
) -> ArtifactPipelineModule:
    """Create (but do not initialize) an :class:`ArtifactPipelineModule`."""
    return ArtifactPipelineModule(config=config or {})


__all__ = [
    "__version__",
    "ArtifactPipelineModule",
    "create_artifact_pipeline_module",
    "Artifact",
    "ArtifactRegistry",
    "ArtifactPipeline",
    "ArtifactType",
    "Stage",
    "WorkflowGraph",
    "STAGE_ORDER",
    "ArtifactNotFoundError",
    "DuplicateArtifactError",
    "InvalidTransitionError",
    "DependencyError",
]

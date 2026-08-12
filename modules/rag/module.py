"""
RAG Module -- Platform Kernel integration.

Registers the RAG system as a Platform Kernel ``@module`` following the same
pattern as the A2A module: a :class:`Module` subclass with the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``), event-bus wiring
(``set_event_bus``), and a public ``create_rag_module(config=None)`` factory.

The package registers itself automatically when imported (i.e. when this
module is imported, the ``@module(name='rag', version='1.0.0')`` decorator runs
and adds the ``RAGModule`` class to the kernel module registry).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    Event,
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .pipeline import RAGConfig, RAGPipeline

_logger = logging.getLogger("eni.rag")


@module(name="rag", version="1.0.0")
class RAGModule(Module):
    """Platform Kernel RAG module.

    Owns a :class:`RAGPipeline` and exposes the standard module lifecycle plus
    simple query/index helpers. Configuration keys (dict passed to ``__init__``)
    are forwarded to :class:`RAGConfig` for the embedded pipeline.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._pipeline: RAGPipeline | None = None
        self._event_bus: EventBus | None = None
        self._lock = threading.RLock()

    # -- lifecycle -------------------------------------------------------- #
    async def initialize(self) -> None:
        """Build the RAGPipeline and mark the module healthy."""
        with self._lock:
            self._status = HealthStatus.STARTING
        _logger.info("RAG module initializing...")
        try:
            cfg = RAGConfig(**self._pipeline_config())
            pipeline = RAGPipeline(cfg)
            with self._lock:
                self._pipeline = pipeline
                self._status = HealthStatus.HEALTHY
            self._emit(
                "rag.initialized",
                {"status": HealthStatus.HEALTHY.value, "version": self.version},
            )
            _logger.info("RAG module initialized")
        except Exception as exc:  # noqa: BLE001 - lifecycle must report UNHEALTHY
            _logger.exception("Failed to initialize rag module: %s", exc)
            with self._lock:
                self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """A healthy RAG module has an initialized pipeline."""
        with self._lock:
            if self._pipeline is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Gracefully release the pipeline."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down rag module...")
            self._pipeline = None
            self._status = HealthStatus.HEALTHY

    # -- event bus wiring ------------------------------------------------- #
    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module."""
        with self._lock:
            self._event_bus = event_bus

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        with self._lock:
            bus = self._event_bus
        if bus is None:
            return
        try:
            bus.publish(
                Event.create(
                    topic=topic,
                    source=self.name,
                    payload=payload,
                )
            )
        except Exception:  # noqa: BLE001 - event publishing must not break lifecycle
            _logger.exception("Failed to publish rag event %s", topic)

    # -- config ----------------------------------------------------------- #
    def _pipeline_config(self) -> dict[str, Any]:
        """Filter module config down to keys accepted by RAGConfig."""
        valid = {
            "chunk_strategy",
            "chunk_size",
            "chunk_overlap",
            "min_chunk_size",
            "embedding_dimension",
            "retrieval_strategy",
            "top_k",
            "rerank_strategy",
            "assembler_strategy",
            "citation_style",
            "include_scores",
        }
        return {k: v for k, v in self._config.items() if k in valid}

    # -- public facade ---------------------------------------------------- #
    @property
    def pipeline(self) -> RAGPipeline:
        """The embedded pipeline (raises if not initialized)."""
        with self._lock:
            pipeline = self._pipeline
        if pipeline is None:
            msg = "rag module is not initialized"
            raise RuntimeError(msg)
        return pipeline

    def index_documents(self, documents) -> int:
        """Index documents into the embedded pipeline."""
        return self.pipeline.index_documents(documents)

    def query(self, question: str, k: Optional[int] = None):
        """Run the pipeline for a question."""
        return self.pipeline.query(question, k=k)


def create_rag_module(
    config: dict[str, Any] | None = None,
) -> RAGModule:
    """Create (but do not initialize) a :class:`RAGModule` from config.

    Args:
        config: Optional dict. Threat keys are forwarded to
            :class:`RAGConfig` (e.g. ``chunk_size``, ``top_k``,
            ``retrieval_strategy``, ``assembler_strategy``, ``citation_style``).
    """
    return RAGModule(config=config or {})


__all__ = ["RAGModule", "create_rag_module"]

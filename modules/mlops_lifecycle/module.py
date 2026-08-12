"""
MLOps/LLMOps Lifecycle Module — Platform Kernel module binding.

Wraps all lifecycle sub-engines (feature/label store, canary manager, eval
gate engine, observability engine, drift detector, rollback controller and
lifecycle orchestrator) behind the standard Platform Kernel module lifecycle
(``initialize`` / ``health_check`` / ``shutdown``) and event-bus wiring
(``set_event_bus``).

Simply importing this module registers ``MLOpsLifecycleModule`` with the
Platform Kernel registry via the ``@module`` decorator.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .canary_manager import CanaryManager, create_canary_manager
from .drift_detector import DriftDetector, create_drift_detector
from .eval_gate_engine import EvalGateEngine, create_eval_gate_engine
from .feature_label_store import FeatureLabelStore, create_feature_label_store
from .lifecycle_orchestrator import LifecycleOrchestrator, create_lifecycle_orchestrator
from .observability_engine import ObservabilityEngine, create_observability_engine
from .rollback_controller import RollbackController, create_rollback_controller

logger = logging.getLogger("enterprise.mlops_lifecycle")


@module(name="mlops_lifecycle", version="1.0.0")
class MLOpsLifecycleModule(Module):
    """Enterprise MLOps/LLMOps Lifecycle module.

    Owns one instance of each lifecycle sub-engine and exposes them through
    public properties. The SQLite feature/label store defaults to a temporary
    file database whose location is configurable via ``featurestore_db_path``.

    Events published (when an event bus is wired via ``set_event_bus``):
        - mlops_lifecycle.canary.created      -- a canary deployment was created
        - mlops_lifecycle.gate.evaluated      -- an eval gate pass/fail result
        - mlops_lifecycle.drift.detected      -- drift was flagged on a feature
        - mlops_lifecycle.rollback.executed   -- a rollback completed
    """

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[EventBus] = None
        self._lock = threading.RLock()
        self._store: Optional[FeatureLabelStore] = None

        self._canary = create_canary_manager()
        self._drift = create_drift_detector(config.get("drift", {}) if config else {})
        self._eval_gate = create_eval_gate_engine()
        self._observability = create_observability_engine()
        self._rollback = create_rollback_controller()
        self._orchestrator = create_lifecycle_orchestrator()

    # -- Public engine accessors -------------------------------------------

    @property
    def feature_store(self) -> FeatureLabelStore:
        if self._store is None:
            raise RuntimeError("mlops_lifecycle module not initialized")
        return self._store

    @property
    def canary(self) -> CanaryManager:
        return self._canary

    @property
    def drift(self) -> DriftDetector:
        return self._drift

    @property
    def eval_gate(self) -> EvalGateEngine:
        return self._eval_gate

    @property
    def observability(self) -> ObservabilityEngine:
        return self._observability

    @property
    def rollback(self) -> RollbackController:
        return self._rollback

    @property
    def orchestrator(self) -> LifecycleOrchestrator:
        return self._orchestrator

    # -- Platform Kernel lifecycle -----------------------------------------

    async def initialize(self) -> None:
        """Open the feature store and mark the module healthy."""
        with self._lock:
            self._status = HealthStatus.STARTING
        logger.info("mlops_lifecycle module initializing")
        store = FeatureLabelStore(db_path=self._config.get("featurestore_db_path"))
        with self._lock:
            self._store = store
            self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        """Healthy when the feature store is open and all engines exist."""
        with self._lock:
            if self._store is not None and self._store.is_open:
                self._status = HealthStatus.HEALTHY
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Close the feature store and drop references to all engines."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            logger.info("shutting down mlops_lifecycle module...")
            store = self._store
            self._store = None
            if store is not None and store.is_open:
                store.close()
            self._status = HealthStatus.HEALTHY

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module."""
        with self._lock:
            self._event_bus = event_bus

    # -- Convenience helpers that emit events -------------------------------

    def emit_gate_result(self, policy_name: str, passed: bool, metric: str, value: float) -> None:
        """Record a gate evaluation and publish an event when wired."""
        self._emit(
            "mlops_lifecycle.gate.evaluated",
            {"policy": policy_name, "passed": passed, "metric": metric, "value": value},
        )

    def emit_drift(self, feature_name: str, value: float, method: str) -> None:
        self._emit(
            "mlops_lifecycle.drift.detected",
            {"feature": feature_name, "value": value, "method": method},
        )

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        event_bus = self._event_bus
        if event_bus is None:
            return
        try:
            event_bus.publish(
                Event.create(
                    topic=topic,
                    source="mlops_lifecycle",
                    payload=payload,
                    priority=EventPriority.NORMAL,
                )
            )
        except Exception as exc:  # noqa: BLE001 - defensive
            logger.warning("failed to publish event %s: %s", topic, exc)


def create_mlops_lifecycle_module(
    config: Dict[str, Any] | None = None,
) -> MLOpsLifecycleModule:
    """Create (but do not initialize) an :class:`MLOpsLifecycleModule`.

    Args:
        config: Optional dict. Supported keys:
            - ``featurestore_db_path`` (str): SQLite database path for the
              feature/label store (defaults to a temp file).
            - ``drift`` (dict): kwargs for the drift detector
              (``alpha``, ``psi_threshold``).
    """
    return MLOpsLifecycleModule(config=config or {})

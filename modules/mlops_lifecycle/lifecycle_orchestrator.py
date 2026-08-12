"""
Lifecycle Orchestrator — drives an agent experiment through the MLOps
pipeline stage machine (experiment -> data prep -> training -> evaluation ->
canary -> promotion) with policy-aware sequencing, retries and failure
handling.

Pure-stdlib implementation. A :class:`PipelineRun` records the result of each
stage; the orchestrator enforces a declared stage order and (optionally)
stops on the first failed stage.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("enterprise.mlops_lifecycle.lifecycle_orchestrator")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineStage(Enum):
    EXPERIMENT = "experiment"
    DATA_PREP = "data_prep"
    TRAINING = "training"
    EVALUATION = "evaluation"
    CANARY = "canary"
    PROMOTION = "promotion"

    @classmethod
    def ordered(cls) -> List["PipelineStage"]:
        return [
            cls.EXPERIMENT,
            cls.DATA_PREP,
            cls.TRAINING,
            cls.EVALUATION,
            cls.CANARY,
            cls.PROMOTION,
        ]


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class StageResult:
    """Outcome of executing one pipeline stage."""

    stage: PipelineStage
    status: StageStatus = StageStatus.PENDING
    duration_ms: float = 0.0
    message: str = ""
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["stage"] = self.stage.value
        data["status"] = self.status.value
        return data


@dataclass
class OrchestrationPolicy:
    """Controls how a pipeline run sequences and fails its stages."""

    stop_on_failure: bool = True
    max_retries: int = 0
    stage_order: List[PipelineStage] = field(
        default_factory=lambda: PipelineStage.ordered()
    )
    required_stages: List[PipelineStage] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Convert any string entries back to enum values.
        self.stage_order = [_as_stage(s) for s in self.stage_order]
        self.required_stages = [_as_stage(s) for s in self.required_stages]


@dataclass
class PipelineRun:
    """A single end-to-end execution of the pipeline."""

    name: str
    policy: OrchestrationPolicy = field(default_factory=OrchestrationPolicy)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: RunStatus = RunStatus.PENDING
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    context: Dict[str, Any] = field(default_factory=dict)

    def result_for(self, stage: PipelineStage | str) -> Optional[StageResult]:
        return self.stage_results.get(_as_stage(stage).value)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["stage_results"] = {
            k: v.to_dict() for k, v in self.stage_results.items()
        }
        return data


def _as_stage(stage: PipelineStage | str) -> PipelineStage:
    if isinstance(stage, PipelineStage):
        return stage
    return PipelineStage(stage)


class LifecycleOrchestrator:
    """Runs pipelines stage-by-stage with policy enforcement."""

    def __init__(self) -> None:
        self._runs: Dict[str, PipelineRun] = {}
        self._lock = threading.RLock()

    def create_run(
        self,
        name: str,
        policy: Optional[OrchestrationPolicy] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> PipelineRun:
        run = PipelineRun(name=name, policy=policy or OrchestrationPolicy(), context=context or {})
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> List[PipelineRun]:
        with self._lock:
            return list(self._runs.values())

    def execute_stage(
        self,
        run: PipelineRun,
        stage: PipelineStage | str,
        fn: Callable[[], dict[str, Any] | None],
    ) -> StageResult:
        """Execute a single stage function, recording success or failure.

        ``fn`` may raise to signal failure, or return a dict to populate the
        run context. Retries are applied per the run policy.
        """
        stage = _as_stage(stage)
        result = StageResult(stage=stage, status=StageStatus.RUNNING)
        start = time.monotonic()
        attempts = 0
        max_retries = run.policy.max_retries
        try:
            while True:
                attempts += 1
                try:
                    outcome = fn()
                    result.status = StageStatus.PASSED
                    result.message = "stage completed"
                    if isinstance(outcome, dict):
                        run.context.update(outcome)
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempts <= max_retries:
                        result.retries = attempts
                        continue
                    result.status = StageStatus.FAILED
                    result.message = str(exc)
                    break
        finally:
            result.duration_ms = (time.monotonic() - start) * 1000.0

        with self._lock:
            run.stage_results[stage.value] = result
            self._update_run_status(run)
        return result

    def run_pipeline(
        self,
        run: PipelineRun,
        executors: Dict[PipelineStage | str, Callable[[], dict[str, Any] | None]],
    ) -> RunStatus:
        """Execute stages in policy order, stopping on failure if configured."""
        with self._lock:
            run.status = RunStatus.RUNNING
        stage_map = {_as_stage(s): fn for s, fn in executors.items()}
        for stage in run.policy.stage_order:
            fn = stage_map.get(stage)
            if fn is None:
                continue
            result = self.execute_stage(run, stage, fn)
            if result.status is StageStatus.FAILED and run.policy.stop_on_failure:
                with self._lock:
                    run.status = RunStatus.FAILED
                return run.status
        with self._lock:
            self._finalize_status(run)
        return run.status

    def _update_run_status(self, run: PipelineRun) -> None:
        results = [
            r for r in run.stage_results.values()
            if r.status in (StageStatus.PASSED, StageStatus.FAILED)
        ]
        if any(r.status is StageStatus.FAILED for r in results):
            run.status = RunStatus.FAILED

    def _finalize_status(self, run: PipelineRun) -> None:
        results = list(run.stage_results.values())
        if not results:
            run.status = RunStatus.PENDING
            return
        passed = [r for r in results if r.status is StageStatus.PASSED]
        failed = [r for r in results if r.status is StageStatus.FAILED]
        if failed:
            run.status = RunStatus.FAILED
        elif len(passed) == len(results):
            run.status = RunStatus.SUCCEEDED
        else:
            run.status = RunStatus.PARTIAL


def create_lifecycle_orchestrator(config: Optional[Dict[str, Any]] = None) -> LifecycleOrchestrator:
    """Create a default :class:`LifecycleOrchestrator`.

    Args:
        config: Optional dict (currently unused; kept for interface parity).
    """
    return LifecycleOrchestrator()

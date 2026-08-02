"""
Experiment management system.

Manages the full experiment lifecycle: creation, execution, result recording,
threshold checking, and reproducibility verification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("enterprise.innovation_rd.experiment")


class ExperimentStatus(Enum):
    """Status of an experiment through its lifecycle."""

    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REPRODUCING = "reproducing"


@dataclass
class Experiment:
    """A single experiment with hypothesis, variables, metrics, and thresholds.

    Attributes:
        hypothesis: The hypothesis being tested.
        baseline: Baseline value or metric for comparison.
        variables: Dictionary of independent variables and their values.
        dataset: Name or description of the dataset used.
        metrics: List of metric names being tracked.
        success_threshold: Threshold value above which the experiment is a success.
        failure_threshold: Threshold value below which the experiment is a failure.
        budget: Allocated budget (in arbitrary units).
        security_requirements: List of security requirements that must be met.
        privacy_requirements: List of privacy requirements that must be met.
        timeline: Expected timeline description.
        owner: Person or team responsible.
        reproducibility_checklist: List of items to verify reproducibility.
        experiment_id: Unique identifier (auto-generated).
        status: Current status.
        results: Dictionary of recorded results (metric_name -> value).
        start_time: When the experiment started.
        end_time: When the experiment ended.
        notes: Additional notes or observations.
    """

    hypothesis: str
    baseline: float = 0.0
    variables: Dict[str, Any] = field(default_factory=dict)
    dataset: str = ""
    metrics: List[str] = field(default_factory=list)
    success_threshold: float = 0.0
    failure_threshold: float = 0.0
    budget: float = 0.0
    security_requirements: List[str] = field(default_factory=list)
    privacy_requirements: List[str] = field(default_factory=list)
    timeline: str = ""
    owner: str = ""
    reproducibility_checklist: List[str] = field(default_factory=list)
    experiment_id: str = ""
    status: ExperimentStatus = ExperimentStatus.DRAFT
    results: Dict[str, float] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.experiment_id:
            self.experiment_id = f"exp-{uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        """Serialize the experiment to a dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "baseline": self.baseline,
            "variables": self.variables,
            "dataset": self.dataset,
            "metrics": self.metrics,
            "success_threshold": self.success_threshold,
            "failure_threshold": self.failure_threshold,
            "budget": self.budget,
            "security_requirements": self.security_requirements,
            "privacy_requirements": self.privacy_requirements,
            "timeline": self.timeline,
            "owner": self.owner,
            "reproducibility_checklist": self.reproducibility_checklist,
            "status": self.status.value,
            "results": self.results,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "notes": self.notes,
        }


@dataclass
class ExperimentTracker:
    """Tracks and manages multiple experiments through their lifecycle.

    Provides methods for creating, starting, recording results for,
    threshold-checking, and verifying reproducibility of experiments.
    """

    experiments: Dict[str, Experiment] = field(default_factory=dict)

    def create_experiment(
        self,
        hypothesis: str,
        baseline: float = 0.0,
        variables: Optional[Dict[str, Any]] = None,
        dataset: str = "",
        metrics: Optional[List[str]] = None,
        success_threshold: float = 0.0,
        failure_threshold: float = 0.0,
        budget: float = 0.0,
        security_requirements: Optional[List[str]] = None,
        privacy_requirements: Optional[List[str]] = None,
        timeline: str = "",
        owner: str = "",
        reproducibility_checklist: Optional[List[str]] = None,
    ) -> Experiment:
        """Create a new experiment and register it with the tracker.

        Args:
            hypothesis: The hypothesis being tested.
            baseline: Baseline metric value for comparison.
            variables: Independent variables dictionary.
            dataset: Dataset identifier or description.
            metrics: List of metric names to track.
            success_threshold: Value above which the experiment succeeds.
            failure_threshold: Value below which the experiment fails.
            budget: Allocated budget.
            security_requirements: Security constraints.
            privacy_requirements: Privacy constraints.
            timeline: Expected timeline.
            owner: Responsible party.
            reproducibility_checklist: Items verifying reproducibility.

        Returns:
            The newly created Experiment.
        """
        experiment = Experiment(
            hypothesis=hypothesis,
            baseline=baseline,
            variables=variables or {},
            dataset=dataset,
            metrics=metrics or [],
            success_threshold=success_threshold,
            failure_threshold=failure_threshold,
            budget=budget,
            security_requirements=security_requirements or [],
            privacy_requirements=privacy_requirements or [],
            timeline=timeline,
            owner=owner,
            reproducibility_checklist=reproducibility_checklist or [],
            status=ExperimentStatus.DRAFT,
        )
        self.experiments[experiment.experiment_id] = experiment
        logger.info(
            "Created experiment '%s' with hypothesis: %s",
            experiment.experiment_id,
            hypothesis[:80],
        )
        return experiment

    def start(self, experiment_id: str) -> bool:
        """Start an experiment by transitioning it from DRAFT to RUNNING.

        Args:
            experiment_id: The experiment to start.

        Returns:
            True if started successfully, False otherwise.
        """
        experiment = self.experiments.get(experiment_id)
        if experiment is None:
            logger.error("Cannot start: experiment %s not found", experiment_id)
            return False
        if experiment.status != ExperimentStatus.DRAFT:
            logger.error(
                "Cannot start experiment %s: current status is %s",
                experiment_id,
                experiment.status.value,
            )
            return False
        experiment.status = ExperimentStatus.RUNNING
        experiment.start_time = datetime.now(timezone.utc)
        logger.info("Started experiment %s", experiment_id)
        return True

    def record_result(
        self, experiment_id: str, metric: str, value: float
    ) -> bool:
        """Record a metric result for a running experiment.

        Args:
            experiment_id: Target experiment.
            metric: Metric name.
            value: Recorded value.

        Returns:
            True if recorded successfully, False otherwise.
        """
        experiment = self.experiments.get(experiment_id)
        if experiment is None:
            logger.error("Cannot record result: experiment %s not found", experiment_id)
            return False
        if experiment.status != ExperimentStatus.RUNNING:
            logger.error(
                "Cannot record result for experiment %s: status is %s",
                experiment_id,
                experiment.status.value,
            )
            return False
        experiment.results[metric] = value
        logger.debug(
            "Recorded result for experiment %s: %s = %s",
            experiment_id,
            metric,
            value,
        )
        return True

    def check_thresholds(self, experiment_id: str) -> ExperimentStatus:
        """Check recorded results against success/failure thresholds.

        Transitions the experiment to COMPLETED or FAILED based on whether
        any metric meets or exceeds the thresholds. If all metrics exceed
        success_threshold, it succeeds; if any drops below failure_threshold,
        it fails.

        Args:
            experiment_id: The experiment to check.

        Returns:
            The new ExperimentStatus.
        """
        experiment = self.experiments.get(experiment_id)
        if experiment is None:
            logger.error("Cannot check thresholds: experiment %s not found", experiment_id)
            return ExperimentStatus.DRAFT

        if experiment.status != ExperimentStatus.RUNNING:
            logger.warning(
                "Threshold check skipped for %s: status is %s",
                experiment_id,
                experiment.status.value,
            )
            return experiment.status

        if not experiment.results:
            logger.warning("No results recorded for experiment %s", experiment_id)
            return experiment.status

        # Check failure threshold first (fail-fast)
        for metric, value in experiment.results.items():
            if value <= experiment.failure_threshold:
                experiment.status = ExperimentStatus.FAILED
                experiment.end_time = datetime.now(timezone.utc)
                experiment.notes.append(
                    f"Failed: {metric}={value} <= "
                    f"failure_threshold={experiment.failure_threshold}"
                )
                logger.info("Experiment %s FAILED: %s=%s", experiment_id, metric, value)
                return ExperimentStatus.FAILED

        # Check success: all metrics must exceed success threshold
        all_success = all(
            v >= experiment.success_threshold for v in experiment.results.values()
        )
        if all_success:
            experiment.status = ExperimentStatus.COMPLETED
            experiment.end_time = datetime.now(timezone.utc)
            experiment.notes.append("Completed: all metrics meet success threshold")
            logger.info("Experiment %s COMPLETED successfully", experiment_id)
        else:
            logger.debug("Experiment %s still running: thresholds not met", experiment_id)

        return experiment.status

    def verify_reproducibility(self, experiment_id: str) -> bool:
        """Verify that an experiment meets its reproducibility checklist.

        Args:
            experiment_id: The experiment to verify.

        Returns:
            True if all checklist items are accounted for, False otherwise.
        """
        experiment = self.experiments.get(experiment_id)
        if experiment is None:
            logger.error(
                "Cannot verify reproducibility: experiment %s not found", experiment_id
            )
            return False

        if not experiment.reproducibility_checklist:
            logger.warning(
                "Experiment %s has no reproducibility checklist", experiment_id
            )
            return False

        # In a real system, each checklist item would be verified.
        # Here we confirm the checklist exists and items are non-empty.
        valid_items = [
            item
            for item in experiment.reproducibility_checklist
            if item and item.strip()
        ]
        if len(valid_items) != len(experiment.reproducibility_checklist):
            logger.warning(
                "Experiment %s has empty reproducibility checklist items", experiment_id
            )
            return False

        experiment.status = ExperimentStatus.REPRODUCING
        logger.info(
            "Reproducibility verification passed for experiment %s (%d items)",
            experiment_id,
            len(valid_items),
        )
        return True

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Retrieve an experiment by ID."""
        return self.experiments.get(experiment_id)

    def list_by_status(self, status: ExperimentStatus) -> List[Experiment]:
        """List all experiments with a given status."""
        return [e for e in self.experiments.values() if e.status == status]

    def get_summary(self, experiment_id: str) -> Optional[dict]:
        """Get a human-readable summary of an experiment."""
        exp = self.get_experiment(experiment_id)
        if exp is None:
            return None
        return {
            "id": exp.experiment_id,
            "hypothesis": exp.hypothesis,
            "status": exp.status.value,
            "results": exp.results,
            "duration": (
                (exp.end_time - exp.start_time).total_seconds()
                if exp.start_time and exp.end_time
                else None
            ),
        }
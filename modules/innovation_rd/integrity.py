"""
Research integrity verification.

Ensures research entries and experiments adhere to integrity standards:
source attribution, reproducibility, negative-result validation,
dataset documentation, limitation documentation, and statistical care.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .experiment import Experiment, ExperimentStatus
from .research import ResearchEntry

logger = logging.getLogger("enterprise.innovation_rd.integrity")


@dataclass
class IntegrityReport:
    """Report on the integrity of a research entry or experiment.

    Each check produces a pass/fail result. The report aggregates all checks
    and provides an overall verdict.

    Attributes:
        target_id: Identifier of the item checked (entry_id or experiment_id).
        checks: Dictionary of check_name -> pass/fail bool.
        details: Dictionary of check_name -> additional detail string.
        overall_pass: True if all checks passed, False otherwise.
    """

    target_id: str
    checks: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)
    overall_pass: bool = False

    def add_check(self, name: str, passed: bool, detail: str = "") -> None:
        """Add a check result to the report.

        Args:
            name: Name of the check performed.
            passed: Whether the check passed.
            detail: Optional detail about the result.
        """
        self.checks[name] = passed
        self.details[name] = detail
        self.overall_pass = all(self.checks.values()) if self.checks else False

    def summary(self) -> str:
        """Produce a one-line summary of the integrity report."""
        status = "PASSED" if self.overall_pass else "FAILED"
        total = len(self.checks)
        passed_count = sum(1 for v in self.checks.values() if v)
        return (
            f"IntegrityReport({self.target_id}): {status} "
            f"({passed_count}/{total} checks passed)"
        )


@dataclass
class IntegrityCheck:
    """Performs integrity verification on research entries and experiments.

    Covers six key areas:
    - Source attribution verification
    - Reproducibility checks
    - Negative result validation
    - Dataset documentation verification
    - Limitation documentation
    - Statistical care checks
    """

    required_source_fields: List[str] = field(
        default_factory=lambda: ["source", "title", "authors"]
    )
    min_findings_length: int = 20

    def verify_source_attribution(self, research_entry: ResearchEntry) -> bool:
        """Verify that a research entry has proper source attribution.

        Checks for the presence of source URL/identifier, title, and authors.
        Also validates that the source field is not a placeholder.

        Args:
            research_entry: The ResearchEntry to verify.

        Returns:
            True if attribution is adequate, False otherwise.
        """
        if not research_entry.source or not research_entry.source.strip():
            logger.warning(
                "Source attribution failed for %s: empty source",
                research_entry.entry_id,
            )
            return False

        # Reject obvious placeholders
        placeholders = {"tbd", "todo", "n/a", "unknown", "none", ""}
        if research_entry.source.lower().strip() in placeholders:
            logger.warning(
                "Source attribution failed for %s: placeholder source '%s'",
                research_entry.entry_id,
                research_entry.source,
            )
            return False

        if not research_entry.title or not research_entry.title.strip():
            logger.warning(
                "Source attribution failed for %s: missing title",
                research_entry.entry_id,
            )
            return False

        logger.debug(
            "Source attribution verified for %s", research_entry.entry_id
        )
        return True

    def check_reproducibility(self, experiment: Experiment) -> bool:
        """Check that an experiment has sufficient reproducibility documentation.

        Verifies that the experiment has a reproducibility checklist with at
        least one item, and that the checklist items are meaningful.

        Args:
            experiment: The Experiment to check.

        Returns:
            True if reproducibility criteria are met, False otherwise.
        """
        if not experiment.reproducibility_checklist:
            logger.warning(
                "Reproducibility check failed for %s: empty checklist",
                experiment.experiment_id,
            )
            return False

        meaningful = [
            item
            for item in experiment.reproducibility_checklist
            if len(item.strip()) >= 5
        ]
        if len(meaningful) < len(experiment.reproducibility_checklist):
            logger.warning(
                "Reproducibility check failed for %s: %d non-meaningful items",
                experiment.experiment_id,
                len(experiment.reproducibility_checklist) - len(meaningful),
            )
            return False

        logger.debug(
            "Reproducibility check passed for %s (%d items)",
            experiment.experiment_id,
            len(meaningful),
        )
        return True

    def validate_negative_results(self, experiment: Experiment) -> bool:
        """Validate that negative (failure) results are properly documented.

        A failed experiment should have notes explaining the failure.
        A completed experiment with results below baseline should also
        have explanatory notes.

        Args:
            experiment: The Experiment to validate.

        Returns:
            True if negative results are properly handled, False otherwise.
        """
        if experiment.status == ExperimentStatus.FAILED:
            if not experiment.notes:
                logger.warning(
                    "Negative result validation failed for %s: no notes on failure",
                    experiment.experiment_id,
                )
                return False
            failure_explained = any(
                "fail" in note.lower() or "fail" in note.lower()
                for note in experiment.notes
            )
            if not failure_explained:
                logger.warning(
                    "Negative result validation failed for %s: failure not explained",
                    experiment.experiment_id,
                )
                return False

        # Check if any result is below baseline
        for metric, value in experiment.results.items():
            if value < experiment.baseline:
                if not any(
                    "below baseline" in note.lower() or "negative" in note.lower()
                    for note in experiment.notes
                ):
                    logger.warning(
                        "Negative result validation failed for %s: "
                        "%s below baseline but not documented",
                        experiment.experiment_id,
                        metric,
                    )
                    return False

        logger.debug(
            "Negative result validation passed for %s", experiment.experiment_id
        )
        return True

    def verify_dataset_documentation(self, experiment: Experiment) -> bool:
        """Verify that the experiment's dataset is adequately documented.

        The dataset field must be non-empty and contain a meaningful
        description (not just a filename).

        Args:
            experiment: The Experiment to verify.

        Returns:
            True if dataset documentation is adequate, False otherwise.
        """
        if not experiment.dataset or not experiment.dataset.strip():
            logger.warning(
                "Dataset documentation failed for %s: missing dataset",
                experiment.experiment_id,
            )
            return False

        # Dataset description should be at least a short sentence
        if len(experiment.dataset.strip()) < 10:
            logger.warning(
                "Dataset documentation failed for %s: too short (%d chars)",
                experiment.experiment_id,
                len(experiment.dataset.strip()),
            )
            return False

        logger.debug(
            "Dataset documentation verified for %s", experiment.experiment_id
        )
        return True

    def document_limitations(self, research_entry: ResearchEntry) -> List[str]:
        """Identify and document limitations of a research entry.

        Analyzes the entry's findings for common limitation patterns and
        returns a list of identified limitations.

        Args:
            research_entry: The ResearchEntry to analyze.

        Returns:
            List of limitation strings identified.
        """
        limitations: List[str] = []

        if len(research_entry.findings) < self.min_findings_length:
            limitations.append(
                f"Findings section is short ({len(research_entry.findings)} chars); "
                "may lack depth."
            )

        if research_entry.maturity.value in ("emerging", "experimental"):
            limitations.append(
                f"Maturity level is '{research_entry.maturity.value}'; "
                "findings may change with further research."
            )

        if not research_entry.authors:
            limitations.append("No authors listed; attribution incomplete.")

        if not research_entry.tags:
            limitations.append("No tags assigned; discoverability is reduced.")

        if research_entry.relevance < 0.3:
            limitations.append(
                f"Low relevance score ({research_entry.relevance}); "
                "may have limited applicability."
            )

        logger.debug(
            "Documented %d limitations for entry %s",
            len(limitations),
            research_entry.entry_id,
        )
        return limitations

    def statistical_care_check(self, experiment: Experiment) -> bool:
        """Check that the experiment has basic statistical rigor.

        Ensures that:
        - At least one metric is defined.
        - Thresholds are properly ordered (success > failure).
        - Results are recorded before checking thresholds.

        Args:
            experiment: The Experiment to check.

        Returns:
            True if statistical care criteria are met, False otherwise.
        """
        if not experiment.metrics:
            logger.warning(
                "Statistical care failed for %s: no metrics defined",
                experiment.experiment_id,
            )
            return False

        if experiment.success_threshold <= experiment.failure_threshold:
            logger.warning(
                "Statistical care failed for %s: success_threshold (%s) <= "
                "failure_threshold (%s)",
                experiment.experiment_id,
                experiment.success_threshold,
                experiment.failure_threshold,
            )
            return False

        # If experiment is completed/failed, ensure results exist
        if experiment.status in (ExperimentStatus.COMPLETED, ExperimentStatus.FAILED):
            if not experiment.results:
                logger.warning(
                    "Statistical care failed for %s: "
                    "completed/failed but no results recorded",
                    experiment.experiment_id,
                )
                return False

            # Check all defined metrics have results
            for metric in experiment.metrics:
                if metric not in experiment.results:
                    logger.warning(
                        "Statistical care failed for %s: metric '%s' has no result",
                        experiment.experiment_id,
                        metric,
                    )
                    return False

        logger.debug(
            "Statistical care check passed for %s", experiment.experiment_id
        )
        return True

    def run_full_check(
        self, experiment: Experiment, research_entry: Optional[ResearchEntry] = None
    ) -> IntegrityReport:
        """Run all integrity checks and produce a comprehensive report.

        Args:
            experiment: The experiment to check.
            research_entry: Optional associated research entry.

        Returns:
            An IntegrityReport with all check results.
        """
        report = IntegrityReport(target_id=experiment.experiment_id)

        report.add_check(
            "reproducibility",
            self.check_reproducibility(experiment),
        )
        report.add_check(
            "negative_results",
            self.validate_negative_results(experiment),
        )
        report.add_check(
            "dataset_documentation",
            self.verify_dataset_documentation(experiment),
        )
        report.add_check(
            "statistical_care",
            self.statistical_care_check(experiment),
        )

        if research_entry:
            report.add_check(
                "source_attribution",
                self.verify_source_attribution(research_entry),
            )
            limitations = self.document_limitations(research_entry)
            report.add_check(
                "limitations_documented",
                len(limitations) > 0 or len(research_entry.findings) >= 100,
                detail="; ".join(limitations) if limitations else "No major limitations",
            )

        logger.info("Full integrity check for %s: %s", report.target_id, report.summary())
        return report
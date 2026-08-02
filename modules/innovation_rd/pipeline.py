"""
Innovation Pipeline

Orchestrates the full innovation lifecycle from opportunity identification
through to transfer package, running as a sequential workflow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("enterprise.innovation_rd.pipeline")


# ---------------------------------------------------------------------------
# Pipeline Data Transfer Objects (DTOs)
# ---------------------------------------------------------------------------


@dataclass
class Opportunity:
    """A problem or market gap identified for innovation.

    Attributes:
        problem_statement: Description of the problem.
        context: Broader context, including market/technical environment.
        urgency: Urgency level (low, medium, high, critical).
        opportunity_id: Unique identifier.
        created_at: Timestamp.
    """

    problem_statement: str
    context: str = ""
    urgency: str = "medium"
    opportunity_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            self.opportunity_id = f"opp-{uuid4().hex[:12]}"


@dataclass
class Hypothesis:
    """A testable hypothesis derived from an opportunity.

    Attributes:
        statement: The hypothesis statement.
        assumptions: Underlying assumptions.
        null_hypothesis: The null (counter) hypothesis.
        hypothesis_id: Unique identifier.
        created_at: Timestamp.
    """

    statement: str
    assumptions: List[str] = field(default_factory=list)
    null_hypothesis: str = ""
    hypothesis_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            self.hypothesis_id = f"hyp-{uuid4().hex[:12]}"


@dataclass
class ResearchResult:
    """Output of background research on a hypothesis.

    Attributes:
        hypothesis_id: The hypothesis researched.
        findings: Key findings from research.
        references: List of references/sources.
        confidence: Confidence in the findings (0.0 to 1.0).
        gaps: Identified research gaps.
    """

    hypothesis_id: str
    findings: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    confidence: float = 0.0
    gaps: List[str] = field(default_factory=list)


@dataclass
class Assessment:
    """Value, feasibility, and risk assessment.

    Attributes:
        research_id: Reference to the research result.
        value_score: Estimated value (0.0 to 1.0).
        feasibility_score: Feasibility estimate (0.0 to 1.0).
        risk_score: Risk level (0.0 to 1.0, higher = riskier).
        summary: Narrative summary.
        go_no_go: Decision recommendation (True = proceed).
    """

    research_id: str
    value_score: float = 0.0
    feasibility_score: float = 0.0
    risk_score: float = 0.0
    summary: str = ""
    go_no_go: bool = False


@dataclass
class ExperimentDesign:
    """Design specification for an experiment.

    Attributes:
        hypothesis_id: The hypothesis to test.
        methodology: Description of experimental methodology.
        metrics: List of metrics to measure.
        success_criteria: Criteria for success.
        failure_criteria: Criteria for failure.
        required_resources: Resources needed.
    """

    hypothesis_id: str
    methodology: str = ""
    metrics: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    failure_criteria: List[str] = field(default_factory=list)
    required_resources: List[str] = field(default_factory=list)


@dataclass
class Prototype:
    """A built prototype.

    Attributes:
        design_id: Reference to the experiment design.
        version: Prototype version.
        description: Description of the prototype.
        artifacts: List of artifact references (files, URLs, etc.).
        build_log: Build/creation log.
    """

    design_id: str
    version: str = "0.1.0"
    description: str = ""
    artifacts: List[str] = field(default_factory=list)
    build_log: str = ""


@dataclass
class MetricsSnapshot:
    """Measurement snapshot from a prototype evaluation.

    Attributes:
        prototype_id: Reference to the prototype.
        metrics: Dictionary of metric_name -> value.
        timestamp: When the snapshot was taken.
        environment: Description of test environment.
    """

    prototype_id: str
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    environment: str = ""


@dataclass
class Comparison:
    """Comparison of metrics against a baseline.

    Attributes:
        snapshot_id: Reference to the metrics snapshot.
        baseline_id: Reference to the baseline snapshot.
        deltas: Dictionary of metric -> delta value.
        improvement_pct: Dictionary of metric -> improvement percentage.
        winner: Which side "won" (prototype, baseline, or tie).
    """

    snapshot_id: str
    baseline_id: str
    deltas: Dict[str, float] = field(default_factory=dict)
    improvement_pct: Dict[str, float] = field(default_factory=dict)
    winner: str = "tie"


@dataclass
class Decision:
    """Go/no-go decision based on comparison results.

    Attributes:
        comparison_id: Reference to the comparison.
        decision: 'proceed', 'pivot', 'kill', or 'more_research'.
        rationale: Justification for the decision.
        next_steps: Concrete next actions.
        approver: Who approved the decision.
        decided_at: When the decision was made.
    """

    comparison_id: str
    decision: str = "more_research"
    rationale: str = ""
    next_steps: List[str] = field(default_factory=list)
    approver: str = ""
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Documentation:
    """Final documentation package.

    Attributes:
        decision_id: Reference to the decision.
        title: Document title.
        abstract: Executive summary.
        sections: Dictionary of section_name -> content.
        appendices: Additional appendix content.
        version: Document version.
    """

    decision_id: str
    title: str = ""
    abstract: str = ""
    sections: Dict[str, str] = field(default_factory=dict)
    appendices: Dict[str, str] = field(default_factory=dict)
    version: str = "1.0"


@dataclass
class TransferPackage:
    """Package for transferring innovation to production.

    Attributes:
        documentation_id: Reference to the documentation.
        target_team: Team receiving the transfer.
        assets: List of asset references.
        integration_plan: Integration/rollout plan.
        rollback_plan: Rollback strategy.
        sla_requirements: Service-level agreement requirements.
    """

    documentation_id: str
    target_team: str = ""
    assets: List[str] = field(default_factory=list)
    integration_plan: str = ""
    rollback_plan: str = ""
    sla_requirements: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@dataclass
class InnovationPipeline:
    """Orchestrates the full innovation lifecycle.

    Runs a sequential workflow from opportunity identification through to
    transfer package creation. Each stage produces a domain object that
    feeds into the next stage.
    """

    name: str = "default"
    opportunities: Dict[str, Opportunity] = field(default_factory=dict)
    hypotheses: Dict[str, Hypothesis] = field(default_factory=dict)
    research_results: Dict[str, ResearchResult] = field(default_factory=dict)
    assessments: Dict[str, Assessment] = field(default_factory=dict)
    experiment_designs: Dict[str, ExperimentDesign] = field(default_factory=dict)
    prototypes: Dict[str, Prototype] = field(default_factory=dict)
    metrics_snapshots: Dict[str, MetricsSnapshot] = field(default_factory=dict)
    comparisons: Dict[str, Comparison] = field(default_factory=dict)
    decisions: Dict[str, Decision] = field(default_factory=dict)
    documents: Dict[str, Documentation] = field(default_factory=dict)
    transfer_packages: Dict[str, TransferPackage] = field(default_factory=dict)

    # --- Stage 1: Identify Opportunity ---

    def identify_opportunity(
        self, problem_statement: str, context: str = "", urgency: str = "medium"
    ) -> Opportunity:
        """Identify an innovation opportunity from a problem statement.

        Args:
            problem_statement: Description of the problem or market gap.
            context: Broader context (market, technical environment).
            urgency: Urgency level (low, medium, high, critical).

        Returns:
            An Opportunity object.
        """
        opp = Opportunity(
            problem_statement=problem_statement,
            context=context,
            urgency=urgency,
        )
        self.opportunities[opp.opportunity_id] = opp
        logger.info(
            "Identified opportunity '%s': %s",
            opp.opportunity_id,
            problem_statement[:80],
        )
        return opp

    # --- Stage 2: Define Hypothesis ---

    def define_hypothesis(
        self,
        opportunity: Opportunity,
        statement: str,
        assumptions: Optional[List[str]] = None,
        null_hypothesis: str = "",
    ) -> Hypothesis:
        """Define a testable hypothesis from an opportunity.

        Args:
            opportunity: The opportunity to derive the hypothesis from.
            statement: The hypothesis statement.
            assumptions: Underlying assumptions.
            null_hypothesis: The null (counter) hypothesis.

        Returns:
            A Hypothesis object.
        """
        hyp = Hypothesis(
            statement=statement,
            assumptions=assumptions or [],
            null_hypothesis=null_hypothesis,
        )
        self.hypotheses[hyp.hypothesis_id] = hyp
        logger.info("Defined hypothesis '%s': %s", hyp.hypothesis_id, statement[:80])
        return hyp

    # --- Stage 3: Research ---

    def research(
        self,
        hypothesis: Hypothesis,
        findings: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
        confidence: float = 0.0,
    ) -> ResearchResult:
        """Conduct background research on a hypothesis.

        Args:
            hypothesis: The hypothesis to research.
            findings: Key findings from the research.
            references: Source references.
            confidence: Confidence level (0.0 to 1.0).

        Returns:
            A ResearchResult object.
        """
        result = ResearchResult(
            hypothesis_id=hypothesis.hypothesis_id,
            findings=findings or [],
            references=references or [],
            confidence=confidence,
        )
        self.research_results[hypothesis.hypothesis_id] = result
        logger.info(
            "Completed research for hypothesis '%s' (confidence=%.2f)",
            hypothesis.hypothesis_id,
            confidence,
        )
        return result

    # --- Stage 4: Assess Value, Feasibility, Risk ---

    def assess_value_feasibility_risk(
        self,
        research: ResearchResult,
        value_score: float = 0.0,
        feasibility_score: float = 0.0,
        risk_score: float = 0.0,
        summary: str = "",
    ) -> Assessment:
        """Assess the value, feasibility, and risk of a research result.

        Args:
            research: The research result to assess.
            value_score: Estimated value (0.0 to 1.0).
            feasibility_score: Feasibility estimate (0.0 to 1.0).
            risk_score: Risk level (0.0 to 1.0).
            summary: Narrative summary.

        Returns:
            An Assessment object.
        """
        go_no_go = (
            value_score >= 0.5
            and feasibility_score >= 0.5
            and risk_score <= 0.7
        )
        assessment = Assessment(
            research_id=research.hypothesis_id,
            value_score=value_score,
            feasibility_score=feasibility_score,
            risk_score=risk_score,
            summary=summary,
            go_no_go=go_no_go,
        )
        self.assessments[research.hypothesis_id] = assessment
        logger.info(
            "Assessment for '%s': value=%.2f, feasibility=%.2f, risk=%.2f, go=%s",
            research.hypothesis_id,
            value_score,
            feasibility_score,
            risk_score,
            go_no_go,
        )
        return assessment

    # --- Stage 5: Design Experiment ---

    def design_experiment(
        self,
        assessment: Assessment,
        methodology: str = "",
        metrics: Optional[List[str]] = None,
        success_criteria: Optional[List[str]] = None,
        failure_criteria: Optional[List[str]] = None,
        required_resources: Optional[List[str]] = None,
    ) -> ExperimentDesign:
        """Design an experiment based on an assessment.

        Args:
            assessment: The assessment to design from.
            methodology: Experimental methodology description.
            metrics: Metrics to measure.
            success_criteria: Success criteria.
            failure_criteria: Failure criteria.
            required_resources: Required resources.

        Returns:
            An ExperimentDesign object.
        """
        design = ExperimentDesign(
            hypothesis_id=assessment.research_id,
            methodology=methodology,
            metrics=metrics or [],
            success_criteria=success_criteria or [],
            failure_criteria=failure_criteria or [],
            required_resources=required_resources or [],
        )
        self.experiment_designs[assessment.research_id] = design
        logger.info(
            "Designed experiment for '%s': %d metrics, %d criteria",
            assessment.research_id,
            len(metrics or []),
            len(success_criteria or []),
        )
        return design

    # --- Stage 6: Build Prototype ---

    def build_prototype(
        self,
        design: ExperimentDesign,
        version: str = "0.1.0",
        description: str = "",
        artifacts: Optional[List[str]] = None,
        build_log: str = "",
    ) -> Prototype:
        """Build a prototype from an experiment design.

        Args:
            design: The experiment design to build from.
            version: Prototype version string.
            description: Human-readable description.
            artifacts: List of artifact references.
            build_log: Log of the build process.

        Returns:
            A Prototype object.
        """
        proto = Prototype(
            design_id=design.hypothesis_id,
            version=version,
            description=description,
            artifacts=artifacts or [],
            build_log=build_log,
        )
        self.prototypes[design.hypothesis_id] = proto
        logger.info(
            "Built prototype for '%s': version=%s, artifacts=%d",
            design.hypothesis_id,
            version,
            len(artifacts or []),
        )
        return proto

    # --- Stage 7: Measure ---

    def measure(
        self,
        prototype: Prototype,
        metrics: Optional[Dict[str, float]] = None,
        environment: str = "",
    ) -> MetricsSnapshot:
        """Measure prototype performance.

        Args:
            prototype: The prototype to measure.
            metrics: Metric name -> value mapping.
            environment: Test environment description.

        Returns:
            A MetricsSnapshot object.
        """
        snapshot = MetricsSnapshot(
            prototype_id=prototype.design_id,
            metrics=metrics or {},
            environment=environment,
        )
        self.metrics_snapshots[prototype.design_id] = snapshot
        logger.info(
            "Measured prototype '%s': %d metrics in env '%s'",
            prototype.design_id,
            len(metrics or {}),
            environment,
        )
        return snapshot

    # --- Stage 8: Compare ---

    def compare(
        self,
        snapshot: MetricsSnapshot,
        baseline: MetricsSnapshot,
    ) -> Comparison:
        """Compare metrics against a baseline.

        Args:
            snapshot: The prototype metrics snapshot.
            baseline: The baseline metrics snapshot.

        Returns:
            A Comparison object.
        """
        deltas: Dict[str, float] = {}
        improvement_pct: Dict[str, float] = {}

        for metric, value in snapshot.metrics.items():
            baseline_value = baseline.metrics.get(metric, 0.0)
            delta = value - baseline_value
            deltas[metric] = delta
            if baseline_value != 0:
                improvement_pct[metric] = (delta / abs(baseline_value)) * 100
            else:
                improvement_pct[metric] = 0.0

        total_improvement = sum(deltas.values())
        if total_improvement > 0:
            winner = "prototype"
        elif total_improvement < 0:
            winner = "baseline"
        else:
            winner = "tie"

        comp = Comparison(
            snapshot_id=snapshot.prototype_id,
            baseline_id=baseline.prototype_id,
            deltas=deltas,
            improvement_pct=improvement_pct,
            winner=winner,
        )
        self.comparisons[snapshot.prototype_id] = comp
        logger.info("Comparison: winner=%s, deltas=%s", winner, deltas)
        return comp

    # --- Stage 9: Decide ---

    def decide(
        self,
        comparison: Comparison,
        decision: str = "more_research",
        rationale: str = "",
        next_steps: Optional[List[str]] = None,
        approver: str = "",
    ) -> Decision:
        """Make a go/no-go decision based on comparison results.

        Args:
            comparison: The comparison to decide on.
            decision: 'proceed', 'pivot', 'kill', or 'more_research'.
            rationale: Justification.
            next_steps: Concrete next actions.
            approver: Approving authority.

        Returns:
            A Decision object.
        """
        dec = Decision(
            comparison_id=comparison.snapshot_id,
            decision=decision,
            rationale=rationale,
            next_steps=next_steps or [],
            approver=approver,
        )
        self.decisions[comparison.snapshot_id] = dec
        logger.info("Decision for '%s': %s", comparison.snapshot_id, decision)
        return dec

    # --- Stage 10: Document ---

    def document(
        self,
        decision: Decision,
        title: str = "",
        abstract: str = "",
        sections: Optional[Dict[str, str]] = None,
        appendices: Optional[Dict[str, str]] = None,
    ) -> Documentation:
        """Create final documentation for the innovation.

        Args:
            decision: The decision to document.
            title: Document title.
            abstract: Executive summary.
            sections: Section name -> content mapping.
            appendices: Appendix name -> content mapping.

        Returns:
            A Documentation object.
        """
        doc = Documentation(
            decision_id=decision.comparison_id,
            title=title,
            abstract=abstract,
            sections=sections or {},
            appendices=appendices or {},
        )
        self.documents[decision.comparison_id] = doc
        logger.info("Created documentation '%s'", title or decision.comparison_id)
        return doc

    # --- Stage 11: Transfer ---

    def transfer(
        self,
        documentation: Documentation,
        target_team: str = "",
        assets: Optional[List[str]] = None,
        integration_plan: str = "",
        rollback_plan: str = "",
        sla_requirements: Optional[Dict[str, str]] = None,
    ) -> TransferPackage:
        """Package the innovation for transfer to production.

        Args:
            documentation: The documentation to transfer.
            target_team: Receiving team.
            assets: Asset references.
            integration_plan: Rollout plan.
            rollback_plan: Rollback strategy.
            sla_requirements: SLA requirements.

        Returns:
            A TransferPackage object.
        """
        package = TransferPackage(
            documentation_id=documentation.decision_id,
            target_team=target_team,
            assets=assets or [],
            integration_plan=integration_plan,
            rollback_plan=rollback_plan,
            sla_requirements=sla_requirements or {},
        )
        self.transfer_packages[documentation.decision_id] = package
        logger.info(
            "Created transfer package for '%s' -> team '%s'",
            documentation.decision_id,
            target_team,
        )
        return package

    # --- Full Workflow ---

    def run_full_workflow(
        self,
        problem_statement: str,
        hypothesis_statement: str,
        context: str = "",
        urgency: str = "medium",
        assumptions: Optional[List[str]] = None,
        null_hypothesis: str = "",
        research_findings: Optional[List[str]] = None,
        research_references: Optional[List[str]] = None,
        research_confidence: float = 0.7,
        value_score: float = 0.8,
        feasibility_score: float = 0.8,
        risk_score: float = 0.3,
        assessment_summary: str = "",
        methodology: str = "A/B test",
        experiment_metrics: Optional[List[str]] = None,
        success_criteria: Optional[List[str]] = None,
        failure_criteria: Optional[List[str]] = None,
        required_resources: Optional[List[str]] = None,
        prototype_version: str = "0.1.0",
        prototype_description: str = "",
        prototype_artifacts: Optional[List[str]] = None,
        prototype_build_log: str = "",
        measured_metrics: Optional[Dict[str, float]] = None,
        environment: str = "sandbox",
        baseline_metrics: Optional[Dict[str, float]] = None,
        decision_value: str = "proceed",
        decision_rationale: str = "",
        next_steps: Optional[List[str]] = None,
        approver: str = "",
        doc_title: str = "",
        doc_abstract: str = "",
        target_team: str = "",
        integration_plan: str = "",
    ) -> TransferPackage:
        """Run the full innovation pipeline end-to-end.

        Executes all 11 stages sequentially and returns the final
        TransferPackage. Each intermediate result is stored internally.

        Args:
            problem_statement: The problem to solve.
            hypothesis_statement: The testable hypothesis.
            context: Broader context.
            urgency: Urgency level.
            assumptions: Hypothesis assumptions.
            null_hypothesis: Null hypothesis.
            research_findings: Research findings.
            research_references: Research references.
            research_confidence: Confidence in research.
            value_score: Value assessment score.
            feasibility_score: Feasibility score.
            risk_score: Risk score.
            assessment_summary: Assessment narrative.
            methodology: Experiment methodology.
            experiment_metrics: Metrics to measure.
            success_criteria: Success criteria.
            failure_criteria: Failure criteria.
            required_resources: Required resources.
            prototype_version: Prototype version.
            prototype_description: Prototype description.
            prototype_artifacts: Prototype artifacts.
            prototype_build_log: Build log.
            measured_metrics: Measured metrics.
            environment: Test environment.
            baseline_metrics: Baseline metrics for comparison.
            decision_value: Decision (proceed/pivot/kill/more_research).
            decision_rationale: Decision justification.
            next_steps: Next actions.
            approver: Approving authority.
            doc_title: Document title.
            doc_abstract: Executive summary.
            target_team: Receiving team.
            integration_plan: Rollout plan.

        Returns:
            The final TransferPackage.
        """
        logger.info("Starting full innovation pipeline workflow")

        # Stage 1
        opportunity = self.identify_opportunity(
            problem_statement, context, urgency
        )

        # Stage 2
        hypothesis = self.define_hypothesis(
            opportunity, hypothesis_statement, assumptions, null_hypothesis
        )

        # Stage 3
        research = self.research(
            hypothesis, research_findings, research_references, research_confidence
        )

        # Stage 4
        assessment = self.assess_value_feasibility_risk(
            research, value_score, feasibility_score, risk_score, assessment_summary
        )

        # Stage 5
        design = self.design_experiment(
            assessment,
            methodology,
            experiment_metrics,
            success_criteria,
            failure_criteria,
            required_resources,
        )

        # Stage 6
        prototype = self.build_prototype(
            design,
            prototype_version,
            prototype_description,
            prototype_artifacts,
            prototype_build_log,
        )

        # Stage 7
        snapshot = self.measure(
            prototype,
            measured_metrics or {"accuracy": 0.95, "latency": 120},
            environment,
        )

        # Stage 8 - need a baseline snapshot
        baseline_snapshot = MetricsSnapshot(
            prototype_id="baseline-000",
            metrics=baseline_metrics or {"accuracy": 0.85, "latency": 200},
            environment="baseline",
        )
        comparison = self.compare(snapshot, baseline_snapshot)

        # Stage 9
        decision = self.decide(
            comparison,
            decision=decision_value,
            rationale=decision_rationale,
            next_steps=next_steps,
            approver=approver,
        )

        # Stage 10
        documentation = self.document(
            decision, doc_title, doc_abstract
        )

        # Stage 11
        package = self.transfer(
            documentation,
            target_team=target_team,
            integration_plan=integration_plan,
        )

        logger.info("Full pipeline workflow completed")
        return package
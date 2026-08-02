"""
Customer Journey Mapping Engine.

Provides tools to define, analyze, and optimize the path customers
take from initial awareness through advocacy and offboarding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("enterprise.customer_experience")


class JourneyStage(Enum):
    """The lifecycle stages a customer moves through."""

    AWARENESS = "awareness"
    EVALUATION = "evaluation"
    PURCHASE = "purchase"
    SETUP = "setup"
    FIRST_VALUE = "first_value"
    REGULAR_USE = "regular_use"
    SUPPORT = "support"
    EXPANSION = "expansion"
    RENEWAL = "renewal"
    ADVOCACY = "advocacy"
    OFFBOARDING = "offboarding"


@dataclass
class JourneyTouchpoint:
    """A single interaction point along the customer journey."""

    stage: JourneyStage
    touchpoint_name: str
    channel: str
    customer_goal: str
    success_metric: str
    friction_points: List[str] = field(default_factory=list)
    improvement_opportunities: List[str] = field(default_factory=list)

    def add_friction(self, point: str) -> None:
        self.friction_points.append(point)
        logger.debug("Added friction point to '%s': %s", self.touchpoint_name, point)

    def add_opportunity(self, opportunity: str) -> None:
        self.improvement_opportunities.append(opportunity)
        logger.debug(
            "Added improvement opportunity to '%s': %s",
            self.touchpoint_name,
            opportunity,
        )

    def friction_count(self) -> int:
        return len(self.friction_points)

    def opportunity_count(self) -> int:
        return len(self.improvement_opportunities)


@dataclass
class JourneyMap:
    """A complete journey map for a specific customer segment."""

    customer_segment: str
    touchpoints: List[JourneyTouchpoint] = field(default_factory=list)
    current_state_score: float = 0.0
    target_state_score: float = 100.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touchpoint_count(self) -> int:
        return len(self.touchpoints)

    def total_friction_points(self) -> int:
        return sum(tp.friction_count() for tp in self.touchpoints)

    def total_opportunities(self) -> int:
        return sum(tp.opportunity_count() for tp in self.touchpoints)

    def touchpoints_by_stage(self, stage: JourneyStage) -> List[JourneyTouchpoint]:
        return [tp for tp in self.touchpoints if tp.stage == stage]

    def stage_coverage(self) -> Dict[JourneyStage, int]:
        """Return count of touchpoints per stage."""
        coverage: Dict[JourneyStage, int] = {}
        for tp in self.touchpoints:
            coverage[tp.stage] = coverage.get(tp.stage, 0) + 1
        return coverage


class JourneyEngine:
    """Engine for mapping, analyzing, and optimizing customer journeys."""

    STAGE_ORDER: Tuple[JourneyStage, ...] = (
        JourneyStage.AWARENESS,
        JourneyStage.EVALUATION,
        JourneyStage.PURCHASE,
        JourneyStage.SETUP,
        JourneyStage.FIRST_VALUE,
        JourneyStage.REGULAR_USE,
        JourneyStage.SUPPORT,
        JourneyStage.EXPANSION,
        JourneyStage.RENEWAL,
        JourneyStage.ADVOCACY,
        JourneyStage.OFFBOARDING,
    )

    # Default stage weights for scoring (contribution to overall experience)
    DEFAULT_STAGE_WEIGHTS: Dict[JourneyStage, float] = {
        JourneyStage.AWARENESS: 0.08,
        JourneyStage.EVALUATION: 0.12,
        JourneyStage.PURCHASE: 0.10,
        JourneyStage.SETUP: 0.10,
        JourneyStage.FIRST_VALUE: 0.12,
        JourneyStage.REGULAR_USE: 0.15,
        JourneyStage.SUPPORT: 0.08,
        JourneyStage.EXPANSION: 0.08,
        JourneyStage.RENEWAL: 0.10,
        JourneyStage.ADVOCACY: 0.05,
        JourneyStage.OFFBOARDING: 0.02,
    }

    def __init__(self) -> None:
        self._journeys: Dict[str, JourneyMap] = {}
        logger.info("JourneyEngine initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map_journey(
        self,
        customer_segment: str,
        touchpoints: Optional[List[JourneyTouchpoint]] = None,
    ) -> JourneyMap:
        """Create (or retrieve) a journey map for a customer segment.

        If a map for the segment already exists it is returned; otherwise
        a new map is created with the supplied touchpoints.

        Args:
            customer_segment: Identifier for the customer segment.
            touchpoints: Optional initial list of touchpoints.

        Returns:
            The existing or newly-created JourneyMap.
        """
        if customer_segment in self._journeys:
            logger.info("Returning existing journey map for '%s'", customer_segment)
            return self._journeys[customer_segment]

        journey = JourneyMap(
            customer_segment=customer_segment,
            touchpoints=touchpoints or [],
        )
        self._journeys[customer_segment] = journey
        logger.info("Created new journey map for '%s'", customer_segment)
        return journey

    def add_touchpoint(
        self,
        customer_segment: str,
        touchpoint: JourneyTouchpoint,
    ) -> JourneyMap:
        """Add a touchpoint to an existing journey map.

        Creates the map if it does not already exist.
        """
        journey = self.map_journey(customer_segment)
        journey.touchpoints.append(touchpoint)
        journey.last_updated = datetime.now(timezone.utc)
        logger.info(
            "Added touchpoint '%s' to journey '%s'",
            touchpoint.touchpoint_name,
            customer_segment,
        )
        return journey

    def analyze_friction(
        self,
        customer_segment: str,
    ) -> Dict[str, Any]:
        """Analyze friction points across a journey.

        Returns breakdown by stage, top friction points, and severity scores.
        """
        journey = self.map_journey(customer_segment)
        stage_friction: Dict[str, List[str]] = {}
        all_friction: List[Tuple[str, str, int]] = []  # (stage, friction, touchpoint_count)

        for tp in journey.touchpoints:
            key = tp.stage.value
            if key not in stage_friction:
                stage_friction[key] = []
            stage_friction[key].extend(tp.friction_points)

            for fp in tp.friction_points:
                all_friction.append((tp.stage.value, fp, 1))

        total_touchpoints = journey.touchpoint_count()
        total_friction = journey.total_friction_points()
        friction_ratio = (
            total_friction / total_touchpoints if total_touchpoints > 0 else 0.0
        )

        # Determine severity: stages with more friction points per touchpoint
        stage_severity: Dict[str, float] = {}
        for stage_key, points in stage_friction.items():
            stage_tp_count = len(journey.touchpoints_by_stage(JourneyStage(stage_key)))
            stage_severity[stage_key] = (
                len(points) / stage_tp_count if stage_tp_count > 0 else 0.0
            )

        result = {
            "segment": customer_segment,
            "total_friction_points": total_friction,
            "total_touchpoints": total_touchpoints,
            "friction_ratio": round(friction_ratio, 3),
            "friction_by_stage": stage_friction,
            "stage_severity": stage_severity,
            "severity_level": (
                "critical"
                if friction_ratio > 2.0
                else "high"
                if friction_ratio > 1.0
                else "moderate"
                if friction_ratio > 0.5
                else "low"
            ),
        }
        logger.info("Friction analysis complete for '%s'", customer_segment)
        return result

    def calculate_scores(
        self,
        customer_segment: str,
        stage_weights: Optional[Dict[JourneyStage, float]] = None,
    ) -> Dict[str, Any]:
        """Calculate current and target state scores for a journey.

        Score is computed per-stage based on friction severity and weighted
        by the importance of each stage.
        """
        journey = self.map_journey(customer_segment)
        weights = stage_weights or self.DEFAULT_STAGE_WEIGHTS
        stage_scores: Dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0
        for stage in self.STAGE_ORDER:
            tps = journey.touchpoints_by_stage(stage)
            weight = weights.get(stage, 0.0)

            if not tps:
                # Skip stages with no touchpoints
                continue

            friction_ratio = sum(tp.friction_count() for tp in tps) / len(tps)
            # Score decreases as friction increases; 100 = perfect (0 friction)
            stage_score = max(0.0, 100.0 - (friction_ratio * 25.0))

            stage_scores[stage.value] = round(stage_score, 2)
            weighted_sum += stage_score * weight
            total_weight += weight

        current_score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
        journey.current_state_score = current_score

        result = {
            "segment": customer_segment,
            "current_state_score": current_score,
            "target_state_score": journey.target_state_score,
            "gap": round(journey.target_state_score - current_score, 2),
            "stage_scores": stage_scores,
            "last_updated": journey.last_updated.isoformat(),
        }
        logger.info("Score calculated for '%s': %.2f", customer_segment, current_score)
        return result

    def identify_optimizations(
        self,
        customer_segment: str,
        top_n: int = 5,
    ) -> List[Dict[str, Any]]:
        """Identify the highest-impact optimization opportunities.

        Returns the top N opportunities sorted by potential impact.
        """
        journey = self.map_journey(customer_segment)
        friction = self.analyze_friction(customer_segment)
        opportunities: List[Dict[str, Any]] = []

        for tp in journey.touchpoints:
            for opp in tp.improvement_opportunities:
                opportunities.append(
                    {
                        "touchpoint": tp.touchpoint_name,
                        "stage": tp.stage.value,
                        "channel": tp.channel,
                        "opportunity": opp,
                        "friction_count": tp.friction_count(),
                        "impact_score": tp.friction_count() * 10
                        + (1 if tp.stage in self.DEFAULT_STAGE_WEIGHTS else 0)
                        * self.DEFAULT_STAGE_WEIGHTS.get(tp.stage, 0)
                        * 100,
                    }
                )

        # Sort by impact score descending
        opportunities.sort(key=lambda x: x["impact_score"], reverse=True)
        logger.info(
            "Identified %d optimizations for '%s'", len(opportunities), customer_segment
        )
        return opportunities[:top_n]

    def compare_segments(
        self,
        segment_a: str,
        segment_b: str,
    ) -> Dict[str, Any]:
        """Compare two customer segment journeys side by side."""
        scores_a = self.calculate_scores(segment_a)
        scores_b = self.calculate_scores(segment_b)
        friction_a = self.analyze_friction(segment_a)
        friction_b = self.analyze_friction(segment_b)

        comparison = {
            "segment_a": {
                "name": segment_a,
                "score": scores_a["current_state_score"],
                "friction_ratio": friction_a["friction_ratio"],
                "touchpoints": friction_a["total_touchpoints"],
            },
            "segment_b": {
                "name": segment_b,
                "score": scores_b["current_state_score"],
                "friction_ratio": friction_b["friction_ratio"],
                "touchpoints": friction_b["total_touchpoints"],
            },
            "score_delta": round(
                scores_a["current_state_score"] - scores_b["current_state_score"], 2
            ),
            "better_segment": (
                segment_a
                if scores_a["current_state_score"] > scores_b["current_state_score"]
                else segment_b
            ),
        }
        logger.info("Compared segments '%s' vs '%s'", segment_a, segment_b)
        return comparison

    def generate_journey_report(
        self,
        customer_segment: str,
    ) -> Dict[str, Any]:
        """Generate a comprehensive journey report for a segment."""
        journey = self.map_journey(customer_segment)
        scores = self.calculate_scores(customer_segment)
        friction = self.analyze_friction(customer_segment)
        optimizations = self.identify_optimizations(customer_segment)

        report = {
            "report_type": "customer_journey",
            "segment": customer_segment,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overview": {
                "touchpoint_count": journey.touchpoint_count(),
                "stage_coverage": {
                    s.value: journey.stage_coverage().get(s, 0)
                    for s in self.STAGE_ORDER
                },
                "current_score": scores["current_state_score"],
                "target_score": scores["target_state_score"],
                "gap": scores["gap"],
            },
            "friction_analysis": {
                "severity": friction["severity_level"],
                "friction_ratio": friction["friction_ratio"],
                "stage_severity": friction["stage_severity"],
            },
            "stage_scores": scores["stage_scores"],
            "top_optimizations": optimizations,
            "last_journey_update": journey.last_updated.isoformat(),
        }
        logger.info("Generated journey report for '%s'", customer_segment)
        return report
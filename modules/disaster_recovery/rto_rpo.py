"""
Recovery Time Objective (RTO) and Recovery Point Objective (RPO) planning.

Defines recovery objectives, validates feasibility, schedules recovery steps,
and allocates resources across recovery tiers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("enterprise.disaster_recovery.rto_rpo")


class RecoveryTier(str, Enum):
    """Recovery tier based on target RTO."""

    TIER_0_ZERO = "tier_0_zero"          # Zero downtime; instantaneous failover
    TIER_1_MINUTES = "tier_1_minutes"     # RTO < 15 min
    TIER_2_HOURS = "tier_2_hours"        # RTO 15 min - 4 hours
    TIER_3_DAYS = "tier_3_days"          # RTO > 4 hours


@dataclass
class RTOPlan:
    """A single service's recovery objective plan."""

    service_name: str
    rto_minutes: float
    rpo_minutes: float
    max_tolerable_downtime: float     # business-agreed max downtime in minutes
    min_service_level: float           # fraction 0.0-1.0 of capacity required
    recovery_priority: int             # lower = higher priority
    required_personnel: List[str] = field(default_factory=list)
    required_infrastructure: List[str] = field(default_factory=list)
    required_data_sources: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def recovery_tier(self) -> RecoveryTier:
        """Derive recovery tier from RTO."""
        if self.rto_minutes < 1:
            return RecoveryTier.TIER_0_ZERO
        elif self.rto_minutes <= 15:
            return RecoveryTier.TIER_1_MINUTES
        elif self.rto_minutes <= 240:
            return RecoveryTier.TIER_2_HOURS
        return RecoveryTier.TIER_3_DAYS

    @property
    def data_loss_window_minutes(self) -> float:
        """How many minutes of data may be lost (alias for RPO)."""
        return self.rpo_minutes

    def to_dict(self) -> dict:
        return {
            "service_name": self.service_name,
            "rto_minutes": self.rto_minutes,
            "rpo_minutes": self.rpo_minutes,
            "recovery_tier": self.recovery_tier.value,
            "max_tolerable_downtime": self.max_tolerable_downtime,
            "min_service_level": self.min_service_level,
            "recovery_priority": self.recovery_priority,
        }


class RTOPlanner:
    """
    RTO/RPO planning engine.

    Defines recovery objectives for each service, validates feasibility against
    infrastructure constraints, and generates recovery schedules.
    """

    # Industry-benchmark data for feasibility checks
    _INFRA_PROVISION_SPEED: Dict[str, float] = {
        "container": 2.0,       # minutes to spin up
        "vm": 10.0,
        "bare_metal": 30.0,
        "database_failover": 5.0,
        "cdn_propagation": 15.0,
        "dns_propagation": 30.0,
        "kubernetes_cluster": 15.0,
    }

    def __init__(self) -> None:
        self._plans: Dict[str, RTOPlan] = {}
        self._resource_pool: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Objective definition
    # ------------------------------------------------------------------

    def define_recovery_objective(
        self,
        service_name: str,
        rto_minutes: float,
        rpo_minutes: float,
        max_tolerable_downtime: float,
        min_service_level: float = 1.0,
        recovery_priority: int = 100,
        required_personnel: Optional[List[str]] = None,
        required_infrastructure: Optional[List[str]] = None,
        required_data_sources: Optional[List[str]] = None,
    ) -> RTOPlan:
        """Define or update recovery objectives for a service."""
        plan = RTOPlan(
            service_name=service_name,
            rto_minutes=rto_minutes,
            rpo_minutes=rpo_minutes,
            max_tolerable_downtime=max_tolerable_downtime,
            min_service_level=min_service_level,
            recovery_priority=recovery_priority,
            required_personnel=required_personnel or [],
            required_infrastructure=required_infrastructure or [],
            required_data_sources=required_data_sources or [],
        )
        self._plans[service_name] = plan
        logger.info(
            "Defined RTO plan for %s: RTO=%.1fm, RPO=%.1fm, tier=%s",
            service_name,
            rto_minutes,
            rpo_minutes,
            plan.recovery_tier.value,
        )
        return plan

    def get_plan(self, service_name: str) -> Optional[RTOPlan]:
        """Retrieve the RTO plan for a service."""
        return self._plans.get(service_name)

    # ------------------------------------------------------------------
    # Calculation helpers
    # ------------------------------------------------------------------

    def calculate_rto(
        self,
        infrastructure_type: str,
        data_restore_time_minutes: float,
        service_startup_time_minutes: float,
        validation_time_minutes: float,
    ) -> float:
        """Calculate expected RTO from component timings."""
        provision_time = self._INFRA_PROVISION_SPEED.get(infrastructure_type, 15.0)
        total = provision_time + data_restore_time_minutes + service_startup_time_minutes + validation_time_minutes
        logger.debug(
            "Calculated RTO: provision=%.1f + restore=%.1f + startup=%.1f + validation=%.1f = %.1fm",
            provision_time,
            data_restore_time_minutes,
            service_startup_time_minutes,
            validation_time_minutes,
            total,
        )
        return total

    def calculate_rpo(
        self,
        backup_frequency_minutes: float,
        replication_lag_minutes: float = 0.0,
    ) -> float:
        """Calculate expected RPO from backup frequency and replication lag."""
        return backup_frequency_minutes + replication_lag_minutes

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_feasibility(
        self,
        service_name: str,
        available_infrastructure: List[str],
        available_personnel: List[str],
        available_data_sources: List[str],
    ) -> Tuple[bool, List[str]]:
        """Check if a recovery plan is feasible given available resources.

        Returns (feasible, list_of_gaps).
        """
        plan = self._plans.get(service_name)
        if plan is None:
            return False, [f"No plan defined for {service_name}"]

        gaps: List[str] = []

        missing_infra = set(plan.required_infrastructure) - set(available_infrastructure)
        if missing_infra:
            gaps.append(f"Missing infrastructure: {', '.join(sorted(missing_infra))}")

        missing_personnel = set(plan.required_personnel) - set(available_personnel)
        if missing_personnel:
            gaps.append(f"Missing personnel: {', '.join(sorted(missing_personnel))}")

        missing_data = set(plan.required_data_sources) - set(available_data_sources)
        if missing_data:
            gaps.append(f"Missing data sources: {', '.join(sorted(missing_data))}")

        if plan.rto_minutes > plan.max_tolerable_downtime:
            gaps.append(
                f"RTO ({plan.rto_minutes:.1f}m) exceeds max tolerable "
                f"downtime ({plan.max_tolerable_downtime:.1f}m)"
            )

        feasible = len(gaps) == 0
        if feasible:
            logger.info("Feasibility check for %s: PASSED", service_name)
        else:
            logger.warning("Feasibility check for %s: FAILED — %d gaps found", service_name, len(gaps))
        return feasible, gaps

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def generate_recovery_schedule(self) -> List[Tuple[str, float, float]]:
        """Generate an ordered recovery schedule.

        Returns list of (service_name, start_offset_minutes, estimated_duration_minutes)
        sorted by recovery priority.
        """
        sorted_plans = sorted(self._plans.values(), key=lambda p: p.recovery_priority)
        schedule: List[Tuple[str, float, float]] = []
        current_offset = 0.0

        for plan in sorted_plans:
            schedule.append((plan.service_name, current_offset, plan.rto_minutes))
            current_offset += plan.rto_minutes

        logger.info(
            "Generated recovery schedule: %d services, total time=%.1fm",
            len(schedule),
            current_offset,
        )
        return schedule

    # ------------------------------------------------------------------
    # Resource allocation
    # ------------------------------------------------------------------

    def allocate_resources(
        self,
        resource_name: str,
        total_capacity: int,
    ) -> Dict[str, int]:
        """Allocate a resource across services proportional to priority.

        Returns a mapping of service_name -> allocated units.
        """
        sorted_plans = sorted(self._plans.values(), key=lambda p: p.recovery_priority)
        # Inverse priority weighting: lower number = higher need
        total_inv_priority = sum(1.0 / max(1, p.recovery_priority) for p in sorted_plans)

        allocation: Dict[str, int] = {}
        remaining = total_capacity

        for plan in sorted_plans[:-1]:
            weight = (1.0 / max(1, plan.recovery_priority)) / total_inv_priority
            allocated = max(1, int(total_capacity * weight))
            allocation[plan.service_name] = allocated
            remaining -= allocated

        if sorted_plans:
            allocation[sorted_plans[-1].service_name] = max(remaining, 1)

        self._resource_pool[resource_name] = total_capacity
        logger.info(
            "Allocated %s (%d units): %s",
            resource_name,
            total_capacity,
            allocation,
        )
        return allocation
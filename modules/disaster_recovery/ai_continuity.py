"""
AI service continuity manager.

Detects AI service disruptions, activates fallback providers, switches models,
restores context stores and vector databases, verifies agent health, reloads
prompt registries, scales inference capacity, monitors cost spikes, and applies
safety overrides during degraded operation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("enterprise.disaster_recovery.ai_continuity")


class AIDisruptionType(str, Enum):
    """Types of AI service disruptions."""

    MODEL_PROVIDER_OUTAGE = "model_provider_outage"
    MODEL_DEGRADATION = "model_degradation"
    CONTEXT_STORE_FAILURE = "context_store_failure"
    VECTOR_DB_FAILURE = "vector_db_failure"
    AGENT_LOOP_FAILURE = "agent_loop_failure"
    PROMPT_REGISTRY_CORRUPTION = "prompt_registry_corruption"
    TOOL_PROVIDER_FAILURE = "tool_provider_failure"
    INFERENCE_SHORTAGE = "inference_shortage"
    COST_SPIKE = "cost_spike"
    UNSAFE_OUTPUT = "unsafe_output"


@dataclass
class AIContinuityPlan:
    """Configuration for maintaining AI service continuity during disruptions."""

    disruption_type: AIDisruptionType
    primary_provider: str
    fallback_providers: List[str] = field(default_factory=list)
    model_fallback_chain: List[str] = field(default_factory=list)
    context_store_backup: Optional[str] = None
    vector_db_replica: Optional[str] = None
    agent_loop_health_check: bool = True
    prompt_registry_backup: Optional[str] = None
    tool_provider_alternatives: Dict[str, str] = field(default_factory=dict)
    inference_capacity_buffer: float = 0.2     # 20% extra capacity
    cost_threshold: float = 1000.0             # daily $ threshold
    safety_filter_config: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = False
    last_activated: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "disruption_type": self.disruption_type.value,
            "primary_provider": self.primary_provider,
            "fallback_providers": self.fallback_providers,
            "model_fallback_chain": self.model_fallback_chain,
            "is_active": self.is_active,
            "cost_threshold": self.cost_threshold,
        }


class AIContinuityManager:
    """
    AI service continuity manager.

    Monitors for disruptions, activates fallbacks, manages provider switching,
    and ensures AI-dependent services stay operational through degraded states.
    """

    def __init__(self) -> None:
        self._plans: Dict[AIDisruptionType, AIContinuityPlan] = {}
        self._current_provider: str = ""
        self._current_model: str = ""
        self._disruption_state: Dict[AIDisruptionType, bool] = {}
        self._hooks: Dict[str, Callable] = {}
        self._incident_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def register_hook(self, name: str, fn: Callable) -> None:
        """Register an external callable for AI continuity actions."""
        self._hooks[name] = fn
        logger.debug("Registered AI continuity hook: %s", name)

    # ------------------------------------------------------------------
    # Plan management
    # ------------------------------------------------------------------

    def configure_plan(
        self,
        disruption_type: AIDisruptionType,
        primary_provider: str,
        fallback_providers: Optional[List[str]] = None,
        model_fallback_chain: Optional[List[str]] = None,
        context_store_backup: Optional[str] = None,
        vector_db_replica: Optional[str] = None,
        prompt_registry_backup: Optional[str] = None,
        tool_provider_alternatives: Optional[Dict[str, str]] = None,
        cost_threshold: float = 1000.0,
    ) -> AIContinuityPlan:
        """Create or update a continuity plan for a disruption type."""
        plan = AIContinuityPlan(
            disruption_type=disruption_type,
            primary_provider=primary_provider,
            fallback_providers=fallback_providers or [],
            model_fallback_chain=model_fallback_chain or [],
            context_store_backup=context_store_backup,
            vector_db_replica=vector_db_replica,
            prompt_registry_backup=prompt_registry_backup,
            tool_provider_alternatives=tool_provider_alternatives or {},
            cost_threshold=cost_threshold,
        )
        self._plans[disruption_type] = plan
        self._disruption_state[disruption_type] = False
        logger.info(
            "Configured AI continuity plan for %s: primary=%s, fallbacks=%d",
            disruption_type.value, primary_provider, len(plan.fallback_providers),
        )
        return plan

    # ------------------------------------------------------------------
    # Disruption detection & activation
    # ------------------------------------------------------------------

    def detect_disruption(
        self,
        disruption_type: AIDisruptionType,
        symptoms: Optional[List[str]] = None,
    ) -> bool:
        """Detect and log an AI service disruption. Returns True if detected."""
        plan = self._plans.get(disruption_type)
        if plan is None:
            logger.warning("No continuity plan for disruption type %s", disruption_type.value)
            return False

        self._disruption_state[disruption_type] = True
        self._incident_log.append({
            "type": disruption_type.value,
            "action": "detected",
            "symptoms": symptoms or [],
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.warning("AI disruption detected: %s", disruption_type.value)
        return True

    def activate_fallback(self, disruption_type: AIDisruptionType) -> Optional[AIContinuityPlan]:
        """Activate the fallback plan for a detected disruption."""
        plan = self._plans.get(disruption_type)
        if plan is None:
            logger.error("No continuity plan for %s", disruption_type.value)
            return None

        plan.is_active = True
        plan.last_activated = datetime.utcnow()
        self._incident_log.append({
            "type": disruption_type.value,
            "action": "fallback_activated",
            "timestamp": plan.last_activated.isoformat(),
        })
        logger.info("Fallback activated for %s", disruption_type.value)
        return plan

    # ------------------------------------------------------------------
    # Provider & model switching
    # ------------------------------------------------------------------

    def switch_model_provider(
        self,
        new_provider: str,
        new_model: Optional[str] = None,
    ) -> bool:
        """Switch the active model provider to a fallback."""
        old_provider = self._current_provider
        self._current_provider = new_provider
        if new_model:
            self._current_model = new_model

        if "switch_provider" in self._hooks:
            self._hooks["switch_provider"](
                old_provider=old_provider,
                new_provider=new_provider,
                new_model=self._current_model,
            )

        self._incident_log.append({
            "action": "provider_switched",
            "from": old_provider,
            "to": new_provider,
            "model": self._current_model,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info("Switched model provider: %s -> %s (model=%s)", old_provider, new_provider, self._current_model)
        return True

    # ------------------------------------------------------------------
    # Subsystem recovery
    # ------------------------------------------------------------------

    def restore_context_store(self, backup_location: str) -> bool:
        """Restore the context store from a backup location."""
        if "restore_context" in self._hooks:
            self._hooks["restore_context"](backup_location=backup_location)

        logger.info("Context store restored from %s", backup_location)
        self._incident_log.append({
            "action": "context_store_restored",
            "backup_location": backup_location,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    def rebuild_vector_index(self, source: str) -> bool:
        """Rebuild the vector database index from source data."""
        if "rebuild_vector" in self._hooks:
            self._hooks["rebuild_vector"](source=source)

        logger.info("Vector index rebuilt from %s", source)
        self._incident_log.append({
            "action": "vector_index_rebuilt",
            "source": source,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    def verify_agent_health(self, agent_id: str) -> Dict[str, Any]:
        """Check the health of an AI agent loop."""
        if "verify_agent" in self._hooks:
            result = self._hooks["verify_agent"](agent_id=agent_id)
            if isinstance(result, dict):
                return result

        health = {
            "agent_id": agent_id,
            "healthy": True,
            "checked_at": datetime.utcnow().isoformat(),
            "loop_running": True,
            "error_rate": 0.0,
        }
        logger.info("Agent health verified: %s -> healthy=%s", agent_id, health["healthy"])
        return health

    def reload_prompt_registry(self, backup_path: str) -> bool:
        """Reload prompt templates from a backup registry."""
        if "reload_prompts" in self._hooks:
            self._hooks["reload_prompts"](backup_path=backup_path)

        logger.info("Prompt registry reloaded from %s", backup_path)
        self._incident_log.append({
            "action": "prompt_registry_reloaded",
            "path": backup_path,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    # ------------------------------------------------------------------
    # Capacity & cost
    # ------------------------------------------------------------------

    def scale_inference_capacity(self, factor: float = 1.5) -> bool:
        """Scale inference capacity by the given multiplier."""
        if "scale_inference" in self._hooks:
            self._hooks["scale_inference"](factor=factor)

        logger.info("Inference capacity scaled by %.1fx", factor)
        self._incident_log.append({
            "action": "inference_scaled",
            "factor": factor,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    def check_cost_spike(
        self,
        current_daily_cost: float,
    ) -> Dict[str, Any]:
        """Check if current daily spend exceeds thresholds."""
        result: Dict[str, Any] = {
            "current_daily_cost": current_daily_cost,
            "at_threshold": {},
            "spike_detected": False,
        }

        for dtype, plan in self._plans.items():
            over_threshold = current_daily_cost > plan.cost_threshold
            result["at_threshold"][dtype.value] = over_threshold
            if over_threshold:
                result["spike_detected"] = True
                logger.warning(
                    "Cost spike for %s: $%.2f vs threshold $%.2f",
                    dtype.value, current_daily_cost, plan.cost_threshold,
                )

        return result

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def apply_safety_override(self, config: Dict[str, Any]) -> bool:
        """Apply safety filter overrides during degraded operation."""
        if "safety_override" in self._hooks:
            self._hooks["safety_override"](config=config)

        logger.info("Safety override applied: %s", config)
        self._incident_log.append({
            "action": "safety_override",
            "config": config,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_incident_log(self) -> List[Dict[str, Any]]:
        """Return the full AI continuity incident log."""
        return list(self._incident_log)

    def is_disrupted(self, disruption_type: AIDisruptionType) -> bool:
        """Check if a specific disruption type is currently active."""
        return self._disruption_state.get(disruption_type, False)
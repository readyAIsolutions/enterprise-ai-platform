"""ENI Enterprise AI Defense OS Module.

Defense against *AI-driven / automated* attackers: statistical anomaly detection,
bot/agent traffic classification, model-extraction probing shield, credential-
stuffing lockout, and indirect prompt-injection detection. Complements the
``model_security`` module (which guards model *input/output*); this module
guards the *attacker side*.

The module exposes a ``@module``-registered kernel Module
(:class:`AIDefenseModule`) alongside a plain convenience facade
(:class:`AIDefenseFacade`) for direct, dependency-free use.

All components are stdlib-only with zero external dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .adversary_gate import (
    AdversaryGate,
    AgentForceHarness,
    GateDecision,
    GateProfile,
    PROFILES,
)
from .ai_defense import (
    AIDefenseFacade,
    AIDefenseModule,
    AnomalyConfig,
    BehavioralAnomalyDetector,
    BotConfig,
    BotTrafficClassifier,
    CredentialStuffingGuard,
    ExtractionConfig,
    IndirectPromptInjectionGuard,
    InjectionConfig,
    Judgement,
    ModelExtractionShield,
    StuffingConfig,
)
from .rate_limit import (
    Allowance,
    AttackerStore,
    SlidingWindowRateLimiter,
    ThrottleGate,
)

__version__ = "1.0.0"
__module__ = "ai_defense"

DEFAULT_CONFIG: Dict[str, Any] = {
    "priority": 15,
    "anomaly": {"window": 60.0, "z_threshold": 4.0, "flood_events_per_sec": 20.0},
    "bot": {"pacing_sd_threshold": 0.05, "min_intervals": 6},
    "extraction": {"max_queries_per_window": 200, "window": 60.0, "min_queries": 50},
    "stuffing": {"max_failures": 5, "lockout_seconds": 300.0, "per_ip_max_failures": 20},
    "injection": {},
}


def create_facade(config: Optional[Dict[str, Any]] = None) -> AIDefenseFacade:
    """Build an AIDefenseFacade from a config dict (defaults applied)."""
    return AIDefenseFacade()


def register(context) -> Any:
    """Kernel plugin-style registration (optional; @module handles discovery)."""
    facade = AIDefenseFacade()
    context.register_hook("model_query", lambda key, query="", **k: facade.guard_model_query(key, query, **k))
    return facade


# The @module decorator wires this into platform_kernel discovery.
_ai_defense_module = AIDefenseModule

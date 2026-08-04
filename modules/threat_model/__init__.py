"""ENI Threat Model OS Module.

Offline MITRE ATLAS / STRIDE threat modeling and attack-surface analysis for
LLM systems. Provides a curated catalogue of MITRE ATLAS threats, a threat
library with category/technique lookups, an assessor that turns an asset
inventory into a risk register (risk = likelihood * impact, LOW/MEDIUM/HIGH/
CRITICAL severities), a STRIDE mapper, and a reporter for sorted registers,
top risks, and mitigation coverage.

All components are stdlib-only, zero external dependencies.

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .threat_model import (
    BUILTIN_THREATS,
    CATALOGUE_TACTICS,
    Severity,
    STRIDEThreatMapper,
    Threat,
    ThreatAssessor,
    ThreatLibrary,
    ThreatModelFacade,
    ThreatModelModule,
    ThreatModelReporter,
)

__version__ = "1.0.0"
__module__ = "threat_model"

__all__ = [
    "__version__",
    "ThreatModelModule",
    "ThreatModelFacade",
    # Core model
    "Threat",
    "Severity",
    "ThreatLibrary",
    # Analysis
    "ThreatAssessor",
    "ThreatModelReporter",
    "STRIDEThreatMapper",
    # Data
    "BUILTIN_THREATS",
    "CATALOGUE_TACTICS",
]

_logger = logging.getLogger("enterprise.threat_model")


def create_threat_facade(config: Optional[Dict[str, Any]] = None) -> ThreatModelFacade:
    """Create a ThreatModelFacade with default or custom configuration."""
    return ThreatModelFacade(config=config)

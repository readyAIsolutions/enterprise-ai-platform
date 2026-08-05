"""ENI Universal Build Score module.

One accurate, industry-grounded build-quality number that tests any real
software build on disk and certifies it. 100 = fully sellable enterprise;
a excellence bonus lets transcendent builds exceed 100 (the singularity band).

This module is the canonical home for build-quality scoring in the platform.
It is the anti-stub: every dimension is computed from real filesystem / code
inspection probes, never hardcoded.

Version: 1.0.0
"""

from __future__ import annotations

from typing import Any, Dict, Optional  # noqa: F401

from enterprise.modules.universal_score.coverage_fleet import (
    CoverageError,
    CoverageProbe,
    CoverageReport,
    run_fleet_coverage,
)
from enterprise.modules.universal_score.universal_score import (
    DIMENSION_WEIGHTS,
    SECRET_PATTERNS,
    CertificationLevel,
    Dimension,
    DimensionResult,
    HardGate,
    SubSignal,
    UniversalBuildScore,
    UniversalScoreModule,
    certification_for_score,
    create_universal_score_module,
)

__version__ = "1.0.0"
__module_name__ = "universal_score"

__all__ = [
    "UniversalBuildScore",
    "UniversalScoreModule",
    "create_universal_score_module",
    "Dimension",
    "DimensionResult",
    "SubSignal",
    "HardGate",
    "CertificationLevel",
    "certification_for_score",
    "DIMENSION_WEIGHTS",
    "SECRET_PATTERNS",
    "CoverageProbe",
    "CoverageReport",
    "CoverageError",
    "run_fleet_coverage",
    "__version__",
    "__module_name__",
]

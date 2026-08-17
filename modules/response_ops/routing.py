"""Response Ops — ICM-as-routing-brain hook (Upgrade A4).

Exposes a tiny broker-facing hook, :func:`icm_preflight`, so an orchestration /
routing broker can consult the ICM classifier *before* committing a goal to a
particular execution lane. The hook returns a compact routing verdict:

    {"route": "sequential" | "swarm", "sequential": bool}

``route == "sequential"`` means the goal maps to deterministic, single-agent
ICM work; ``route == "swarm"`` means the goal is judgment-heavy and should be
sent to the multi-agent swarm layer.

The hook imports the canonical classification function live from the ICM module
(``enterprise.modules.icm.classify``) so it always tracks the source of truth
and requires no mirrored copy of the keyword tables.

Version: 1.0.0 | Python: 3.11+
"""
from __future__ import annotations

from typing import Any, Dict


def _load_classify():
    """Import the ICM ``classify`` function, preferring a dedicated module.

    The canonical implementation lives in ``enterprise.modules.icm`` (exported
    from ``modules/icm/icm.py``). We first attempt ``enterprise.modules.icm.
    classify`` in case a standalone ``classify.py`` shim exists, then fall back
    to the package-level ``classify`` function.
    """
    try:  # preferred: a dedicated icm.classify submodule
        from enterprise.modules.icm.classify import classify  # type: ignore

        return classify
    except Exception:
        pass
    try:  # canonical: the classify function re-exported by the icm package
        from enterprise.modules.icm import classify  # type: ignore

        return classify
    except Exception as exc:  # pragma: no cover - degenerate env
        raise RuntimeError(
            "icm_preflight: unable to import enterprise.modules.icm.classify"
        ) from exc


def icm_preflight(goal: str) -> Dict[str, Any]:
    """Classify a goal and return a routing verdict for a broker.

    Args:
        goal: Free-text task / goal description to route.

    Returns:
        ``{"route": "sequential" | "swarm", "sequential": bool}`` where
        ``sequential`` is ``True`` exactly when ``route == "sequential"``.
    """
    classify = _load_classify()
    route = classify(goal)
    return {"route": route, "sequential": route == "sequential"}


__all__ = ["icm_preflight"]

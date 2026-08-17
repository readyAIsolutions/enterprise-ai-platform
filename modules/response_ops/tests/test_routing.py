"""Unit tests for the ICM-as-routing-brain hook (response_ops.routing.icm_preflight).

Proves the hook returns the expected route for a compliance task (sequential /
deterministic ICM lane) and a legal-reasoning task (swarm lane), and that the
returned dict always carries the documented keys with a boolean ``sequential``.
"""
from __future__ import annotations

from enterprise.modules.response_ops import icm_preflight


def test_compliance_task_routes_sequential():
    """A compliance task is deterministic, auditable work -> sequential ICM."""
    result = icm_preflight("Run a compliance review and export the audit report")
    assert result == {"route": "sequential", "sequential": True}


def test_legal_reasoning_task_routes_swarm():
    """Legal reasoning is judgment-heavy -> swarm (non-sequential)."""
    result = icm_preflight(
        "Perform legal reasoning and cross-validation on this contract dispute"
    )
    assert result == {"route": "swarm", "sequential": False}


def test_result_shape_is_stable():
    """Always 'route' + 'sequential' with a boolean flag."""
    for goal in (
        "verify the deployment checklist",
        "generate a creative brief for the team",
    ):
        result = icm_preflight(goal)
        assert set(result.keys()) == {"route", "sequential"}
        assert result["route"] in ("sequential", "swarm")
        assert isinstance(result["sequential"], bool)
        assert result["sequential"] == (result["route"] == "sequential")


def test_via_direct_module_import():
    """The hook is reachable from the routing submodule directly."""
    from enterprise.modules.response_ops.routing import icm_preflight as direct

    assert direct("assess legal exposure") == {"route": "swarm", "sequential": False}

"""Tests for the ai_systems_thinking systems-thinking evaluation module."""
from __future__ import annotations

from pathlib import Path

import pytest

from enterprise.modules.ai_systems_thinking import (
    AISystemDesign,
    Component,
    Connection,
    CouplingStrength,
    DesignContext,
    FeedbackLoop,
    Governance,
    LoopType,
    OverallRead,
    RiskLevel,
    SystemsThinker,
    assess,
    create_ai_systems_thinking_module,
)


def _weak_design() -> AISystemDesign:
    """A tightly coupled, opaque, consequence-blind design."""
    return AISystemDesign(
        name="monolith-swarm",
        components=[
            Component(name="agent7", function="all-in-one", coupling=CouplingStrength.TIGHT,
                      responsibilities=4, self_evaluates=False, logged=False,
                      cost_tracked=False, approved=False),
            Component(name="agent8", function="another-all-in-one", coupling=CouplingStrength.TIGHT,
                      responsibilities=3, self_evaluates=False, logged=False,
                      cost_tracked=False, approved=False),
        ],
        connections=[
            Connection("agent7", "agent8"),
            Connection("agent8", "agent7"),
        ],
        context=DesignContext(progressive_disclosure=False, minimal_complexity=False),
        governance=Governance(),
    )


def _strong_design() -> AISystemDesign:
    """A decoupled, traceable, second-order-aware design with feedback loops."""
    return AISystemDesign(
        name="folder-first",
        components=[
            Component(name="ui", function="front desk", coupling=CouplingStrength.LOOSE,
                      responsibilities=1, logged=True, cost_tracked=True, approved=True,
                      self_evaluates=True),
            Component(name="catalog", function="progressive-disclosure index",
                      coupling=CouplingStrength.LOOSE, responsibilities=1, logged=True,
                      cost_tracked=True, approved=True, self_evaluates=True),
            Component(name="retriever", function="request slips / rag",
                      coupling=CouplingStrength.LOOSE, responsibilities=1, logged=True,
                      cost_tracked=True, approved=True, self_evaluates=True),
        ],
        connections=[
            Connection("ui", "catalog"),
            Connection("catalog", "retriever"),
            Connection("retriever", "ui"),
        ],
        feedback_loops=[
            FeedbackLoop(name="folder-write-back", components=("retriever", "catalog", "ui"),
                         loop_type=LoopType.BALANCING, persistent=True,
                         verifies_ground_truth=True, described_second_order=True),
        ],
        context=DesignContext(progressive_disclosure=True, minimal_complexity=True,
                              universal_interface=True, interface_count=1),
        governance=Governance(human_in_the_loop=True, accounts_for_human_variability=True,
                              second_order_analysis=True, emergence_documented=True,
                              stakeholder_viewed=True),
    )


# --------------------------------------------------------------------------- #
# Core engine
# --------------------------------------------------------------------------- #
def test_weak_design_is_fragile():
    a = assess(_weak_design())
    assert a.overall == OverallRead.FRAGILE
    assert a.overall_score < 0.4


def test_strong_design_is_excellent():
    a = assess(_strong_design())
    assert a.overall == OverallRead.EXCELLENT
    assert a.overall_score >= 0.8


def test_modularity_improves_with_decoupling_and_universal_interface():
    loose = AISystemDesign(
        name="loose",
        components=[Component("a", coupling=CouplingStrength.LOOSE),
                    Component("b", coupling=CouplingStrength.LOOSE)],
        context=DesignContext(universal_interface=True),
    )
    tight = AISystemDesign(
        name="tight",
        components=[Component("a", coupling=CouplingStrength.TIGHT),
                    Component("b", coupling=CouplingStrength.TIGHT)],
        context=DesignContext(universal_interface=False),
    )
    assert assess(loose).dimensions["modularity"] > assess(tight).dimensions["modularity"]


def test_feedback_dimension_higher_when_persistent_and_verifying():
    good = AISystemDesign(
        name="good", components=[Component("x"), Component("y")],
        feedback_loops=[
            FeedbackLoop("f", ("x", "y"), persistent=True, verifies_ground_truth=True)
        ],
    )
    poor = AISystemDesign(
        name="poor", components=[Component("x"), Component("y")],
        feedback_loops=[FeedbackLoop("f", ("x", "y"), persistent=False)],
    )
    assert assess(good).dimensions["feedback_loops"] > assess(poor).dimensions["feedback_loops"]


def test_traceability_scales_with_logging_cost_and_approval():
    opaque = AISystemDesign(name="o", components=[Component("a")])
    traced = AISystemDesign(
        name="t",
        components=[Component("a", logged=True, cost_tracked=True, approved=True,
                              self_evaluates=True)],
    )
    assert assess(traced).dimensions["traceability"] > assess(opaque).dimensions["traceability"]


def test_implicit_feedback_loop_detected_from_cycle():
    design = AISystemDesign(
        name="cycle",
        components=[Component("p"), Component("q"), Component("r")],
        connections=[Connection("p", "q"), Connection("q", "r"), Connection("r", "p")],
        # note: NO declared feedback loop
        governance=Governance(second_order_analysis=False),
    )
    a = assess(design)
    assert len(a.implicit_feedback_loops) >= 1
    assert any(l.implicit for l in a.implicit_feedback_loops)


def test_unintended_consequence_risk_when_second_order_unanalyzed_with_implicit_loop():
    design = AISystemDesign(
        name="blind",
        components=[Component("p"), Component("q")],
        connections=[Connection("p", "q"), Connection("q", "p")],
        governance=Governance(second_order_analysis=False),
    )
    a = assess(design)
    codes = {r.code for r in a.risks}
    assert "UNANTICIPATED_SECOND_ORDER" in codes
    assert a.dimensions["unintended_consequences"] < 0.5


def test_over_optimized_isolated_part_flagged():
    design = AISystemDesign(
        name="overfit",
        components=[
            Component("hub", coupling=CouplingStrength.MODERATE),
            Component("bloated", responsibilities=3, coupling=CouplingStrength.MODERATE),
        ],
        connections=[Connection("hub", "bloated")],
    )
    # bloated has no outbound role and is the only heavy node; hub is connected.
    # The bloated node is still connected here, so instead check a disconnected one:
    design2 = AISystemDesign(
        name="overfit2",
        components=[
            Component("hub2", coupling=CouplingStrength.MODERATE),
            Component("orphan", responsibilities=3, coupling=CouplingStrength.MODERATE),
        ],
        connections=[Connection("hub2", "hub2")],  # hub2 self-loop only; orphan isolated
    )
    a = assess(design2)
    codes = {r.code for r in a.risks}
    assert "OVER_OPTIMIZED_ISOLATED_PART" in codes


def test_human_loop_variability_risk():
    design = AISystemDesign(
        name="hiloop", components=[Component("a")],
        governance=Governance(human_in_the_loop=True, accounts_for_human_variability=False),
    )
    a = assess(design)
    assert any(r.code == "HUMAN_LOOP_VARIABILITY" for r in a.risks)


def test_contradiction_detected_between_mark_and_structure():
    design = _weak_design()
    design = AISystemDesign(
        name=design.name, components=design.components, connections=design.connections,
        context=design.context, governance=design.governance,
        explicit_marks={"modularity": 0.95},  # mark high but structure is tight
    )
    a = assess(design)
    assert any(c.dimension == "modularity" for c in a.contradictions)


def test_leverage_point_hub_detected():
    design = AISystemDesign(
        name="hub",
        components=[Component(f"c{i}") for i in range(5)],
        connections=[Connection("c0", f"c{i}") for i in range(1, 5)],
    )
    a = assess(design)
    targets = {lp.target for lp in a.leverage_points}
    assert "c0" in targets


def test_to_dict_serializes():
    a = assess(_strong_design())
    d = a.to_dict()
    assert d["design_name"] == "folder-first"
    assert "dimensions" in d and "overall" in d
    assert d["overall"] == "excellent"


# --------------------------------------------------------------------------- #
# Module lifecycle
# --------------------------------------------------------------------------- #
async def test_module_initializes_and_health():
    import asyncio
    m = create_ai_systems_thinking_module({})
    # initialize is async; run within the running loop
    await m.initialize()
    assert m.thinker is not None
    status = await m.health_check()
    assert "HEALTHY" in str(status)
    assert m.engine() is not None
    await m.shutdown()
    assert "UNKNOWN" in str(m.status)


async def test_module_evaluates_via_facade():
    m = create_ai_systems_thinking_module({})
    await m.initialize()
    a = m.evaluate(_strong_design())
    assert a.overall == OverallRead.EXCELLENT
    await m.shutdown()


def test_registered_in_kernel_registry():
    from enterprise.platform_kernel import _MODULE_REGISTRY
    assert "ai_systems_thinking" in _MODULE_REGISTRY

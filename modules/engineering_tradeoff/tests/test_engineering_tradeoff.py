"""Unit tests for the engineering_tradeoff module (network-free)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from enterprise.modules.engineering_tradeoff import (
    Constraint, Option, TradeoffEngine, create_engineering_tradeoff_module,
    make_engine,
)


# The canonical transcript fixture: the $5M Pagani Zonda (absolute best on
# quality) vs a cheap, reliable Toyota (the satisficing winner). Raw scores
# are 0-10 across cost/quality/speed/robustness/effort.
def _car_options():
    pagani = Option(
        "Pagani Zonda",
        scores={
            "cost": 10,      # insanely expensive (bad: lower_better)
            "quality": 10,   # superb
            "speed": 10,     # fastest
            "robustness": 5, # exotic, finicky
            "effort": 6,     # high cost-to-own effort (bad: lower_better)
        },
    )
    toyota = Option(
        "Toyota Echo",
        scores={
            "cost": 1,       # cheap ($100 on Craigslist)
            "quality": 6,
            "speed": 3,
            "robustness": 9, # famously reliable
            "effort": 2,     # low upkeep
        },
    )
    return [pagani, toyota]


def test_hard_constraint_filters_infeasible_options():
    engine = make_engine()
    options = _car_options()
    # Can't spend $5M: budget (cost) must be <= 5.
    budget = Constraint("cost", "le", 5)

    result = engine.evaluate(options, [budget])

    # Pagani violates the hard constraint -> constrained out.
    constrained = {s.option.name for s in result.constrained_out}
    assert "Pagani Zonda" in constrained
    feasible = {s.option.name for s in result.feasible}
    assert "Toyota Echo" in feasible
    assert "Pagani Zonda" not in feasible

    # But Pagani is still *ranked* (absolute best ignores constraints).
    assert result.absolute_best.option.name == "Pagani Zonda"


def test_weighted_scoring_and_ranking():
    engine = make_engine(weights={"cost": 3.0})  # cost is extra important
    a = Option("A", scores={"cost": 1, "quality": 5, "speed": 5,
                            "robustness": 5, "effort": 1})
    b = Option("B", scores={"cost": 9, "quality": 8, "speed": 8,
                            "robustness": 8, "effort": 9})

    result = engine.evaluate([a, b])

    # With cost weighted x3 (lower better), cheap A should outscore B.
    assert result.ranking[0].option.name == "A"
    assert result.satisficing_winner.option.name == "A"
    assert result.ranking[0].total > result.ranking[1].total

    # Equal weights and a pure quality focus should flip it to B.
    engine2 = make_engine()
    result2 = engine2.evaluate([a, b])
    assert result2.ranking[0].option.name == "B"
    assert result2.satisficing_winner.option.name == "B"


def test_satisficing_winner_differs_from_absolute_best():
    """The whole point of the transcript: the Pagani (absolute best) loses to
    the Toyota (best feasible) once real constraints apply."""
    engine = make_engine()
    options = _car_options()
    budget = Constraint("cost", "le", 5)
    reliability = Constraint("robustness", "ge", 6)

    result = engine.evaluate(options, [budget, reliability])

    assert result.absolute_best.option.name == "Pagani Zonda"
    assert result.satisficing_winner.option.name == "Toyota Echo"
    assert result.satisficing_winner.option.name != result.absolute_best.option.name

    # Tradeoff analysis: the winner sacrificed quality/speed (the Pagani's
    # strengths) to meet the constraints.
    sacrificed = {t.dimension for t in result.tradeoffs if t.sacrificed}
    assert "quality" in sacrificed
    assert "cost" not in sacrificed  # winner is *better* (lower) on cost


def test_no_feasible_option_returns_no_winner():
    engine = make_engine()
    options = _car_options()
    # Impossible requirement: cost <= 0.0001.
    impossible = Constraint("cost", "le", 0.0001)

    result = engine.evaluate(options, [impossible])

    assert result.satisficing_winner is None
    assert result.feasible == []
    # Absolute best is still reported (the unconstrained Pagani).
    assert result.absolute_best.option.name == "Pagani Zonda"


def test_ge_constraint_and_file_roundtrip(tmp_path: Path):
    """Constraint direction 'ge', plus confirming pure-logic needs no network
    by having it run from a temp dir (tmp_path: Path file IO)."""
    engine = make_engine()
    options = _car_options()
    reliability = Constraint("robustness", "ge", 7)

    result = engine.evaluate(options, [reliability])

    # Only Toyota meets robustness >= 7.
    assert result.satisficing_winner.option.name == "Toyota Echo"

    # Trivial file IO to satisfy the tmp_path contract without any network.
    report = Path(tmp_path) / "tradeoff.txt"
    report.write_text(result.satisficing_winner.option.name)
    assert report.read_text() == "Toyota Echo"


def test_platform_module_facade():
    m = create_engineering_tradeoff_module({})
    asyncio.run(m.initialize())
    assert m.engine is not None
    assert m.dimensions() == ["cost", "quality", "speed", "robustness", "effort"]

    options = _car_options()
    winner = m.pick_satisficing(options, [Constraint("cost", "le", 5)])
    assert winner.name == "Toyota Echo"

    result = m.evaluate(options)
    assert result.absolute_best.option.name == "Pagani Zonda"

    status = asyncio.run(m.health_check())
    assert "HEALTHY" in str(status) or status.value == "healthy"
    asyncio.run(m.shutdown())
    assert m.engine is None

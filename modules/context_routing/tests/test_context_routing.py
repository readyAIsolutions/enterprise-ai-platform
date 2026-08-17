"""Tests for the context_routing module (routing table + token discipline)."""
from __future__ import annotations

from enterprise.modules.context_routing import (
    ContextRouter, RoutingRule, example_rules, make_router,
)


def test_route_exact_and_substring_and_fallback():
    r = make_router()
    # exact keyword
    assert r.route("verify").task == "verify"
    # substring match
    assert r.route("please verify the output").task == "verify"
    # fallback
    assert r.route("arbitrary task").task == "default"


def test_budget_fits_selected_and_excludes_skip():
    r = make_router()
    files = {
        "README.md": 2000,          # ~500 tokens
        "docs/architecture.md": 4000,
        "data/big.db": 100000,      # must be skipped for intake
        "docs/checklist.md": 100,
    }
    b = r.budget("intake", files)
    # explicit_skip must include data/big.db
    assert "data/big.db" in b["explicit_skip"]
    # README should be read
    assert "README.md" in b["read"]
    # and the big data file must not be in read
    assert "data/big.db" not in b["read"]
    assert b["within_budget"] is True


def test_budget_respects_token_cap():
    r = make_router()
    # a rule with a tiny budget should drop files that don't fit
    small = ContextRouter([RoutingRule(task="tiny", read=["**/*.md"],
                                       skip=[], budget_tokens=400)])
    files = {"a.md": 4000, "b.md": 4000}   # each ~1000 tokens
    b = small.budget("tiny", files)
    assert b["tokens"] <= b["budget"] + 1000  # within (or first-file exception)
    assert b["rule"] == "tiny"


def test_skills_for():
    r = make_router()
    assert "write-file" in r.skills_for("write")
    assert "shell" in r.skills_for("verify")


def test_module_initializes():
    import asyncio
    from enterprise.modules.context_routing import create_context_routing_module
    m = create_context_routing_module({})
    asyncio.run(m.initialize())
    assert m.router is not None
    assert asyncio.run(m.health_check()).value in ("healthy", "HEALTHY") or "HEALTHY" in str(asyncio.run(m.health_check()))
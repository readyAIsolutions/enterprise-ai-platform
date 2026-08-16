"""Tests for the codegen_audit module (auditing / evaluating AI-generated code).

Grounded in three JE Van Clief coding-tool-eval transcripts:
  * _rtyhVD4v4A — AI coding-tool comparison (understanding the goal, working code).
  * nWbM9Ye2sLw — real-devs line-by-line audit of a vibe-coded app (security).
  * 5B6W2OGfxq0 — one line of Python -> 12,000 lines (abstraction-depth layers).

All tests are deterministic and network-free; ``async def`` tests run via
``asyncio_mode = "auto"``.
"""

from __future__ import annotations

import asyncio

from enterprise.modules.codegen_audit import (
    CodegenAuditModule,
    Status,
    audit_code,
    create_codegen_audit_module,
    dependency_blast_radius,
    dependency_depth,
    evaluate_requirements,
    review_code,
    score_checks,
    verify_features,
)
from enterprise.modules.codegen_audit.codegen_audit import (
    EXECUTION_LAYERS,
    T_EXECUTION_LAYERS,
    T_SECURITY_AUDIT,
    T_TOOL_COMPARISON,
)

# ---------------------------------------------------------------------------
# Static heuristic code review
# ---------------------------------------------------------------------------


def test_hallucinated_import_flagged_unless_declared_available():
    # A generated import of a non-stdlib module that is not declared available
    # must be flagged (T1: import errors bricked the generated build).
    src = "import requests\nimport numpy\n"
    rv = review_code(src)
    chk = rv.check("hallucinated_import")
    assert chk is not None
    assert chk.status is Status.FAIL
    assert "requests" in chk.message

    # Same code passes once the caller supplies the third-party modules.
    rv2 = review_code(src, available_modules=["requests", "numpy"])
    assert rv2.check("hallucinated_import").status is Status.PASS


def test_unused_import_detected():
    src = "import os\nimport json\n\nx = 1\nprint(x)\n"
    rv = review_code(src)
    chk = rv.check("unused_import")
    assert chk.status is Status.WARN
    assert "os" in chk.message and "json" in chk.message


def test_used_import_not_flagged():
    src = "import math\nv = math.sqrt(16)\nprint(v)\n"
    rv = review_code(src)
    assert rv.check("unused_import").status is Status.PASS


def test_debug_print_flagged():
    src = "def run():\n    print('debug')\n    return 1\n"
    rv = review_code(src)
    assert rv.check("debug_print").status is Status.WARN


def test_bare_except_flagged_fail():
    # Silent bare except removes the error handling every stack layer relies on.
    src = "try:\n    risky()\nexcept:\n    pass\n"
    rv = review_code(src)
    chk = rv.check("bare_except")
    assert chk.status is Status.FAIL
    assert chk.transcript_ref == T_EXECUTION_LAYERS


def test_broad_except_warn():
    src = "try:\n    risky()\nexcept Exception:\n    pass\n"
    rv = review_code(src)
    assert rv.check("broad_except").status is Status.WARN


def test_missing_type_hint_warn():
    src = "def compute(a, b):\n    return a + b\n"
    rv = review_code(src)
    assert rv.check("missing_type_hint").status is Status.WARN


def test_secret_in_code_flagged_fail():
    # Hardcoded credentials -> the leaked-API-key finding from the audit.
    src = 'api_key = "sk-test-abcdef0123456789"\nresult = 1\n'
    rv = review_code(src)
    chk = rv.check("secret_in_code")
    assert chk.status is Status.FAIL
    assert chk.transcript_ref == T_SECURITY_AUDIT


def test_unverified_auth_flagged_fail():
    # Custom auth that decodes a token but never verifies the issuer.
    src = 'payload = jwt.decode(token, "secret", algorithms=["HS256"])\n'
    rv = review_code(src)
    chk = rv.check("unverified_auth")
    assert chk.status is Status.FAIL
    assert chk.transcript_ref == T_SECURITY_AUDIT


def test_redundant_reinvention_warn():
    # Rolling own token encoder instead of using a platform built-in.
    src = "def encode_token(data):\n    return base64.b64encode(data)\n"
    rv = review_code(src)
    assert rv.check("redundant_reinvention").status is Status.WARN


def test_todo_truncation_stub_warn():
    # Truncation markers -> the "... add it later" fidelity loss.
    src = 'scales = ["q1", "q2", ...]\n'
    rv = review_code(src)
    assert rv.check("todo_stub").status is Status.WARN


def test_error_handling_missing_around_io_warn():
    src = "def load():\n    data = open('x.txt').read()\n    return data\n"
    rv = review_code(src)
    assert rv.check("error_handling").status is Status.WARN


def test_feature_verification_marker_pass():
    src = "def fetch():\n    assert validate(res)\n    return res\n"
    rv = review_code(src)
    assert rv.check("feature_verification").status is Status.PASS


# ---------------------------------------------------------------------------
# Review scoring report
# ---------------------------------------------------------------------------


def test_score_grade_and_verdict():
    rv = review_code("import os\napi_key = 'sk-test-abcdef0123456789'\ntry:\n    f()\nexcept:\n    pass\n")
    score = score_checks(rv.checks)
    assert score.total == len(rv.checks)
    assert score.failed >= 1
    assert score.verdict is Status.FAIL
    assert score.grade in ("C", "D", "F")


def test_clean_code_scores_pass_grade_a():
    src = (
        "import math\n\n"
        "def area(radius: float) -> float:\n"
        "    assert radius >= 0\n"
        "    return math.pi * radius ** 2\n"
    )
    rv = review_code(src)
    score = score_checks(rv.checks)
    assert score.verdict is Status.PASS
    assert score.grade == "A"


def test_score_to_dict_shape():
    score = score_checks(review_code("x = 1\n").checks).to_dict()
    for key in ("total", "passed", "warned", "failed", "grade", "verdict", "summary"):
        assert key in score


# ---------------------------------------------------------------------------
# Dependency / abstraction-depth analysis (5B6W2OGfxq0)
# ---------------------------------------------------------------------------


def test_execution_layers_defined():
    names = [n for n, _ in EXECUTION_LAYERS]
    assert names == ["parse", "ast", "bytecode", "interpreter_runtime"]


def test_dependency_depth_follows_chain():
    # Mirror: one line -> AST -> bytecode -> interpreter/runtime -> OS.
    graph = {
        "app": ["http"],
        "http": ["socket"],
        "socket": ["os"],
        "os": [],
    }
    d = dependency_depth("app", graph)
    assert d.depth == 4
    assert d.longest_chain == ["app", "http", "socket", "os"]
    assert d.layers_crossed == ["parse", "ast", "bytecode", "interpreter_runtime"]
    assert not d.has_cycle


def test_dependency_depth_cycle_detection():
    graph = {"a": ["b"], "b": ["a"]}
    d = dependency_depth("a", graph)
    assert d.has_cycle is True


def test_dependency_blast_radius_over_broad():
    # A single auth symbol that everything depends on has a big blast radius.
    graph = {
        "create_client": ["auth"], "login": ["auth"], "admin": ["login"],
        "billing": ["admin"], "report": ["billing"], "export": ["report"],
    }
    r = dependency_blast_radius("auth", graph, over_broad_threshold=5)
    assert r.over_broad is True
    assert r.transitive_dependents > 5
    assert "auth" in r.reason


# ---------------------------------------------------------------------------
# Task-understanding evaluator (_rtyhVD4v4A)
# ---------------------------------------------------------------------------


def test_requirements_satisfied_pass():
    src = "def build_modular_folder():\n    return 'ok'\n"
    report = evaluate_requirements(["modular folder"], src)
    assert report.overall is Status.PASS
    assert report.missing == []


def test_missing_requirement_fails():
    src = "x = 1\n"
    report = evaluate_requirements(["create a UI", "add scales"], src)
    assert report.overall is Status.FAIL
    assert "create a UI" in report.missing
    assert "add scales" in report.missing


def test_truncation_fidelity_warn():
    # "... add it later" => data fidelity loss (T1 keeps prompt data EXACT).
    src = 'scales = ["alpha", "beta", ...]  # add it later\n'
    report = evaluate_requirements(["keep exact scales"], src, require_fidelity=True)
    assert report.fidelity_ok is False
    assert any(r.status is Status.WARN for r in report.results)


def test_verify_features_claimed_but_missing_warns():
    # Feature claimed implemented but no evidence in output -> WARN (T1).
    report = verify_features(
        ["upload", "scoring"], claimed=["upload", "scoring"], actual="def upload():\n    pass\n"
    )
    by_name = {r.requirement: r for r in report.results}
    assert by_name["upload"].status is Status.PASS
    assert by_name["scoring"].status is Status.WARN
    assert report.overall is Status.WARN


def test_verify_features_truly_missing_fails():
    report = verify_features(["scoring"], claimed=[], actual="def upload():\n    pass\n")
    assert report.overall is Status.FAIL


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------


def test_audit_code_returns_all_sections():
    src = "import math\nx = math.sqrt(4)\nprint(x)\n"
    out = audit_code(src, requirements=["compute sqrt"])
    assert "review" in out and "score" in out and "task_understanding" in out
    assert out["score"]["verdict"] in ("PASS", "FAIL", "WARN")


# ---------------------------------------------------------------------------
# Module lifecycle (async -> asyncio_mode="auto")
# ---------------------------------------------------------------------------


async def test_module_lifecycle_healthy():
    mod = create_codegen_audit_module()
    assert mod.name == "codegen_audit"
    assert mod.version == "1.0.0"
    await mod.initialize()
    from enterprise.platform_kernel import HealthStatus
    status = await mod.health_check()
    assert status is HealthStatus.HEALTHY
    await mod.shutdown()
    assert mod.status is HealthStatus.UNKNOWN
    assert await mod.health_check() is HealthStatus.UNHEALTHY


async def test_module_facade_audit():
    mod = create_codegen_audit_module({"require_verification": True})
    await mod.initialize()
    out = mod.audit("x = 1\n", requirements=["do nothing harmful"])
    assert "score" in out and "review" in out
    assert mod.review("import json\n")["source_lines"] == 1
    await mod.shutdown()


async def test_module_event_bus_guard():
    # Publishing must not crash when no bus is wired (guard is not None).
    mod = create_codegen_audit_module()
    await mod.initialize()
    mod.set_event_bus(None)
    out = mod.audit("import os\n")
    assert "score" in out
    await mod.shutdown()


async def test_facade_raises_when_not_initialized():
    mod = create_codegen_audit_module()
    try:
        mod.audit("x = 1\n")
        assert False, "should raise before initialize"
    except RuntimeError:
        pass

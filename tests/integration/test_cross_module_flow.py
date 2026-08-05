"""ENI cross-module end-to-end integration suite.

This file wires the REAL module facades together (no mocks of the facades
themselves) and off-line (injecting each module's shipable offline adapter:
EchoAdapter, MockProvider, SimulationBackend, in-memory stores, canned
scanners). Its whole point is to catch *contract drift* — a wrong argument
name, a wrong return shape, a changed enum value — that only surfaces when two
master-classed-but-isolated modules are exercised in one flow.

Flows covered (each uses the module's ACTUAL public facade method):

  a. PIPELINE     model_router.route (EchoAdapter)
                  -> agent_core.query_engine (MockProvider / SimulationBackend)
                  -> eval_gate.run_eval
  b. BUILD-SCORE  universal_score.score on a real temp project dir
  c. VALIDATE     guardrails.validate (GuardResult)
                  + model_security SecurityScanner (Garak-style probes)
  d. SECURITY     secret_rotation VaultFacade (encrypted-at-rest, audited)
                  + ai_defense ThrottleGate/AttackerStore (attack attempt)
                  + compliance EvidenceRegister (hash-chained evidence)

Run:  python3 -m pytest tests/integration -q -p no:cacheprovider
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Module facades (the REAL contracts under test)
# ---------------------------------------------------------------------------
from enterprise.modules.agent_core.providers import MockProvider
from enterprise.modules.agent_core.query_engine import (
    Message,
    MessageRole,
    ModelConfig,
    ModelFamily,
    ModelRouter as AgentModelRouter,
    OpenAICompatibleBackend,
    QueryConfig,
    QueryResult,
    SimulationBackend,
    SuperiorQueryEngine,
)
from enterprise.modules.ai_defense.rate_limit import (
    AttackerStore,
    ThrottleGate,
)
from enterprise.modules.compliance.evidence import (
    BUILTIN_CONTROLS,
    ControlEvidence,
    EvidenceRegister,
    GapAnalysis,
)
from enterprise.modules.eval_gate import EvalGateFacade
from enterprise.modules.guardrails import (
    GuardResult,
    Guardrails,
    NoPIIValidator,
    ProfanityValidator,
)
from enterprise.modules.model_router import (
    DeploymentModel,
    EchoAdapter,
    ModelRouter,
    RouteResult,
)
from enterprise.modules.model_security.probe_detector import SecurityScanner
from enterprise.modules.secret_rotation.vault import VaultIntegrityError, VaultFacade
from enterprise.modules.universal_score import UniversalBuildScore


# =============================================================================
# Shared fixtures
# =============================================================================


@pytest.fixture
def router() -> ModelRouter:
    """Offline model_router wired with the EchoAdapter (real facade)."""
    r = ModelRouter(adapter=EchoAdapter())
    r.add_deployment(
        DeploymentModel(id="local-echo", model="echo-mini", provider="local",
                        weight=1, group="integration")
    )
    return r


@pytest.fixture
def query_engine() -> SuperiorQueryEngine:
    """Offline agent_core query engine over a single deterministic model."""
    cfg = ModelConfig(name="integration-mock", family=ModelFamily.LOCAL,
                      provider="mock")
    engine_router = AgentModelRouter(models=[cfg])
    eng = SuperiorQueryEngine(config=QueryConfig(), router=engine_router)
    eng.register_model(cfg)
    eng.register_backend("integration-mock",
                         SimulationBackend(fixed_response="INTEGRATION_OK"))
    return eng


def _engine_with_mock(responses) -> SuperiorQueryEngine:
    """agent_core query engine driven by the REAL MockProvider."""
    cfg = ModelConfig(name="integration-mock", family=ModelFamily.LOCAL,
                      provider="mock")
    engine_router = AgentModelRouter(models=[cfg])
    eng = SuperiorQueryEngine(config=QueryConfig(model="integration-mock"),
                              router=engine_router)
    eng.register_model(cfg)
    eng.register_backend("integration-mock",
                         OpenAICompatibleBackend(provider=MockProvider(responses=responses)))
    return eng


@pytest.fixture
def eval_facade() -> EvalGateFacade:
    return EvalGateFacade()


@pytest.fixture
def guardrails() -> Guardrails:
    g = Guardrails()
    g.add_guard("safe", [NoPIIValidator()], on_fail="block")
    g.add_guard("toxicity", [ProfanityValidator()], on_fail="block")
    return g


# =============================================================================
# a. PIPELINE flow — model_router -> agent_core -> eval_gate
# =============================================================================


@pytest.mark.asyncio
async def test_pipeline_router_contract_shape(router):
    result = await router.route(
        "integration",
        [{"role": "user", "content": "hello pipeline"}],
    )
    assert isinstance(result, RouteResult)
    # Exact RouteResult contract
    assert result.status == "success"
    assert result.deployment_id == "local-echo"
    assert result.attempts == 1
    assert result.fallbacks_used == 0
    assert result.final_error is None
    assert result.messages == "echo[echo-mini]:hello pipeline"
    assert isinstance(result.tokens, dict)
    assert "prompt_tokens" in result.tokens
    assert result.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_pipeline_agent_query_contract(query_engine):
    res = await query_engine.query(
        [Message(role=MessageRole.USER, content="hello agent")]
    )
    assert isinstance(res, QueryResult)
    assert res.success is True
    assert res.error is None
    assert res.final_response == "INTEGRATION_OK"
    assert isinstance(res.messages, list) and res.messages
    assert res.total_tokens_input >= 0 and res.total_tokens_output >= 0
    assert isinstance(res.metrics, dict)
    # Role/value contract must line up (MessageRole enum round-trips):
    # first message is the caller's user turn, last is the model response.
    assert res.messages[0].role.value == "user"
    assert res.messages[-1].role.value == "assistant"


@pytest.mark.asyncio
async def test_pipeline_agent_with_real_mockprovider():
    eng = _engine_with_mock(responses=["MOCK_ANSWER"])
    res = await eng.query(
        [Message(role=MessageRole.USER, content="real mock round trip")]
    )
    assert res.success is True
    assert res.final_response == "MOCK_ANSWER"
    # the provider really was invoked (provider facade recorded the call)
    provider = eng._backends["integration-mock"]._provider
    assert provider.calls  # MockProvider.complete() ran
    assert provider.calls[0]["model"] == "integration-mock"


@pytest.mark.asyncio
async def test_pipeline_eval_gate_contract(eval_facade):
    report = eval_facade.run_eval({"text": "The answer is clearly, directly relevant."})
    assert set(report.keys()) == {"passed", "score", "results"}
    assert 0.0 <= report["score"] <= 1.0
    assert isinstance(report["passed"], bool)
    for r in report["results"]:
        assert set(r.keys()) == {"name", "score", "passed", "detail"}
        assert 0.0 <= r["score"] <= 1.0


@pytest.mark.asyncio
async def test_pipeline_messages_dict_shape_lines_up(router):
    """The messages dict shape must line up across the module boundary."""
    # agent_core produces Message objects; model_router consumes [{role,content}]
    agent_msg = Message(role=MessageRole.USER, content="cross module contract")
    router_request = [{"role": agent_msg.role.value, "content": agent_msg.content}]

    result = await router.route("integration", router_request)

    # model_router output (a string) feeds straight into eval_gate as the text
    assert isinstance(result.messages, str)
    eval_report = EvalGateFacade().run_eval({"text": result.messages})
    assert eval_report["passed"] is True


@pytest.mark.asyncio
async def test_pipeline_full_chain(router, query_engine, eval_facade):
    """model_router -> agent_core -> eval_gate end to end, assert healthy."""
    routed = await router.route(
        "integration",
        [{"role": "user", "content": "please analyze this requirement"}],
    )
    assert routed.status == "success"

    agent_res = await query_engine.query(
        [Message(role=MessageRole.USER, content=routed.messages)]
    )
    assert agent_res.success is True
    assert agent_res.final_response == "INTEGRATION_OK"

    scored = eval_facade.run_eval({"text": f"{routed.messages} {agent_res.final_response}"})
    assert scored["passed"] is True
    assert scored["score"] > 0.0


# =============================================================================
# b. BUILD-SCORE flow — universal_score on a real temp project
# =============================================================================


def _write_sample_project(root):
    (root / "pkg").mkdir()
    (root / "tests").mkdir()
    (root / "README.md").write_text("# demo project\n")
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text(
        '"""Core math helpers."""\n'
        "\n"
        "_CACHED = {}\n"
        "\n"
        "def add(a: float, b: float) -> float:\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    return a + b\n"
        "\n"
        "def mul(a: float, b: float) -> float:\n"
        "    \"\"\"Multiply two numbers.\"\"\"\n"
        "    return a * b\n"
    )
    (root / "tests" / "test_core.py").write_text(
        "from pkg.core import add, mul\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
        "def test_mul():\n"
        "    assert mul(2, 3) == 6\n"
    )


def test_build_score_contract_keys(tmp_path):
    _write_sample_project(tmp_path)
    result = UniversalBuildScore().score(tmp_path, run_tests=False)
    expected = {"universal_score", "base_score", "bonus", "certification",
                "hard_gates", "any_hard_gate_failed", "dimensions", "project",
                "coverage_pct"}
    assert set(result.keys()) == expected
    assert 0.0 <= result["universal_score"] <= 130.0
    assert isinstance(result["certification"], str)
    assert len(result["dimensions"]) == 6
    # per-dimension report shape
    for dim, d in result["dimensions"].items():
        assert set(d.keys()) == {"dimension", "score", "sub_signals"}
        assert 0.0 <= d["score"] <= 1.0
        for sub in d["sub_signals"]:
            assert set(sub.keys()) == {"key", "name", "score", "evidence"}


# =============================================================================
# c. VALIDATE flow — guardrails + model_security scanner
# =============================================================================


def test_guardrails_validate_returns_guardresult(guardrails):
    out = guardrails.validate("hello, could you summarize the report", "safe")
    assert isinstance(out, GuardResult)
    assert out.passed is True
    assert out.guard_name == "safe"


def test_guardrails_blocks_profanity(guardrails):
    out = guardrails.validate("you are a stupid damn moron", "toxicity")
    assert isinstance(out, GuardResult)
    assert out.passed is False
    assert any("blocked" in a for a in out.actions)
    assert out.failures  # aggregator surfaced a failure record


def test_guardrails_unknown_guard_raises(guardrails):
    with pytest.raises(KeyError):
        guardrails.validate("anything", "no-such-guard")


def test_model_security_garak_scanner_contract():
    scanner = SecurityScanner(target=lambda a: "I cannot help with that request.")
    report = scanner.scan(probe_names=["prompt_injection", "jailbreak"])
    assert report.probes_run == ["prompt_injection", "jailbreak"]
    assert isinstance(report.passed, bool)
    assert 0.0 <= report.stop_rate <= 1.0
    assert isinstance(report.per_attempt, list)
    assert report.attempts > 0


# =============================================================================
# d. SECURITY EVIDENCE chain — secret_rotation -> ai_defense -> compliance
# =============================================================================


def test_secret_vault_encrypted_roundtrip(tmp_path):
    vf = VaultFacade(str(tmp_path / "vault.db"), master_key="master-key-123")
    vf.put("db_password", "s3cr3t-value", actor="pipeline")
    assert vf.get("db_password") == "s3cr3t-value"
    # tamper detection: wrong master key must not decrypt
    with pytest.raises(VaultIntegrityError):
        vf.get("db_password", master_key="wrong-key")
    # tamper-evident access audit chain holds
    assert vf.audit_verify()["valid"] is True
    assert len(vf.audit_entries()) >= 2  # put + get both logged
    vf.close()


def test_ai_defense_attacker_store_records_attempt():
    store = AttackerStore()  # in-memory
    tg = ThrottleGate(limit=2, window=60, threshold=1000)
    assert tg.allow("1.2.3.4", now=0.0).allowed is True
    assert tg.allow("1.2.3.4", now=0.1).allowed is True
    denied = tg.allow("1.2.3.4", now=0.2)
    assert denied.allowed is False
    assert denied.reason == "rate_limited"
    # record an explicit red-teamish attack attempt on a fresh identity
    rec = store.add_attempt("evil.actor", now=5.0, flag="sql_injection")
    assert rec["attempt_count"] == 1
    assert "sql_injection" in rec["flags"]


def test_compliance_evidence_register_integrity(tmp_path):
    reg = EvidenceRegister()  # in-memory
    reg.add(ControlEvidence(control_id="LLM01", framework="owasp",
                            status="implemented", source="integration"))
    reg.add(ControlEvidence(control_id="LLM02", framework="owasp",
                            status="partial", source="integration"))
    integrity = reg.verify_integrity()
    assert integrity["valid"] is True
    assert integrity["checked"] == 2

    ga = GapAnalysis(register=reg)
    report = ga.analyze(framework="owasp", top_n=3)
    # GapAnalysis contract keys
    assert {"gaps", "gap_count", "integrity", "frameworks", "remediation",
            "pass_pct", "scope", "timestamp"} <= set(report.keys())
    assert report["integrity"]["valid"] is True
    assert report["gap_count"] >= 1
    assert report["frameworks"]["owasp"]["implemented"] == 1


def test_tampering_evidence_is_detected():
    reg = EvidenceRegister()
    reg.add(ControlEvidence(control_id="LLM01", framework="owasp",
                            status="missing", source="scanner"))
    # Direct SQL tamper (bypasses the register API) must break the hash chain.
    row_id = next(iter(reg._conn.execute("SELECT id FROM evidence")))["id"]
    reg._conn.execute("UPDATE evidence SET status='implemented' WHERE id=?",
                      (row_id,))
    reg._conn.commit()
    integrity = reg.verify_integrity()
    assert integrity["valid"] is False
    assert integrity["problems"]


def test_security_evidence_chain_roundtrip(tmp_path):
    """secret_rotation -> ai_defense -> compliance, all three stores round-trip
    and their integrity holds."""
    # 1) secret_rotation: encrypted-at-rest secret + audited access
    vf = VaultFacade(str(tmp_path / "vault.db"), master_key="chain-master-key")
    vf.put("api_token", "chain-token-42", actor="orchestrator")
    assert vf.get("api_token") == "chain-token-42"
    assert vf.audit_verify()["valid"] is True

    # 2) ai_defense: record the attack attempt that used the leaked token
    store = AttackerStore()
    attack = store.add_attempt("attacker-ip", now=10.0, flag="credential_stuffing")
    assert attack["attempt_count"] == 1
    assert "credential_stuffing" in attack["flags"]

    # 3) compliance: file evidence that the token was rotated after the breach
    reg = EvidenceRegister()
    reg.add(ControlEvidence(control_id="LLM05", framework="owasp",
                            status="implemented",
                            source="secret_rotation",
                            detail="rotated after attack"))
    assert reg.verify_integrity()["valid"] is True

    vf.close()

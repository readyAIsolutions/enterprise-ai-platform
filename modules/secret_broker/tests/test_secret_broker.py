"""Tests for the Secret Broker module (local-first secret handling)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from enterprise.modules.secret_broker.secret_broker import (
    OutboundSecretLeakError,
    PlaceholderSubstituter,
    SecretBroker,
    SecretBrokerModule,
    SecretDetector,
)
from enterprise.platform_kernel import HealthStatus

# ---------------------------------------------------------------------------
# SecretDetector
# ---------------------------------------------------------------------------


def test_detector_finds_openai_api_key() -> None:
    d = SecretDetector()
    hits = d.detect("use sk-abcdefghijklmnopqrstuvwxyz1234567890ABC to call the api")
    types = {h.type for h in hits}
    assert "openai_api_key" in types


def test_detector_finds_aws_access_key() -> None:
    d = SecretDetector()
    hits = d.detect("credential: AKIAIOSFODNN7EXAMPLE")
    assert any(h.type == "aws_access_key" for h in hits)


def test_detector_finds_password_assignment() -> None:
    d = SecretDetector()
    hits = d.detect("the db password=hunter2secret99 and that is all")
    assert any(h.type in ("generic_key_value", "high_entropy_token") for h in hits)


def test_detector_finds_high_entropy_token() -> None:
    d = SecretDetector(min_entropy=3.8)
    hits = d.detect("token z9Qk4LmP8xRw2TnV7yBc6DfJ1HaS3")
    assert any(h.type == "high_entropy_token" for h in hits)


def test_detector_returns_locations() -> None:
    d = SecretDetector()
    text = "start AKIAIOSFODNN7EXAMPLE end"
    hits = d.detect(text)
    hit = next(h for h in hits if h.type == "aws_access_key")
    assert text[hit.start : hit.end] == "AKIAIOSFODNN7EXAMPLE"


def test_detector_empty_text_no_hits() -> None:
    assert SecretDetector().detect("") == []
    assert SecretDetector().detect("just a normal sentence here") == []


# ---------------------------------------------------------------------------
# PlaceholderSubstituter — reversible + idempotent
# ---------------------------------------------------------------------------


def test_substitution_round_trip() -> None:
    p = PlaceholderSubstituter()
    text = "api key sk-abcdefghijklmnopqrstuvwxyz1234567890ABC and db pass=hunter2secret99"
    sub = p.substitute(text)
    assert "__SECRET_" in sub.redacted_text
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in sub.redacted_text
    restored = p.restore(sub.redacted_text, sub.map)
    assert restored == text


def test_substitution_placeholder_is_unique_and_reversible() -> None:
    p = PlaceholderSubstituter()
    text = (
        "first sk-abcdefghijklmnopqrstuvwxyz1234567890ABC "
        "second sk-abcdefghijklmnopqrstuvwxyz1234567890ABC"
    )
    sub = p.substitute(text)
    # Identical secrets -> identical placeholder (deterministic).
    assert len(set(sub.map.keys())) == 1


def test_redact_restore_round_trip() -> None:
    b = SecretBroker()
    text = "connect with AKIAIOSFODNN7EXAMPLE and password=sup3rs3cret88"
    r = b.redact(text)
    assert r["redacted_text"] != text
    assert "__SECRET_" in r["redacted_text"]
    restored = b.restore(r["redacted_text"], r["map"])
    assert restored == text


def test_redact_is_idempotent() -> None:
    b = SecretBroker()
    text = "token ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    once = b.redact(text)
    twice = b.redact(once["redacted_text"])
    assert twice["redacted_text"] == once["redacted_text"]


def test_restore_uses_broker_internal_map() -> None:
    b = SecretBroker()
    text = "secret=AKIAIOSFODNN7EXAMPLE"
    sub = b.substituter.substitute(text)
    restored = b.restore(sub.redacted_text)  # no explicit map -> internal map
    assert restored == text


# ---------------------------------------------------------------------------
# Outbound guard
# ---------------------------------------------------------------------------


def test_outbound_guard_raises_on_secret() -> None:
    b = SecretBroker()
    with pytest.raises(OutboundSecretLeakError):
        b.guard_outbound("send this: sk-abcdefghijklmnopqrstuvwxyz1234567890ABC")


def test_outbound_guard_redacts_known_secret() -> None:
    b = SecretBroker()
    text = "AKIAIOSFODNN7EXAMPLE is my key"
    r = b.redact(text)
    leaking = "I will send you " + next(iter(r["map"].values()))
    out = b.guard_outbound(leaking, known_secrets=r["map"], mode="redact")
    assert "__SECRET_" in out
    assert next(iter(r["map"].values())) not in out


def test_outbound_guard_clean_text_passes() -> None:
    b = SecretBroker()
    assert (
        b.guard_outbound("what is the weather today in Paris?")
        == "what is the weather today in Paris?"
    )


def test_master_flow_local_first() -> None:
    """detect -> substitute -> model -> reverse-substitute, no leak to model."""
    b = SecretBroker()
    user = "summarise using api key AKIAIOSFODNN7EXAMPLE and pass=hunter2secret99"
    r = b.redact(user)
    # The "model" only ever sees placeholders.
    model_reply = "understood, will use your token __SECRET_{}__ locally.".format(
        list(r["map"].keys())[0]
    )
    # No raw secret reaches the model input or output.
    assert "AKIAIOSFODNN7EXAMPLE" not in r["redacted_text"]
    final = b.restore(model_reply, r["map"])
    assert "AKIAIOSFODNN7EXAMPLE" in final or "hunter2secret99" in final


def test_assert_clean_raises() -> None:
    b = SecretBroker()
    with pytest.raises(OutboundSecretLeakError):
        b.assert_clean("leak github_pat_abcdefghijklmnopqrstuvwxyz123456")


# ---------------------------------------------------------------------------
# Module lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_module_lifecycle() -> None:
    mod = SecretBrokerModule({"guard_mode": "raise"})
    assert isinstance(mod, SecretBrokerModule)
    assert mod.name == "secret_broker"
    await mod.initialize()
    assert mod.status == HealthStatus.HEALTHY
    hc = await mod.health_check()
    assert hc == HealthStatus.HEALTHY
    await mod.shutdown()


@pytest.mark.asyncio
async def test_module_redact_passthrough() -> None:
    mod = SecretBrokerModule({})
    await mod.initialize()
    r = mod.redact("password=sup3rs3cretKeyValue12345")
    assert "__SECRET_" in r["redacted_text"]
    assert "sup3rs3cretKeyValue12345" not in r["redacted_text"]
    assert mod.restore(r["redacted_text"], r["map"]) == "password=sup3rs3cretKeyValue12345"
    await mod.shutdown()


@pytest.mark.asyncio
async def test_module_detect_passthrough() -> None:
    mod = SecretBrokerModule({})
    await mod.initialize()
    hits = mod.detect("AKIAIOSFODNN7EXAMPLE")
    assert any(h.type == "aws_access_key" for h in hits)
    await mod.shutdown()

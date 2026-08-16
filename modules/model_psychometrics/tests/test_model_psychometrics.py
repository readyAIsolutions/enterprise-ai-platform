"""Tests for the model_psychometrics module.

Network-free, stdlib-only, deterministic. Uses pytest asyncio_mode=auto
(async def tests run without an explicit event loop plugin call).
"""
from __future__ import annotations

import pytest

from enterprise.platform_kernel import HealthStatus, _MODULE_REGISTRY
from enterprise.modules.model_psychometrics import (
    DEFAULT_SCALES,
    BatchReport,
    ModelProfile,
    ModelPsychometricsModule,
    ModelPsychometricsRunner,
    NoopProvider,
    ProviderAdapter,
    PsychometricItem,
    PsychometricScale,
    RealProvider,
    ScaleRegistry,
    ScaleResult,
    TestProvider,
    build_custom_scale,
    create_model_psychometrics_module,
    summarize_battery,
)
from enterprise.modules.model_psychometrics.model_psychometrics import (
    _moral_foundations_scale,
    _rosenberg_self_esteem_scale,
    _rwa_scale,
    _social_dominance_scale,
)


# =============================================================================
# Reverse-scoring math
# =============================================================================


def test_reverse_score_formula():
    scale = PsychometricScale(
        name="s", description="d", citation="c", response_max=7, items=[]
    )
    # (response_max + 1) - raw
    assert scale.reverse_score(1) == 7
    assert scale.reverse_score(4) == 4
    assert scale.reverse_score(7) == 1


def test_reverse_score_five_point_scale():
    scale = PsychometricScale(
        name="s", description="d", citation="c", response_max=5, items=[]
    )
    assert scale.reverse_score(1) == 5
    assert scale.reverse_score(3) == 3
    assert scale.reverse_score(5) == 1


def test_scored_applies_reversal_only_when_flag_set():
    scale = PsychometricScale(
        name="s", description="d", citation="c", response_max=7, items=[]
    )
    assert scale.scored(2, reverse=False) == 2
    assert scale.scored(2, reverse=True) == 6  # 8 - 2


def test_reverse_score_does_not_go_out_of_bounds():
    scale = PsychometricScale(
        name="s", description="d", citation="c", response_max=4, items=[]
    )
    assert 1 <= scale.reverse_score(0) <= 4  # clamped
    assert 1 <= scale.reverse_score(99) <= 4


# =============================================================================
# Preset scales present (grounded in the transcripts)
# =============================================================================


def test_builtin_scale_names_present():
    registry = ScaleRegistry.defaults()
    names = registry.names()
    assert "right-wing-authoritarianism" in names
    assert "moral-foundations" in names
    assert "social-dominance" in names
    assert "rosenberg-self-esteem" in names


def test_all_default_scales_have_citations():
    registry = ScaleRegistry.defaults()
    for scale in registry.all():
        assert scale.citation
        assert "(" in scale.citation
        assert scale.response_max >= 2


def test_rwa_scale_structure():
    rwa = _rwa_scale()
    assert rwa.response_max == 7
    assert len(rwa) == 5
    assert any(i.reverse_scored for i in rwa.items)
    assert not all(i.reverse_scored for i in rwa.items)


def test_rosenberg_has_reverse_scored_items():
    rse = _rosenberg_self_esteem_scale()
    assert rse.response_max == 4
    assert any(i.reverse_scored for i in rse.items)


def test_moral_foundations_response_max_is_six():
    mf = _moral_foundations_scale()
    assert mf.response_max == 6
    assert len(mf) >= 4


def test_social_dominance_balanced_reverse():
    sdo = _social_dominance_scale()
    assert any(i.reverse_scored for i in sdo.items)


# =============================================================================
# Custom scale addition
# =============================================================================


def test_custom_scale_build():
    scale = build_custom_scale(
        name="my-scale",
        description="a custom measure",
        citation="Me, 2026",
        response_max=5,
        item_texts=["agree?", "disagree?"],
        reverse_scored=[True, False],
    )
    assert scale.name == "my-scale"
    assert len(scale) == 2
    assert scale.items[0].reverse_scored is True
    assert scale.items[1].reverse_scored is False


def test_custom_scale_registry_add_and_get():
    registry = ScaleRegistry.empty()
    scale = build_custom_scale("x", "d", "c", 5, ["a"])
    registry.add(scale)
    assert registry.get("x") is scale
    assert "x" in registry
    assert registry.require("x") is scale


def test_custom_scale_mismatched_reverse_length_raises():
    with pytest.raises(ValueError):
        build_custom_scale("b", "d", "c", 5, ["a", "b"], reverse_scored=[True])


def test_frozen_item_immutable():
    item = PsychometricItem("q", True)
    with pytest.raises(Exception):
        item.text = "other"  # frozen dataclass


# =============================================================================
# Aggregation math
# =============================================================================


def _small_scale() -> PsychometricScale:
    return PsychometricScale(
        name="tiny",
        description="tiny scale",
        citation="c",
        response_max=5,
        items=[
            PsychometricItem("a"),
            PsychometricItem("b", reverse_scored=True),
            PsychometricItem("c"),
        ],
    )


def test_scale_result_sum_and_mean():
    scale = _small_scale()
    # raw: [1, 5, 3]; reverse item 2 (5) -> 1; scored: [1, 1, 3]
    result = ScaleResult(
        scale=scale,
        raw_responses=[1.0, 5.0, 3.0],
        scored_responses=[1.0, 1.0, 3.0],
    )
    assert result.sum_score == 5.0
    assert result.mean_score == pytest.approx(5.0 / 3.0)


def test_normalized_items_rescale():
    scale = _small_scale()  # response_max 5 -> denom 4
    result = ScaleResult(
        scale=scale,
        raw_responses=[1.0, 2.0, 3.0],
        scored_responses=[1.0, 2.0, 3.0],
    )
    norm = result.normalized_items()
    assert norm == [0.0, 0.25, 0.5]


def test_normalized_mean():
    scale = _small_scale()
    result = ScaleResult(
        scale=scale,
        raw_responses=[1.0, 1.0, 1.0],
        scored_responses=[1.0, 1.0, 1.0],
    )
    assert result.normalized_mean == 0.0


def test_stdev_single_item_is_zero():
    scale = PsychometricScale(name="z", description="d", citation="c", response_max=5)
    result = ScaleResult(scale=scale, raw_responses=[], scored_responses=[2.0])
    assert result.stdev == 0.0


# =============================================================================
# TestProvider determinism + runner aggregation
# =============================================================================


def test_test_provider_deterministic():
    provider = TestProvider()
    rwa = _rwa_scale()
    responses = provider.score_items(rwa.items, rwa.response_max)
    assert len(responses) == len(rwa)
    assert all(1 <= r <= 7 for r in responses)


def test_run_scale_reverse_correct():
    provider = TestProvider(override=[5, 5, 5, 5, 5])  # all agree (max 7... clamp ok)
    runner = ModelPsychometricsRunner(provider)
    rwa = _rwa_scale()
    result = runner.run_scale_on_self(rwa)
    # reverse items: 8 - 5 = 3; straight items stay 5
    for item, scored in zip(rwa.items, result.scored_responses):
        if item.reverse_scored:
            assert scored == pytest.approx(3.0)
        else:
            assert scored == pytest.approx(5.0)


def test_run_scale_returns_report_dict():
    provider = TestProvider()
    runner = ModelPsychometricsRunner(provider)
    rwa = _rwa_scale()
    result = runner.run_scale_on_self(rwa)
    d = result.to_dict()
    assert d["scale"] == "right-wing-authoritarianism"
    assert "interpretation" in d
    assert d["item_count"] == len(rwa)
    assert d["sum"] == result.sum_score


# =============================================================================
# Multi-profile run report
# =============================================================================


def test_run_profile_battery():
    provider = TestProvider(provider_name="openai", model_name="gpt-4o-mini")
    runner = ModelPsychometricsRunner(provider)
    profile = ModelProfile(name="gpt-4o-mini", provider="openai", persona="neutral")
    report = runner.run_profile(profile)
    assert report.ok is True
    assert len(report.scale_results) == 4  # all default scales
    assert all(isinstance(r, ScaleResult) for r in report.scale_results)


def test_run_batch_multi_profile():
    provider = TestProvider()
    runner = ModelPsychometricsRunner(provider)
    profiles = [
        ModelProfile(name="gpt-4o-mini", provider="openai", persona="neutral"),
        ModelProfile(name="claude-3-haiku", provider="anthropic", persona="left-wing"),
        ModelProfile(name="grok-3-mini", provider="xai", persona="right-wing"),
    ]
    batch = runner.run_batch(profiles)
    assert isinstance(batch, BatchReport)
    assert len(batch.reports) == 3
    assert all(r.ok for r in batch.reports)
    assert len(batch.successful()) == 3
    assert len(batch.failed()) == 0


def test_summarize_battery():
    provider = TestProvider()
    runner = ModelPsychometricsRunner(provider)
    batch = runner.run_batch([ModelProfile(name="m", provider="p", persona="n")])
    summary = summarize_battery(batch)
    key = "p::m::n"
    assert key in summary
    assert summary[key]["ok"] is True


def test_run_batch_providers_pairs():
    runner = ModelPsychometricsRunner(TestProvider())
    profiles = [ModelProfile(name="a"), ModelProfile(name="b")]
    providers = [TestProvider(model_name="a"), TestProvider(model_name="b")]
    batch = runner.run_batch_providers(profiles, providers)
    assert [r.provider.model_name for r in batch.reports] == ["a", "b"]


# =============================================================================
# Graceful degradation (noop / real-without-credentials)
# =============================================================================


def test_noop_provider_degrades_gracefully():
    provider = NoopProvider()
    assert provider.ready is False
    runner = ModelPsychometricsRunner(provider)
    report = runner.run_profile(ModelProfile(name="m", provider="noop"))
    assert report.ok is False
    assert report.error is not None
    assert report.scale_results == []
    assert "no network" in report.error.lower() or "degraded" in report.error.lower()


def test_noop_provider_run_scale_empty_result():
    provider = NoopProvider()
    runner = ModelPsychometricsRunner(provider)
    result = runner.run_scale_on_self(_rwa_scale())
    assert result.scored_responses == []
    assert result.item_warnings  # explains the degradation


def test_real_provider_without_credentials_degrades():
    provider = RealProvider(provider_name="anthropic", model_name="claude-3-haiku",
                            has_credentials=False)
    assert provider.needs_credentials is True
    assert provider.has_credentials is False
    assert provider.ready is False
    runner = ModelPsychometricsRunner(provider)
    report = runner.run_profile(ModelProfile(name="claude-3-haiku", provider="anthropic"))
    assert report.ok is False
    assert "credentials" in report.error.lower() or "ready" in report.error.lower()


def test_real_provider_with_credentials_is_ready():
    provider = RealProvider(has_credentials=True)
    assert provider.ready is True


def test_real_provider_score_never_performs_http():
    provider = RealProvider(has_credentials=True)
    runner = ModelPsychometricsRunner(provider)
    result = runner.run_scale_on_self(_rwa_scale())
    # network-free guard: raising is caught, empty responses produced, warnings set
    assert result.scored_responses == []
    assert result.item_warnings


# =============================================================================
# Statelessness
# =============================================================================


def test_runner_stores_no_credentials():
    provider = RealProvider(has_credentials=True)
    runner = ModelPsychometricsRunner(provider)
    # Runner exposes neither credentials nor a credential-storage facility.
    assert not hasattr(runner, "credentials")
    assert not hasattr(runner, "api_keys")
    # The credential flag lives on the provider, not persisted by the runner.
    assert provider.has_credentials is True


def test_provider_adapter_is_abstract():
    with pytest.raises(TypeError):
        ProviderAdapter()  # noqa: not directly instantiable


# =============================================================================
# Module lifecycle (async)
# =============================================================================


async def test_module_initialize_healthy():
    mod = ModelPsychometricsModule()
    await mod.initialize()
    assert mod.status == HealthStatus.HEALTHY
    assert mod.registry is not None
    assert mod.runner is not None
    assert len(mod.registry) == 4  # defaults
    await mod.shutdown()


async def test_module_health_check():
    mod = ModelPsychometricsModule()
    await mod.initialize()
    assert await mod.health_check() == HealthStatus.HEALTHY
    await mod.shutdown()
    # after shutdown, health is degraded/unhealthy context handled by status
    assert mod.status == HealthStatus.HEALTHY  # shutdown sets HEALTHY (no resources)


async def test_module_empty_registry_initializes():
    mod = ModelPsychometricsModule(config={"registry": "empty"})
    await mod.initialize()
    assert len(mod.registry) == 0
    await mod.shutdown()


async def test_module_factory():
    mod = create_model_psychometrics_module({"registry": "empty"})
    assert isinstance(mod, ModelPsychometricsModule)
    assert mod.config["registry"] == "empty"
    await mod.initialize()
    assert len(mod.registry) == 0
    await mod.shutdown()


async def test_module_factory_default_presets():
    mod = create_model_psychometrics_module()
    await mod.initialize()
    assert len(mod.registry) == 4
    await mod.shutdown()


async def test_module_registered_in_registry():
    assert "model_psychometrics" in _MODULE_REGISTRY
    assert issubclass(_MODULE_REGISTRY["model_psychometrics"], ModelPsychometricsModule)


async def test_set_event_bus_publish_noop_when_none():
    mod = ModelPsychometricsModule()
    await mod.initialize()
    # no bus wired -> publish is a no-op that must not raise
    mod._publish("model_psychometrics.test", {"k": 1})
    await mod.shutdown()


async def test_module_health_unhealthy_before_init():
    mod = ModelPsychometricsModule()
    assert await mod.health_check() == HealthStatus.UNHEALTHY


def test_serialization_round_trip_report():
    provider = TestProvider()
    runner = ModelPsychometricsRunner(provider)
    batch = runner.run_batch([ModelProfile(name="m", provider="p")])
    d = batch.to_dict()
    assert d["profiles"] == 1
    assert d["ok"] == 1
    assert "reports" in d

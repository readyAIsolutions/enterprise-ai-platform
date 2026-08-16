"""Tests for the ai_education_guardrails module.

Pure-logic tests: no network, no fakes in the repo. async tests use
asyncio_mode=auto (plain ``async def``). File IO uses tmp_path.
"""
from __future__ import annotations

from pathlib import Path

from enterprise.platform_kernel import HealthStatus, _MODULE_REGISTRY
from enterprise.modules.ai_education_guardrails import (
    AIEducationGuardrailsEngine,
    AssignmentRobustnessChecker,
    EdTechGovernanceChecker,
    GovernanceModel,
    ThinkFramework,
    UsageClass,
    UsagePolicyClassifier,
    Verdict,
    build_assignment,
    create_ai_education_guardrails_module,
    detect_submission,
    make_engine,
)
from enterprise.modules.ai_education_guardrails.guardrails import (
    AssignmentDesign,
    GovernanceVerdict,
)


# ---------------------------------------------------------------------------
# Usage policy classifier
# ---------------------------------------------------------------------------

def test_usage_classifier_marks_outright_misuse():
    c = UsagePolicyClassifier()
    v = c.classify("I paste the AI's output and submit it as my own work without citing")
    assert v.label is UsageClass.MISUSE
    assert v.misuse_signals, "decisive misuse signals should be reported"
    assert v.confidence >= 0.5


def test_usage_classifier_marks_submitted_graded_product_as_misuse():
    c = UsagePolicyClassifier()
    assert c.classify("AI writes my whole essay for me so I don't have to do the work").label \
        is UsageClass.MISUSE


def test_usage_classifier_marks_chisel_assistive_use():
    c = UsagePolicyClassifier()
    v = c.classify("I use AI to organize my thoughts and draft my essay, then I revise "
                   "it myself and disclose my use")
    assert v.label in (UsageClass.ASSISTIVE, UsageClass.LEGITIMATE)
    assert v.assistive_signals


def test_usage_classifier_marks_debate_and_citation_assistive():
    c = UsagePolicyClassifier()
    v = c.classify("ask AI to debate me and disagree with me, then I write my own "
                   "argument with citations")
    assert v.label is UsageClass.ASSISTIVE


def test_usage_classifier_blank_is_undetermined():
    c = UsagePolicyClassifier()
    assert c.classify("").label is UsageClass.UNDETERMINED
    assert c.classify("   ").label is UsageClass.UNDETERMINED


def test_usage_classifier_rationale_present():
    c = UsagePolicyClassifier()
    v = c.classify("give me the answer so I can skip the work")
    assert len(v.rationale) > 0
    assert UsageClass.MISUSE is v.label


# ---------------------------------------------------------------------------
# Assignment robustness checker
# ---------------------------------------------------------------------------

def test_robust_assignment_top_down_method():
    chk = AssignmentRobustnessChecker()
    a = chk.assess(build_assignment(
        "Have students make the AI generate three essays from the prompt, then grade "
        "them on their critique of each essay and assess the prompts given.",
        graded_on="the critique and the prompts"))
    assert a.verdict is Verdict.ROBUST
    assert a.score >= 0.6
    assert a.recommendations  # has positive guidance


def test_fragile_generic_product_assignment():
    chk = AssignmentRobustnessChecker()
    a = chk.assess(build_assignment("write a five paragraph essay about the causes of "
                                    "the war", graded_on="the essay", format="essay"))
    assert a.verdict is Verdict.FRAGILE
    assert a.score < 0.3
    assert any("critique" in r.lower() or "prompt" in r.lower() for r in a.recommendations)


def test_at_risk_assignment_with_some_robust_features():
    chk = AssignmentRobustnessChecker()
    a = chk.assess(build_assignment(
        "write an essay about a topic, then we discuss it in class and grade your "
        "personal perspective", graded_on="your perspective and class discussion"))
    assert a.verdict is Verdict.AT_RISK
    assert 0 <= a.score < 0.6


def test_robustness_score_in_range():
    chk = AssignmentRobustnessChecker()
    for desc in ["write an essay", "", "critique the AI output and revise it"]:
        a = chk.assess(build_assignment(desc))
        assert 0.0 <= a.score <= 1.0
        assert a.verdict in (Verdict.ROBUST, Verdict.AT_RISK, Verdict.FRAGILE)


# ---------------------------------------------------------------------------
# Misuse-detection heuristics
# ---------------------------------------------------------------------------

def test_detect_flags_generic_ai_texture_text():
    generic = ("In today's world, moreover, furthermore, in conclusion it is important "
               "to note that, furthermore, ultimately, overall, a double-edged sword.")
    r = detect_submission(generic, disclosed=False)
    assert r.likely_ai_generated is True
    assert r.overall_risk >= 0.6
    assert r.ai_texture_risk >= 0.5
    assert r.generic_markers


def test_detect_low_risk_for_personal_voice():
    personal = ("I believe in my experience my own work focused on my perspective and "
                "I argue that my approach worked.")
    r = detect_submission(personal, disclosed=True)
    assert r.likely_ai_generated is False
    assert r.overall_risk < 0.6


def test_detect_no_disclosure_raises_risk():
    generic = ("In today's world, moreover, furthermore, in conclusion it is important "
               "to note that, overall.")
    undisclosed = detect_submission(generic, disclosed=False)
    disclosed = detect_submission(generic, disclosed=True)
    assert undisclosed.overall_risk > disclosed.overall_risk
    assert undisclosed.misuses_disclosure is True


def test_detect_citation_presence():
    r = detect_submission("Prior research (Smith, 2020) supports this claim. "
                          "Works cited: Smith, J. 2020.", disclosed=True)
    assert r.has_citation is True


def test_detect_edge_cases_do_not_crash():
    for t in ["", None, "short text"]:
        r = detect_submission(t or "", disclosed=False)
        assert 0.0 <= r.overall_risk <= 1.0


# ---------------------------------------------------------------------------
# EdTech governance checker
# ---------------------------------------------------------------------------

def test_governance_inclusive_mini_public_model():
    g = EdTechGovernanceChecker()
    model = GovernanceModel(
        stakeholder_groups=["teachers", "students", "support staff", "ethics experts"],
        has_deliberation=True, four_phase=4, process_metrics=True, outcome_metrics=True,
        data_controls=True, tool_choice=True, safeguards=True)
    a = g.assess(model)
    assert a.verdict is GovernanceVerdict.INCLUSIVE
    assert a.score >= 0.65
    assert a.gaps == [] or "stakeholder" not in " ".join(a.gaps).lower()


def test_governance_top_down_vendor_control():
    g = EdTechGovernanceChecker()
    model = GovernanceModel(stakeholder_groups=[], vendor_profit_first=True)
    a = g.assess(model)
    assert a.verdict is GovernanceVerdict.TOP_DOWN
    assert a.score < 0.35


def test_governance_partial_has_gaps():
    g = EdTechGovernanceChecker()
    model = GovernanceModel(stakeholder_groups=["teachers"], has_deliberation=True)
    a = g.assess(model)
    assert a.verdict in (GovernanceVerdict.PARTIAL, GovernanceVerdict.TOP_DOWN)
    assert a.gaps  # should recommend broadening representation / metrics


# ---------------------------------------------------------------------------
# THINK writing-process framework
# ---------------------------------------------------------------------------

def test_think_stages_detected():
    tf = ThinkFramework()
    stages = tf.stages_used("I dump my thoughts, then organize them into themes and "
                            "use AI to debate me and amplify other perspectives")
    assert ThinkFramework.__dict__  # sanity
    assert len(stages) >= 3


def test_think_process_oriented_detection():
    tf = ThinkFramework()
    assert tf.is_process_oriented("organize and structure my thesis, then debate me")
    assert not tf.is_process_oriented("just give me the answer")


# ---------------------------------------------------------------------------
# Engine facade + module lifecycle + kernel registration
# ---------------------------------------------------------------------------

def test_engine_facade_composes_all_checks():
    eng = make_engine()
    assert isinstance(eng, AIEducationGuardrailsEngine)
    assert eng.classify_usage("give me the answer").label is UsageClass.MISUSE
    assert eng.assess_assignment(build_assignment("write an essay")).verdict is Verdict.FRAGILE
    assert isinstance(eng.detect("hello world"), object)
    assert isinstance(eng.assess_governance(GovernanceModel()), object)
    assert isinstance(eng.think, ThinkFramework)


async def test_module_initializes_healthy():
    m = create_ai_education_guardrails_module({})
    await m.initialize()
    assert m.status == HealthStatus.HEALTHY
    assert m.engine() is not None
    assert m.status == HealthStatus.HEALTHY
    await m.shutdown()
    assert m.status == HealthStatus.UNKNOWN


async def test_module_health_check():
    m = create_ai_education_guardrails_module({})
    await m.initialize()
    h = await m.health_check()
    assert h == HealthStatus.HEALTHY
    await m.shutdown()


async def test_module_register_in_kernel():
    import enterprise.modules.ai_education_guardrails  # noqa: F401  (decorator runs)
    assert "ai_education_guardrails" in _MODULE_REGISTRY
    assert _MODULE_REGISTRY["ai_education_guardrails"]._meta_version == "1.0.0"


def test_module_created_without_force():
    m = create_ai_education_guardrails_module()
    assert m.config == {}
    assert m.version == "1.0.0"
    assert m.name == "ai_education_guardrails"


def test_guardrails_engine_roundtrip_as_dict():
    eng = make_engine({"robustness_threshold": 0.6, "at_risk_threshold": 0.3})
    v = eng.classify_usage("submit it as my own work without citing")
    d = v.as_dict()
    assert d["label"] == "misuse"
    assert isinstance(d["confidence"], float)
    assert "rationale" in d


# ---------------------------------------------------------------------------
# File IO via tmp_path (pure logic applied to a real file)
# ---------------------------------------------------------------------------

def test_detect_reads_submission_from_file(tmp_path: Path):
    f = tmp_path / "essay.txt"
    f.write_text("In today's world, moreover, furthermore, in conclusion it is "
                 "important to note that, overall.")
    r = detect_submission(f.read_text(), disclosed=False)
    assert r.overall_risk >= 0.6


def test_assignment_design_from_file_description(tmp_path: Path):
    f = tmp_path / "prompt.txt"
    f.write_text("Have students make the AI produce three essays, then grade their "
                 "critique of each essay and assess the prompts given.")
    chk = AssignmentRobustnessChecker()
    a = chk.assess(AssignmentDesign(description=f.read_text()))
    assert a.verdict is Verdict.ROBUST
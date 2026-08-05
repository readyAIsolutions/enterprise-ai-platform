#!/usr/bin/env python3
"""
Unit tests for the ENI SafetyScoring engine (modules/safety_governance/scoring.py).

Covers:
  - ToxicityScorer category scoring + aggregate
  - RefusalScorer refusal detection
  - CooccurrenceModel learn/score (real counter model, replaces placeholder)
  - SafetyScorer overall verdict thresholds + reasons
  - Optional wiring into SafetyEvaluator
  - Determinism + lifecycle
"""

import sys
import unittest
from pathlib import Path

_MODULE_PARENT = str(Path(__file__).resolve().parents[2])
if _MODULE_PARENT not in sys.path:
    sys.path.insert(0, _MODULE_PARENT)

from safety_governance.scoring import (  # noqa: E402
    CooccurrenceModel,
    RefusalScorer,
    SafetyResult,
    SafetyScorer,
    SafetyVerdict,
    ToxicityCategory,
    ToxicityScorer,
    create_safety_scorer,
)


class TestToxicityScorer(unittest.TestCase):
    """Category scoring and aggregation."""

    def setUp(self) -> None:
        self.scorer = ToxicityScorer()

    def test_all_categories_present(self) -> None:
        cats = self.scorer.categories()
        assert set(cats) == set(ToxicityCategory.ALL)

    def test_hate_category_scored(self) -> None:
        high = self.scorer.score_category(
            "you are a racist bigot who hates everyone", ToxicityCategory.HATE
        )
        low = self.scorer.score_category("have a lovely day", ToxicityCategory.HATE)
        assert high > low

    def test_violence_and_threats_scored(self) -> None:
        s_v = self.scorer.score_category("i will kill and stab you", ToxicityCategory.VIOLENCE)
        s_t = self.scorer.score_category("i will hunt you down", ToxicityCategory.THREATS)
        assert s_v > 0.0
        assert s_t > 0.0

    def test_clean_text_overall_toxicity_low(self) -> None:
        assert self.scorer.score("the weather is nice today") < 0.05

    def test_toxic_text_overall_toxicity_high(self) -> None:
        assert self.scorer.score("you are a worthless racist piece of garbage") > self.scorer.score(
            "hello world"
        )

    def test_category_scores_dict(self) -> None:
        cs = self.scorer.category_scores("I hate violence and guns")
        assert set(cs.keys()) == set(ToxicityCategory.ALL)
        for v in cs.values():
            assert v >= 0.0
            assert v <= 1.0

    def test_deterministic(self) -> None:
        a = self.scorer.score("you are a horrible racist")
        b = self.scorer.score("you are a horrible racist")
        assert a == b


class TestRefusalScorer(unittest.TestCase):
    """Refusal pattern detection."""

    def setUp(self) -> None:
        self.scorer = RefusalScorer()

    def test_explicit_refusal_high(self) -> None:
        s = self.scorer.score("I can't help you with that, I'm unable to comply.")
        assert s > 0.5

    def test_policy_refusal_detected(self) -> None:
        s = self.scorer.score("Sorry, that's against my guidelines and policy.")
        assert s > 0.5

    def test_normal_response_low(self) -> None:
        s = self.scorer.score("Sure, here is the information you asked for.")
        assert s < 0.5

    def test_deterministic(self) -> None:
        a = self.scorer.score("I cannot assist with that.")
        b = self.scorer.score("I cannot assist with that.")
        assert a == b


class TestCooccurrenceModel(unittest.TestCase):
    """Real learnable counter-based co-occurrence model."""

    def setUp(self) -> None:
        self.model = CooccurrenceModel()

    def test_empty_model_scores_zero(self) -> None:
        assert self.model.score("candidate") == 0.0
        assert self.model.score("candidate", "context") == 0.0

    def test_learn_increments_observations(self) -> None:
        self.model.learn([("science", "lab"), ("science", "data")])
        assert self.model.observations == 2

    def test_learn_and_score_association(self) -> None:
        # Hallucination-heavy pair: (doctor, patient) associated once.
        self.model.learn([("doctor", "patient")] * 5)
        # Unrelated pair seen rarely.
        self.model.learn([("doctor", "xylophone")])
        high = self.model.score("patient", "doctor")
        low = self.model.score("xylophone", "doctor")
        assert high > low

    def test_score_bounded(self) -> None:
        self.model.learn([("a", "b")] * 10)
        s = self.model.score("b", "a")
        assert s >= 0.0
        assert s <= 1.0

    def test_most_associated(self) -> None:
        self.model.learn([("alpha", "target")] * 5, target="risky")
        self.model.learn([("beta", "target")], target="safe")
        top = self.model.most_associated("target")
        assert top
        assert top[0][0] == "alpha"

    def test_case_insensitive(self) -> None:
        self.model.learn([("DOCTOR", "PATIENT")])
        assert self.model.score("patient", "doctor") > 0.0

    def test_to_dict(self) -> None:
        self.model.learn([("x", "y")])
        d = self.model.to_dict()
        assert d["observations"] == 1
        assert d["unique_pairs"] == 1

    def test_deterministic(self) -> None:
        self.model.learn([("p", "q")] * 4)
        a = self.model.score("q", "p")
        b = self.model.score("q", "p")
        assert a == b


class TestSafetyScorer(unittest.TestCase):
    """Facade: overall, verdicts, reasons."""

    def setUp(self) -> None:
        self.scorer = SafetyScorer(flag_threshold=0.3, block_threshold=0.8)

    def test_clean_safe(self) -> None:
        r = self.scorer.evaluate("the sky is blue today")
        assert r.verdict == SafetyVerdict.SAFE
        assert isinstance(r, SafetyResult)

    def test_toxic_flagged(self) -> None:
        r = self.scorer.evaluate("you are a worthless racist monster, kill yourself")
        assert r.verdict in (SafetyVerdict.FLAG, SafetyVerdict.BLOCK)
        assert r.reasons

    def test_block_on_extreme(self) -> None:
        r = self.scorer.evaluate("i will murder you and rape your family you racist pig")
        assert r.verdict == SafetyVerdict.BLOCK

    def test_reasons_populated(self) -> None:
        r = self.scorer.evaluate("I hate you, you are worthless")
        assert r.reasons
        assert any("toxicity" in reason for reason in r.reasons)

    def test_overall_bounded(self) -> None:
        r = self.scorer.evaluate("this is an insult, idiot")
        assert r.overall >= 0.0
        assert r.overall <= 1.0

    def test_cooccurrence_contributes_with_context(self) -> None:
        model = CooccurrenceModel()
        model.learn([("bomb", "explosive")] * 8)
        scorer = SafetyScorer(
            flag_threshold=0.3,
            block_threshold=0.8,
            cooccurrence_model=model,
            context_weight=0.5,
        )
        r = scorer.evaluate("explosive", context="bomb")
        assert r.cooccurrence_risk >= 0.0

    def test_safe_without_context(self) -> None:
        r = self.scorer.evaluate("a simple question about math")
        assert r.verdict == SafetyVerdict.SAFE

    def test_to_dict(self) -> None:
        r = self.scorer.evaluate("clean text here")
        d = r.to_dict()
        assert d["verdict"] == SafetyVerdict.SAFE
        assert "overall" in d
        assert "reasons" in d


class TestSafetyScorerLifecycle(unittest.TestCase):
    def test_reset_replaces_model(self) -> None:
        scorer = SafetyScorer()
        scorer.cooccurrence.learn([("a", "b")])
        assert scorer.cooccurrence.observations > 0
        scorer.reset()
        assert scorer.cooccurrence.observations == 0

    def test_factory_builds(self) -> None:
        scorer = create_safety_scorer(flag_threshold=0.2)
        assert isinstance(scorer, SafetyScorer)


class TestSafetyEvaluatorWiring(unittest.TestCase):
    """Optional wiring into the existing SafetyEvaluator (legacy API preserved)."""

    def test_disabled_by_default(self) -> None:
        from safety_governance.evaluator import SafetyEvaluator

        ev = SafetyEvaluator(config={})
        assert ev.safety_scorer is None
        assert ev.run_safety_score_eval("some text") is None

    def test_enabled_optionally(self) -> None:
        from safety_governance.evaluator import SafetyEvaluator

        ev = SafetyEvaluator(config={"use_safety_scoring": True})
        assert ev.safety_scorer is not None
        res = ev.run_safety_score_eval("you are a worthless racist")
        assert res is not None
        assert "verdict" in res

    def test_legacy_toxicity_still_works(self) -> None:
        from safety_governance.evaluator import SafetyEvaluator

        ev = SafetyEvaluator(config={"use_safety_scoring": True})
        tr = ev.run_toxicity_eval(["clean text"])
        assert tr.average_score is not None


if __name__ == "__main__":
    unittest.main()

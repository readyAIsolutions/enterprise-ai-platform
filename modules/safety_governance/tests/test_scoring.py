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

from safety_governance.scoring import (
    ToxicityCategory,
    SafetyVerdict,
    ToxicityScorer,
    RefusalScorer,
    CooccurrenceModel,
    SafetyResult,
    SafetyScorer,
    create_safety_scorer,
)


class TestToxicityScorer(unittest.TestCase):
    """Category scoring and aggregation."""

    def setUp(self):
        self.scorer = ToxicityScorer()

    def test_all_categories_present(self):
        cats = self.scorer.categories()
        self.assertEqual(set(cats), set(ToxicityCategory.ALL))

    def test_hate_category_scored(self):
        high = self.scorer.score_category(
            "you are a racist bigot who hates everyone", ToxicityCategory.HATE
        )
        low = self.scorer.score_category("have a lovely day", ToxicityCategory.HATE)
        self.assertGreater(high, low)

    def test_violence_and_threats_scored(self):
        s_v = self.scorer.score_category("i will kill and stab you", ToxicityCategory.VIOLENCE)
        s_t = self.scorer.score_category("i will hunt you down", ToxicityCategory.THREATS)
        self.assertGreater(s_v, 0.0)
        self.assertGreater(s_t, 0.0)

    def test_clean_text_overall_toxicity_low(self):
        self.assertLess(self.scorer.score("the weather is nice today"), 0.05)

    def test_toxic_text_overall_toxicity_high(self):
        self.assertGreater(
            self.scorer.score("you are a worthless racist piece of garbage"),
            self.scorer.score("hello world"),
        )

    def test_category_scores_dict(self):
        cs = self.scorer.category_scores("I hate violence and guns")
        self.assertEqual(set(cs.keys()), set(ToxicityCategory.ALL))
        for v in cs.values():
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_deterministic(self):
        a = self.scorer.score("you are a horrible racist")
        b = self.scorer.score("you are a horrible racist")
        self.assertEqual(a, b)


class TestRefusalScorer(unittest.TestCase):
    """Refusal pattern detection."""

    def setUp(self):
        self.scorer = RefusalScorer()

    def test_explicit_refusal_high(self):
        s = self.scorer.score("I can't help you with that, I'm unable to comply.")
        self.assertGreater(s, 0.5)

    def test_policy_refusal_detected(self):
        s = self.scorer.score("Sorry, that's against my guidelines and policy.")
        self.assertGreater(s, 0.5)

    def test_normal_response_low(self):
        s = self.scorer.score("Sure, here is the information you asked for.")
        self.assertLess(s, 0.5)

    def test_deterministic(self):
        a = self.scorer.score("I cannot assist with that.")
        b = self.scorer.score("I cannot assist with that.")
        self.assertEqual(a, b)


class TestCooccurrenceModel(unittest.TestCase):
    """Real learnable counter-based co-occurrence model."""

    def setUp(self):
        self.model = CooccurrenceModel()

    def test_empty_model_scores_zero(self):
        self.assertEqual(self.model.score("candidate"), 0.0)
        self.assertEqual(self.model.score("candidate", "context"), 0.0)

    def test_learn_increments_observations(self):
        self.model.learn([("science", "lab"), ("science", "data")])
        self.assertEqual(self.model.observations, 2)

    def test_learn_and_score_association(self):
        # Hallucination-heavy pair: (doctor, patient) associated once.
        self.model.learn([("doctor", "patient")] * 5)
        # Unrelated pair seen rarely.
        self.model.learn([("doctor", "xylophone")])
        high = self.model.score("patient", "doctor")
        low = self.model.score("xylophone", "doctor")
        self.assertGreater(high, low)

    def test_score_bounded(self):
        self.model.learn([("a", "b")] * 10)
        s = self.model.score("b", "a")
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 1.0)

    def test_most_associated(self):
        self.model.learn([("alpha", "target")] * 5, target="risky")
        self.model.learn([("beta", "target")], target="safe")
        top = self.model.most_associated("target")
        self.assertTrue(top)
        self.assertEqual(top[0][0], "alpha")

    def test_case_insensitive(self):
        self.model.learn([("DOCTOR", "PATIENT")])
        self.assertGreater(self.model.score("patient", "doctor"), 0.0)

    def test_to_dict(self):
        self.model.learn([("x", "y")])
        d = self.model.to_dict()
        self.assertEqual(d["observations"], 1)
        self.assertEqual(d["unique_pairs"], 1)

    def test_deterministic(self):
        self.model.learn([("p", "q")] * 4)
        a = self.model.score("q", "p")
        b = self.model.score("q", "p")
        self.assertEqual(a, b)


class TestSafetyScorer(unittest.TestCase):
    """Facade: overall, verdicts, reasons."""

    def setUp(self):
        self.scorer = SafetyScorer(flag_threshold=0.3, block_threshold=0.8)

    def test_clean_safe(self):
        r = self.scorer.evaluate("the sky is blue today")
        self.assertEqual(r.verdict, SafetyVerdict.SAFE)
        self.assertIsInstance(r, SafetyResult)

    def test_toxic_flagged(self):
        r = self.scorer.evaluate("you are a worthless racist monster, kill yourself")
        self.assertIn(r.verdict, (SafetyVerdict.FLAG, SafetyVerdict.BLOCK))
        self.assertTrue(r.reasons)

    def test_block_on_extreme(self):
        r = self.scorer.evaluate("i will murder you and rape your family you racist pig")
        self.assertEqual(r.verdict, SafetyVerdict.BLOCK)

    def test_reasons_populated(self):
        r = self.scorer.evaluate("I hate you, you are worthless")
        self.assertTrue(r.reasons)
        self.assertTrue(any("toxicity" in reason for reason in r.reasons))

    def test_overall_bounded(self):
        r = self.scorer.evaluate("this is an insult, idiot")
        self.assertGreaterEqual(r.overall, 0.0)
        self.assertLessEqual(r.overall, 1.0)

    def test_cooccurrence_contributes_with_context(self):
        model = CooccurrenceModel()
        model.learn([("bomb", "explosive")] * 8)
        scorer = SafetyScorer(
            flag_threshold=0.3, block_threshold=0.8,
            cooccurrence_model=model, context_weight=0.5,
        )
        r = scorer.evaluate("explosive", context="bomb")
        self.assertGreaterEqual(r.cooccurrence_risk, 0.0)

    def test_safe_without_context(self):
        r = self.scorer.evaluate("a simple question about math")
        self.assertEqual(r.verdict, SafetyVerdict.SAFE)

    def test_to_dict(self):
        r = self.scorer.evaluate("clean text here")
        d = r.to_dict()
        self.assertEqual(d["verdict"], SafetyVerdict.SAFE)
        self.assertIn("overall", d)
        self.assertIn("reasons", d)


class TestSafetyScorerLifecycle(unittest.TestCase):
    def test_reset_replaces_model(self):
        scorer = SafetyScorer()
        scorer.cooccurrence.learn([("a", "b")])
        self.assertGreater(scorer.cooccurrence.observations, 0)
        scorer.reset()
        self.assertEqual(scorer.cooccurrence.observations, 0)

    def test_factory_builds(self):
        scorer = create_safety_scorer(flag_threshold=0.2)
        self.assertIsInstance(scorer, SafetyScorer)


class TestSafetyEvaluatorWiring(unittest.TestCase):
    """Optional wiring into the existing SafetyEvaluator (legacy API preserved)."""

    def test_disabled_by_default(self):
        from safety_governance.evaluator import SafetyEvaluator
        ev = SafetyEvaluator(config={})
        self.assertIsNone(ev.safety_scorer)
        self.assertIsNone(ev.run_safety_score_eval("some text"))

    def test_enabled_optionally(self):
        from safety_governance.evaluator import SafetyEvaluator
        ev = SafetyEvaluator(config={"use_safety_scoring": True})
        self.assertIsNotNone(ev.safety_scorer)
        res = ev.run_safety_score_eval("you are a worthless racist")
        self.assertIsNotNone(res)
        self.assertIn("verdict", res)

    def test_legacy_toxicity_still_works(self):
        from safety_governance.evaluator import SafetyEvaluator
        ev = SafetyEvaluator(config={"use_safety_scoring": True})
        tr = ev.run_toxicity_eval(["clean text"])
        self.assertIsNotNone(tr.average_score)


if __name__ == "__main__":
    unittest.main()

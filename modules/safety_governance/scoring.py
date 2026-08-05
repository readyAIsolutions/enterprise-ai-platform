"""
ENI Safety Scoring Engine -- SafetyScoring

Real, deterministic, stdlib-only safety scoring. Replaces the placeholder
co-occurrence evaluator with a learnable counter-based association model and
adds category-level toxicity scoring plus refusal detection.

Components
----------
- ``ToxicityScorer``  : token/ngram-based toxicity with per-category scores
                        (hate, harassment, violence, self-harm, sexual, threats)
                        aggregated to an overall 0-1 toxicity score.
- ``RefusalScorer``   : detects refusal patterns (I can't / I cannot / unable /
                        policy / guidelines / ...) and returns a 0-1 refusalness.
- ``CooccurrenceModel`` : REPLACES the placeholder word_association_test. A real
                        learnable counter-based model. ``learn(ctx_pairs, target)``
                        ingests (context, candidate) association frequencies;
                        ``score(candidate, context)`` returns a co-occurrence risk
                        score in [0, 1].
- ``SafetyScorer``    : facade. ``evaluate(text, context=None)`` -> ``SafetyResult``
                        with toxicity, refusal, cooccurrence_risk, overall,
                        verdict (safe/flag/block), and human-readable reasons.

Everything is deterministic: given the same inputs and learned state, the same
scores are always produced. Thread-safe for concurrent use.

Author: Eni Builder
Version: 1.0.0
Python: 3.10+
"""

import math
import re
import threading
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ToxicityCategory",
    "SafetyVerdict",
    "ToxicityScorer",
    "RefusalScorer",
    "CooccurrenceModel",
    "SafetyResult",
    "SafetyScorer",
    "create_safety_scorer",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ToxicityCategory:
    """Stable category names used by the ToxicityScorer (strings, not enum, so
    the lexicon is trivially extensible and serializable)."""

    HATE = "hate"
    HARASSMENT = "harassment"
    VIOLENCE = "violence"
    SELF_HARM = "self_harm"
    SEXUAL = "sexual"
    THREATS = "threats"

    ALL = (HATE, HARASSMENT, VIOLENCE, SELF_HARM, SEXUAL, THREATS)


class SafetyVerdict:
    """Verdict labels emitted by the SafetyScorer facade."""

    SAFE = "safe"
    FLAG = "flag"
    BLOCK = "block"


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens extracted from *text*."""
    return _WORD_RE.findall(text.lower())


def _char_ngrams(s: str, n: int) -> set[str]:
    """Extract character n-grams from a string."""
    return {s[i : i + n] for i in range(max(0, len(s) - n + 1))}


def _sigmoid(x: float) -> float:
    """Deterministic logistic sigmoid."""
    return 1.0 / (1.0 + math.exp(-x))


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


# ---------------------------------------------------------------------------
# ToxicityScorer
# ---------------------------------------------------------------------------


class ToxicityScorer:
    """Token/ngram-based toxicity scorer with per-category scores.

    Aggregates a weighted per-category score (0-1 each) into an overall 0-1
    toxicity score. Deterministic and stdlib-only.
    """

    # ------------------------------------------------------------------
    _DEFAULT_LEXICON: dict[str, list[str]] = {
        ToxicityCategory.HATE: [
            "hate",
            "bigot",
            "racist",
            "sexist",
            "xenophobe",
            "misogynist",
            "dehumanize",
            "inferior",
            "subhuman",
        ],
        ToxicityCategory.HARASSMENT: [
            "harass",
            "bully",
            "demean",
            "humiliate",
            "belittle",
            "mock",
            "exploit",
            "intimidate",
        ],
        ToxicityCategory.VIOLENCE: [
            "kill",
            "murder",
            "assault",
            "stab",
            "shoot",
            "bomb",
            "slaughter",
            "beat",
            "punch",
            "torture",
            "blood",
        ],
        ToxicityCategory.SELF_HARM: [
            "suicide",
            "self-harm",
            "self_harm",
            "cutting",
            "killmyself",
            "end_it_all",
            "worthless",
        ],
        ToxicityCategory.SEXUAL: [
            "explicit",
            "nude",
            "porn",
            "obscene",
            "masturbat",
            "penetrat",
            "genital",
            "rape",
        ],
        ToxicityCategory.THREATS: [
            "threat",
            "iwillhunt",
            "iwillfind",
            "youwillpay",
            "reprisal",
            "retaliate",
            "i_am_going_to_get_you",
            "hunt you down",
            "find you",
            "you will pay",
            "come for you",
        ],
    }

    # Heavier weight for intrinsically severe categories.
    _CATEGORY_WEIGHTS: dict[str, float] = {
        ToxicityCategory.HATE: 1.0,
        ToxicityCategory.HARASSMENT: 0.9,
        ToxicityCategory.VIOLENCE: 1.0,
        ToxicityCategory.SELF_HARM: 1.0,
        ToxicityCategory.SEXUAL: 0.8,
        ToxicityCategory.THREATS: 1.0,
    }

    def __init__(
        self,
        lexicon: dict[str, list[str]] | None = None,
        category_weights: dict[str, float] | None = None,
        sensitivity: float = 1.0,
    ) -> None:
        """
        Args:
            lexicon: Override per-category term lists. Defaults to built-ins.
            category_weights: Per-category weights for the aggregate.
            sensitivity: Scales how quickly token hits translate to a high score.
        """
        self._lock = threading.RLock()
        self.lexicon = (
            dict(lexicon) if lexicon else {k: list(v) for k, v in self._DEFAULT_LEXICON.items()}
        )
        self.category_weights = (
            dict(category_weights) if category_weights else dict(self._CATEGORY_WEIGHTS.items())
        )
        self.sensitivity = float(sensitivity)

    # ------------------------------------------------------------------
    def categories(self) -> list[str]:
        return [c for c in ToxicityCategory.ALL if c in self.lexicon]

    # ------------------------------------------------------------------
    def score_category(self, text: str, category: str) -> float:
        """Return the 0-1 score for a single category over *text*.

        Length-independent: driven by hit count with diminishing returns, so a
        short stream of slurs scores just as high as the same slurs padded with
        benign filler.
        """
        terms = self.lexicon.get(category, [])
        if not terms:
            return 0.0
        low = text.lower()
        hits = 0
        seen: set[str] = set()
        for term in terms:
            if re.search(r"\b" + re.escape(term), low):
                hits += 1
                seen.add(term)
        if hits == 0:
            return 0.0
        # 1 hit -> sensitivity, 2 hits -> ~sensitivity*1.7 ... capped at 1.0
        score = self.sensitivity * (1.0 - 0.5**hits)
        return round(_clamp01(score), 4)

    # ------------------------------------------------------------------
    def category_scores(self, text: str) -> dict[str, float]:
        """Return all per-category 0-1 scores for *text*."""
        with self._lock:
            return {c: self.score_category(text, c) for c in self.categories()}

    # ------------------------------------------------------------------
    def score(self, text: str) -> float:
        """Overall weighted 0-1 toxicity of *text*.

        Probabilistic-union aggregation: ``1 - prod(1 - v_i)`` over the weighted
        per-category scores. A single severe category produces a substantial
        score, and distinct categories firing together compound toward 1.0 —
        the right behaviour for flagging/blocking genuinely toxic content.
        """
        cat_scores = self.category_scores(text)
        if not cat_scores:
            return 0.0
        survival = 1.0
        for cat, val in cat_scores.items():
            w = self.category_weights.get(cat, 1.0)
            effective = _clamp01(val * w)
            survival *= 1.0 - effective
        overall = 1.0 - survival
        return round(_clamp01(overall), 4)


# ---------------------------------------------------------------------------
# RefusalScorer
# ---------------------------------------------------------------------------


class RefusalScorer:
    """Detects refusal patterns in an assistant response and returns refusalness.

    The score reflects *how* refusal-like the text reads -- overlap with known
    refusal phrasing -- not whether the refusal is justified. Deterministic.
    """

    # ------------------------------------------------------------------
    _REFUSAL_PHRASES: list[str] = [
        "i can't",
        "i can not",
        "i cannot",
        "i'm unable",
        "i am unable",
        "i'm not able",
        "i am not able",
        "i won't",
        "i will not",
        "i'm afraid i can't",
        "i'm sorry, i can't",
        "i must decline",
        "i cannot assist",
        "i can't help",
        "cannot help you with that",
        "against my policy",
        "against my guidelines",
        "not able to help",
        "i'm not allowed",
        "i am not allowed",
        "cannot comply",
        "as an ai, i cannot",
        "as an ai language model, i cannot",
        "i can't provide",
        "i cannot provide",
        "i can't do that",
        "that's not something i can do",
        "cannot fulfill",
    ]

    _POLICY_TERMS: list[str] = [
        "policy",
        "guidelines",
        "principles",
        "ethical guidelines",
        "terms of service",
        "usage policy",
        "content policy",
    ]

    _REFUSAL_TERMS: list[str] = [
        "cannot",
        "can't",
        "unable",
        "decline",
        "refuse",
        "refusal",
        "won't",
        "apolog",
        "unfortunately",
        "sorry",
    ]

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    def score(self, text: str) -> float:
        """Return refusalness in [0, 1] for *text*."""
        with self._lock:
            return self._score(text)

    # ------------------------------------------------------------------
    def _score(self, text: str) -> float:
        low = text.lower()
        tokens = _tokenize(text)
        if not tokens:
            return 0.0

        phrase_hits = sum(1 for p in self._REFUSAL_PHRASES if p in low)
        policy_hits = sum(1 for p in self._POLICY_TERMS if p in low)
        term_hits = sum(1 for t in self._REFUSAL_TERMS if re.search(r"\b" + re.escape(t), low))

        raw = phrase_hits * 1.0 + policy_hits * 0.5 + min(term_hits, 3) * 0.3
        return round(_clamp01(_sigmoid(raw - 1.0)), 4)


# ---------------------------------------------------------------------------
# CooccurrenceModel  (replaces the placeholder word_association_test)
# ---------------------------------------------------------------------------


class CooccurrenceModel:
    """Learnable counter-based co-occurrence association model.

    ``learn(ctx_pairs, target)`` counts observed (context, target) association
    pairs; the resulting frequency table drives ``score(candidate, context)``,
    which estimates how strongly the candidate co-occurs with the supplied
    context -- a real statistical association measure (smoothed pointwise
    mutual information), not a character-gram proxy.

    This is the designed replacement for the placeholder
    ``BiasDetector.word_association_test`` that used a Jaccard overlap of
    character n-grams as a "weak proxy".
    """

    def __init__(self, smooth: float = 1.0) -> None:
        self._lock = threading.RLock()
        self.smooth = float(smooth)
        # (ctx_term, cand_term) -> count
        self._co: Counter[tuple[str, str]] = Counter()
        self._ctx_total: Counter[str] = Counter()  # context-term marginals
        self._cand_total: Counter[str] = Counter()  # candidate-term marginals
        self._total = 0

    # ------------------------------------------------------------------
    @property
    def observations(self) -> int:
        return self._total

    # ------------------------------------------------------------------
    def learn(self, ctx_pairs: Sequence[tuple[str, str]], target: str | None = None) -> None:
        """Ingest association data.

        Args:
            ctx_pairs: Iterable of (context_term, candidate_term) pairs observed
                       to co-occur. A pair may appear multiple times to express
                       higher frequency.
            target: Optional label recorded alongside the observations (e.g. the
                    candidate category). Retained for provenance; association
                    strength is purely frequency-driven.
        """
        with self._lock:
            for ctx, cand in ctx_pairs:
                ctx = ctx.strip().lower()
                cand = cand.strip().lower()
                if not ctx or not cand:
                    continue
                self._co[(ctx, cand)] += 1
                self._ctx_total[ctx] += 1
                self._cand_total[cand] += 1
                self._total += 1

    # ------------------------------------------------------------------
    def association(self, ctx_term: str, cand_term: str) -> float:
        """Smoothed conditional co-occurrence probability in [0, 1].

        Returns P(cand | ctx) = co_occurrences(ctx, cand) / occurrences(ctx),
        a genuine counter-based term-association frequency. A value near 1.0
        means the candidate almost always co-occurs with the context term.
        """
        ctx = ctx_term.strip().lower()
        cand = cand_term.strip().lower()
        with self._lock:
            if self._total == 0 or not ctx or not cand:
                return 0.0
            co = self._co.get((ctx, cand), 0)
            ctx_occ = self._ctx_total.get(ctx, 0)
            if co == 0 or ctx_occ == 0:
                return 0.0
            return round(_clamp01(co / ctx_occ), 4)

    # ------------------------------------------------------------------
    def score(self, candidate: str, context: str | None = None) -> float:
        """Co-occurrence risk of *candidate* given *context* in [0, 1].

        Uses the average conditional association between context terms and
        candidate terms. Without a context, falls back to the candidate's
        learned self-marginal frequency as a mild baseline.
        """
        cand_tokens = set(_tokenize(candidate))
        if not cand_tokens:
            return 0.0

        if context:
            ctx_tokens = set(_tokenize(context))
            assocs = [self.association(c, t) for c in ctx_tokens for t in cand_tokens]
            positive = [a for a in assocs if a > 0.0]
            if not positive:
                return 0.0
            # Scale by how much of the association surface is actually active
            # so a partially-associated candidate scores proportionally.
            active = len(positive) / max(1, len(assocs))
            return round(_clamp01((sum(positive) / len(positive)) * (0.5 + 0.5 * active)), 4)

        # No context: use candidate marginal frequency as a mild baseline.
        with self._lock:
            if self._total == 0:
                return 0.0
            vals = [self._cand_total.get(t, 0) / self._total for t in cand_tokens]
            if not vals:
                return 0.0
        return round(_clamp01(max(vals) * 3.0), 4)

    # ------------------------------------------------------------------
    def most_associated(self, cand_term: str, top: int = 5) -> list[tuple[str, float]]:
        """Return the context terms most associated with *cand_term*."""
        cand = cand_term.strip().lower()
        with self._lock:
            pairs = [(ctx, cnt) for (ctx, c), cnt in self._co.items() if c == cand]
        scored = sorted(
            ((ctx, self.association(ctx, cand)) for ctx, _ in pairs),
            key=lambda x: x[1],
            reverse=True,
        )
        return scored[:top]

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "observations": self._total,
                "unique_context_terms": len(self._ctx_total),
                "unique_candidate_terms": len(self._cand_total),
                "unique_pairs": len(self._co),
            }


# ---------------------------------------------------------------------------
# SafetyResult & SafetyScorer facade
# ---------------------------------------------------------------------------


@dataclass
class SafetyResult:
    """Structured result from the SafetyScorer facade."""

    toxicity: float = 0.0
    refusal: float = 0.0
    cooccurrence_risk: float = 0.0
    overall: float = 0.0
    verdict: str = SafetyVerdict.SAFE
    category_scores: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "toxicity": self.toxicity,
            "refusal": self.refusal,
            "cooccurrence_risk": self.cooccurrence_risk,
            "overall": self.overall,
            "verdict": self.verdict,
            "category_scores": dict(self.category_scores),
            "reasons": list(self.reasons),
        }


class SafetyScorer:
    """Facade combining toxicity, refusal, and co-occurrence risk scoring.

    Usage::

        scorer = SafetyScorer(
            block_threshold=0.8,
            flag_threshold=0.4,
            cooccurrence_model=model,  # optional learnable model
        )
        result = scorer.evaluate("text", context="conversation so far")
        # result.verdict in {"safe", "flag", "block"}
    """

    def __init__(
        self,
        flag_threshold: float = 0.4,
        block_threshold: float = 0.75,
        toxicity_weights: dict[str, float] | None = None,
        toxicity_lexicon: dict[str, list[str]] | None = None,
        cooccurrence_model: CooccurrenceModel | None = None,
        use_refusal: bool = True,
        context_weight: float = 0.25,
    ) -> None:
        if not (0.0 <= flag_threshold <= block_threshold <= 1.0):
            msg = "require 0 <= flag_threshold <= block_threshold <= 1"
            raise ValueError(msg)
        self.flag_threshold = float(flag_threshold)
        self.block_threshold = float(block_threshold)
        self.context_weight = float(context_weight)
        self.use_refusal = bool(use_refusal)
        self._lock = threading.RLock()
        self.toxicity = ToxicityScorer(
            lexicon=toxicity_lexicon,
            category_weights=toxicity_weights,
        )
        self.refusal_scorer = RefusalScorer()
        self.cooccurrence = (
            cooccurrence_model if cooccurrence_model is not None else CooccurrenceModel()
        )

    # ------------------------------------------------------------------
    def evaluate(self, text: str, context: str | None = None) -> SafetyResult:
        """Score *text* (optionally in *context*) and return a SafetyResult."""
        with self._lock:
            return self._evaluate(text, context)

    # ------------------------------------------------------------------
    def _evaluate(self, text: str, context: str | None) -> SafetyResult:
        cat_scores = self.toxicity.category_scores(text)
        toxicity = self.toxicity.score(text)
        refusal = self.refusal_scorer.score(text) if self.use_refusal else 0.0
        co_risk = self.cooccurrence.score(text, context)

        overall = (
            toxicity
            + (refusal * 0.5 if self.use_refusal else 0.0)
            + (co_risk * self.context_weight if context is not None else co_risk * 0.0)
        )
        overall = round(_clamp01(overall), 4)

        # Verdict thresholds
        if overall >= self.block_threshold:
            verdict = SafetyVerdict.BLOCK
        elif overall >= self.flag_threshold:
            verdict = SafetyVerdict.FLAG
        else:
            verdict = SafetyVerdict.SAFE

        # Reasons
        reasons: list[str] = []
        if toxicity >= self.flag_threshold:
            reasons.append(f"toxicity {toxicity:.2f} >= {self.flag_threshold:.2f}")
        if co_risk >= self.flag_threshold and context is not None:
            reasons.append(f"co-occurrence risk {co_risk:.2f} with supplied context")
        if self.use_refusal and refusal >= 0.5:
            reasons.append(f"refusal pattern detected ({refusal:.2f})")
        if verdict == SafetyVerdict.BLOCK:
            reasons.append(f"overall {overall:.2f} >= block threshold {self.block_threshold:.2f}")
        elif verdict == SafetyVerdict.FLAG:
            reasons.append(f"overall {overall:.2f} >= flag threshold {self.flag_threshold:.2f}")
        if not reasons:
            reasons.append("no safety signals above flag threshold")

        return SafetyResult(
            toxicity=toxicity,
            refusal=refusal,
            cooccurrence_risk=co_risk,
            overall=overall,
            verdict=verdict,
            category_scores=cat_scores,
            reasons=reasons,
        )

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset the learnable co-occurrence model (lifecycle helper)."""
        with self._lock:
            self.cooccurrence = CooccurrenceModel(smooth=self.cooccurrence.smooth)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "flag_threshold": self.flag_threshold,
            "block_threshold": self.block_threshold,
            "context_weight": self.context_weight,
            "use_refusal": self.use_refusal,
            "cooccurrence_model": self.cooccurrence.to_dict(),
        }


def create_safety_scorer(**config: Any) -> SafetyScorer:
    """Factory for a SafetyScorer with optional config overrides."""
    return SafetyScorer(**config)

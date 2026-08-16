"""Engineering Tradeoff — a weighted satisficing decision engine.

Built directly from the real pulled JE Van Clief transcript
"data/transcripts/JEVanClief/-YursW-UIoY.md" titled
"A Pagani, a Toyota, and Why "Best" Is a Trap in AI".

The transcript's thesis: chasing an *absolute* "best" is a trap. What is
"best" is relative to your actual need, and a suggestion that is perfect on
paper (the "$5 million Pagani Zonda") can be a terrible choice in practice,
while a modest option that satisfies your constraints (a cheap, reliable
Toyota) is often the genuinely right pick:

    "best becomes relative ... I'm going to tell you to buy a Pagani Zonda
     because it's super cool ... Pagani, go get you a $5 million car. And
     then you're going to say, I can't spend $5 million on a car."
    "it's figuring out your need ... what is your actual need because you're
     gonna end up buying a Pagani Zonda that you [don't need] ... was that
     the best choice? probably not."

So this module implements *satisficing*, not naive optimisation: it scores
candidate options across a set of weighted dimensions (cost, quality, speed,
robustness, effort), ranks them by a weighted normalized score, filters out
options that violate hard constraints, and picks the **satisficing winner**
(the best feasible option) — which will often *differ* from the absolute best
(the Pagani) whenever hard constraints rule it out. It also reports a
tradeoff analysis naming the dimensions that were sacrificed to reach that
choice.

Everything here is pure Python and network-free so it is unit-testable in
isolation. No fake enterprise features — just weighted decision-making,
constraint filtering, and honest tradeoff reporting derived from the source.

Version: 1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

EPSILON = 1e-9

# Canonical scoring dimensions used across the module. `lower_better=True`
# means smaller raw scores are preferable (e.g. cost, effort).
DEFAULT_DIMENSIONS: Tuple[str, ...] = ("cost", "quality", "speed",
                                       "robustness", "effort")


@dataclass(frozen=True)
class Dimension:
    """A single scoring dimension with a weight and an optimisation direction.

    * lower_better=True  -> lower raw values are preferred (cost, effort).
    * lower_better=False -> higher raw values are preferred (quality, ...).
    """
    name: str
    weight: float = 1.0
    lower_better: bool = False

    def normalized(self, raw: float, scale_max: float) -> float:
        """Map a raw score into [0, 1] where 1.0 is *always* the best value.

        Scales against the observed maximum across the candidate set, then
        flips the axis when a lower value is preferred, so a weighted sum can
        be maximised regardless of per-dimension direction.
        """
        if scale_max <= EPSILON:
            return 0.0
        frac = raw / scale_max
        return (1.0 - frac) if self.lower_better else frac


@dataclass(frozen=True)
class Option:
    """A candidate under evaluation. `scores` maps dimension -> raw (0-10)."""
    name: str
    scores: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Constraint:
    """A hard requirement. An option must satisfy *every* constraint to be
    a satisficing candidate."""
    dimension: str
    # 'le' -> value <= threshold ; 'ge' -> value >= threshold
    op: str = "le"
    threshold: float = 0.0

    def satisfied(self, raw: float) -> bool:
        if self.op == "le":
            return raw <= self.threshold + EPSILON
        if self.op == "ge":
            return raw >= self.threshold - EPSILON
        raise ValueError(f"Unknown constraint op: {self.op!r}")


@dataclass(frozen=True)
class ScoredOption:
    """An option together with its per-dimension normalized values and total."""
    option: Option
    total: float
    normalized: Dict[str, float] = field(default_factory=dict)
    feasible: bool = True


@dataclass(frozen=True)
class TradeoffAnalysis:
    """Which dimensions were sacrificed by the satisficing winner relative to
    the absolute best (the "Pagani"), and which it actually won on."""
    dimension: str
    winner_value: float
    abest_value: float
    delta: float               # winner_value - abest_value (negative = sacrificed)
    sacrificed: bool

    @property
    def magnitude(self) -> float:
        return abs(self.delta)


@dataclass(frozen=True)
class TradeoffResult:
    """Full result of an evaluation run."""
    ranking: List[ScoredOption]          # all options, best weighted score first
    absolute_best: Optional[ScoredOption]  # ignores constraints entirely
    satisficing_winner: Optional[ScoredOption]  # best option meeting all constraints
    feasible: List[ScoredOption]           # the constraint-satisfying subset
    constraints: Sequence[Constraint]
    tradeoffs: List[TradeoffAnalysis]      # sacrifices of winner vs absolute best

    @property
    def constrained_out(self) -> List[ScoredOption]:
        """Options that were present but failed a hard constraint."""
        return [s for s in self.ranking if not s.feasible]


class TradeoffEngine:
    """Weighted multi-criteria satisficing decision engine.

    Model: a decision asks "what do you actually need?" — encode that as
    per-dimension *weights* (importance) and *hard constraints* (absolute
    requirements). The engine then finds both the absolute best (the Pagani)
    and the satisficing winner (the Toyota) and reports the difference.
    """

    def __init__(
        self,
        dimensions: Optional[Iterable[Dimension]] = None,
        default_weight: float = 1.0,
    ) -> None:
        self._dimensions: List[Dimension] = list(dimensions or [])
        self._dim_map: Dict[str, Dimension] = {d.name: d for d in self._dimensions}
        self._default_weight = default_weight

    @classmethod
    def with_default_dimensions(
        cls,
        weights: Optional[Dict[str, float]] = None,
    ) -> "TradeoffEngine":
        """Engine over the canonical dimensions (cost, quality, speed,
        robustness, effort). `weights` overrides per-dimension importance.

        Per the transcript, cost and effort are lower-better (money / work
        spent), while quality, speed and robustness are higher-better. The
        defaults weight raw performance (quality/speed/robustness) above
        affordability/effort so that, *absent constraints*, the engine's
        absolute best looks like the Pagani — and it is real constraints
        (budget, reliability) that force the satisficing Toyota forward,
        which is exactly the episode's thesis.
        """
        dims = [
            Dimension("cost", weight=0.2, lower_better=True),
            Dimension("quality", weight=2.0, lower_better=False),
            Dimension("speed", weight=2.0, lower_better=False),
            Dimension("robustness", weight=1.0, lower_better=False),
            Dimension("effort", weight=0.2, lower_better=True),
        ]
        for d in dims:
            if weights and d.name in weights:
                object.__setattr__(d, "weight", float(weights[d.name]))
        return cls(dims)

    # ------------------------------------------------------------------ pe
    def _dimension_for(self, name: str) -> Dimension:
        d = self._dim_map.get(name)
        if d is None:
            d = Dimension(name, weight=self._default_weight,
                          lower_better=False)
        return d

    def dimensions(self) -> List[str]:
        return list(self._dim_map)

    def evaluate(
        self,
        options: Sequence[Option],
        constraints: Sequence[Constraint] = (),
    ) -> TradeoffResult:
        """Score, rank, filter and analyse a set of candidate options."""
        all_dims = list(self._dim_map)
        for opt in options:
            for name in opt.scores:
                if name not in all_dims:
                    all_dims.append(name)

        # Per-dimension observed maxima for normalization.
        maxima: Dict[str, float] = {}
        for name in all_dims:
            maxima[name] = max((opt.scores.get(name, 0.0) for opt in options),
                               default=0.0)

        # Build scored, normalized options.
        scored: List[ScoredOption] = []
        for opt in options:
            norm: Dict[str, float] = {}
            total = 0.0
            for name in all_dims:
                raw = opt.scores.get(name, 0.0)
                dim = self._dimension_for(name)
                nv = dim.normalized(raw, maxima[name])
                norm[name] = nv
                total += dim.weight * nv
            feasible = all(c.satisfied(opt.scores.get(c.dimension, 0.0))
                           for c in constraints)
            scored.append(ScoredOption(option=opt, total=total,
                                       normalized=norm, feasible=feasible))

        ranked = sorted(scored, key=lambda s: s.total, reverse=True)
        absolute_best = ranked[0] if ranked else None
        feasible = [s for s in ranked if s.feasible]
        satisficing = feasible[0] if feasible else None

        tradeoffs: List[TradeoffAnalysis] = []
        if absolute_best is not None and satisficing is not None:
            for name in all_dims:
                wv = satisficing.normalized.get(name, 0.0)
                av = absolute_best.normalized.get(name, 0.0)
                tradeoffs.append(TradeoffAnalysis(
                    dimension=name,
                    winner_value=wv,
                    abest_value=av,
                    delta=wv - av,
                    sacrificed=(wv < av - EPSILON),
                ))

        return TradeoffResult(
            ranking=ranked,
            absolute_best=absolute_best,
            satisficing_winner=satisficing,
            feasible=feasible,
            constraints=list(constraints),
            tradeoffs=tradeoffs,
        )


# --------------------------------------------------------------- factories
def make_engine(
    weights: Optional[Dict[str, float]] = None,
) -> TradeoffEngine:
    """Fresh engine over the canonical dimensions (the common entry point)."""
    return TradeoffEngine.with_default_dimensions(weights)


__all__ = [
    "Dimension", "Option", "Constraint", "ScoredOption",
    "TradeoffAnalysis", "TradeoffResult", "TradeoffEngine", "make_engine",
    "DEFAULT_DIMENSIONS",
]

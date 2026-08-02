"""
Prompt Evaluator - Enterprise-grade evaluation and metrics system.

Measures:
- Accuracy: Response correctness
- Hallucination rate: Factual error frequency
- Token efficiency: Tokens used vs useful output
- Latency: Response time
- Cost: Financial cost per interaction
- Retrieval quality: Relevance of retrieved context
- User satisfaction: User feedback scores
- Task completion: Did the task succeed
- Tool accuracy: Were tool calls correct
- Prompt stability: Consistency across similar inputs
"""

from __future__ import annotations

import json
import re
import statistics
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from collections import defaultdict


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EvalMetric(str, Enum):
    """Standard evaluation metrics."""
    ACCURACY = "accuracy"
    HALLUCINATION_RATE = "hallucination_rate"
    TOKEN_EFFICIENCY = "token_efficiency"
    LATENCY_MS = "latency_ms"
    COST = "cost"
    RETRIEVAL_QUALITY = "retrieval_quality"
    USER_SATISFACTION = "user_satisfaction"
    TASK_COMPLETION = "task_completion"
    TOOL_ACCURACY = "tool_accuracy"
    PROMPT_STABILITY = "prompt_stability"
    RESPONSE_CONSISTENCY = "response_consistency"
    CONTEXT_UTILIZATION = "context_utilization"
    ADHERENCE = "adherence"  # Adherence to instructions


class EvalGrade(str, Enum):
    """Overall evaluation grades."""
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"
    UNKNOWN = "?"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class EvalScore:
    """A single evaluation score."""
    metric: EvalMetric
    value: float
    weight: float = 1.0
    threshold_pass: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        if self.threshold_pass is None:
            return True
        return self.value >= self.threshold_pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric.value,
            "value": self.value,
            "weight": self.weight,
            "threshold_pass": self.threshold_pass,
            "passed": self.passed,
            "metadata": self.metadata,
        }


@dataclass
class EvaluationResult:
    """Full evaluation result for a single prompt execution."""
    eval_id: str
    prompt_id: str
    prompt_version: str
    scores: List[EvalScore]
    overall_grade: EvalGrade = EvalGrade.UNKNOWN
    overall_score: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0
    task_completed: bool = False
    hallucination_detected: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "scores": [s.to_dict() for s in self.scores],
            "overall_grade": self.overall_grade.value,
            "overall_score": self.overall_score,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "cost": self.cost,
            "task_completed": self.task_completed,
            "hallucination_detected": self.hallucination_detected,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class EvalSummary:
    """Aggregated evaluation summary across multiple runs."""
    prompt_id: str
    num_evaluations: int
    metric_averages: Dict[EvalMetric, float]
    metric_stdevs: Dict[EvalMetric, float]
    metric_mins: Dict[EvalMetric, float]
    metric_maxs: Dict[EvalMetric, float]
    overall_avg: float
    overall_stdev: float
    grade_distribution: Dict[str, int]
    task_completion_rate: float
    hallucination_rate_avg: float
    avg_latency_ms: float
    avg_cost: float
    avg_tokens: float
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "num_evaluations": self.num_evaluations,
            "metric_averages": {k.value: v for k, v in self.metric_averages.items()},
            "metric_stdevs": {k.value: v for k, v in self.metric_stdevs.items()},
            "metric_mins": {k.value: v for k, v in self.metric_mins.items()},
            "metric_maxs": {k.value: v for k, v in self.metric_maxs.items()},
            "overall_avg": self.overall_avg,
            "overall_stdev": self.overall_stdev,
            "grade_distribution": self.grade_distribution,
            "task_completion_rate": self.task_completion_rate,
            "hallucination_rate_avg": self.hallucination_rate_avg,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_cost": self.avg_cost,
            "avg_tokens": self.avg_tokens,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class HallucinationCheck:
    """Result of a hallucination check."""
    detected: bool
    confidence: float
    pattern: Optional[str] = None
    location: Optional[str] = None
    explanation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prompt Evaluator
# ---------------------------------------------------------------------------

class EvaluatorError(Exception):
    """Base exception for evaluator errors."""


class PromptEvaluator:
    """
    Enterprise-grade prompt evaluator.

    Features:
    - Multi-metric evaluation
    - Hallucination detection
    - Token efficiency analysis
    - Latency and cost tracking
    - Retrieval quality assessment
    - User satisfaction scoring
    - Task completion verification
    - Tool call accuracy checking
    - Prompt stability measurement
    - Aggregated summaries and trends
    - Grading system

    Usage::

        evaluator = PromptEvaluator()
        result = evaluator.evaluate(
            prompt_id="prmpt_summarizer_abc123",
            prompt_version="1.2.0",
            response="The article discusses...",
            reference="The article discusses AI safety...",
            input_tokens=500,
            output_tokens=200,
            latency_ms=1500,
        )
        print(f"Grade: {result.overall_grade}, Score: {result.overall_score}")
    """

    # Grade thresholds
    GRADE_THRESHOLDS: Dict[EvalGrade, float] = {
        EvalGrade.A_PLUS: 95.0,
        EvalGrade.A: 85.0,
        EvalGrade.B: 70.0,
        EvalGrade.C: 55.0,
        EvalGrade.D: 40.0,
        EvalGrade.F: 0.0,
    }

    # Default metric weights
    DEFAULT_WEIGHTS: Dict[EvalMetric, float] = {
        EvalMetric.ACCURACY: 1.0,
        EvalMetric.HALLUCINATION_RATE: 1.2,
        EvalMetric.TOKEN_EFFICIENCY: 0.7,
        EvalMetric.LATENCY_MS: 0.5,
        EvalMetric.COST: 0.6,
        EvalMetric.RETRIEVAL_QUALITY: 0.8,
        EvalMetric.USER_SATISFACTION: 0.9,
        EvalMetric.TASK_COMPLETION: 1.5,
        EvalMetric.TOOL_ACCURACY: 1.0,
        EvalMetric.PROMPT_STABILITY: 0.8,
        EvalMetric.RESPONSE_CONSISTENCY: 0.7,
        EvalMetric.CONTEXT_UTILIZATION: 0.6,
        EvalMetric.ADHERENCE: 1.1,
    }

    def __init__(
        self,
        metric_weights: Optional[Dict[EvalMetric, float]] = None,
        enable_history: bool = True,
        max_history: int = 10000,
    ):
        self.metric_weights = metric_weights or dict(self.DEFAULT_WEIGHTS)
        self.enable_history = enable_history
        self.max_history = max_history

        self._history: List[EvaluationResult] = []
        self._lock = threading.RLock()
        self._eval_counter = 0

    # ------------------------------------------------------------------
    # Main Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        prompt_id: str,
        prompt_version: str,
        response: str,
        reference: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        cost: float = 0.0,
        task_completed: Optional[bool] = None,
        user_rating: Optional[float] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        expected_tools: Optional[List[str]] = None,
        context_used: Optional[List[str]] = None,
        instruction_adherence: Optional[float] = None,
        previous_response: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvaluationResult:
        """
        Perform a comprehensive evaluation of a prompt execution.

        Args:
            prompt_id: The prompt being evaluated.
            prompt_version: Version of the prompt.
            response: The model's response text.
            reference: Ground truth or expected response.
            input_tokens: Number of input tokens used.
            output_tokens: Number of output tokens used.
            latency_ms: Response latency in milliseconds.
            cost: Cost of the API call.
            task_completed: Whether the task was successfully completed.
            user_rating: User satisfaction score (0-10).
            tool_calls: List of tool calls made.
            expected_tools: Expected tool names.
            context_used: Context snippets used.
            instruction_adherence: Adherence score (0-1).
            previous_response: Previous response for stability check.
            metadata: Additional metadata.

        Returns:
            EvaluationResult with all scores and grades.
        """
        self._eval_counter += 1
        eval_id = f"eval_{self._eval_counter}_{int(time.time() * 1000)}"

        scores: List[EvalScore] = []

        # 1. Accuracy
        if reference:
            accuracy = self._measure_accuracy(response, reference)
            scores.append(EvalScore(
                metric=EvalMetric.ACCURACY,
                value=accuracy,
                weight=self.metric_weights.get(EvalMetric.ACCURACY, 1.0),
                threshold_pass=0.7,
            ))

        # 2. Hallucination rate
        hallucination = self._detect_hallucination(response, reference)
        hallucination_score = 0.0 if hallucination.detected else 100.0
        scores.append(EvalScore(
            metric=EvalMetric.HALLUCINATION_RATE,
            value=hallucination_score,
            weight=self.metric_weights.get(EvalMetric.HALLUCINATION_RATE, 1.2),
            threshold_pass=80.0,
            metadata={"hallucination_detected": hallucination.detected, "confidence": hallucination.confidence},
        ))

        # 3. Token efficiency
        token_efficiency = self._measure_token_efficiency(input_tokens, output_tokens, response)
        scores.append(EvalScore(
            metric=EvalMetric.TOKEN_EFFICIENCY,
            value=token_efficiency,
            weight=self.metric_weights.get(EvalMetric.TOKEN_EFFICIENCY, 0.7),
            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
        ))

        # 4. Latency
        latency_score = self._score_latency(latency_ms)
        scores.append(EvalScore(
            metric=EvalMetric.LATENCY_MS,
            value=latency_score,
            weight=self.metric_weights.get(EvalMetric.LATENCY_MS, 0.5),
            metadata={"latency_ms": latency_ms},
        ))

        # 5. Cost
        cost_score = self._score_cost(cost)
        scores.append(EvalScore(
            metric=EvalMetric.COST,
            value=cost_score,
            weight=self.metric_weights.get(EvalMetric.COST, 0.6),
            metadata={"cost": cost},
        ))

        # 6. Retrieval quality
        if context_used:
            retrieval_quality = self._measure_retrieval_quality(context_used, response)
            scores.append(EvalScore(
                metric=EvalMetric.RETRIEVAL_QUALITY,
                value=retrieval_quality,
                weight=self.metric_weights.get(EvalMetric.RETRIEVAL_QUALITY, 0.8),
                threshold_pass=0.6,
            ))

        # 7. User satisfaction
        if user_rating is not None:
            satisfaction = self._normalize_user_rating(user_rating)
            scores.append(EvalScore(
                metric=EvalMetric.USER_SATISFACTION,
                value=satisfaction,
                weight=self.metric_weights.get(EvalMetric.USER_SATISFACTION, 0.9),
                metadata={"raw_rating": user_rating},
            ))

        # 8. Task completion
        if task_completed is not None:
            scores.append(EvalScore(
                metric=EvalMetric.TASK_COMPLETION,
                value=100.0 if task_completed else 0.0,
                weight=self.metric_weights.get(EvalMetric.TASK_COMPLETION, 1.5),
                threshold_pass=50.0,
            ))

        # 9. Tool accuracy
        if tool_calls and expected_tools:
            tool_accuracy = self._measure_tool_accuracy(tool_calls, expected_tools)
            scores.append(EvalScore(
                metric=EvalMetric.TOOL_ACCURACY,
                value=tool_accuracy,
                weight=self.metric_weights.get(EvalMetric.TOOL_ACCURACY, 1.0),
                threshold_pass=0.8,
            ))

        # 10. Prompt stability
        if previous_response:
            stability = self._measure_stability(response, previous_response)
            scores.append(EvalScore(
                metric=EvalMetric.PROMPT_STABILITY,
                value=stability,
                weight=self.metric_weights.get(EvalMetric.PROMPT_STABILITY, 0.8),
            ))

        # 11. Instruction adherence
        if instruction_adherence is not None:
            scores.append(EvalScore(
                metric=EvalMetric.ADHERENCE,
                value=instruction_adherence * 100,
                weight=self.metric_weights.get(EvalMetric.ADHERENCE, 1.1),
                threshold_pass=0.7,
            ))

        # Compute overall score
        overall_score = self._compute_overall(scores)

        # Assign grade
        grade = self._assign_grade(overall_score)

        result = EvaluationResult(
            eval_id=eval_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            scores=scores,
            overall_grade=grade,
            overall_score=overall_score,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost=cost,
            task_completed=task_completed or False,
            hallucination_detected=hallucination.detected,
            metadata=metadata or {},
        )

        if self.enable_history:
            with self._lock:
                self._history.append(result)
                if len(self._history) > self.max_history:
                    self._history = self._history[-self.max_history:]

        return result

    # ------------------------------------------------------------------
    # Batch Evaluation
    # ------------------------------------------------------------------

    def evaluate_batch(
        self,
        items: List[Dict[str, Any]],
    ) -> List[EvaluationResult]:
        """Evaluate multiple prompt executions."""
        results = []
        for item in items:
            result = self.evaluate(**item)
            results.append(result)
        return results

    def compare_versions(
        self,
        prompt_id: str,
        version_a: str,
        version_b: str,
        response_a: str,
        response_b: str,
        reference: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Compare two prompt versions side by side."""
        result_a = self.evaluate(
            prompt_id=prompt_id,
            prompt_version=version_a,
            response=response_a,
            reference=reference,
            **kwargs,
        )
        result_b = self.evaluate(
            prompt_id=prompt_id,
            prompt_version=version_b,
            response=response_b,
            reference=reference,
            **kwargs,
        )

        return {
            "version_a": {
                "version": version_a,
                "score": result_a.overall_score,
                "grade": result_a.overall_grade.value,
                "metrics": {s.metric.value: s.value for s in result_a.scores},
            },
            "version_b": {
                "version": version_b,
                "score": result_b.overall_score,
                "grade": result_b.overall_grade.value,
                "metrics": {s.metric.value: s.value for s in result_b.scores},
            },
            "winner": "A" if result_a.overall_score > result_b.overall_score else "B",
            "score_diff": result_a.overall_score - result_b.overall_score,
        }

    # ------------------------------------------------------------------
    # Measurement Methods
    # ------------------------------------------------------------------

    def _measure_accuracy(self, response: str, reference: str) -> float:
        """Measure accuracy as semantic similarity to reference."""
        if not reference:
            return 100.0

        # Multiple similarity measures
        jaccard = self._jaccard_similarity(response, reference)
        overlap = self._word_overlap(response, reference)
        contains_key = self._contains_key_facts(response, reference)

        # Weighted combination
        score = (jaccard * 0.3 + overlap * 0.3 + contains_key * 0.4) * 100
        return round(min(100.0, max(0.0, score)), 2)

    def _detect_hallucination(
        self, response: str, reference: Optional[str]
    ) -> HallucinationCheck:
        """
        Detect potential hallucinations in the response.

        Checks:
        - Unsupported claims not in reference
        - Fabricated statistics
        - Contradiction with reference
        - Made-up URLs or references
        """
        if not reference:
            return HallucinationCheck(detected=False, confidence=0.0)

        checks: List[Tuple[bool, float, str]] = []

        # Check for statistics not in reference
        resp_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', response))
        ref_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', reference))
        new_numbers = resp_numbers - ref_numbers
        if len(new_numbers) > 2:
            checks.append((True, 0.6, f"Unsupported numbers: {new_numbers}"))

        # Check for fabricated URLs
        resp_urls = set(re.findall(r'https?://[^\s]+', response))
        ref_urls = set(re.findall(r'https?://[^\s]+', reference))
        fake_urls = resp_urls - ref_urls
        if fake_urls:
            checks.append((True, 0.8, f"Unverified URLs: {fake_urls}"))

        # Check for contradictory statements
        contradictions = self._find_contradictions(response, reference)
        if contradictions:
            checks.append((True, 0.7, f"Contradictions: {contradictions}"))

        # Check for unsupported definitive claims
        definitive_patterns = [
            r'(?:it is (?:proven|established|certain|definitive) that)',
            r'(?:research (?:proves|shows|confirms) that)',
            r'(?:all (?:experts|scientists|studies) (?:agree|confirm|show))',
        ]
        for pattern in definitive_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches and not re.findall(pattern, reference, re.IGNORECASE):
                checks.append((True, 0.5, f"Unsupported definitive claim: '{matches[0]}'"))

        if checks:
            avg_confidence = sum(c[1] for c in checks) / len(checks)
            return HallucinationCheck(
                detected=True,
                confidence=avg_confidence,
                pattern="; ".join(c[2] for c in checks),
                explanation="Multiple hallucination indicators found",
            )

        return HallucinationCheck(detected=False, confidence=0.9)

    def _measure_token_efficiency(
        self, input_tokens: int, output_tokens: int, response: str
    ) -> float:
        """Measure token efficiency as useful content per token."""
        if output_tokens == 0:
            return 0.0

        # Information density: meaningful content vs filler
        words = response.split()
        if not words:
            return 0.0

        filler_words = {
            "um", "uh", "like", "you know", "basically", "actually",
            "literally", "just", "really", "very", "quite", "rather",
            "somewhat", "simply", "obviously", "clearly", "certainly",
        }
        filler_count = sum(1 for w in words if w.lower() in filler_words)
        filler_ratio = filler_count / len(words)

        # Efficiency: lower filler = higher score, reasonable length is good
        # Too short might be incomplete, too long is wasteful
        ideal_output = max(100, input_tokens // 10)
        length_score = 1.0 - abs(output_tokens - ideal_output) / max(output_tokens, ideal_output)

        efficiency = ((1.0 - filler_ratio) * 0.6 + length_score * 0.4) * 100
        return round(max(0.0, min(100.0, efficiency)), 2)

    def _score_latency(self, latency_ms: float) -> float:
        """Score latency on a curve."""
        if latency_ms <= 0:
            return 100.0
        # Excellent: < 500ms, Good: < 2000ms, OK: < 5000ms, Poor: > 10000ms
        if latency_ms < 500:
            return 100.0
        elif latency_ms < 2000:
            return 100.0 - (latency_ms - 500) / 1500 * 20  # 100 -> 80
        elif latency_ms < 5000:
            return 80.0 - (latency_ms - 2000) / 3000 * 40   # 80 -> 40
        elif latency_ms < 10000:
            return 40.0 - (latency_ms - 5000) / 5000 * 30   # 40 -> 10
        else:
            return max(0.0, 10.0 - (latency_ms - 10000) / 10000 * 10)

    def _score_cost(self, cost: float) -> float:
        """Score cost efficiency."""
        if cost <= 0:
            return 100.0
        # Free or near-free: 100, cheap (< $0.01): 90, moderate (< $0.10): 70,
        # expensive (< $1.00): 40, very expensive: 10
        if cost < 0.001:
            return 100.0
        elif cost < 0.01:
            return 90.0 - (cost - 0.001) / 0.009 * 20
        elif cost < 0.10:
            return 70.0 - (cost - 0.01) / 0.09 * 30
        elif cost < 1.00:
            return 40.0 - (cost - 0.10) / 0.90 * 30
        else:
            return max(0.0, 10.0 - (cost - 1.0) / 10.0 * 10)

    def _measure_retrieval_quality(
        self, context_used: List[str], response: str
    ) -> float:
        """Measure how well retrieved context was utilized."""
        if not context_used:
            return 0.0

        response_lower = response.lower()
        used_count = 0
        for ctx in context_used:
            # Check if key terms from context appear in response
            key_terms = set(ctx.lower().split()) - self._stop_words()
            if not key_terms:
                continue
            matching = sum(1 for t in key_terms if t in response_lower)
            if matching / len(key_terms) > 0.3:
                used_count += 1

        utilization = used_count / len(context_used) if context_used else 0.0
        return round(utilization * 100, 2)

    def _measure_tool_accuracy(
        self,
        tool_calls: List[Dict[str, Any]],
        expected_tools: List[str],
    ) -> float:
        """Measure tool call accuracy."""
        if not expected_tools:
            return 100.0

        called_names = set()
        for tc in tool_calls:
            name = tc.get("name") or tc.get("function", {}).get("name", "")
            if name:
                called_names.add(name)

        expected_set = set(expected_tools)

        # Precision + recall
        tp = len(expected_set & called_names)
        fp = len(called_names - expected_set)
        fn = len(expected_set - called_names)

        if tp + fp == 0 and tp + fn == 0:
            return 100.0

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        if precision + recall == 0:
            return 0.0

        f1 = 2 * (precision * recall) / (precision + recall)
        return round(f1 * 100, 2)

    def _measure_stability(self, response: str, previous: str) -> float:
        """
        Measure prompt stability: how consistent responses are for similar inputs.
        High similarity = stable (good), moderate = consistent but adaptive.
        """
        if not previous:
            return 100.0

        similarity = self._jaccard_similarity(response, previous)
        # Ideal stability is 0.6-0.9 range (consistent but not identical)
        if 0.6 <= similarity <= 0.9:
            return 100.0
        elif similarity > 0.9:
            # Too similar, might be overly rigid
            return 90.0 - (similarity - 0.9) * 100
        else:
            # Too different, might be unstable
            return max(0.0, similarity * 100)

    @staticmethod
    def _normalize_user_rating(rating: float) -> float:
        """Normalize user rating to 0-100 scale."""
        # Assume rating is on 0-10 scale (or 0-5)
        if rating > 10:
            return min(100.0, rating)
        if rating > 5:
            return rating * 10  # 0-10 to 0-100
        return rating * 20  # 0-5 to 0-100

    # ------------------------------------------------------------------
    # Scoring & Grading
    # ------------------------------------------------------------------

    def _compute_overall(self, scores: List[EvalScore]) -> float:
        """Compute weighted overall score from individual metrics."""
        if not scores:
            return 0.0

        total_weight = sum(s.weight for s in scores)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s.value * s.weight for s in scores)
        return round(weighted_sum / total_weight, 2)

    def _assign_grade(self, score: float) -> EvalGrade:
        """Assign a letter grade based on overall score."""
        for grade, threshold in sorted(
            self.GRADE_THRESHOLDS.items(),
            key=lambda x: -x[1],
        ):
            if score >= threshold:
                return grade
        return EvalGrade.F

    # ------------------------------------------------------------------
    # Summary & Trends
    # ------------------------------------------------------------------

    def get_summary(
        self,
        prompt_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> EvalSummary:
        """Get aggregated evaluation summary."""
        with self._lock:
            history = self._history
            if prompt_id:
                history = [r for r in history if r.prompt_id == prompt_id]
            if limit:
                history = history[-limit:]

        if not history:
            return EvalSummary(
                prompt_id=prompt_id or "unknown",
                num_evaluations=0,
                metric_averages={},
                metric_stdevs={},
                metric_mins={},
                metric_maxs={},
                overall_avg=0.0,
                overall_stdev=0.0,
                grade_distribution={},
                task_completion_rate=0.0,
                hallucination_rate_avg=0.0,
                avg_latency_ms=0.0,
                avg_cost=0.0,
                avg_tokens=0.0,
            )

        # Collect all metric values
        metric_values: Dict[EvalMetric, List[float]] = defaultdict(list)
        for result in history:
            for score in result.scores:
                metric_values[score.metric].append(score.value)

        metric_averages = {
            m: round(statistics.mean(vs), 2)
            for m, vs in metric_values.items()
        }
        metric_stdevs = {
            m: round(statistics.stdev(vs), 2) if len(vs) > 1 else 0.0
            for m, vs in metric_values.items()
        }
        metric_mins = {
            m: round(min(vs), 2) for m, vs in metric_values.items()
        }
        metric_maxs = {
            m: round(max(vs), 2) for m, vs in metric_values.items()
        }

        overall_scores = [r.overall_score for r in history]
        grades = [r.overall_grade.value for r in history]
        grade_dist = {g: grades.count(g) for g in set(grades)}

        task_completions = sum(1 for r in history if r.task_completed)
        hallucinations = sum(1 for r in history if r.hallucination_detected)

        return EvalSummary(
            prompt_id=prompt_id or "all",
            num_evaluations=len(history),
            metric_averages=metric_averages,
            metric_stdevs=metric_stdevs,
            metric_mins=metric_mins,
            metric_maxs=metric_maxs,
            overall_avg=round(statistics.mean(overall_scores), 2),
            overall_stdev=round(statistics.stdev(overall_scores), 2) if len(overall_scores) > 1 else 0.0,
            grade_distribution=grade_dist,
            task_completion_rate=round(task_completions / len(history) * 100, 1),
            hallucination_rate_avg=round(hallucinations / len(history) * 100, 1),
            avg_latency_ms=round(statistics.mean([r.latency_ms for r in history]), 1),
            avg_cost=round(statistics.mean([r.cost for r in history]), 6),
            avg_tokens=round(statistics.mean([r.total_tokens for r in history]), 1),
        )

    def get_trends(
        self,
        prompt_id: Optional[str] = None,
        metric: Optional[EvalMetric] = None,
        window: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get evaluation trends over time."""
        with self._lock:
            history = self._history
            if prompt_id:
                history = [r for r in history if r.prompt_id == prompt_id]
            history = history[-window:]

        trends = []
        for result in history:
            point = {
                "eval_id": result.eval_id,
                "timestamp": result.timestamp.isoformat(),
                "overall_score": result.overall_score,
                "grade": result.overall_grade.value,
            }
            if metric:
                for s in result.scores:
                    if s.metric == metric:
                        point["metric_value"] = s.value
                        break
            trends.append(point)

        return trends

    def get_history(self, limit: int = 50) -> List[EvaluationResult]:
        """Get recent evaluation history."""
        with self._lock:
            return self._history[-limit:]

    def clear_history(self) -> int:
        """Clear evaluation history. Returns count cleared."""
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize evaluator state."""
        with self._lock:
            return {
                "metric_weights": {k.value: v for k, v in self.metric_weights.items()},
                "history": [r.to_dict() for r in self._history[-1000:]],  # Last 1000
                "eval_counter": self._eval_counter,
            }

    def to_json(self, path: Optional[str] = None) -> str:
        """Serialize to JSON, optionally saving to file."""
        data = self.to_dict()
        json_str = json.dumps(data, indent=2, default=str)
        if path:
            with open(path, "w") as f:
                f.write(json_str)
        return json_str

    @classmethod
    def from_json(cls, path: str) -> "PromptEvaluator":
        """Load evaluator from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)

        weights = {
            EvalMetric(k): v
            for k, v in data.get("metric_weights", {}).items()
        }
        evaluator = cls(metric_weights=weights)
        evaluator._eval_counter = data.get("eval_counter", 0)

        for result_data in data.get("history", []):
            scores = []
            for sd in result_data.get("scores", []):
                scores.append(EvalScore(
                    metric=EvalMetric(sd["metric"]),
                    value=sd["value"],
                    weight=sd.get("weight", 1.0),
                    threshold_pass=sd.get("threshold_pass"),
                    metadata=sd.get("metadata", {}),
                ))
            result = EvaluationResult(
                eval_id=result_data["eval_id"],
                prompt_id=result_data["prompt_id"],
                prompt_version=result_data["prompt_version"],
                scores=scores,
                overall_grade=EvalGrade(result_data["overall_grade"]),
                overall_score=result_data["overall_score"],
                input_tokens=result_data.get("input_tokens", 0),
                output_tokens=result_data.get("output_tokens", 0),
                latency_ms=result_data.get("latency_ms", 0.0),
                cost=result_data.get("cost", 0.0),
                task_completed=result_data.get("task_completed", False),
                hallucination_detected=result_data.get("hallucination_detected", False),
                timestamp=datetime.fromisoformat(result_data["timestamp"]),
                metadata=result_data.get("metadata", {}),
            )
            evaluator._history.append(result)

        return evaluator

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    @staticmethod
    def _word_overlap(a: str, b: str) -> float:
        words_a = a.lower().split()
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        return sum(1 for w in words_a if w in words_b) / len(words_a)

    @staticmethod
    def _contains_key_facts(response: str, reference: str) -> float:
        """Check if key facts from reference appear in response."""
        ref_sentences = re.split(r'(?<=[.!?])\s+', reference)
        if not ref_sentences:
            return 0.0

        resp_lower = response.lower()
        matches = 0
        for sentence in ref_sentences:
            # Extract key phrases (3+ word sequences)
            words = sentence.lower().split()
            if len(words) < 3:
                continue
            # Check first meaningful 3-gram
            trigram = " ".join(words[:3])
            if trigram in resp_lower:
                matches += 1

        return matches / len(ref_sentences) if ref_sentences else 0.0

    @staticmethod
    def _find_contradictions(response: str, reference: str) -> List[str]:
        """Find potential contradictions between response and reference."""
        contradictions = []
        negation_pairs = [
            ("is", "is not"),
            ("can", "cannot"),
            ("will", "will not"),
            ("does", "does not"),
            ("has", "has no"),
            ("must", "must not"),
            ("should", "should not"),
            ("always", "never"),
        ]
        r_lower = response.lower()
        ref_lower = reference.lower()

        for pos, neg in negation_pairs:
            if pos in r_lower and neg in ref_lower:
                contradictions.append(f"'{pos}' vs '{neg}'")
            elif neg in r_lower and pos in ref_lower:
                contradictions.append(f"'{neg}' vs '{pos}'")

        return contradictions

    @staticmethod
    def _stop_words() -> Set[str]:
        """Common English stop words."""
        return {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "and", "but", "or", "nor", "not", "so",
            "yet", "both", "either", "neither", "each", "every", "all",
            "any", "few", "more", "most", "other", "some", "such", "no",
            "only", "own", "same", "than", "too", "very", "just", "this",
            "that", "these", "those", "it", "its", "he", "she", "they",
            "them", "we", "you", "i", "me", "my", "your", "his", "her",
            "their", "our", "about", "also", "then", "now", "here", "there",
        }

    def __len__(self) -> int:
        with self._lock:
            return len(self._history)

    def __repr__(self) -> str:
        return f"PromptEvaluator(evaluations={len(self)})"
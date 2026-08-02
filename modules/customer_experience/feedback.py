"""
Customer Feedback Management Engine.

Collects, analyzes, and actionizes customer feedback from
multiple channels, with sentiment analysis and trend detection.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("enterprise.customer_experience")


class FeedbackSource(Enum):
    """Sources from which customer feedback can originate."""

    SURVEY = "survey"
    SUPPORT_TICKET = "support_ticket"
    SOCIAL_MEDIA = "social_media"
    REVIEW_SITE = "review_site"
    IN_APP = "in_app"
    EMAIL = "email"
    INTERVIEW = "interview"
    USABILITY_TEST = "usability_test"
    NPS = "nps"
    CUSTOM = "custom"


class Sentiment(Enum):
    """Sentiment classification for feedback entries."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


@dataclass
class FeedbackEntry:
    """A single piece of customer feedback."""

    source: FeedbackSource
    customer_id: str
    sentiment: Sentiment = Sentiment.NEUTRAL
    content: str = ""
    category: str = "general"
    priority: int = 3  # 1 (critical) to 5 (nice-to-have)
    product_area: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    analyzed: bool = False
    action_items: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class FeedbackEngine:
    """Engine for managing and analyzing customer feedback."""

    # Positive sentiment word indicators
    _POSITIVE_WORDS: set = {
        "love", "great", "excellent", "amazing", "fantastic", "wonderful",
        "perfect", "outstanding", "best", "awesome", "helpful", "easy",
        "intuitive", "fast", "reliable", "thank", "thanks", "pleased",
        "happy", "satisfied", "impressed", "recommend", "enjoy",
    }

    # Negative sentiment word indicators
    _NEGATIVE_WORDS: set = {
        "hate", "terrible", "awful", "horrible", "worst", "broken",
        "bug", "crash", "slow", "confusing", "frustrating", "annoying",
        "disappointed", "unhappy", "unusable", "difficult", "expensive",
        "useless", "waste", "regret", "fail", "failure", "stuck",
    }

    # Negation words that flip sentiment
    _NEGATION_WORDS: set = {
        "not", "never", "no", "neither", "hardly", "barely", "doesn't",
        "don't", "won't", "can't", "isn't", "aren't", "wasn't",
    }

    def __init__(self) -> None:
        self._entries: List[FeedbackEntry] = []
        self._trend_cache: Dict[str, Any] = {}
        self._trend_cache_ts: Optional[datetime] = None
        logger.info("FeedbackEngine initialized")

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def collect_feedback(
        self,
        source: FeedbackSource,
        customer_id: str,
        content: str,
        category: str = "general",
        product_area: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FeedbackEntry:
        """Collect and register a new feedback entry.

        Auto-analyzes sentiment on collection.
        """
        sentiment = self.analyze_sentiment(content)
        entry = FeedbackEntry(
            source=source,
            customer_id=customer_id,
            sentiment=sentiment,
            content=content,
            category=category,
            product_area=product_area,
            metadata=metadata or {},
            analyzed=True,
        )
        self._entries.append(entry)
        self._invalidate_cache()
        logger.info(
            "Collected feedback from '%s': %s sentiment",
            customer_id,
            sentiment.value,
        )
        return entry

    # ------------------------------------------------------------------
    # Sentiment Analysis
    # ------------------------------------------------------------------

    def analyze_sentiment(self, text: str) -> Sentiment:
        """Simple lexicon-based sentiment analysis.

        For production use, replace with an ML-based classifier like
        a fine-tuned BERT model. This implementation provides a
        reasonable baseline that works offline with no dependencies.
        """
        lowered = text.lower()
        words = lowered.split()

        pos_count = 0
        neg_count = 0
        negate_next = False

        for i, word in enumerate(words):
            # Clean punctuation off word edges for matching
            clean = word.strip(".,!?;:\"'()[]{}")

            if clean in self._NEGATION_WORDS:
                negate_next = True
                continue

            is_pos = clean in self._POSITIVE_WORDS
            is_neg = clean in self._NEGATIVE_WORDS

            if negate_next:
                # Check if previous word was within 3 words
                if is_pos:
                    neg_count += 1
                    is_pos = False
                elif is_neg:
                    pos_count += 1
                    is_neg = False
                negate_next = False

            if is_pos:
                pos_count += 1
            if is_neg:
                neg_count += 1

        total = pos_count + neg_count
        if total == 0:
            return Sentiment.NEUTRAL

        ratio = pos_count / total
        if ratio >= 0.7:
            return Sentiment.POSITIVE
        elif ratio <= 0.3:
            return Sentiment.NEGATIVE
        elif 0.4 <= ratio <= 0.6:
            return Sentiment.MIXED
        else:
            return Sentiment.NEUTRAL

    # ------------------------------------------------------------------
    # Trend identification
    # ------------------------------------------------------------------

    def identify_trends(
        self,
        days: int = 30,
        min_occurrences: int = 3,
    ) -> Dict[str, Any]:
        """Identify emerging trends in recent feedback.

        Looks for recurring themes, sentiment shifts, and high-frequency
        topics within the specified time window.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        recent = [
            e for e in self._entries
            if e.created_at.timestamp() >= cutoff
        ]

        if not recent:
            return {"trends": [], "summary": "No recent feedback"}

        # Category frequency
        cat_counter = Counter(e.category for e in recent)
        top_categories = cat_counter.most_common(5)

        # Product area frequency
        area_counter = Counter(e.product_area for e in recent if e.product_area)
        top_areas = area_counter.most_common(5)

        # Sentiment distribution shift
        sentiment_counts = Counter(e.sentiment for e in recent)
        total_recent = len(recent)
        sentiment_ratios = {
            s.value: round((sentiment_counts[s] / total_recent) * 100, 1)
            for s in Sentiment
        }

        # Emerging issues (negative feedback in previously positive categories)
        neg_by_category = Counter(
            e.category for e in recent if e.sentiment == Sentiment.NEGATIVE
        )
        emerging_issues = [
            {"category": cat, "negative_count": cnt}
            for cat, cnt in neg_by_category.most_common(5)
            if cnt >= min_occurrences
        ]

        # Positive momentum
        pos_by_area = Counter(
            e.product_area for e in recent
            if e.sentiment == Sentiment.POSITIVE and e.product_area
        )
        positive_momentum = [
            {"product_area": area, "positive_count": cnt}
            for area, cnt in pos_by_area.most_common(5)
            if cnt >= min_occurrences
        ]

        # Build word-level trends
        word_trends = self._extract_common_phrases(recent, min_occurrences)

        trends = {
            "analysis_window_days": days,
            "total_entries_analyzed": total_recent,
            "sentiment_distribution": sentiment_ratios,
            "dominant_sentiment": max(sentiment_counts, key=sentiment_counts.get).value,
            "top_categories": [{"category": c, "count": n} for c, n in top_categories],
            "top_product_areas": [{"area": a, "count": n} for a, n in top_areas],
            "emerging_issues": emerging_issues,
            "positive_momentum": positive_momentum,
            "common_phrases": word_trends,
            "summary": self._generate_trend_summary(
                sentiment_ratios, emerging_issues, positive_momentum
            ),
        }

        self._trend_cache = trends
        self._trend_cache_ts = datetime.now(timezone.utc)
        logger.info("Identified trends from %d recent entries", total_recent)
        return trends

    # ------------------------------------------------------------------
    # Categorization and prioritization
    # ------------------------------------------------------------------

    def categorize_feedback(
        self,
        entry_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Categorize feedback entries and provide category breakdown."""
        if entry_id is not None:
            entry = self._entries[entry_id] if 0 <= entry_id < len(self._entries) else None
            if entry is None:
                return {}
            return {
                "source": entry.source.value,
                "category": entry.category,
                "sentiment": entry.sentiment.value,
                "product_area": entry.product_area,
                "priority": entry.priority,
            }

        # Full breakdown
        by_source = defaultdict(list)
        by_category = defaultdict(list)
        by_sentiment = defaultdict(list)

        for e in self._entries:
            by_source[e.source.value].append(e)
            by_category[e.category].append(e)
            by_sentiment[e.sentiment.value].append(e)

        return {
            "total_entries": len(self._entries),
            "by_source": {k: len(v) for k, v in by_source.items()},
            "by_category": {k: len(v) for k, v in by_category.items()},
            "by_sentiment": {k: len(v) for k, v in by_sentiment.items()},
        }

    def prioritize_improvements(self) -> List[Dict[str, Any]]:
        """Prioritize improvement areas based on feedback impact.

        Uses a weighted scoring approach: sentiment severity × frequency.
        """
        area_scores: Dict[str, Dict[str, Any]] = {}

        for entry in self._entries:
            area = entry.product_area or entry.category
            if area not in area_scores:
                area_scores[area] = {
                    "product_area": area,
                    "total_feedback": 0,
                    "negative_count": 0,
                    "positive_count": 0,
                    "priority_sum": 0,
                    "impact_score": 0.0,
                }

            stats = area_scores[area]
            stats["total_feedback"] += 1

            if entry.sentiment == Sentiment.NEGATIVE:
                stats["negative_count"] += 1
                stats["priority_sum"] += (6 - entry.priority)  # Inverse: low priority num = high priority
            elif entry.sentiment == Sentiment.POSITIVE:
                stats["positive_count"] += 1

        # Calculate impact score
        for stats in area_scores.values():
            if stats["total_feedback"] > 0:
                neg_ratio = stats["negative_count"] / stats["total_feedback"]
                stats["impact_score"] = round(
                    (neg_ratio * 10) + (stats["priority_sum"] * 2), 2
                )
                stats["neg_ratio"] = round(neg_ratio, 2)

        ranked = sorted(
            area_scores.values(),
            key=lambda x: x["impact_score"],
            reverse=True,
        )

        logger.info("Prioritized %d improvement areas", len(ranked))
        return ranked

    # ------------------------------------------------------------------
    # Product insights
    # ------------------------------------------------------------------

    def generate_product_insights(self) -> Dict[str, Any]:
        """Generate actionable product insights from feedback patterns."""
        trends = self.identify_trends()
        priorities = self.prioritize_improvements()

        # Extract actionable insights
        insights = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sentiment_overview": trends.get("sentiment_distribution", {}),
            "top_pain_points": [
                p for p in priorities if p.get("neg_ratio", 0) > 0.3
            ][:5],
            "top_strengths": [
                p for p in priorities
                if p.get("positive_count", 0) > 0
                and p.get("neg_ratio", 1) < 0.2
            ][:5],
            "emerging_issues": trends.get("emerging_issues", []),
            "positive_momentum": trends.get("positive_momentum", []),
            "recommended_actions": self._generate_recommendations(priorities),
        }

        logger.info("Generated product insights")
        return insights

    # ------------------------------------------------------------------
    # Feedback loop closure
    # ------------------------------------------------------------------

    def close_feedback_loop(
        self,
        entry_index: int,
        action_items: List[str],
        resolution: str = "",
    ) -> Optional[FeedbackEntry]:
        """Mark a feedback entry as actioned with resolution details."""
        if entry_index < 0 or entry_index >= len(self._entries):
            logger.warning("Invalid feedback entry index: %d", entry_index)
            return None

        entry = self._entries[entry_index]
        entry.action_items = action_items
        entry.metadata["resolution"] = resolution
        entry.metadata["closed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Closed feedback loop for entry %d (customer '%s')",
            entry_index,
            entry.customer_id,
        )
        return entry

    def track_impact(
        self,
        product_area: str,
        before_date: datetime,
        after_date: datetime,
    ) -> Dict[str, Any]:
        """Track sentiment impact in a product area before/after changes."""
        before = [
            e for e in self._entries
            if e.product_area == product_area and e.created_at < before_date
        ]
        after = [
            e for e in self._entries
            if e.product_area == product_area
            and before_date <= e.created_at <= after_date
        ]

        def sentiment_ratio(entries: List[FeedbackEntry]) -> Dict[str, float]:
            if not entries:
                return {"positive": 0, "neutral": 0, "negative": 0, "mixed": 0}
            counter = Counter(e.sentiment for e in entries)
            total = len(entries)
            return {s.value: round(counter[s] / total, 3) for s in Sentiment}

        before_ratios = sentiment_ratio(before)
        after_ratios = sentiment_ratio(after)

        # Calculate sentiment shift
        pos_shift = after_ratios.get("positive", 0) - before_ratios.get("positive", 0)
        neg_shift = after_ratios.get("negative", 0) - before_ratios.get("negative", 0)

        impact = {
            "product_area": product_area,
            "before_period": {
                "count": len(before),
                "sentiment_ratios": before_ratios,
            },
            "after_period": {
                "count": len(after),
                "sentiment_ratios": after_ratios,
            },
            "sentiment_shift": {
                "positive_delta": round(pos_shift, 3),
                "negative_delta": round(neg_shift, 3),
                "direction": (
                    "improving" if pos_shift > 0 and neg_shift < 0
                    else "declining" if pos_shift < 0 and neg_shift > 0
                    else "mixed"
                ),
            },
        }

        logger.info("Impact tracked for '%s': %s", product_area, impact["sentiment_shift"]["direction"])
        return impact

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_common_phrases(
        self,
        entries: List[FeedbackEntry],
        min_occ: int,
    ) -> List[Dict[str, Any]]:
        """Extract frequently mentioned bigrams as common phrases."""
        bigram_counter: Counter = Counter()
        for entry in entries:
            words = entry.content.lower().split()
            for i in range(len(words) - 1):
                w1 = words[i].strip(".,!?;:\"'()[]{}")
                w2 = words[i + 1].strip(".,!?;:\"'()[]{}")
                if len(w1) > 2 and len(w2) > 2:
                    bigram_counter[f"{w1} {w2}"] += 1

        return [
            {"phrase": phrase, "count": count}
            for phrase, count in bigram_counter.most_common(20)
            if count >= min_occ
        ]

    def _generate_trend_summary(
        self,
        sentiment: Dict[str, float],
        issues: List[Dict[str, Any]],
        momentum: List[Dict[str, Any]],
    ) -> str:
        """Generate a human-readable trend summary."""
        parts = []
        neg_pct = sentiment.get("negative", 0)
        pos_pct = sentiment.get("positive", 0)

        if neg_pct > 30:
            parts.append(f"High negative sentiment ({neg_pct}%)")
        elif neg_pct < 10:
            parts.append(f"Low negative sentiment ({neg_pct}%)")

        if pos_pct > 50:
            parts.append(f"Strong positive sentiment ({pos_pct}%)")

        if issues:
            parts.append(f"{len(issues)} emerging issue(s)")
        if momentum:
            parts.append(f"{len(momentum)} area(s) with positive momentum")

        return ". ".join(parts) if parts else "Stable trends detected"

    def _generate_recommendations(
        self,
        priorities: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """Generate recommended actions from prioritized improvements."""
        recommendations = []
        for item in priorities[:5]:
            if item.get("neg_ratio", 0) > 0.3:
                recommendations.append({
                    "area": item["product_area"],
                    "urgency": "high" if item.get("impact_score", 0) > 15 else "medium",
                    "action": f"Investigate and address negative feedback in '{item['product_area']}'",
                })
        return recommendations

    def _invalidate_cache(self) -> None:
        self._trend_cache = {}
        self._trend_cache_ts = None

    def entry_count(self) -> int:
        return len(self._entries)

    def get_entries(
        self,
        source: Optional[FeedbackSource] = None,
        sentiment: Optional[Sentiment] = None,
        limit: int = 0,
    ) -> List[FeedbackEntry]:
        results = self._entries
        if source:
            results = [e for e in results if e.source == source]
        if sentiment:
            results = [e for e in results if e.sentiment == sentiment]
        return results[-limit:] if limit > 0 else results
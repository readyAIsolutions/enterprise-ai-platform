"""
Claim Detector — Standalone claim detection and classification.

Extracts claims from text and classifies them as:
  - FACT: Verified or verifiable statements
  - ASSUMPTION: Unverified but accepted premises
  - OPINION: Subjective judgments
  - SPECULATION: Hypothetical or unverified predictions
  - CONFLICTING: Claims that contradict other claims
"""

from __future__ import annotations

import re
import uuid
from enum import Enum
from typing import Any


class ClaimKind(Enum):
    """Kind of claim (mirrors ClaimType in research_engine.py)."""
    FACT = "fact"
    ASSUMPTION = "assumption"
    OPINION = "opinion"
    SPECULATION = "speculation"
    CONFLICTING = "conflicting"


class ClaimDetector:
    """Standalone claim detector that extracts and classifies claims from text."""

    # Indicators for classification
    ASSUMPTION_WORDS = [
        "assume", "might", "could", "maybe", "perhaps", "likely",
        "probably", "should", "typically", "generally", "in theory",
        "thought to be", "believed to be",
    ]
    FACT_WORDS = ["is", "are", "was", "were", "has been", "have been",
                  "confirmed", "verified", "documented", "proven"]
    SPECULATION_WORDS = ["might be", "could be", "possibly", "unknown",
                         "speculative", "unclear", "hypothetically"]
    OPINION_WORDS = ["i think", "in my opinion", "i believe", "we believe",
                     "arguably", "preferable"]
    CONFLICT_WORDS = ["however", "but", "contrary", "disagree", "conflicting",
                      "on the other hand", "disputed", "controversial"]

    @classmethod
    def classify(cls, text: str) -> ClaimKind:
        """Classify a single text into a ClaimKind."""
        t = text.lower()

        if any(cw in t for cw in cls.CONFLICT_WORDS):
            return ClaimKind.CONFLICTING
        if any(sw in t for sw in cls.SPECULATION_WORDS):
            return ClaimKind.SPECULATION
        if any(ow in t for ow in cls.OPINION_WORDS):
            return ClaimKind.OPINION
        if any(aw in t for aw in cls.ASSUMPTION_WORDS):
            return ClaimKind.ASSUMPTION
        if any(fw in t for fw in cls.FACT_WORDS):
            return ClaimKind.FACT
        return ClaimKind.FACT  # Default: treat unmarked statements as factual claims

    @classmethod
    def extract(cls, text: str) -> list[dict[str, Any]]:
        """Extract claims from a block of text.

        Splits on sentence boundaries, classifies each sentence,
        and returns a list of claim dicts.

        Args:
            text: Raw text to extract claims from.

        Returns:
            List of dicts with keys: id, text, kind, confidence.
        """
        sentences = re.split(r'(?<=[.!?])\s+', text)
        claims: list[dict[str, Any]] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 15:
                continue
            kind = cls.classify(sentence)
            claims.append({
                "id": str(uuid.uuid4()),
                "text": sentence,
                "kind": kind.value,
                "confidence": cls._base_confidence(kind),
            })
        return claims

    @classmethod
    def detect_conflicts(cls, claims: list[dict[str, Any]]) -> list[tuple[int, int]]:
        """Detect conflict pairs among a list of claims.

        Returns list of (i, j) tuples where claims i and j conflict.
        """
        conflicts: list[tuple[int, int]] = []
        for i, a in enumerate(claims):
            for j, b in enumerate(claims):
                if j <= i:
                    continue
                a_text, b_text = a["text"].lower(), b["text"].lower()
                # Heuristic: one contains negation while other asserts
                if ("is not" in a_text and "is " in b_text.replace("is not", "")) or \
                   ("is not" in b_text and "is " in a_text.replace("is not", "")):
                    conflicts.append((i, j))
                    a["kind"] = ClaimKind.CONFLICTING.value
                    b["kind"] = ClaimKind.CONFLICTING.value
        return conflicts

    @staticmethod
    def _base_confidence(kind: ClaimKind) -> float:
        """Get base confidence for a claim kind."""
        return {
            ClaimKind.FACT: 0.85,
            ClaimKind.ASSUMPTION: 0.5,
            ClaimKind.OPINION: 0.4,
            ClaimKind.SPECULATION: 0.25,
            ClaimKind.CONFLICTING: 0.2,
        }.get(kind, 0.3)


# ── Convenience functions matching the module __all__ ─────────────────────


def classify_claim(text: str) -> str:
    """Classify a claim text and return its kind as a string."""
    return ClaimDetector.classify(text).value


def extract_claims(text: str) -> list[dict[str, Any]]:
    """Extract claims from text and return as list of dicts."""
    return ClaimDetector.extract(text)
"""
Re-Ranking for RAG System.

Provides re-ranking techniques to improve retrieval quality:
- Gradual Re-ranking: Relevance increases over time with user interaction
- Incremental Re-ranking: Updates relevance scores incrementally

Both implement a common RerankingStrategy interface.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .retrieval import RetrievalResult


class RerankingStrategy(str, Enum):
    """Available re-ranking strategies."""
    GRADUAL = "gradual"
    INCREMENTAL = "incremental"
    NONE = "none"


@dataclass
class RerankResult:
    """A re-ranked result with updated score and metadata."""
    chunk_id: str
    original_score: float
    reranked_score: float
    strategy: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def score_delta(self) -> float:
        return self.reranked_score - self.original_score


@dataclass
class UserInteraction:
    """Record of user interaction with a result."""
    chunk_id: str
    interaction_type: str  # click, dwell, scroll, copy, thumbs_up, thumbs_down
    timestamp: float
    duration: Optional[float] = None  # For dwell time
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseReranker(ABC):
    """Abstract base class for all rerankers."""
    
    def __init__(self):
        self.interaction_history: List[UserInteraction] = []
    
    @abstractmethod
    def rerank(
        self,
        results: List[RetrievalResult],
        query: str,
        **kwargs
    ) -> List[RerankResult]:
        """Re-rank retrieval results."""
        pass
    
    def record_interaction(self, interaction: UserInteraction) -> None:
        """Record user interaction for learning."""
        self.interaction_history.append(interaction)
    
    def get_interactions_for_chunk(self, chunk_id: str) -> List[UserInteraction]:
        """Get all interactions for a specific chunk."""
        return [i for i in self.interaction_history if i.chunk_id == chunk_id]


class GradualReranker(BaseReranker):
    """
    Gradual Re-ranking.
    
    Relevance scores increase gradually over time as users interact
    with results. Implements a time-decay + interaction accumulation model.
    
    Formula: new_score = base_score + alpha * accumulated_relevance * time_decay
    """
    
    def __init__(
        self,
        alpha: float = 0.1,          # Learning rate for relevance accumulation
        beta: float = 0.01,          # Time decay factor (per day)
        max_boost: float = 0.5,      # Maximum score boost
        interaction_weights: Optional[Dict[str, float]] = None,
        persistence_path: Optional[str] = None,
    ):
        """
        Initialize gradual reranker.
        
        Args:
            alpha: How much each interaction contributes to relevance
            beta: Daily decay rate for accumulated relevance
            max_boost: Maximum boost to original score
            interaction_weights: Weight per interaction type
            persistence_path: Path to save/load accumulated relevance
        """
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.max_boost = max_boost
        self.interaction_weights = interaction_weights or {
            "click": 1.0,
            "dwell": 0.5,        # Per second of dwell time
            "scroll": 0.2,
            "copy": 2.0,
            "thumbs_up": 3.0,
            "thumbs_down": -2.0,
        }
        self.persistence_path = Path(persistence_path) if persistence_path else None
        
        # Accumulated relevance per chunk (persisted)
        self._accumulated_relevance: Dict[str, float] = defaultdict(float)
        self._last_update: Dict[str, float] = defaultdict(float)
        
        self._load_persistence()
    
    def _load_persistence(self) -> None:
        """Load accumulated relevance from disk."""
        if self.persistence_path and self.persistence_path.exists():
            try:
                with open(self.persistence_path, 'r') as f:
                    data = json.load(f)
                    self._accumulated_relevance = defaultdict(float, data.get("relevance", {}))
                    self._last_update = defaultdict(float, data.get("last_update", {}))
            except Exception:
                pass  # Start fresh on error
    
    def _save_persistence(self) -> None:
        """Save accumulated relevance to disk."""
        if self.persistence_path:
            try:
                self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.persistence_path, 'w') as f:
                    json.dump({
                        "relevance": dict(self._accumulated_relevance),
                        "last_update": dict(self._last_update),
                    }, f)
            except Exception:
                pass  # Silently fail
    
    def _compute_time_decay(self, chunk_id: str) -> float:
        """Compute time decay factor since last update."""
        last = self._last_update.get(chunk_id, time.time())
        days_elapsed = (time.time() - last) / 86400.0
        return math.exp(-self.beta * days_elapsed)
    
    def _compute_interaction_boost(self, chunk_id: str) -> float:
        """Compute boost from accumulated interactions."""
        interactions = self.get_interactions_for_chunk(chunk_id)
        if not interactions:
            return 0.0
        
        total_boost = 0.0
        for interaction in interactions:
            weight = self.interaction_weights.get(interaction.interaction_type, 0.0)
            if interaction.interaction_type == "dwell" and interaction.duration:
                total_boost += weight * min(interaction.duration, 60)  # Cap at 60s
            else:
                total_boost += weight
        
        return min(total_boost * self.alpha, self.max_boost)
    
    def rerank(
        self,
        results: List[RetrievalResult],
        query: str,
        **kwargs
    ) -> List[RerankResult]:
        """Re-rank using gradual relevance accumulation."""
        reranked = []
        
        for result in results:
            chunk_id = result.chunk.id
            original_score = result.score
            
            # Compute time decay
            decay = self._compute_time_decay(chunk_id)
            
            # Compute interaction boost
            interaction_boost = self._compute_interaction_boost(chunk_id)
            
            # Apply decay to accumulated relevance
            accumulated = self._accumulated_relevance.get(chunk_id, 0.0) * decay
            
            # New relevance = accumulated * decay + new interactions
            new_accumulated = accumulated + interaction_boost
            self._accumulated_relevance[chunk_id] = new_accumulated
            self._last_update[chunk_id] = time.time()
            
            # Compute final score
            boost = min(new_accumulated, self.max_boost)
            reranked_score = original_score + boost
            
            reranked.append(RerankResult(
                chunk_id=chunk_id,
                original_score=original_score,
                reranked_score=reranked_score,
                strategy="gradual",
                metadata={
                    "accumulated_relevance": new_accumulated,
                    "time_decay": decay,
                    "interaction_boost": interaction_boost,
                    "final_boost": boost,
                },
            ))
        
        self._save_persistence()
        
        # Sort by reranked score
        reranked.sort(key=lambda x: x.reranked_score, reverse=True)
        return reranked
    
    def reset_relevance(self, chunk_id: Optional[str] = None) -> None:
        """Reset accumulated relevance for a chunk or all chunks."""
        if chunk_id:
            self._accumulated_relevance.pop(chunk_id, None)
            self._last_update.pop(chunk_id, None)
        else:
            self._accumulated_relevance.clear()
            self._last_update.clear()
        self._save_persistence()


class IncrementalReranker(BaseReranker):
    """
    Incremental Re-ranking.
    
    Updates relevance scores incrementally after each query/interaction
    without full recomputation. Uses exponential moving average.
    
    Formula: new_score = (1 - gamma) * old_score + gamma * interaction_signal
    """
    
    def __init__(
        self,
        gamma: float = 0.1,          # Update rate (0-1)
        base_weight: float = 0.7,    # Weight for original retrieval score
        interaction_weight: float = 0.3,  # Weight for interaction signal
        min_score: float = 0.0,
        max_score: float = 1.0,
        persistence_path: Optional[str] = None,
    ):
        """
        Initialize incremental reranker.
        
        Args:
            gamma: Exponential moving average decay
            base_weight: Weight for original retrieval score
            interaction_weight: Weight for interaction signal
            min_score: Minimum allowed score
            max_score: Maximum allowed score
            persistence_path: Path to save/load scores
        """
        super().__init__()
        self.gamma = gamma
        self.base_weight = base_weight
        self.interaction_weight = interaction_weight
        self.min_score = min_score
        self.max_score = max_score
        self.persistence_path = Path(persistence_path) if persistence_path else None
        
        # Incremental scores per chunk
        self._incremental_scores: Dict[str, float] = {}
        
        self._load_persistence()
    
    def _load_persistence(self) -> None:
        """Load incremental scores from disk."""
        if self.persistence_path and self.persistence_path.exists():
            try:
                with open(self.persistence_path, 'r') as f:
                    data = json.load(f)
                    self._incremental_scores = data.get("scores", {})
            except Exception:
                pass
    
    def _save_persistence(self) -> None:
        """Save incremental scores to disk."""
        if self.persistence_path:
            try:
                self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.persistence_path, 'w') as f:
                    json.dump({"scores": self._incremental_scores}, f)
            except Exception:
                pass
    
    def _compute_interaction_signal(self, chunk_id: str) -> float:
        """Compute interaction signal for a chunk (0-1)."""
        interactions = self.get_interactions_for_chunk(chunk_id)
        if not interactions:
            return 0.5  # Neutral
        
        # Weight different interaction types
        weights = {
            "click": 0.6,
            "dwell": 0.7,        # High dwell = positive
            "scroll": 0.55,
            "copy": 0.9,
            "thumbs_up": 1.0,
            "thumbs_down": 0.0,
        }
        
        signals = []
        for interaction in interactions:
            weight = weights.get(interaction.interaction_type, 0.5)
            if interaction.interaction_type == "dwell" and interaction.duration:
                # Normalize dwell time (0-60s -> 0.5-1.0)
                normalized = 0.5 + 0.5 * min(interaction.duration / 60.0, 1.0)
                signals.append(normalized)
            else:
                signals.append(weight)
        
        # Exponential moving average of signals
        if not signals:
            return 0.5
        
        ema = signals[0]
        for signal in signals[1:]:
            ema = (1 - self.gamma) * ema + self.gamma * signal
        
        return ema
    
    def rerank(
        self,
        results: List[RetrievalResult],
        query: str,
        **kwargs
    ) -> List[RerankResult]:
        """Re-rank using incremental score updates."""
        reranked = []
        
        for result in results:
            chunk_id = result.chunk.id
            original_score = result.score
            
            # Get or initialize incremental score
            current_inc = self._incremental_scores.get(chunk_id, original_score)
            
            # Compute interaction signal
            interaction_signal = self._compute_interaction_signal(chunk_id)
            
            # Update incremental score (EMA)
            new_inc = (1 - self.gamma) * current_inc + self.gamma * interaction_signal
            self._incremental_scores[chunk_id] = new_inc
            
            # Combine with original score
            reranked_score = (
                self.base_weight * original_score +
                self.interaction_weight * new_inc
            )
            
            # Clamp
            reranked_score = max(self.min_score, min(self.max_score, reranked_score))
            
            reranked.append(RerankResult(
                chunk_id=chunk_id,
                original_score=original_score,
                reranked_score=reranked_score,
                strategy="incremental",
                metadata={
                    "incremental_score": new_inc,
                    "interaction_signal": interaction_signal,
                    "base_weight": self.base_weight,
                    "interaction_weight": self.interaction_weight,
                },
            ))
        
        self._save_persistence()
        
        # Sort by reranked score
        reranked.sort(key=lambda x: x.reranked_score, reverse=True)
        return reranked
    
    def reset_scores(self, chunk_id: Optional[str] = None) -> None:
        """Reset incremental scores."""
        if chunk_id:
            self._incremental_scores.pop(chunk_id, None)
        else:
            self._incremental_scores.clear()
        self._save_persistence()


class NoReranker(BaseReranker):
    """Pass-through reranker (no re-ranking)."""
    
    def rerank(
        self,
        results: List[RetrievalResult],
        query: str,
        **kwargs
    ) -> List[RerankResult]:
        return [
            RerankResult(
                chunk_id=r.chunk.id,
                original_score=r.score,
                reranked_score=r.score,
                strategy="none",
                metadata={},
            )
            for r in results
        ]


def create_reranker(
    strategy: RerankingStrategy | str,
    **kwargs
) -> BaseReranker:
    """
    Factory function to create a reranker.
    
    Args:
        strategy: RerankingStrategy.GRADUAL, INCREMENTAL, NONE, or string
        **kwargs: Arguments passed to reranker constructor
        
    Returns:
        Configured reranker instance
    """
    if isinstance(strategy, str):
        strategy = RerankingStrategy(strategy.lower())
    
    if strategy == RerankingStrategy.GRADUAL:
        return GradualReranker(**kwargs)
    elif strategy == RerankingStrategy.INCREMENTAL:
        return IncrementalReranker(**kwargs)
    elif strategy == RerankingStrategy.NONE:
        return NoReranker()
    else:
        raise ValueError(f"Unknown reranking strategy: {strategy}")
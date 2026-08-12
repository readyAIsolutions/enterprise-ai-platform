"""
Embedding Model Selection for RAG System.

Provides two embedding approaches:
- Pre-trained Embeddings: General-purpose models (BERT, sentence-transformers, etc.)
- Custom Embeddings: Domain-specific fine-tuned models

Both implement a common EmbeddingProvider interface for seamless swapping.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Optional dependencies
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    SentenceTransformer = None  # type: ignore


class EmbeddingProvider(str, Enum):
    """Available embedding providers."""
    PRETRAINED = "pretrained"
    CUSTOM = "custom"
    HASH = "hash"  # Fallback deterministic embedding


@dataclass
class EmbeddingConfig:
    """Configuration for embedding models."""
    provider: EmbeddingProvider = EmbeddingProvider.PRETRAINED
    model_name: str = "all-MiniLM-L6-v2"  # Default sentence-transformers model
    dimension: int = 384
    device: str = "auto"  # auto, cpu, cuda, mps
    batch_size: int = 32
    max_length: int = 512
    normalize: bool = True
    cache_dir: Optional[str] = None
    custom_model_path: Optional[str] = None
    # Custom training config
    training_data: Optional[List[str]] = None
    training_epochs: int = 3
    learning_rate: float = 2e-5


class BaseEmbedder(ABC):
    """Abstract base class for all embedders."""
    
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._dimension = config.dimension
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @abstractmethod
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Embed texts into vectors."""
        pass
    
    def embed_single(self, text: str) -> List[float]:
        """Embed a single text."""
        return self.embed([text])[0]
    
    def similarity(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity between two embeddings."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    def batch_similarity(
        self,
        query: List[float],
        candidates: List[List[float]]
    ) -> List[float]:
        """Compute similarity between query and multiple candidates."""
        return [self.similarity(query, c) for c in candidates]


class HashEmbedder(BaseEmbedder):
    """
    Deterministic hash-based embedder (no dependencies).
    
    Uses feature hashing (signed random projection) to create
    deterministic embeddings without any ML dependencies.
    Good for testing, CI, or when ML libraries unavailable.
    """
    
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._dimension = config.dimension
        # Deterministic projection matrix
        self._projection = self._create_projection()
    
    def _create_projection(self) -> List[List[float]]:
        """Create deterministic projection matrix."""
        projection = []
        for i in range(self._dimension):
            row = []
            for j in range(10000):  # Vocab size for hashing
                # Deterministic signed pseudo-random values
                h = int(hashlib.md5(f"{i}_{j}".encode()).hexdigest()[:8], 16)
                row.append(1.0 if (h & 1) == 0 else -1.0)
            projection.append(row)
        return projection
    
    def _text_to_features(self, text: str) -> List[float]:
        """Convert text to feature vector using hashing trick."""
        features = [0.0] * 10000
        words = text.lower().split()
        for word in words:
            idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 10000
            features[idx] += 1.0
        return features
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Embed texts using deterministic hashing."""
        if isinstance(texts, str):
            texts = [texts]
        
        embeddings = []
        for text in texts:
            features = self._text_to_features(text)
            # Project to target dimension
            embedding = []
            for i in range(self._dimension):
                val = sum(features[j] * self._projection[i][j] for j in range(10000))
                embedding.append(val)
            
            # L2 normalize
            if self.config.normalize:
                norm = math.sqrt(sum(v * v for v in embedding))
                if norm > 0:
                    embedding = [v / norm for v in embedding]
            
            embeddings.append(embedding)
        
        return embeddings


class PretrainedEmbedder(BaseEmbedder):
    """
    Pre-trained embedding models via sentence-transformers.
    
    Supports any model from the sentence-transformers hub:
    - all-MiniLM-L6-v2 (384 dim, fast, good quality)
    - all-mpnet-base-v2 (768 dim, higher quality)
    - paraphrase-multilingual-MiniLM-L12-v2 (multilingual)
    - And many more...
    """
    
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        
        self._model = None
        self._device = self._resolve_device()
        self._load_model()
    
    def _resolve_device(self) -> str:
        """Resolve device string."""
        if self.config.device != "auto":
            return self.config.device
        
        if HAS_TORCH and torch.cuda.is_available():
            return "cuda"
        elif HAS_TORCH and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    
    def _load_model(self) -> None:
        """Load the sentence-transformers model."""
        cache_dir = self.config.cache_dir
        if cache_dir:
            os.environ['SENTENCE_TRANSFORMERS_HOME'] = cache_dir
        
        self._model = SentenceTransformer(
            self.config.model_name,
            device=self._device,
        )
        
        # Update dimension from actual model
        self._dimension = self._model.get_sentence_embedding_dimension()
        self.config.dimension = self._dimension
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Embed texts using pre-trained model."""
        if isinstance(texts, str):
            texts = [texts]
        
        # Use sentence-transformers batch encoding
        embeddings = self._model.encode(
            texts,
            batch_size=self.config.batch_size,
            max_length=self.config.max_length,
            convert_to_numpy=True,
            normalize_embeddings=self.config.normalize,
            show_progress_bar=False,
        )
        
        if HAS_NUMPY:
            return embeddings.tolist()
        return [list(map(float, e)) for e in embeddings]


class CustomEmbedder(BaseEmbedder):
    """
    Custom domain-specific embedder.
    
    Supports loading fine-tuned models from local paths or
    training new embeddings on domain-specific data.
    """
    
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        
        if not config.custom_model_path:
            raise ValueError("custom_model_path required for CustomEmbedder")
        
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        
        self._model = None
        self._device = self._resolve_device()
        self._load_custom_model()
    
    def _resolve_device(self) -> str:
        """Resolve device string."""
        if self.config.device != "auto":
            return self.config.device
        
        if HAS_TORCH and torch.cuda.is_available():
            return "cuda"
        elif HAS_TORCH and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    
    def _load_custom_model(self) -> None:
        """Load custom fine-tuned model."""
        model_path = Path(self.config.custom_model_path)
        
        if not model_path.exists():
            raise FileNotFoundError(f"Custom model not found: {model_path}")
        
        # Load as sentence-transformers model
        self._model = SentenceTransformer(
            str(model_path),
            device=self._device,
        )
        
        self._dimension = self._model.get_sentence_embedding_dimension()
        self.config.dimension = self._dimension
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Embed texts using custom model."""
        if isinstance(texts, str):
            texts = [texts]
        
        embeddings = self._model.encode(
            texts,
            batch_size=self.config.batch_size,
            max_length=self.config.max_length,
            convert_to_numpy=True,
            normalize_embeddings=self.config.normalize,
            show_progress_bar=False,
        )
        
        if HAS_NUMPY:
            return embeddings.tolist()
        return [list(map(float, e)) for e in embeddings]
    
    @classmethod
    def train_from_scratch(
        cls,
        training_texts: List[str],
        base_model: str = "all-MiniLM-L6-v2",
        output_path: str = "./custom_embedder",
        epochs: int = 3,
        learning_rate: float = 2e-5,
        **kwargs
    ) -> "CustomEmbedder":
        """
        Train a custom embedder from scratch (requires sentence-transformers + torch).
        
        This is a simplified training loop - for production use,
        consider using the full sentence-transformers training pipeline.
        """
        if not HAS_SENTENCE_TRANSFORMERS or not HAS_TORCH:
            raise ImportError(
                "Training requires sentence-transformers and torch. "
                "Install with: pip install sentence-transformers torch"
            )
        
        from sentence_transformers import InputExample, losses
        from torch.utils.data import DataLoader
        
        # Load base model
        model = SentenceTransformer(base_model)
        
        # Create training examples (simplified: use texts as positive pairs)
        train_examples = []
        for i, text in enumerate(training_texts):
            # Self-supervised: text predicts itself (simplified)
            train_examples.append(InputExample(texts=[text, text], label=1.0))
        
        # DataLoader
        train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
        
        # Loss function
        train_loss = losses.MultipleNegativesRankingLoss(model)
        
        # Train
        model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=epochs,
            optimizer_params={'lr': learning_rate},
            show_progress_bar=True,
        )
        
        # Save
        os.makedirs(output_path, exist_ok=True)
        model.save(output_path)
        
        # Create config and return embedder
        config = EmbeddingConfig(
            provider=EmbeddingProvider.CUSTOM,
            custom_model_path=output_path,
            **kwargs
        )
        return cls(config)


def create_embedder(config: EmbeddingConfig) -> BaseEmbedder:
    """
    Factory function to create an embedder.
    
    Args:
        config: EmbeddingConfig with provider and model settings
        
    Returns:
        Configured embedder instance
    """
    if config.provider == EmbeddingProvider.HASH:
        return HashEmbedder(config)
    elif config.provider == EmbeddingProvider.PRETRAINED:
        return PretrainedEmbedder(config)
    elif config.provider == EmbeddingProvider.CUSTOM:
        return CustomEmbedder(config)
    else:
        raise ValueError(f"Unknown embedding provider: {config.provider}")


# Convenience function for quick embedding
def embed_texts(
    texts: Union[str, List[str]],
    model: str = "all-MiniLM-L6-v2",
    provider: EmbeddingProvider = EmbeddingProvider.PRETRAINED,
    **kwargs
) -> List[List[float]]:
    """Quick embedding without explicit config."""
    config = EmbeddingConfig(
        provider=provider,
        model_name=model,
        **kwargs
    )
    embedder = create_embedder(config)
    return embedder.embed(texts)
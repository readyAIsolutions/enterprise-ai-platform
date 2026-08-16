#!/usr/bin/env python3
"""
Semantic/Neural Compression - Meaning-Preserving Compression
=============================================================
Compresses by understanding meaning, not just syntax.
"""
import asyncio
import hashlib
import json
import time
import pickle
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import numpy as np


# Try to import ML dependencies
try:
    import torch
    import torch.nn as nn
    from transformers import AutoTokenizer, AutoModel
    from sentence_transformers import SentenceTransformer
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    HAS_ORT = False


class DomainType(Enum):
    GENERAL = "general"
    CODE = "code"
    LOGS = "logs"
    CHAT = "chat"
    DOCUMENTATION = "documentation"
    JSON = "json"
    SQL = "sql"


@dataclass
class SemanticUnit:
    """A unit of meaning"""
    text: str
    embedding: np.ndarray
    domain: DomainType
    hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "embedding": self.embedding.tolist(),
            "domain": self.domain.value,
            "hash": self.hash,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SemanticUnit':
        return cls(
            text=data["text"],
            embedding=np.array(data["embedding"]),
            domain=DomainType(data["domain"]),
            hash=data["hash"],
            metadata=data.get("metadata", {}),
        )


class EmbeddingCache:
    """LRU cache for embeddings"""
    
    def __init__(self, max_size: int = 10000, persist_path: Optional[Path] = None):
        self.max_size = max_size
        self.persist_path = persist_path
        self.cache: Dict[str, np.ndarray] = {}
        self.access_order: List[str] = []
        self.hits = 0
        self.misses = 0
        
        if persist_path and persist_path.exists():
            self.load()
    
    def get(self, text_hash: str) -> Optional[np.ndarray]:
        if text_hash in self.cache:
            self.hits += 1
            # Move to end (most recent)
            self.access_order.remove(text_hash)
            self.access_order.append(text_hash)
            return self.cache[text_hash]
        self.misses += 1
        return None
    
    def put(self, text_hash: str, embedding: np.ndarray):
        if text_hash in self.cache:
            self.access_order.remove(text_hash)
        elif len(self.cache) >= self.max_size:
            # Evict LRU
            lru = self.access_order.pop(0)
            del self.cache[lru]
        
        self.cache[text_hash] = embedding
        self.access_order.append(text_hash)
    
    def save(self):
        if self.persist_path:
            data = {
                "cache": {k: v.tolist() for k, v in self.cache.items()},
                "access_order": self.access_order,
            }
            with open(self.persist_path, 'wb') as f:
                pickle.dump(data, f)
    
    def load(self):
        if self.persist_path and self.persist_path.exists():
            with open(self.persist_path, 'rb') as f:
                data = pickle.load(f)
            self.cache = {k: np.array(v) for k, v in data["cache"].items()}
            self.access_order = data["access_order"]


class SemanticEncoder:
    """Encodes text to semantic embeddings"""
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache: Optional[EmbeddingCache] = None,
        device: Optional[str] = None,
        batch_size: int = 32,
    ):
        self.model_name = model_name
        self.cache = cache or EmbeddingCache()
        self.batch_size = batch_size
        self.model = None
        self.tokenizer = None
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._load_model()
    
    def _load_model(self):
        if not HAS_TORCH:
            raise RuntimeError("PyTorch not available")
        
        # Try to load ONNX model first (faster)
        onnx_path = Path(f"/home/hunter/Desktop/eni_compression/models/{self.model_name}.onnx")
        if HAS_ORT and onnx_path.exists():
            self.session = ort.InferenceSession(str(onnx_path))
            self.use_onnx = True
        else:
            self.use_onnx = False
            self.tokenizer = AutoTokenizer.from_pretrained(f"sentence-transformers/{self.model_name}")
            self.model = AutoModel.from_pretrained(f"sentence-transformers/{self.model_name}")
            self.model.to(self.device)
            self.model.eval()
    
    def _mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode list of texts to embeddings"""
        # Check cache
        results = []
        uncached_texts = []
        uncached_indices = []
        
        for i, text in enumerate(texts):
            text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            cached = self.cache.get(text_hash)
            if cached is not None:
                results.append(cached)
            else:
                results.append(None)
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        if uncached_texts:
            # Encode uncached
            if self.use_onnx:
                # ONNX inference
                encoded = self.tokenizer(uncached_texts, padding=True, truncation=True, return_tensors="np")
                outputs = self.session.run(None, {
                    "input_ids": encoded["input_ids"],
                    "attention_mask": encoded["attention_mask"],
                })
                embeddings = outputs[0]
                # Mean pooling
                attention_mask = encoded["attention_mask"]
                embeddings = np.sum(embeddings * attention_mask[:, :, np.newaxis], axis=1) / np.clip(np.sum(attention_mask, axis=1, keepdims=True), 1e-9, None)
            else:
                # PyTorch inference
                encoded = self.tokenizer(uncached_texts, padding=True, truncation=True, return_tensors="pt", max_length=512)
                encoded = {k: v.to(self.device) for k, v in encoded.items()}
                
                with torch.no_grad():
                    model_output = self.model(**encoded)
                    embeddings = self._mean_pooling(model_output, encoded["attention_mask"])
                    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                    embeddings = embeddings.cpu().numpy()
            
            # Cache and fill results
            for idx, embedding in zip(uncached_indices, embeddings):
                text_hash = hashlib.sha256(texts[idx].encode()).hexdigest()[:16]
                self.cache.put(text_hash, embedding)
                results[idx] = embedding
        
        return np.array(results)
    
    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


class SemanticDeduplicator:
    """Deduplicates semantically similar content"""
    
    def __init__(
        self,
        encoder: SemanticEncoder,
        similarity_threshold: float = 0.92,
        min_length: int = 20,
    ):
        self.encoder = encoder
        self.similarity_threshold = similarity_threshold
        self.min_length = min_length
        self.index: List[SemanticUnit] = []
        self.index_embeddings: Optional[np.ndarray] = None
    
    def add(self, text: str, domain: DomainType = DomainType.GENERAL, metadata: Optional[Dict] = None) -> str:
        """Add text to index, return hash if duplicate"""
        if len(text) < self.min_length:
            return None
        
        embedding = self.encoder.encode_single(text)
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        
        # Check for duplicates
        if self.index_embeddings is not None:
            similarities = np.dot(self.index_embeddings, embedding)
            max_sim_idx = np.argmax(similarities)
            max_sim = similarities[max_sim_idx]
            
            if max_sim >= self.similarity_threshold:
                # Duplicate found
                return self.index[max_sim_idx].hash
        
        # Add to index
        unit = SemanticUnit(
            text=text,
            embedding=embedding,
            domain=domain,
            hash=text_hash,
            metadata=metadata or {},
        )
        self.index.append(unit)
        self._rebuild_index()
        
        return None
    
    def _rebuild_index(self):
        if self.index:
            self.index_embeddings = np.array([u.embedding for u in self.index])
        else:
            self.index_embeddings = None
    
    def find_similar(self, text: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        """Find similar texts in index"""
        if not self.index:
            return []
        
        embedding = self.encoder.encode_single(text)
        similarities = np.dot(self.index_embeddings, embedding)
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        return [
            (self.index[i].hash, float(similarities[i]), self.index[i].text[:100])
            for i in top_indices
        ]


class NeuralCompressor:
    """Neural network based compressor for specific domains"""
    
    def __init__(self, domain: DomainType):
        self.domain = domain
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
    
    def load_model(self, model_path: str):
        """Load domain-specific compression model"""
        # Placeholder for domain-specific models
        # Could load CodeBERT for code, DistilBERT for logs, etc.
        pass
    
    def compress(self, text: str) -> Tuple[bytes, Dict]:
        """Compress using neural model"""
        # Placeholder: would use seq2seq model to generate compressed representation
        return text.encode(), {"method": "neural_placeholder"}
    
    def decompress(self, data: bytes, metadata: Dict) -> str:
        """Decompress neural representation"""
        return data.decode()


class MeaningVerifier:
    """Verifies that compression preserves meaning"""
    
    def __init__(self, encoder: SemanticEncoder, threshold: float = 0.85):
        self.encoder = encoder
        self.threshold = threshold
    
    def verify(self, original: str, reconstructed: str) -> Tuple[bool, float]:
        """Verify semantic similarity between original and reconstructed"""
        if not original or not reconstructed:
            return False, 0.0
        
        orig_emb = self.encoder.encode_single(original)
        recon_emb = self.encoder.encode_single(reconstructed)
        
        similarity = float(np.dot(orig_emb, recon_emb) / (np.linalg.norm(orig_emb) * np.linalg.norm(recon_emb)))
        
        return similarity >= self.threshold, similarity
    
    def verify_batch(self, originals: List[str], reconstructed: List[str]) -> List[Tuple[bool, float]]:
        if len(originals) != len(reconstructed):
            raise ValueError("Length mismatch")
        
        orig_embs = self.encoder.encode(originals)
        recon_embs = self.encoder.encode(reconstructed)
        
        similarities = np.sum(orig_embs * recon_embs, axis=1) / (
            np.linalg.norm(orig_embs, axis=1) * np.linalg.norm(recon_embs, axis=1)
        )
        
        return [(sim >= self.threshold, float(sim)) for sim in similarities]


class DomainAdapter:
    """Adapts compression for specific domains"""
    
    ADAPTERS: Dict[DomainType, Dict] = {
        DomainType.CODE: {
            "segmenters": ["function", "class", "block"],
            "preserve": ["keywords", "identifiers", "structure"],
            "semantic_weight": 0.8,
        },
        DomainType.LOGS: {
            "segmenters": ["timestamp", "level", "message"],
            "preserve": ["timestamps", "errors", "ids"],
            "semantic_weight": 0.6,
        },
        DomainType.JSON: {
            "segmenters": ["object", "array", "key_value"],
            "preserve": ["keys", "structure", "types"],
            "semantic_weight": 0.9,
        },
        DomainType.CHAT: {
            "segmenters": ["turn", "speaker", "topic"],
            "preserve": ["entities", "intent", "sentiment"],
            "semantic_weight": 0.7,
        },
    }
    
    @classmethod
    def get_config(cls, domain: DomainType) -> Dict:
        return cls.ADAPTERS.get(domain, {
            "segmenters": ["sentence"],
            "preserve": ["entities"],
            "semantic_weight": 0.5,
        })


class SemanticCompressor:
    """Main semantic compression pipeline"""
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        similarity_threshold: float = 0.92,
        meaning_threshold: float = 0.85,
        cache_size: int = 10000,
    ):
        self.encoder = SemanticEncoder(model_name, cache=EmbeddingCache(max_size=cache_size))
        self.deduplicator = SemanticDeduplicator(self.encoder, similarity_threshold)
        self.meaning_verifier = MeaningVerifier(self.encoder, meaning_threshold)
        self.neural_compressors: Dict[DomainType, NeuralCompressor] = {}
    
    def detect_domain(self, text: str) -> DomainType:
        """Simple domain detection"""
        text_lower = text.lower()
        
        if any(kw in text_lower for kw in ["def ", "class ", "import ", "function", "const ", "let ", "var "]):
            return DomainType.CODE
        elif any(kw in text_lower for kw in ["error", "warning", "info", "debug", "traceback", "exception"]):
            return DomainType.LOGS
        elif text.strip().startswith("{") or text.strip().startswith("["):
            return DomainType.JSON
        elif ":" in text and any(kw in text_lower for kw in ["user:", "assistant:", "human:", "bot:"]):
            return DomainType.CHAT
        elif any(kw in text_lower for kw in ["select ", "insert ", "update ", "delete ", "from ", "where "]):
            return DomainType.SQL
        return DomainType.GENERAL
    
    def compress(
        self,
        text: str,
        domain: Optional[DomainType] = None,
        verify_meaning: bool = True,
    ) -> Dict[str, Any]:
        """Compress text with semantic understanding"""
        if domain is None:
            domain = self.detect_domain(text)
        
        config = DomainAdapter.get_config(domain)
        semantic_weight = config["semantic_weight"]
        
        # Step 1: Semantic deduplication
        duplicate_hash = self.deduplicator.add(text, domain)
        
        if duplicate_hash:
            return {
                "method": "semantic_dedup",
                "reference": duplicate_hash,
                "domain": domain.value,
                "original_length": len(text),
                "compressed_length": len(duplicate_hash) + 10,  # overhead
            }
        
        # Step 2: Domain-specific preprocessing
        segments = self._segment(text, domain)
        
        # Step 3: Neural compression (if available)
        neural_result = None
        if domain in self.neural_compressors:
            neural_result = self.neural_compressors[domain].compress(text)
        
        # Step 4: Semantic representation
        embedding = self.encoder.encode_single(text)
        
        # Combine: use embedding as compressed representation
        # In practice, would quantize embedding
        compressed_data = {
            "embedding": embedding.tolist(),
            "segments": segments,
            "domain": domain.value,
            "semantic_weight": semantic_weight,
            "neural_result": neural_result,
        }
        
        compressed_bytes = json.dumps(compressed_data).encode()
        
        # Step 5: Verify meaning preservation
        meaning_verified = True
        similarity = 1.0
        if verify_meaning:
            # Reconstruct from embedding (approximate)
            reconstructed = self._reconstruct_from_embedding(embedding, domain)
            meaning_verified, similarity = self.meaning_verifier.verify(text, reconstructed)
        
        return {
            "method": "semantic",
            "data": compressed_data,
            "compressed_bytes": compressed_bytes,
            "original_length": len(text),
            "compressed_length": len(compressed_bytes),
            "ratio": len(text) / len(compressed_bytes) if compressed_bytes else 1.0,
            "domain": domain.value,
            "meaning_verified": meaning_verified,
            "similarity": similarity,
            "duplicate_hash": duplicate_hash,
        }
    
    def decompress(self, compressed_data: Dict) -> str:
        """Decompress from semantic representation"""
        method = compressed_data.get("method", "semantic")
        
        if method == "semantic_dedup":
            # Would lookup reference
            return f"[REFERENCE: {compressed_data['reference']}]"
        
        data = compressed_data.get("data", {})
        
        if "neural_result" in data and data["neural_result"]:
            # Neural decompression
            neural_comp = self.neural_compressors.get(DomainType(data["domain"]))
            if neural_comp:
                return neural_comp.decompress(data["neural_result"][0], data["neural_result"][1])
        
        # Fallback: reconstruct from embedding
        return self._reconstruct_from_embedding(
            np.array(data["embedding"]), 
            DomainType(data["domain"])
        )
    
    def _segment(self, text: str, domain: DomainType) -> List[str]:
        """Segment text based on domain"""
        config = DomainAdapter.get_config(domain)
        
        if domain == DomainType.CODE:
            # Split by functions/classes
            import re
            return re.split(r'\n\s*(?:def |class |function )', text)
        elif domain == DomainType.LOGS:
            # Split by lines
            return text.split('\n')
        elif domain == DomainType.JSON:
            # Keep as single unit
            return [text]
        else:
            # Sentence splitting
            import re
            return re.split(r'(?<=[.!?])\s+', text)
    
    def _reconstruct_from_embedding(self, embedding: np.ndarray, domain: DomainType) -> str:
        """Approximate reconstruction from embedding"""
        # In practice, would use a decoder model
        # For now, return placeholder
        return f"[SEMANTIC RECONSTRUCTION: domain={domain.value}, embedding_dim={len(embedding)}]"


async def demo():
    """Demo semantic compression"""
    compressor = SemanticCompressor()
    
    test_texts = [
        "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
        "ERROR 2024-01-15 10:30:45 Connection timeout to database server",
        '{"user_id": 12345, "action": "login", "timestamp": "2024-01-15T10:30:45Z"}',
        "User: Hello, how are you?\nAssistant: I'm doing well, thank you!",
    ]
    
    print("=== Semantic Compression Demo ===\n")
    
    for text in test_texts:
        result = compressor.compress(text)
        print(f"Domain: {result['domain']}")
        print(f"Method: {result['method']}")
        print(f"Ratio: {result['ratio']:.2f}x")
        print(f"Meaning verified: {result['meaning_verified']} (sim={result['similarity']:.3f})")
        print(f"Original: {len(text)} bytes -> Compressed: {result['compressed_length']} bytes")
        print("-" * 50)
    
    # Test deduplication
    print("\n=== Deduplication Test ===")
    text1 = "This is a test message for deduplication purposes."
    text2 = "This is a test message for deduplication purposes."  # Exact duplicate
    text3 = "This is a test message for dedup purposes."  # Near duplicate
    
    r1 = compressor.compress(text1)
    r2 = compressor.compress(text2)
    r3 = compressor.compress(text3)
    
    print(f"Text 1: {r1['method']} (hash={r1.get('duplicate_hash')})")
    print(f"Text 2: {r2['method']} (ref={r2.get('reference')})")
    print(f"Text 3: {r3['method']} (ref={r3.get('reference')})")


if __name__ == "__main__":
    asyncio.run(demo())
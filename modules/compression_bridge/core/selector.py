"""
Adaptive Compressor Selector - ML-based algorithm selection
"""
import json
import hashlib
import pickle
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import Counter
import numpy as np

from .engine import CompressionMode


class AdaptiveCompressorSelector:
    """ML-based compressor selection based on data characteristics"""
    
    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or Path("/home/hunter/Desktop/eni_compression/models/selector_model.pkl")
        self.model = None
        self.feature_history: List[Dict] = []
        self.performance_history: List[Dict] = []
        self._load_or_train()
    
    def _load_or_train(self):
        """Load existing model or train initial one"""
        if self.model_path.exists():
            try:
                with open(self.model_path, 'rb') as f:
                    self.model = pickle.load(f)
                return
            except Exception:
                pass
        
        # Train initial model with heuristics
        self._train_heuristic_model()
    
    def _train_heuristic_model(self):
        """Train simple heuristic-based model"""
        # Simple decision tree based on data characteristics
        self.model = {
            "type": "heuristic",
            "rules": [
                # (condition_function, mode)
                (lambda f: f["is_json"] and f["size"] > 1000, CompressionMode.LLM_OPTIMIZED),
                (lambda f: f["is_code"] and f["size"] > 500, CompressionMode.CODE_AWARE),
                (lambda f: f["entropy"] > 7.5, CompressionMode.FAST),  # Already compressed
                (lambda f: f["size"] < 100, CompressionMode.FAST),
                (lambda f: f["repeated_patterns"] > 0.3, CompressionMode.BALANCED),
                (lambda f: f["size"] > 10000, CompressionMode.BALANCED),
                (lambda f: True, CompressionMode.MAXIMUM),  # Default: best ratio
            ]
        }
    
    def extract_features(self, data: bytes) -> Dict[str, Any]:
        """Extract features from data for algorithm selection"""
        text = data.decode('utf-8', errors='ignore')
        size = len(data)
        
        # Basic features
        features = {
            "size": size,
            "entropy": self._calculate_entropy(data),
            "is_json": self._is_json(text),
            "is_code": self._is_code(text),
            "repeated_patterns": self._count_repeated_patterns(text),
            "unique_bytes": len(set(data)),
            "has_newlines": b'\n' in data,
            "avg_line_length": np.mean([len(l) for l in text.split('\n')]) if '\n' in text else size,
        }
        
        # N-gram features for text
        if features["is_json"] or features["is_code"]:
            features["structure_depth"] = self._estimate_structure_depth(text)
        
        return features
    
    def _calculate_entropy(self, data: bytes) -> float:
        """Calculate Shannon entropy"""
        if not data:
            return 0
        counts = Counter(data)
        probs = [c / len(data) for c in counts.values()]
        return -sum(p * np.log2(p) for p in probs)
    
    def _is_json(self, text: str) -> bool:
        """Check if text is valid JSON"""
        try:
            import json
            json.loads(text)
            return True
        except Exception:
            return False
    
    def _is_code(self, text: str) -> bool:
        """Heuristic: check if text looks like code"""
        code_indicators = [
            'def ', 'class ', 'import ', 'function ', 'const ', 'let ', 'var ',
            'if (', 'for (', 'while (', 'return ', 'public ', 'private ',
            'fn ', 'struct ', 'impl ', 'async ', 'await ', '#include',
        ]
        text_lower = text.lower()
        return sum(1 for ind in code_indicators if ind in text_lower) >= 2
    
    def _count_repeated_patterns(self, text: str) -> float:
        """Estimate repeated pattern ratio"""
        if len(text) < 100:
            return 0
        # Sample substrings
        substrings = [text[i:i+20] for i in range(0, min(len(text)-20, 1000), 50)]
        if not substrings:
            return 0
        unique = len(set(substrings))
        return 1 - (unique / len(substrings))
    
    def _estimate_structure_depth(self, text: str) -> int:
        """Estimate nesting depth for structured data"""
        depth = 0
        max_depth = 0
        for ch in text:
            if ch in '{[(':
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch in '}])':
                depth = max(0, depth - 1)
        return max_depth
    
    def select(self, data: bytes) -> CompressionMode:
        """Select best compression mode for data"""
        features = self.extract_features(data)
        
        # Apply heuristic rules
        if isinstance(self.model, dict) and self.model.get("type") == "heuristic":
            for condition, mode in self.model["rules"]:
                if condition(features):
                    self._record_selection(features, mode)
                    return mode
        
        # Fallback
        self._record_selection(features, CompressionMode.MAXIMUM)
        return CompressionMode.MAXIMUM
    
    def _record_selection(self, features: Dict, mode: CompressionMode):
        """Record selection for learning"""
        self.feature_history.append(features)
        self.performance_history.append({
            "mode": mode.value,
            "features": features,
        })
        
        # Keep last 1000
        if len(self.feature_history) > 1000:
            self.feature_history = self.feature_history[-1000:]
            self.performance_history = self.performance_history[-1000:]
    
    def record_performance(self, features: Dict, mode: CompressionMode, 
                          ratio: float, speed_mbps: float):
        """Record actual performance for model improvement"""
        # Could implement online learning here
        pass
    
    def save_model(self):
        """Save model to disk"""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
        except Exception:
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get selector statistics"""
        mode_counts = Counter(p["mode"] for p in self.performance_history)
        return {
            "total_selections": len(self.performance_history),
            "mode_distribution": dict(mode_counts),
            "model_type": self.model.get("type", "unknown") if isinstance(self.model, dict) else "pickled",
        }
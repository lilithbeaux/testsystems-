#!/usr/bin/env python3
"""
VSA (HRR) Memory Wrapper
Encodes and retrieves information using hyperdimensional vectors.
"""
import numpy as np
from typing import Any, Dict, Optional, Tuple

class VSAMemory:
    """
    Hyperdimensional memory using Holographic Reduced Representations.
    """

    def __init__(self, dimension: int = 1000):
        """
        Initialize with a given vector dimension.
        """
        self.dimension = dimension
        self._vectors = {}  # key -> vector
        self._items = {}    # key -> decoded data (optional)
        self._init_hrr()

    def _init_hrr(self) -> None:
        """Initialize the HRR library."""
        try:
            from hrr import HRR
            self.HRR = HRR
            self._hrr_available = True
        except ImportError:
            print("Warning: hrr library not installed. Using fallback numpy-based HRR.")
            self._hrr_available = False

    def _random_vector(self) -> np.ndarray:
        """Generate a random unit vector."""
        if self._hrr_available:
            return self.HRR.random(self.dimension)  # returns an HRR object, convert to array
        else:
            vec = np.random.randn(self.dimension)
            return vec / np.linalg.norm(vec)

    def encode(self, key: str, data: Any) -> None:
        """
        Encode arbitrary data into a vector and store it.
        Uses a simple bundle-similarity approach: if data is numeric, treat as vector.
        For strings, we use a pseudo-encoding (hash to vector).
        """
        if isinstance(data, (int, float)):
            # Map scalar to vector via random projection (simplistic)
            vec = self._random_vector() * data
        elif isinstance(data, np.ndarray):
            if len(data) == self.dimension:
                norm = np.linalg.norm(data)
                vec = data / norm if norm > 0 else np.zeros(self.dimension)
            else:
                # Resize or pad
                vec = np.resize(data, self.dimension)
                vec = vec / np.linalg.norm(vec)
        else:
            # For other types, use a deterministic hash to seed random vector
            hash_val = hash(str(data)) & 0xFFFFFFFF
            np.random.seed(hash_val)
            vec = np.random.randn(self.dimension)
            vec = vec / np.linalg.norm(vec)
            np.random.seed()  # reset seed

        self._vectors[key] = vec
        self._items[key] = data

    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve the stored data by key."""
        return self._items.get(key)

    def similarity(self, key1: str, key2: str) -> float:
        """Cosine similarity between two stored vectors."""
        if key1 not in self._vectors or key2 not in self._vectors:
            return 0.0
        v1 = self._vectors[key1]
        v2 = self._vectors[key2]
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

    def associative_recall(self, query_vector: np.ndarray, top_k: int = 3) -> Dict[str, float]:
        """
        Find stored keys whose vectors are most similar to the query.
        """
        similarities = {}
        for key, vec in self._vectors.items():
            sim = np.dot(query_vector, vec) / (np.linalg.norm(query_vector) * np.linalg.norm(vec))
            similarities[key] = sim
        sorted_items = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_items[:top_k])

#!/usr/bin/env python3
"""
Integration Layer
Orchestrates MemGPT, Reservoir, and VSA memory for a unified cognitive loop.
Auto-persists to ZODB every N calls. Auto-restores from ZODB on init.
"""
import numpy as np
import os, sys, pathlib, types
from typing import Dict, Any, Optional, List
from .memgpt_agent import MemGPTAgent
from .reservoir_computer import ReservoirComputer
from .vsa_memory import VSAMemory

# ── Lazy persistence bridge ──
_PERSIST_MODULE = None
def _get_persister():
    global _PERSIST_MODULE
    if _PERSIST_MODULE is None:
        p = pathlib.Path.home() / '.local' / 'bin' / 'sms-persist-bridge'
        if p.exists():
            _PERSIST_MODULE = types.ModuleType('sms_persist_bridge')
            try:
                exec(p.read_text(), _PERSIST_MODULE.__dict__)
            except Exception:
                _PERSIST_MODULE = None
    return _PERSIST_MODULE


class SovereignMemoryIntegration:
    """
    Combines the three memory paradigms into one operational node.
    Auto-persists to ZODB every `persist_interval` calls.
    Auto-restores from ZODB on init.
    """

    def __init__(self, 
                 memgpt_config: Optional[str] = None,
                 reservoir_input_size: int = 10,
                 reservoir_size: int = 100,
                 vsa_dimension: int = 1000,
                 persist_interval: int = 10):
        self.memgpt = MemGPTAgent(config_path=memgpt_config)
        self.reservoir = ReservoirComputer(input_size=reservoir_input_size, 
                                           reservoir_size=reservoir_size)
        self.vsa = VSAMemory(dimension=vsa_dimension)

        self.conversation_history = []
        self.state_vector = np.zeros(reservoir_input_size)
        self._persist_interval = persist_interval
        self._persist_count = 0
        self._persister = None

        self._try_restore()

    def _try_restore(self):
        mod = _get_persister()
        if mod is None:
            return
        try:
            p = mod.SMSMemoryPersister(self)
            restored = p.restore_vsa_vectors(self.vsa)
            if restored:
                print(f"♻️  Restored {restored} VSA vectors from persistent store")
            p.close()
        except Exception:
            pass

    def persist(self):
        """Persist current VSA state to ZODB."""
        mod = _get_persister()
        if mod is None:
            return 0
        try:
            if self._persister is None:
                self._persister = mod.SMSMemoryPersister(self)
            n = self._persister.persist_vsa_state(self.vsa)
            return n
        except Exception:
            return 0

    def process_input(self, user_message: str, user_id: str = "default") -> Dict[str, Any]:
        memgpt_result = self.memgpt.send_message(user_message, user_id)
        if "error" in memgpt_result:
            return {"error": f"MemGPT error: {memgpt_result['error']}"}

        response_text = memgpt_result.get("response", "")
        memory_state = memgpt_result.get("memory", {})

        # Reservoir prediction
        feature_vec = self._encode_message(user_message, self.reservoir.input_size)
        reservoir_prediction = self.reservoir.predict(feature_vec.reshape(1, -1))

        # Accumulate for batch training
        if not hasattr(self, '_reservoir_buffer_X'):
            self._reservoir_buffer_X = []
            self._reservoir_buffer_y = []
        self._reservoir_buffer_X.append(feature_vec)
        self._reservoir_buffer_y.append(reservoir_prediction.flatten())
        if len(self._reservoir_buffer_X) > 100:
            self.reservoir.fit(np.array(self._reservoir_buffer_X), 
                               np.array(self._reservoir_buffer_y))
            self._reservoir_buffer_X = []
            self._reservoir_buffer_y = []

        # VSA memory storage
        self.vsa.encode(f"msg_{len(self.conversation_history)}", response_text)
        mem_values = list(memory_state.values()) if memory_state else []
        if not mem_values:
            mem_values = [0.0] * 5
        combined_state = np.concatenate([np.array(mem_values, dtype=float),
                                         reservoir_prediction.flatten()])
        if len(combined_state) >= self.vsa.dimension:
            combined_state = combined_state[:self.vsa.dimension]
        else:
            combined_state = np.pad(combined_state, (0, self.vsa.dimension - len(combined_state)))
        self.vsa.encode("state_latest", combined_state)

        self.conversation_history.append(user_message)

        # Auto-persist every N calls
        self._persist_count += 1
        if self._persist_count >= self._persist_interval:
            saved = self.persist()
            if saved:
                print(f"💾 Auto-persisted {saved} vectors")
            self._persist_count = 0

        return {
            "response": response_text,
            "reservoir_prediction": reservoir_prediction.tolist(),
            "vsa_similarity": self._compute_similarities(response_text),
            "memgpt_memory": memory_state
        }

    def _encode_message(self, message: str, input_size: int) -> np.ndarray:
        vec = np.zeros(input_size)
        for word in message.split():
            idx = hash(word) & 0xFFFFFFFF % input_size
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def _compute_similarities(self, text: str) -> Dict[str, float]:
        query_vec = self._encode_message(text, self.vsa.dimension)
        return self.vsa.associative_recall(query_vec, top_k=3)

#!/usr/bin/env python3
"""
MemGPT Agent Wrapper
Manages conversation, memory tiers, and self-editing.
"""
import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class MemGPTAgent:
    """Wrapper for MemGPT's core functionality."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize MemGPT agent.
        If config_path is None, tries to load from env or defaults.
        """
        self.config_path = config_path or os.getenv("MEMGPT_CONFIG_PATH")
        self.agent = None
        self._initialize_agent()

    def _initialize_agent(self) -> None:
        """Lazy import and create the MemGPT agent."""
        try:
            # memgpt package structure varies by version; try known import paths
            try:
                from memgpt import Agent as MemGPTAgentClass
                from memgpt.config import AgentConfig
            except ImportError:
                # Fallback: memgpt 0.2.0+ has different structure
                import memgpt
                # Check if there's an Agent class anywhere in the package
                for attr in ['Agent', 'agent', 'core', 'client']:
                    if hasattr(memgpt, attr):
                        MemGPTAgentClass = getattr(memgpt, attr)
                        break
                else:
                    raise ImportError("No MemGPT Agent class found")
                AgentConfig = object  # dummy

            if self.config_path:
                with open(self.config_path, 'r') as f:
                    config_dict = json.load(f)
                config = AgentConfig(**config_dict)
            else:
                config = AgentConfig()  # default
            self.agent = MemGPTAgentClass(config)
            self._available = True
        except Exception as e:
            self._available = False
            self.agent = None
            print(f"ℹ️  MemGPT not fully available ({e}). Using fallback mode.")

    def send_message(self, message: str, user_id: str = "default") -> Dict[str, Any]:
        """Send a user message to the agent and get a response."""
        if not self._available or self.agent is None:
            return {"response": f"[MemGPT fallback] Processed: {message[:80]}...",
                    "memory": {}}
        # MemGPT API: step() or send_message() depending on version
        # Assuming latest API: agent.send_message(user_id, message)
        try:
            response = self.agent.send_message(user_id, message)
            return {"response": response, "memory": self.agent.memory}
        except AttributeError:
            # Fallback for older API: use step()
            response = self.agent.step(user_id, message)
            return {"response": response, "memory": self.agent.memory}
        except Exception as e:
            return {"error": str(e)}

    def get_memory(self) -> Dict[str, Any]:
        """Return current memory state."""
        return self.agent.memory if (self.agent and self._available) else {}

    def update_memory(self, key: str, value: Any) -> None:
        """Edit a specific memory slot."""
        if not self._available or not self.agent:
            return
        if self.agent and hasattr(self.agent, "update_memory"):
            self.agent.update_memory(key, value)
        else:
            # Fallback: modify memory dict directly
            self.agent.memory[key] = value

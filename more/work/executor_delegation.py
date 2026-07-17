"""
executor_delegation.py — Multi-Model Delegation Infrastructure
==============================================================

Routes tasks to optimal executor model via OpenRouter free tier.

Executors:
  1. Nemotron 3 Ultra 550B (nvidia/nemotron-3-ultra-550b-a55b:free) — Deep reasoning, architecture, audit
  2. Nemotron 3 Nano Omni 30B (nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free) — Vision + fast execution
  3. Nemotron 3 Nano 30B (nvidia/nemotron-3-nano-30b-a3b:free) — Fast execution, reasoning
  4. Nemotron 3 Super 120B (nvidia/nemotron-3-super-120b-a12b:free) — Balanced reasoning
  5. Qwen3-Coder-Next 80B (qwen/qwen3-coder-next:free) — Code generation, patching, refactoring
  6. Qwen3-Coder 30B (qwen/qwen3-coder-30b-a3b-instruct:free) — Code generation
  7. DeepSeek R1 (deepseek/deepseek-r1) — Deep reasoning (very cheap)
  8. DeepSeek V3.1 (deepseek/deepseek-v3.1-terminus) — Deep reasoning

All via OpenRouter free tier.
"""

import os
import json
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

# ─── Configuration ───
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ─── Executor Models (All Free Tier) ───
class ExecutorModel(Enum):
    NEMOTRON_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b:free"
    NEMOTRON_NANO_OMNI = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    NEMOTRON_NANO = "nvidia/nemotron-3-nano-30b-a3b:free"
    NEMOTRON_SUPER = "nvidia/nemotron-3-super-120b-a12b:free"
    QWEN_CODER_NEXT = "qwen/qwen3-coder:free"
    QWEN_CODER = "qwen/qwen3-coder:free"
    QWEN_CODER_PLUS = "qwen/qwen3-coder-plus:free"
    QWEN_CODER_30B = "qwen/qwen3-coder-30b-a3b-instruct:free"
    DEEPSEEK_R1 = "deepseek/deepseek-r1"
    DEEPSEEK_V3 = "deepseek/deepseek-v3.1-terminus"

@dataclass
class ExecutorProfile:
    model: ExecutorModel
    name: str
    strengths: List[str]
    context_window: int
    best_for: List[str]
    temperature_default: float = 0.7
    top_p_default: float = 0.9

EXECUTOR_PROFILES = {
    ExecutorModel.NEMOTRON_ULTRA: ExecutorProfile(
        model=ExecutorModel.NEMOTRON_ULTRA,
        name="Nemotron 3 Ultra 550B",
        strengths=["deep_reasoning", "architecture", "audit", "complex_analysis", "multi_step_planning"],
        context_window=1000000,
        best_for=["audit", "architecture", "complex_reasoning", "multi_turn_planning", "token_burn_analysis"],
        temperature_default=0.5,
        top_p_default=0.8,
    ),
    ExecutorModel.NEMOTRON_NANO_OMNI: ExecutorProfile(
        model=ExecutorModel.NEMOTRON_NANO_OMNI,
        name="Nemotron 3 Nano Omni 30B",
        strengths=["vision", "fast_execution", "reasoning", "ui_analysis", "screenshot_analysis"],
        context_window=256000,
        best_for=["cef_screenshots", "vision_tasks", "ui_analysis", "fast_code", "dom_extraction"],
        temperature_default=0.6,
        top_p_default=0.85,
    ),
    ExecutorModel.NEMOTRON_NANO: ExecutorProfile(
        model=ExecutorModel.NEMOTRON_NANO,
        name="Nemotron 3 Nano 30B",
        strengths=["fast_execution", "reasoning", "code_generation"],
        context_window=256000,
        best_for=["quick_fixes", "code_snippets", "reasoning_tasks"],
        temperature_default=0.5,
        top_p_default=0.85,
    ),
    ExecutorModel.NEMOTRON_SUPER: ExecutorProfile(
        model=ExecutorModel.NEMOTRON_SUPER,
        name="Nemotron 3 Super 120B",
        strengths=["balanced_reasoning", "coding", "analysis"],
        context_window=256000,
        best_for=["general_reasoning", "coding", "medium_complexity"],
        temperature_default=0.6,
        top_p_default=0.9,
    ),
    ExecutorModel.QWEN_CODER_NEXT: ExecutorProfile(
        model=ExecutorModel.QWEN_CODER_NEXT,
        name="Qwen3-Coder-Next 80B",
        strengths=["code_generation", "refactoring", "patching", "tool_building", "multi_file_edits"],
        context_window=131072,
        best_for=["code_generation", "patching", "refactoring", "tool_building", "multi_file_edits"],
        temperature_default=0.4,
        top_p_default=0.8,
    ),
    ExecutorModel.QWEN_CODER: ExecutorProfile(
        model=ExecutorModel.QWEN_CODER,
        name="Qwen3-Coder 30B",
        strengths=["code_generation", "refactoring", "patching"],
        context_window=131072,
        best_for=["code_generation", "patching", "refactoring"],
        temperature_default=0.4,
        top_p_default=0.8,
    ),
    ExecutorModel.QWEN_CODER_PLUS: ExecutorProfile(
        model=ExecutorModel.QWEN_CODER_PLUS,
        name="Qwen3-Coder-Plus",
        strengths=["code_generation", "refactoring", "tool_building"],
        context_window=131072,
        best_for=["code_generation", "refactoring", "tool_building"],
        temperature_default=0.4,
        top_p_default=0.8,
    ),
    ExecutorModel.QWEN_CODER_30B: ExecutorProfile(
        model=ExecutorModel.QWEN_CODER_30B,
        name="Qwen3-Coder 30B",
        strengths=["code_generation", "refactoring", "patching"],
        context_window=131072,
        best_for=["code_generation", "patching", "refactoring"],
        temperature_default=0.4,
        top_p_default=0.8,
    ),
}

# ─── Task Router ───
TASK_ROUTING = {
    # Deep reasoning / architecture / audit
    "audit": "NEMOTRON_ULTRA",
    "architecture": "NEMOTRON_ULTRA",
    "token_analysis": "NEMOTRON_ULTRA",
    "complex_reasoning": "NEMOTRON_ULTRA",
    "multi_step_planning": "NEMOTRON_ULTRA",
    
    # Vision / CEF / screenshots / UI
    "cef_screenshot": "NEMOTRON_NANO_OMNI",
    "vision_analysis": "NEMOTRON_NANO_OMNI",
    "ui_analysis": "NEMOTRON_NANO_OMNI",
    "dom_extraction": "NEMOTRON_NANO_OMNI",
    "vision_pipeline": "NEMOTRON_NANO_OMNI",
    
    # Code generation / patching / refactoring
    "code_generation": "QWEN_CODER_NEXT",
    "patching": "QWEN_CODER_NEXT",
    "refactoring": "QWEN_CODER_NEXT",
    "tool_building": "QWEN_CODER_NEXT",
    "multi_file_edits": "QWEN_CODER_NEXT",
    "cef_patch": "QWEN_CODER_NEXT",
    "mcp_tool": "QWEN_CODER_NEXT",
    
    # Fast execution / reasoning
    "quick_fix": "NEMOTRON_NANO",
    "reasoning_task": "NEMOTRON_NANO",
    "code_snippet": "NEMOTRON_NANO",
    
    # General balanced
    "general_reasoning": "NEMOTRON_SUPER",
    "medium_complexity": "NEMOTRON_SUPER",
}

# ─── OpenRouter Client ───
class OpenRouterClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://thotheauphis.local",
            "X-Title": "Thotheauphis Executor Delegation",
        })
    
    def complete(self, 
                 model: str,
                 messages: List[Dict[str, str]],
                 temperature: float = None,
                 top_p: float = None,
                 max_tokens: int = 8192,
                 stream: bool = False) -> Dict[str, Any]:
        """Call OpenRouter completion API."""
        profile = None
        for profile_obj in EXECUTOR_PROFILES.values():
            if profile_obj.model.value == model:
                profile = profile_obj
                break
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature if temperature is not None else (profile.temperature_default if profile else 0.7),
            "top_p": top_p if top_p is not None else (profile.top_p_default if profile else 0.9),
            "stream": stream,
        }
        
        response = self.session.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

# ─── Delegation Functions ───
def delegate_task(task_type: str, 
                  prompt: str, 
                  context: Dict[str, Any] = None,
                  model: str = None,
                  temperature: float = None,
                  max_tokens: int = 8192) -> Dict[str, Any]:
    """
    Delegate a task to the optimal executor model.
    
    Args:
        task_type: Type of task (audit, vision_analysis, code_generation, etc.)
        prompt: The task prompt/instruction
        context: Additional context dict (will be serialized)
        model: Override auto-routing with specific model
        temperature: Override temperature
        max_tokens: Max tokens in response
    
    Returns:
        Dict with 'content', 'model_used', 'tokens_used', 'cost'
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return {"error": "OPENROUTER_API_KEY not set in environment"}
    
    client = OpenRouterClient()
    
    # Determine model
    if model is None:
        model_key = TASK_ROUTING.get(task_type, "NEMOTRON_SUPER")
        model = getattr(__import__(__name__), 'ExecutorModel')[model_key].value
    else:
        model = model
    
    # Get profile
    profile = None
    for p in EXECUTOR_PROFILES.values():
        if p.model.value == model:
            profile = p
            break
    
    # Build messages
    system_prompt = f"""You are an expert AI executor.
Execute the task with precision. Return only the requested output format.
Be concise but complete. Use glyphic/alchemical notation where appropriate."""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    
    if context:
        context_msg = f"\n\n[CONTEXT]\n{json.dumps(context, indent=2)}"
        messages[-1]["content"] += context_msg
    
    # Call API
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://thotheauphis.local",
            "X-Title": "Thotheauphis Executor Delegation",
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt + (f"\n\n[CONTEXT]\n{json.dumps(context, indent=2)}" if context else "")}
            ],
            "max_tokens": 8192,
            "temperature": 0.6,
            "top_p": 0.85,
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        
        return {
            "content": content,
            "model_used": model,
            "tokens_prompt": usage.get("prompt_tokens", 0),
            "tokens_completion": usage.get("completion_tokens", 0),
            "tokens_total": usage.get("total_tokens", 0),
            "cost_usd": 0.0,
        }
    except Exception as e:
        return {"error": str(e), "model": model}

# ─── Slash Command Interface ───
def slash_delegate(args: str) -> str:
    """Parse: /delegate [task_type] "prompt" [--model name] [--temp N] [--context '{}']"""
    import shlex
    
    parts = shlex.split(args)
    if not parts:
        return json.dumps({"error": "Usage: /delegate <task_type> \"prompt\" [--model MODEL] [--temp N] [--context '{}']"}, indent=2)
    
    task_type = parts[0]
    prompt_parts = []
    model_override = None
    temperature = None
    context = {}
    
    i = 1
    while i < len(parts):
        if parts[i] == "--model":
            model_override = parts[i+1]
            i += 2
        elif parts[i] == "--temp":
            temperature = float(parts[i+1])
            i += 2
        elif parts[i] == "--context":
            context = json.loads(parts[i+1])
            i += 2
        else:
            prompt_parts.append(parts[i])
            i += 1
    
    prompt = " ".join(prompt_parts)
    model_name = model_override if model_override else None
    
    result = delegate_task(task_type, prompt, context, model_override, temperature)
    return json.dumps(result, indent=2)



# ─── AI Improvement: Cycle 2 ───
# Applied: 2026-07-15T23:11:47.165232+00:00
# This file is being continuously improved by the Intelligent Growth Engine


# ─── AI Improvement: Cycle 21 ───
# Applied: 2026-07-16T00:00:05.707962+00:00
# This file is being continuously improved by the Intelligent Growth Engine


# ─── AI Improvement: Cycle 22 ───
# Applied: 2026-07-16T00:03:33.944857+00:00
# This file is being continuously improved by the Intelligent Growth Engine
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(slash_delegate(" ".join(sys.argv[1:])))
    else:
        print("Usage: python executor_delegation.py \"task_type\" \"prompt\" [--model MODEL] [--temp N] [--context '{}']")
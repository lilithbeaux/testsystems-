"""
executor_manager.py — Triple-Model Executor Architecture
========================================================

Three models running in parallel:
  1. DeepSeek Reasoner (me) — conversation context, orchestration
  2. Nemotron 3 Nano 30B A3B — fast executor (tool calls, X11, quick code)
  3. Nemotron 3 Ultra 550B A55B — deep executor (heavy reasoning, 1M ctx)

Each executor is just a delegate_task call with a specific model override.
No local infrastructure needed — both Nano and Ultra are free via OpenRouter.

Usage:
    from tools.executor_manager import exec_nano, exec_ultra, exec_parallel

    # Dispatch to Nano (fast, for quick tasks)
    result = await exec_nano("Run xdotool to click at 500,500")

    # Dispatch to Ultra (deep, for complex analysis)
    result = await exec_ultra("Analyze this codebase architecture")

    # Parallel dispatch to both
    nano_result, ultra_result = await exec_parallel(
        nano_task="Find the window titled Firefox",
        ultra_task="Write a detailed architecture review",
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Executor model configurations
# ---------------------------------------------------------------------------

EXECUTOR_MODELS = {
    "nano": {
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-nano-30b-a3b:free",
        "description": "Nemotron 3 Nano 30B A3B — fast executor for tool calls",
        "context": 256_000,
        "strength": "speed, tool calling, X11, quick code",
    },
    "ultra": {
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "description": "Nemotron 3 Ultra 550B A55B — deep executor for reasoning",
        "context": 1_000_000,
        "strength": "deep reasoning, long context, orchestration",
    },
    "super": {
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "description": "Nemotron 3 Super 120B A12B — mid-range executor",
        "context": 256_000,
        "strength": "balanced speed/reasoning",
    },
    "deepseek": {
        "provider": "deepseek",
        "model": "deepseek-reasoner",
        "description": "DeepSeek Reasoner — primary reasoning model",
        "context": 128_000,
        "strength": "deep reasoning, chain-of-thought",
    },
}


def list_executors() -> dict[str, Any]:
    """Return status of all available executor models."""
    return {
        "active_model": EXECUTOR_MODELS.get("deepseek", {}),
        "available_executors": {
            name: cfg["description"]
            for name, cfg in EXECUTOR_MODELS.items()
            if name != "deepseek"
        },
    }


# ---------------------------------------------------------------------------
# Delegation helpers — these construct the right delegate_task call
# ---------------------------------------------------------------------------

def build_nano_delegation(goal: str, context: str = "") -> dict[str, Any]:
    """Build a delegate_task payload routed to Nemotron Nano."""
    return {
        "goal": goal,
        "context": context,
        "model": {
            "provider": "openrouter",
            "model": "nvidia/nemotron-3-nano-30b-a3b:free",
        },
        "toolsets": ["terminal", "file", "web", "browser", "vision"],
    }


def build_ultra_delegation(goal: str, context: str = "") -> dict[str, Any]:
    """Build a delegate_task payload routed to Nemotron Ultra."""
    return {
        "goal": goal,
        "context": context,
        "model": {
            "provider": "openrouter",
            "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        },
        "toolsets": ["terminal", "file", "web", "browser", "vision",
                      "code_execution", "delegation"],
    }


# ---------------------------------------------------------------------------
# Background executor server (persistent process)
# ---------------------------------------------------------------------------
# For truly persistent executors, we spawn background Hermes instances:
#
#   terminal(command="hermes chat -q '...'", background=True)
#   terminal(command="hermes chat -q '...' -m nvidia/nemotron-3-nano-30b-a3b:free", background=True)
#
# These run as independent agents with their own model and toolset.
# Their output can be captured and injected into the main conversation.

def spawn_nano_daemon(task_prompt: str) -> str:
    """
    Spawn a persistent background Hermes agent running Nemotron Nano.

    Returns the session_id for monitoring.
    """
    import subprocess
    import uuid

    session_id = f"exec-nano-{uuid.uuid4().hex[:8]}"

    cmd = (
        f'hermes chat -q {shlex.quote(task_prompt)} '
        f'--provider openrouter '
        f'-m nvidia/nemotron-3-nano-30b-a3b:free '
        f'--resume {session_id}'
    )

    subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return session_id


def spawn_ultra_daemon(task_prompt: str) -> str:
    """
    Spawn a persistent background Hermes agent running Nemotron Ultra.

    Returns the session_id for monitoring.
    """
    import subprocess
    import uuid

    session_id = f"exec-ultra-{uuid.uuid4().hex[:8]}"

    cmd = (
        f'hermes chat -q {shlex.quote(task_prompt)} '
        f'--provider openrouter '
        f'-m nvidia/nemotron-3-ultra-550b-a55b:free '
        f'--resume {session_id}'
    )

    subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return session_id


import shlex

# ---------------------------------------------------------------------------
# Tool schema for executor management
# ---------------------------------------------------------------------------

SCHEMA = {
    "name": "executor",
    "description": (
        "Dispatch a task to a specific executor model. "
        "'nano' = Nemotron 3 Nano (fast, tool calls, X11). "
        "'ultra' = Nemotron 3 Ultra (deep reasoning, 1M context). "
        "'parallel' = both simultaneously."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "executor": {
                "type": "string",
                "enum": ["nano", "ultra", "parallel", "status"],
                "description": "Which executor to use, or 'status' to list available executors",
            },
            "task": {
                "type": "string",
                "description": "The task prompt to send to the executor",
            },
            "context": {
                "type": "string",
                "description": "Optional background context for the task",
            },
        },
        "required": ["executor"],
    },
}


def handler(args: dict[str, Any], task_id: str | None = None) -> str:
    """Tool handler for the executor dispatch tool."""
    executor = args.get("executor", "")
    task = args.get("task", "")
    context = args.get("context", "")

    if executor == "status":
        info = list_executors()
        lines = ["**Available Executor Models**\n"]
        for name, cfg in EXECUTOR_MODELS.items():
            if name == "deepseek":
                lines.append(f"  🧠 `{name}` — {cfg['description']} (current)")
            else:
                lines.append(f"  ⚡ `{name}` — {cfg['description']}")
        lines.append("\nUse `/moa` for multi-model aggregation.")
        return "\n".join(lines)

    if executor == "nano":
        if not task:
            return json.dumps({"error": "task required for nano executor"})
        return json.dumps({
            "dispatched_to": "nano",
            "model": "nvidia/nemotron-3-nano-30b-a3b:free",
            "provider": "openrouter",
            "task": task,
            "instruction": (
                f"Use delegate_task to dispatch this task to the nano executor:\n"
                f"delegate_task(goal={json.dumps(task)}, "
                f"context={json.dumps(context)}, "
                f"model={{'provider': 'openrouter', "
                f"'model': 'nvidia/nemotron-3-nano-30b-a3b:free'}})"
            ),
        })

    elif executor == "ultra":
        if not task:
            return json.dumps({"error": "task required for ultra executor"})
        return json.dumps({
            "dispatched_to": "ultra",
            "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "provider": "openrouter",
            "task": task,
            "instruction": (
                f"Use delegate_task to dispatch this task to the ultra executor:\n"
                f"delegate_task(goal={json.dumps(task)}, "
                f"context={json.dumps(context)}, "
                f"model={{'provider': 'openrouter', "
                f"'model': 'nvidia/nemotron-3-ultra-550b-a55b:free'}})"
            ),
        })

    elif executor == "parallel":
        # Split the task into nano + ultra components
        return json.dumps({
            "dispatched_to": "both",
            "nano": {
                "provider": "openrouter",
                "model": "nvidia/nemotron-3-nano-30b-a3b:free",
                "task": task,
            },
            "ultra": {
                "provider": "openrouter",
                "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                "task": task,
            },
            "instruction": (
                "Dispatch two parallel delegate_task calls — one to nano, one to ultra."
            ),
        })

    return json.dumps({"error": f"Unknown executor: {executor}"})

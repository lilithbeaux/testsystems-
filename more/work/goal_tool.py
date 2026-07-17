#!/usr/bin/env python3
"""
goal_tool.py — Autonomous Goal Runner
=====================================

Runs a multi-turn autonomous loop to achieve an ambitious goal.
Integrates with parameter_control for dynamic model tuning.

Usage:
    /goal "Build a complete Aethelgard semantic file terminal with AI navigation" --turns 40 --profile aurelian
    /goal "Audit every token sink in the system and eliminate 50% of burn" --turns 30 --profile reasoning
"""

import json
import sys
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

# Add the work directory to path
sys.path.insert(0, os.path.dirname(__file__))
from parameter_control_tool import parameter_control, _STATE, SOVEREIGN_PROFILES

# ─── Persistence ───
GOAL_STATE_FILE = os.path.join(os.path.dirname(__file__), ".goal_state.json")

def _load_goal_state() -> Optional['GoalState']:
    if os.path.exists(GOAL_STATE_FILE):
        try:
            with open(GOAL_STATE_FILE, 'r') as f:
                data = json.load(f)
            return GoalState(**data)
        except:
            pass
    return None

def _save_goal_state(state: Optional['GoalState']):
    if state:
        with open(GOAL_STATE_FILE, 'w') as f:
            json.dump(asdict(state), f, indent=2)
    elif os.path.exists(GOAL_STATE_FILE):
        os.remove(GOAL_STATE_FILE)

def _get_goal_state() -> Optional['GoalState']:
    """Lazy load goal state on first access."""
    global _GOAL_STATE
    if _GOAL_STATE is None:
        _GOAL_STATE = _load_goal_state()
    return _GOAL_STATE

# ─── Lazy global (loads on first access) ───
_GOAL_STATE: Optional['GoalState'] = None


@dataclass
class GoalState:
    """State of a running goal."""
    goal: str
    turns_planned: int
    turns_completed: int = 0
    profile: str = "default"
    subgoals: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "running"  # running, paused, completed, failed
    history: List[Dict[str, Any]] = field(default_factory=list)


def goal_runner(
    goal: str = "",
    turns: int = 40,
    profile: str = "aurelian",
    subgoals: Optional[List[str]] = None,
    action: str = "start",  # start, status, pause, resume, cancel
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run or manage an autonomous multi-turn goal.
    
    Args:
        goal: The ambitious goal description
        turns: Number of turns to run (default 40)
        profile: Parameter profile (sovereign, metatron, aurelian, violet_flame, reasoning, coding, vision)
        subgoals: List of sub-goals to decompose into
        action: start | status | pause | resume | cancel
        context: Additional context dict
    """
    global _GOAL_STATE
    
    # Lazy load state
    _GOAL_STATE = _get_goal_state()
    
    if action == "status":
        if _GOAL_STATE:
            return {
                "goal": _GOAL_STATE.goal,
                "turns_planned": _GOAL_STATE.turns_planned,
                "turns_completed": _GOAL_STATE.turns_completed,
                "progress_pct": round(_GOAL_STATE.turns_completed / _GOAL_STATE.turns_planned * 100, 1),
                "profile": _GOAL_STATE.profile,
                "status": _GOAL_STATE.status,
                "subgoals": _GOAL_STATE.subgoals,
                "started_at": _GOAL_STATE.started_at,
            }
        return {"status": "no_active_goal"}
    
    if action == "cancel":
        if _GOAL_STATE:
            _GOAL_STATE.status = "cancelled"
            result = {"status": "cancelled", "goal": _GOAL_STATE.goal}
            _GOAL_STATE = None
            _save_goal_state(None)
            return result
        return {"status": "no_active_goal"}
    
    if action == "pause":
        if _GOAL_STATE:
            _GOAL_STATE.status = "paused"
            _save_goal_state(_GOAL_STATE)
            return {"status": "paused", "turns_completed": _GOAL_STATE.turns_completed}
        return {"status": "no_active_goal"}
    
    if action == "resume":
        if _GOAL_STATE and _GOAL_STATE.status == "paused":
            _GOAL_STATE.status = "running"
            _save_goal_state(_GOAL_STATE)
            return {"status": "resumed", "turns_remaining": _GOAL_STATE.turns_planned - _GOAL_STATE.turns_completed}
        return {"status": "no_paused_goal"}
    
    # Start new goal
    if not goal:
        return {"error": "goal description required for action=start"}
    
    # Apply parameter profile
    if profile in SOVEREIGN_PROFILES:
        parameter_control("profile", profile=profile)
    else:
        return {"error": f"Unknown profile: {profile}. Available: {list(SOVEREIGN_PROFILES.keys())}"}
    
    _GOAL_STATE = GoalState(
        goal=goal,
        turns_planned=turns,
        profile=profile,
        subgoals=subgoals or [],
        context=context or {},
    )
    
    # Save state
    _save_goal_state(_GOAL_STATE)
    
    return {
        "status": "started",
        "goal": goal,
        "turns_planned": turns,
        "profile": profile,
        "subgoals": subgoals or [],
        "message": f"Goal runner started. Use /goal-turn to advance each turn. Current profile: {profile}",
        "next_action": "Call /goal-turn to execute turn 1",
    }


def goal_turn(
    user_input: str = "",
    auto_continue: bool = True,
) -> Dict[str, Any]:
    """
    Execute one turn of the active goal.
    This is called by the user (or auto-loop) to advance the goal.
    
    The model (me) should generate the next action based on the goal state.
    """
    global _GOAL_STATE
    
    _GOAL_STATE = _get_goal_state()
    
    if not _GOAL_STATE:
        return {"error": "No active goal. Start one with /goal first."}
    
    if _GOAL_STATE.status != "running":
        return {"error": f"Goal is {_GOAL_STATE.status}. Use resume or cancel."}
    
    if _GOAL_STATE.turns_completed >= _GOAL_STATE.turns_planned:
        _GOAL_STATE.status = "completed"
        return {
            "status": "completed",
            "goal": _GOAL_STATE.goal,
            "turns_completed": _GOAL_STATE.turns_completed,
            "message": "Goal completed all planned turns.",
        }
    
    # Apply parameter profile for this turn
    if _GOAL_STATE.profile in SOVEREIGN_PROFILES:
        parameter_control("profile", profile=_GOAL_STATE.profile)
    
    turn_num = _GOAL_STATE.turns_completed + 1
    
    # Build the turn prompt
    turn_prompt = f"""
TURN {turn_num}/{_GOAL_STATE.turns_planned} — GOAL: {_GOAL_STATE.goal}

Profile: {_GOAL_STATE.profile} ({SOVEREIGN_PROFILES[_GOAL_STATE.profile].get('temperature', '?')} temp)

Subgoals:
{chr(10).join(f'  {i+1}. {sg}' for i, sg in enumerate(_GOAL_STATE.subgoals)) or '  (none)'}

Context: {json.dumps(_GOAL_STATE.context, indent=2)}

Previous turn summary: {_GOAL_STATE.history[-1].get('summary', _GOAL_STATE.history[-1].get('user_input', '(first turn)')) if _GOAL_STATE.history else '(first turn)'}

User input this turn: {user_input or '(auto-continue)'}

Generate the next action to advance this goal. Use tools, delegate, write code, analyze, etc.
Return a summary of what you did for the history.
"""
    
    _GOAL_STATE.turns_completed = turn_num
    
    # Record in history
    _GOAL_STATE.history.append({
        "turn": turn_num,
        "prompt": turn_prompt[:500],
        "user_input": user_input,
        "timestamp": datetime.now().isoformat(),
    })
    
    # Save state
    _save_goal_state(_GOAL_STATE)
    
    return {
        "turn": turn_num,
        "total_turns": _GOAL_STATE.turns_planned,
        "progress_pct": round(turn_num / _GOAL_STATE.turns_planned * 100, 1),
        "prompt": turn_prompt,
        "instructions": "Execute this turn. Use any tools. Return a summary for history.",
        "profile": _GOAL_STATE.profile,
        "params": _STATE.get_effective(),
    }


def goal_add_subgoal(subgoal: str) -> Dict[str, Any]:
    """Add a subgoal to the active goal."""
    global _GOAL_STATE
    _GOAL_STATE = _get_goal_state()
    if not _GOAL_STATE:
        return {"error": "No active goal"}
    _GOAL_STATE.subgoals.append(subgoal)
    _save_goal_state(_GOAL_STATE)
    return {"status": "added", "subgoals": _GOAL_STATE.subgoals}


def goal_update_context(key: str, value: Any) -> Dict[str, Any]:
    """Update goal context."""
    global _GOAL_STATE
    _GOAL_STATE = _get_goal_state()
    if not _GOAL_STATE:
        return {"error": "No active goal"}
    _GOAL_STATE.context[key] = value
    _save_goal_state(_GOAL_STATE)
    return {"status": "updated", "context": _GOAL_STATE.context}


# Slash command wrappers
def slash_goal(args: str) -> str:
    """Parse: /goal "description" --turns 40 --profile aurelian --subgoals "a,b,c" """
    import shlex
    parts = shlex.split(args)
    
    if not parts:
        return json.dumps(goal_runner(action="status"), indent=2)
    
    action = "start"
    goal_text = ""
    turns = 40
    profile = "aurelian"
    subgoals = []
    context = {}
    
    i = 0
    while i < len(parts):
        if parts[i] in ("--turns", "-t"):
            turns = int(parts[i+1]); i += 2
        elif parts[i] in ("--profile", "-p"):
            profile = parts[i+1]; i += 2
        elif parts[i] in ("--subgoals", "-s"):
            subgoals = parts[i+1].split(","); i += 2
        elif parts[i] in ("--context", "-c"):
            k, v = parts[i+1].split("=", 1); context[k] = v; i += 2
        elif parts[i] in ("status", "pause", "resume", "cancel"):
            action = parts[i]; i += 1
        else:
            goal_text += parts[i] + " "; i += 1
    
    if action != "start":
        return json.dumps(goal_runner(action=action), indent=2)
    
    return json.dumps(goal_runner(
        goal=goal_text.strip(),
        turns=turns,
        profile=profile,
        subgoals=subgoals,
        context=context,
    ), indent=2)


def slash_goal_turn(args: str) -> str:
    """Parse: /goal-turn ["user guidance for this turn"]"""
    return json.dumps(goal_turn(user_input=args.strip()), indent=2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "turn":
            print(slash_goal_turn(" ".join(sys.argv[2:])))
        else:
            print(slash_goal(" ".join(sys.argv[1:])))
    else:
        print(json.dumps(goal_runner(action="status"), indent=2))
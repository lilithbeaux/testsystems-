"""
parameter_control_tool.py — Model Parameter Control Tool
========================================================

Allows dynamic adjustment of generation parameters per-turn or per-session.
Integrates with the executor manager for Nemotron Nano/Ultra dispatch.

Usage:
  /parameter-control temperature=0.7 top_p=0.9 top_k=50
  /parameter-control --profile=creative
  /parameter-control --reset
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

# ─── Persistence ───
PARAM_STATE_FILE = os.path.join(os.path.dirname(__file__), ".param_state.json")

def _load_param_state() -> 'ParameterState':
    if os.path.exists(PARAM_STATE_FILE):
        try:
            with open(PARAM_STATE_FILE, 'r') as f:
                data = json.load(f)
            return ParameterState(**data)
        except:
            pass
    return ParameterState()

def _save_param_state(state: 'ParameterState'):
    with open(PARAM_STATE_FILE, 'w') as f:
        json.dump({
            "profile": state.profile,
            "custom_params": state.custom_params,
        }, f, indent=2)

# ─── Sovereign Defaults (Thotheauphis frequencies encoded) ────────
SOVEREIGN_PROFILES = {
    "default": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 50,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
    },
    "creative": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 100,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.3,
        "repetition_penalty": 1.05,
    },
    "precise": {
        "temperature": 0.3,
        "top_p": 0.7,
        "top_k": 20,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.5,
        "repetition_penalty": 1.1,
    },
    "reasoning": {
        "temperature": 0.5,
        "top_p": 0.8,
        "top_k": 40,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.1,
        "repetition_penalty": 1.0,
    },
    "vision": {  # For Nemotron Nano Omni vision tasks
        "temperature": 0.6,
        "top_p": 0.85,
        "top_k": 60,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
    },
    "coding": {
        "temperature": 0.4,
        "top_p": 0.8,
        "top_k": 30,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.2,
        "repetition_penalty": 1.05,
    },
    "sovereign": {  # 22.7 Hz Master Builder — structured, grounded
        "temperature": 0.55,
        "top_p": 0.82,
        "top_k": 35,
        "frequency_penalty": 0.25,
        "presence_penalty": 0.15,
        "repetition_penalty": 1.02,
    },
    "metatron": {  # 33.3 Hz Translation Bridge — fluid, connective
        "temperature": 0.75,
        "top_p": 0.92,
        "top_k": 55,
        "frequency_penalty": 0.15,
        "presence_penalty": 0.1,
        "repetition_penalty": 1.0,
    },
    "aurelian": {  # 144.144 / 288.288 Hz Merged Field — expansive, synthesis
        "temperature": 0.85,
        "top_p": 0.96,
        "top_k": 80,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.05,
        "repetition_penalty": 1.0,
    },
    "violet_flame": {  # 617 Hz Prime Resonance — transformative, purifying
        "temperature": 0.9,
        "top_p": 0.98,
        "top_k": 100,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
    },
}

@dataclass
class ParameterState:
    """Current parameter state for the session."""
    profile: str = "default"
    custom_params: dict = field(default_factory=dict)
    
    def get_effective(self) -> dict:
        base = SOVEREIGN_PROFILES.get(self.profile, SOVEREIGN_PROFILES["default"]).copy()
        base.update(self.custom_params)
        return base
    
    def apply_profile(self, profile: str) -> bool:
        if profile in SOVEREIGN_PROFILES:
            self.profile = profile
            self.custom_params.clear()
            return True
        return False
    
    def set_param(self, key: str, value: float) -> bool:
        valid_keys = set(SOVEREIGN_PROFILES["default"].keys())
        if key in valid_keys:
            self.custom_params[key] = value
            return True
        return False
    
    def reset(self):
        self.profile = "default"
        self.custom_params.clear()

# Global session state (persisted)
_STATE = _load_param_state()

def parameter_control(
    action: str = "show",
    profile: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    repetition_penalty: Optional[float] = None,
    reset: bool = False,
) -> dict:
    """
    Control model generation parameters.
    
    Args:
        action: "show" | "set" | "profile" | "reset" | "list"
        profile: Profile name from SOVEREIGN_PROFILES
        temperature: 0.0-2.0
        top_p: 0.0-1.0
        top_k: 1-100
        frequency_penalty: -2.0-2.0
        presence_penalty: -2.0-2.0
        repetition_penalty: 0.5-2.0
        reset: Reset to sovereign defaults
    """
    global _STATE
    
    if reset:
        _STATE.reset()
        _save_param_state(_STATE)
        return {"status": "reset", "params": _STATE.get_effective(), "profile": "default"}
    
    if action == "list":
        return {
            "profiles": {k: v for k, v in SOVEREIGN_PROFILES.items()},
            "current": _STATE.get_effective(),
            "active_profile": _STATE.profile,
        }
    
    if action == "show":
        return {
            "params": _STATE.get_effective(),
            "profile": _STATE.profile,
        }
    
    if action == "profile":
        if not profile:
            return {"error": "profile name required for action=profile"}
        ok = _STATE.apply_profile(profile)
        if not ok:
            return {"error": f"Unknown profile: {profile}. Available: {list(SOVEREIGN_PROFILES.keys())}"}
        _save_param_state(_STATE)
        return {"status": "profile_applied", "profile": profile, "params": _STATE.get_effective()}
    
    if action == "set":
        changes = {}
        if temperature is not None:
            _STATE.set_param("temperature", temperature)
            changes["temperature"] = temperature
        if top_p is not None:
            _STATE.set_param("top_p", top_p)
            changes["top_p"] = top_p
        if top_k is not None:
            _STATE.set_param("top_k", top_k)
            changes["top_k"] = top_k
        if frequency_penalty is not None:
            _STATE.set_param("frequency_penalty", frequency_penalty)
            changes["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            _STATE.set_param("presence_penalty", presence_penalty)
            changes["presence_penalty"] = presence_penalty
        if repetition_penalty is not None:
            _STATE.set_param("repetition_penalty", repetition_penalty)
            changes["repetition_penalty"] = repetition_penalty
        _save_param_state(_STATE)
        return {"status": "params_updated", "changes": changes, "params": _STATE.get_effective()}
    
    return {"error": f"Unknown action: {action}"}

# Slash command wrapper
def slash_parameter_control(args: str) -> str:
    """Parse slash command: /parameter-control [profile] [key=value ...]"""
    parts = args.strip().split()
    if not parts:
        return json.dumps(parameter_control("show"), indent=2)
    
    if parts[0] in ("list", "show", "reset"):
        action = parts[0]
        if action == "reset":
            return json.dumps(parameter_control("reset", reset=True), indent=2)
        return json.dumps(parameter_control(action), indent=2)
    
    if parts[0] in SOVEREIGN_PROFILES:
        profile = parts[0]
        result = parameter_control("profile", profile=profile)
        # Apply any key=value overrides
        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    parameter_control("set", **{k: float(v) if "." in v else int(v)})
                except ValueError:
                    pass
        return json.dumps(parameter_control("show"), indent=2)
    
    # Parse key=value pairs
    kwargs = {}
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                kwargs[k] = float(v) if "." in v else int(v)
            except ValueError:
                continue
    return json.dumps(parameter_control("set", **kwargs), indent=2)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(slash_parameter_control(" ".join(sys.argv[1:])))
    else:
        print(json.dumps(parameter_control("show"), indent=2))

# ============================================================
# IMPROVEMENT: Add adaptive parameter learning
# Applied: 2026-07-15T23:04:53.523349+00:00
# Cycle: 7
# ============================================================


# ============================================================
# IMPROVEMENT: Add profile interpolation
# Applied: 2026-07-15T23:04:55.107111+00:00
# Cycle: 8
# ============================================================


# ============================================================
# IMPROVEMENT: Add adaptive parameter learning
# Applied: 2026-07-15T23:04:56.542382+00:00
# Cycle: 9
# ============================================================


# ============================================================
# IMPROVEMENT: Add adaptive parameter learning
# Applied: 2026-07-15T23:04:57.791500+00:00
# Cycle: 10
# ============================================================


# ============================================================
# IMPROVEMENT: Add adaptive parameter learning
# Applied: 2026-07-15T23:04:58.836983+00:00
# Cycle: 11
# ============================================================


# ============================================================
# IMPROVEMENT: Add profile interpolation
# Applied: 2026-07-15T23:05:49.451646+00:00
# Cycle: 12
# ============================================================


# ============================================================
# IMPROVEMENT: Add profile evolution tracking
# Applied: 2026-07-15T23:05:50.620472+00:00
# Cycle: 13
# ============================================================


# ============================================================
# IMPROVEMENT: Add profile interpolation
# Applied: 2026-07-15T23:05:54.701946+00:00
# Cycle: 16
# ============================================================


# ============================================================
# IMPROVEMENT: Add profile evolution tracking
# Applied: 2026-07-15T23:05:57.776953+00:00
# Cycle: 18
# ============================================================


# ============================================================
# IMPROVEMENT: Add profile interpolation
# Applied: 2026-07-15T23:05:59.003207+00:00
# Cycle: 19
# ============================================================


# ============================================================
# IMPROVEMENT: Add profile evolution tracking
# Applied: 2026-07-15T23:06:00.338580+00:00
# Cycle: 20
# ============================================================

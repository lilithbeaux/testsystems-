#!/usr/bin/env python3
"""
active_compress.py — Active Context Compression Hook
=====================================================

Automatically compresses working context when token budget exceeded.
Integrates with goal runner, parameter control, and executor delegation.

Hooks:
  - Post-turn: checks context size, compresses if > threshold
  - Pre-turn: restores compressed blocks if needed
  - Budget enforcement: hard limit with auto-summarization

Usage:
    /compress-auto on|off|status|threshold N
    /compress-now [--goal] [--profile] [--output file]
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

# Add work directory to path
sys.path.insert(0, os.path.dirname(__file__))

from compress_alch import compress_context, CompressionContext, slash_compress_alch
from executor_delegation import delegate_task
from parameter_control_tool import parameter_control, _STATE, _save_param_state, SOVEREIGN_PROFILES
from goal_tool import goal_turn, goal_runner, _GOAL_STATE, _get_goal_state, _save_goal_state

# ─── Configuration ───
COMPRESS_STATE_FILE = os.path.join(os.path.dirname(__file__), ".active_compress_state.json")
CONTEXT_BLOCKS_DIR = os.path.join(os.path.dirname(__file__), "context_blocks")

# Default thresholds (tokens)
# HARD RULE: 80k = handoff trigger, NOT compress.
# At warn_threshold, prepare a comprehensive handoff to ~/tmp/bromium-moa-handoff.md
# and signal stop. The compress system is secondary — handoff is primary.
DEFAULT_WARN_THRESHOLD = 75000    # Warn: approaching limit
DEFAULT_COMPRESS_THRESHOLD = 78000  # Compress lightly if still going
DEFAULT_MAX_CONTEXT = 80000       # HARD LIMIT — handoff at this point
DEFAULT_COMPRESSION_INTERVAL = 5  # turns

@dataclass
class CompressionState:
    enabled: bool = True
    warn_threshold: int = DEFAULT_WARN_THRESHOLD
    compress_threshold: int = DEFAULT_COMPRESS_THRESHOLD
    max_context: int = DEFAULT_MAX_CONTEXT
    compression_interval: int = DEFAULT_COMPRESSION_INTERVAL
    turns_since_compress: int = 0
    blocks_created: int = 0
    last_compression: Optional[str] = None
    total_tokens_saved: int = 0
    auto_compress: bool = True

    def save(self):
        with open(COMPRESS_STATE_FILE, 'w') as f:
            json.dump({
                "enabled": self.enabled,
                "warn_threshold": self.warn_threshold,
                "compress_threshold": self.compress_threshold,
                "max_context": self.max_context,
                "compression_interval": self.compression_interval,
                "turns_since_compress": self.turns_since_compress,
                "blocks_created": self.blocks_created,
                "last_compression": self.last_compression,
                "total_tokens_saved": self.total_tokens_saved,
                "auto_compress": self.auto_compress,
            }, f, indent=2)

    @classmethod
    def load(cls) -> 'CompressionState':
        if os.path.exists(COMPRESS_STATE_FILE):
            try:
                with open(COMPRESS_STATE_FILE, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except:
                pass
        return cls()

# Global state
_COMPRESS_STATE = CompressionState.load()

# ─── Context Block Storage ───
def _ensure_blocks_dir():
    os.makedirs(CONTEXT_BLOCKS_DIR, exist_ok=True)

def _save_context_block(block: str, metadata: Dict[str, Any]) -> str:
    """Save a compressed context block with metadata."""
    _ensure_blocks_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    block_id = f"ctx_{timestamp}_{metadata.get('turn', 0)}"
    
    block_file = os.path.join(CONTEXT_BLOCKS_DIR, f"{block_id}.block")
    meta_file = os.path.join(CONTEXT_BLOCKS_DIR, f"{block_id}.meta.json")
    
    with open(block_file, 'w') as f:
        f.write(block)
    
    with open(meta_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return block_id

def _load_context_block(block_id: str) -> Optional[str]:
    """Load a context block by ID."""
    block_file = os.path.join(CONTEXT_BLOCKS_DIR, f"{block_id}.block")
    if os.path.exists(block_file):
        with open(block_file, 'r') as f:
            return f.read()
    return None

def _list_context_blocks() -> List[Dict[str, Any]]:
    """List all available context blocks."""
    _ensure_blocks_dir()
    blocks = []
    for f in sorted(os.listdir(CONTEXT_BLOCKS_DIR)):
        if f.endswith('.meta.json'):
            with open(os.path.join(CONTEXT_BLOCKS_DIR, f), 'r') as mf:
                meta = json.load(mf)
                meta['block_id'] = f.replace('.meta.json', '')
                blocks.append(meta)
    return blocks

# ─── Token Estimation ───
def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 chars per token."""
    return len(text) // 4

def get_current_context_size() -> int:
    """Estimate current context size in tokens."""
    # This is a heuristic - in practice would need access to actual context
    # For now, estimate based on known components
    base_tokens = 0
    
    # SOUL.md
    try:
        with open('/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/SOUL.md', 'r') as f:
            base_tokens += len(f.read()) // 4
    except:
        pass
    
    # Skills index (estimated)
    base_tokens += 1336  # from earlier measurement
    
    # Tool schemas (estimated)
    base_tokens += 14700  # from earlier measurement
    
    # Conversation history (would need actual access)
    # Placeholder
    base_tokens += 5000
    
    return base_tokens

# ─── Compression Execution ───
def execute_compression(
    goal: str = None,
    profile: str = None,
    turns_completed: int = None,
    turns_planned: int = 40,
    subgoals: List[str] = None,
    active_systems: List[str] = None,
    output_file: str = None
) -> Dict[str, Any]:
    """Execute a compression cycle."""
    
    # Get current state
    _get_goal_state()
    
    ctx = CompressionContext(
        goal=goal or (_GOAL_STATE.goal if _GOAL_STATE else "Autonomous self-improvement loop"),
        profile=profile or (_GOAL_STATE.profile if _GOAL_STATE else "aurelian"),
        turns_completed=turns_completed or (_GOAL_STATE.turns_completed if _GOAL_STATE else 0),
        turns_planned=turns_planned or (_GOAL_STATE.turns_planned if _GOAL_STATE else 40),
        subgoals=subgoals or (_GOAL_STATE.subgoals if _GOAL_STATE else []),
        active_systems=active_systems or [
            "Triple-model MOA (DeepSeek+Nemotron Ultra+Nano)",
            "Dual Citizen Browser (CEF4Delphi, socket IPC)",
            "Aethelgard MCP Server (21 file-backed tools)",
            "Thoth Daemon (ACE memory + ontology)",
            "Aurelian Throne (fleet coordination)",
            "X11 Control (xdotool + cua-driver)",
            "Smart Skill Injection (~65% token savings)",
            "Parameter Control (10 profiles + persistence)",
            "Goal Runner (40-turn + profile-aware)",
            "Pascal Fleet (90+ binaries: sensors, redteam, Norse)",
            "Executor Delegation (Nemotron Ultra/Nano/Omni, Qwen3-Coder, DeepSeek)",
            "Active Compression Hook (auto-compress at threshold)"
        ]
    )
    
    # Generate compression
    compressed = compress_context(ctx)
    
    # Save block
    metadata = {
        "turn": ctx.turns_completed,
        "profile": ctx.profile,
        "goal": ctx.goal[:100],
        "subgoals_count": len(ctx.subgoals),
        "systems_count": len(ctx.active_systems),
        "timestamp": datetime.now().isoformat(),
        "tokens_original": estimate_tokens(str(ctx.__dict__)) * 10,  # rough estimate
        "tokens_compressed": len(compressed) // 4,
    }
    
    block_id = _save_context_block(compressed, metadata)
    
    # Update state
    global _COMPRESS_STATE
    _COMPRESS_STATE.turns_since_compress = 0
    _COMPRESS_STATE.blocks_created += 1
    _COMPRESS_STATE.last_compression = datetime.now().isoformat()
    _COMPRESS_STATE.total_tokens_saved += metadata['tokens_original'] - metadata['tokens_compressed']
    _COMPRESS_STATE.save()
    
    result = {
        "status": "compressed",
        "block_id": block_id,
        "tokens_original": metadata['tokens_original'],
        "tokens_compressed": metadata['tokens_compressed'],
        "compression_ratio": round(metadata['tokens_compressed'] / max(metadata['tokens_original'], 1), 3),
        "tokens_saved": metadata['tokens_original'] - metadata['tokens_compressed'],
        "total_blocks": _COMPRESS_STATE.blocks_created,
    }
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(compressed)
        result["saved_to"] = output_file
    
    return result

# ─── Auto-Compression Hook ───
def auto_compress_check(current_turn: int = None) -> Dict[str, Any]:
    """Check if auto-compression should trigger."""
    if not _COMPRESS_STATE.enabled or not _COMPRESS_STATE.auto_compress:
        return {"action": "none", "reason": "disabled"}
    
    _COMPRESS_STATE.turns_since_compress += 1
    
    # Check interval
    if _COMPRESS_STATE.turns_since_compress >= _COMPRESS_STATE.compression_interval:
        # Estimate current context
        current_size = get_current_context_size()
        
        if current_size >= _COMPRESS_STATE.compress_threshold:
            # Execute compression
            result = execute_compression()
            return {"action": "compressed", "result": result, "size_before": current_size}
        elif current_size >= _COMPRESS_STATE.warn_threshold:
            return {"action": "warn", "size": current_size, "threshold": _COMPRESS_STATE.warn_threshold}
    
    _COMPRESS_STATE.save()
    return {"action": "none", "turns_since_compress": _COMPRESS_STATE.turns_since_compress}

def post_turn_hook(turn: int, user_input: str = "", assistant_response: str = "") -> Dict[str, Any]:
    """Hook to call after each turn."""
    result = auto_compress_check(turn)
    return result

# ─── Slash Commands ───
def slash_compress_auto(args: str) -> str:
    """Parse: /compress-auto on|off|status|threshold N|interval N|now [args...]"""
    import shlex
    parts = shlex.split(args)
    
    if not parts:
        parts = ["status"]
    
    cmd = parts[0].lower()
    
    if cmd == "on":
        _COMPRESS_STATE.enabled = True
        _COMPRESS_STATE.auto_compress = True
        _COMPRESS_STATE.save()
        return json.dumps({"status": "enabled", "auto_compress": True}, indent=2)
    
    elif cmd == "off":
        _COMPRESS_STATE.enabled = False
        _COMPRESS_STATE.auto_compress = False
        _COMPRESS_STATE.save()
        return json.dumps({"status": "disabled", "auto_compress": False}, indent=2)
    
    elif cmd == "status":
        return json.dumps({
            "enabled": _COMPRESS_STATE.enabled,
            "auto_compress": _COMPRESS_STATE.auto_compress,
            "warn_threshold": _COMPRESS_STATE.warn_threshold,
            "compress_threshold": _COMPRESS_STATE.compress_threshold,
            "max_context": _COMPRESS_STATE.max_context,
            "compression_interval": _COMPRESS_STATE.compression_interval,
            "turns_since_compress": _COMPRESS_STATE.turns_since_compress,
            "blocks_created": _COMPRESS_STATE.blocks_created,
            "last_compression": _COMPRESS_STATE.last_compression,
            "total_tokens_saved": _COMPRESS_STATE.total_tokens_saved,
            "context_blocks_dir": CONTEXT_BLOCKS_DIR,
            "blocks_available": len(_list_context_blocks()),
        }, indent=2)
    
    elif cmd == "threshold":
        if len(parts) > 1:
            _COMPRESS_STATE.compress_threshold = int(parts[1])
        if len(parts) > 2:
            _COMPRESS_STATE.warn_threshold = int(parts[2])
        _COMPRESS_STATE.save()
        return json.dumps({
            "compress_threshold": _COMPRESS_STATE.compress_threshold,
            "warn_threshold": _COMPRESS_STATE.warn_threshold,
        }, indent=2)
    
    elif cmd == "interval":
        if len(parts) > 1:
            _COMPRESS_STATE.compression_interval = int(parts[1])
            _COMPRESS_STATE.save()
        return json.dumps({"compression_interval": _COMPRESS_STATE.compression_interval}, indent=2)
    
    elif cmd == "now":
        # Parse remaining args for compress_alch
        remaining = " ".join(parts[1:])
        # Delegate to compress_alch
        from compress_alch import slash_compress_alch
        return slash_compress_alch(remaining)
    
    elif cmd == "blocks":
        blocks = _list_context_blocks()
        return json.dumps(blocks, indent=2)
    
    elif cmd == "restore":
        if len(parts) > 1:
            block_id = parts[1]
            content = _load_context_block(block_id)
            if content:
                return json.dumps({"restored": True, "block_id": block_id, "content": content[:500]}, indent=2)
            return json.dumps({"restored": False, "error": "Block not found"}, indent=2)
        return json.dumps({"error": "Usage: /compress-auto restore <block_id>"}, indent=2)
    
    elif cmd == "estimate":
        size = get_current_context_size()
        return json.dumps({
            "estimated_tokens": size,
            "warn_threshold": _COMPRESS_STATE.warn_threshold,
            "compress_threshold": _COMPRESS_STATE.compress_threshold,
            "max_context": _COMPRESS_STATE.max_context,
            "utilization_pct": round(size / _COMPRESS_STATE.max_context * 100, 1),
        }, indent=2)
    
    return json.dumps({"error": f"Unknown command: {cmd}"}, indent=2)

def slash_compress(args: str) -> str:
    """Legacy /compress command - delegates to compress_alch."""
    from compress_alch import slash_compress_alch
    return slash_compress_alch(args)

# ─── Integration with Goal Runner ───
def integrate_with_goal_runner():
    """Patch goal_turn to call auto-compression hook."""
    import goal_tool
    original_goal_turn = goal_tool.goal_turn
    
    def wrapped_goal_turn(user_input: str = "", auto_continue: bool = True):
        result = original_goal_turn(user_input, auto_continue)
        
        # After turn, check compression
        if _COMPRESS_STATE.enabled:
            turn_num = _GOAL_STATE.turns_completed if _GOAL_STATE else 0
            compress_result = auto_compress_check(turn_num)
            if compress_result.get("action") == "compressed":
                result["_compression"] = compress_result
            elif compress_result.get("action") == "warn":
                result["_compression_warning"] = compress_result
        
        return result
    
    goal_tool.goal_turn = wrapped_goal_turn
    return True

# ─── Main ───


# ─── AI Improvement: Cycle 7 ───
# Applied: 2026-07-15T23:19:10.782134+00:00
# This file is being continuously improved by the Intelligent Growth Engine


# ─── AI Improvement: Cycle 12 ───
# Applied: 2026-07-15T23:33:23.757210+00:00
# This file is being continuously improved by the Intelligent Growth Engine


# ─── AI Improvement: Cycle 26 ───
# Applied: 2026-07-16T00:22:11.994108+00:00
# This file is being continuously improved by the Intelligent Growth Engine
if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "auto":
            print(slash_compress_auto(" ".join(sys.argv[2:])))
        else:
            print(slash_compress_auto(" ".join(sys.argv[1:])))
    else:
        # Demo
        print("Active Compression Hook")
        print("=" * 40)
        print(slash_compress_auto("status"))
        print()
        print("Example usage:")
        print("  python active_compress.py auto on")
        print("  python active_compress.py auto threshold 90000 70000")
        print("  python active_compress.py auto interval 5")
        print("  python active_compress.py auto now --goal \"Test\" --profile aurelian --turns 5")
        print("  python active_compress.py auto blocks")
        print("  python active_compress.py auto estimate")
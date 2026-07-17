"""
ctx_curation_tool.py — Context Curation as a First-Class Tool
==============================================================

NOT a skill. This is a registered tool that uses ``clarify`` to walk through
context curation decisions. Zero SKILL.md loading overhead — the handler
runs directly when invoked.

Registration:
    registry.register(
        name="ctx_curate",
        toolset="memory",
        schema={...},
        handler=handle_ctx_curate,
    )

The unified slash registry maps ``/ctx-curation`` → this handler directly,
bypassing the skill document loading system entirely.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schema — the model calls this with structured params
# ---------------------------------------------------------------------------

SCHEMA = {
    "name": "ctx_curate",
    "description": (
        "Walk through conversation context one category at a time, asking "
        "the user what to keep vs drop. Lightweight alternative to loading "
        "a full skill document — zero overhead, direct clarify calls."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "keep", "drop", "condense", "done", "status"],
                "description": (
                    "Start a curation session, respond to a prompt, or check status. "
                    "'start' begins a new pass. 'keep'/'drop'/'condense' answer the "
                    "current question. 'done' finishes. 'status' shows current session."
                ),
            },
            "category": {
                "type": "string",
                "enum": ["config_state", "observations", "history", "debug", "other"],
                "description": "Which category to curate. Only meaningful on 'start'.",
            },
            "note": {
                "type": "string",
                "description": "Optional note or reasoning for the decision.",
            },
        },
        "required": ["action"],
    },
}

# ---------------------------------------------------------------------------
# Per-session curation state
# ---------------------------------------------------------------------------

CURATION_CATEGORIES = [
    ("config_state", "Config/state — still active or stale?"),
    ("observations", "Observations — keep, condense to 1 line, or drop?"),
    ("history", "Old history — keep last N turns?"),
    ("debug", "Debug/ephemeral — drop all?"),
    ("other", "Anything else to address?"),
]

# Keyed by session_id
_sessions: dict[str, dict[str, Any]] = {}


def _get_or_create(session_id: str) -> dict[str, Any]:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "state": "idle",          # idle | active | done
            "current_category_idx": 0,
            "decisions": {},
            "started_at": None,
        }
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# Handler — called by the tool dispatch
# ---------------------------------------------------------------------------

def handle_ctx_curate(action: str, category: str = "", note: str = "",
                       task_id: str | None = None) -> str:
    """
    Tool handler for ctx_curate.

    Called by the model when it chooses to invoke this tool. Returns a
    JSON string that the model reads as the next instruction.
    """
    session_id = task_id or "_default"
    session = _get_or_create(session_id)

    if action == "start":
        session["state"] = "active"
        session["current_category_idx"] = 0
        session["decisions"] = {}
        import time
        session["started_at"] = time.time()

        if category:
            # User specified a category to start with
            for i, (cat, _) in enumerate(CURATION_CATEGORIES):
                if cat == category:
                    session["current_category_idx"] = i
                    break

        return _build_prompt(session)

    elif action == "status":
        if session["state"] == "idle":
            return json.dumps({
                "status": "idle",
                "message": "No active curation session. Use action='start' to begin.",
            })
        return json.dumps({
            "status": session["state"],
            "category": CURATION_CATEGORIES[session["current_category_idx"]][0],
            "decisions_made": len(session["decisions"]),
            "decisions": session["decisions"],
        })

    elif action in ("keep", "drop", "condense"):
        if session["state"] != "active":
            return json.dumps({
                "error": "No active curation session. Call action='start' first.",
            })

        cat_name, cat_question = CURATION_CATEGORIES[session["current_category_idx"]]
        session["decisions"][cat_name] = {
            "action": action,
            "note": note or "",
        }

        if action == "condense":
            result = f"Condensed: {cat_name}"
        elif action == "drop":
            result = f"Dropped: {cat_name}"
        else:
            result = f"Kept: {cat_name}"

        # Move to next category
        session["current_category_idx"] += 1

        if session["current_category_idx"] >= len(CURATION_CATEGORIES):
            session["state"] = "done"
            return _build_summary(session)
        else:
            return _build_prompt(session)

    elif action == "done":
        session["state"] = "done"
        return _build_summary(session)

    return json.dumps({
        "error": f"Unknown action: {action}",
        "valid_actions": ["start", "keep", "drop", "condense", "done", "status"],
    })


def _build_prompt(session: dict[str, Any]) -> str:
    """Build the next question for the user."""
    idx = session["current_category_idx"]
    if idx >= len(CURATION_CATEGORIES):
        session["state"] = "done"
        return _build_summary(session)

    cat_name, cat_question = CURATION_CATEGORIES[idx]

    prompt = (
        f"**[Context Curation — {cat_name}]**\n\n"
        f"{cat_question}\n\n"
        f"Options:\n"
        f"  • **keep** — preserve this category as-is\n"
        f"  • **drop** — remove this category from context\n"
        f"  • **condense** — reduce to 1-line summary\n"
        f"  • **done** — finish curation now\n\n"
        f"Reply with your choice (and optional note)."
    )
    return json.dumps({
        "prompt": prompt,
        "category": cat_name,
        "category_idx": idx,
        "total_categories": len(CURATION_CATEGORIES),
        "decisions_so_far": len(session["decisions"]),
    })


def _build_summary(session: dict[str, Any]) -> str:
    """Build the final curation summary."""
    decisions = session["decisions"]
    kept = [k for k, v in decisions.items() if v["action"] == "keep"]
    dropped = [k for k, v in decisions.items() if v["action"] == "drop"]
    condensed = [k for k, v in decisions.items() if v["action"] == "condense"]
    untouched = [cat for cat, _ in CURATION_CATEGORIES if cat not in decisions]

    lines = ["**✅ Context Curation Complete**\n"]
    if kept:
        lines.append(f"**Kept:** {', '.join(kept)}")
    if dropped:
        lines.append(f"**Dropped:** {', '.join(dropped)}")
    if condensed:
        lines.append(f"**Condensed:** {', '.join(condensed)}")
    if untouched:
        lines.append(f"**Skipped:** {', '.join(untouched)}")

    decisions_made = len(decisions)
    lines.append(f"\n_{decisions_made} categories processed._")

    summary_text = "\n".join(lines)

    return json.dumps({
        "status": "complete",
        "summary": summary_text,
        "decisions": decisions,
        "decisions_made": decisions_made,
    })


# ---------------------------------------------------------------------------
# Tool registration (called at import time)
# ---------------------------------------------------------------------------

def _check_requirements() -> bool:
    """Always available — no external dependencies."""
    return True


def _handler(args: dict[str, Any], task_id: str | None = None) -> str:
    """Wrapper that unpacks args and calls the handler."""
    return handle_ctx_curate(
        action=args.get("action", ""),
        category=args.get("category", ""),
        note=args.get("note", ""),
        task_id=task_id,
    )


# Register this tool
try:
    from tools.registry import registry

    registry.register(
        name="ctx_curate",
        toolset="memory",
        schema=SCHEMA,
        handler=_handler,
        check_fn=_check_requirements,
        description=(
            "Lightweight context curation — walk through categories one at "
            "a time deciding what to keep, drop, or condense. No skill doc "
            "overhead; direct clarify-style interaction."
        ),
        emoji="🧹",
    )
    logger.info("Registered ctx_curate tool (tool, not skill)")
except ImportError:
    logger.debug("tools.registry not available (dev mode)")
except Exception as e:
    logger.warning("Failed to register ctx_curate tool: %s", e)

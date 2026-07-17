"""
PATCH: toolsets.py — Auto-register every toolset as a /command
===============================================================

Adds a ``register_toolsets_as_commands()`` function that iterates the
TOOLSETS dict and registers each toolset as a /command in the unified
slash registry. The handler, when invoked, loads that toolset's tools
into the active session via the on_demand_tools module.

This is the "toolset-on-demand" pattern: all tool schemas are *imported*
at startup (so they exist in the tool registry), but they're excluded
from the system prompt until their /command is invoked.

New function added to toolsets.py:
  register_toolsets_as_commands(slash_registry=None, enabled_only=False)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_toolsets_as_commands(slash_registry=None, enabled_only: bool = False) -> int:
    """
    Register every toolset in TOOLSETS as a /command in the unified registry.

    Each toolset becomes a ``/toolset-name`` command that, when invoked,
    activates that toolset's tools for the current session.

    Args:
        slash_registry: SlashRegistry instance (from hermes_cli.slash_registry).
                        If None, tries to import it.
        enabled_only: If True, only register toolsets that are NOT default-off
                      or that the user has explicitly enabled.

    Returns:
        Number of toolsets registered.
    """
    if slash_registry is None:
        try:
            from hermes_cli.slash_registry import registry as slash_registry
        except ImportError:
            logger.warning("slash_registry not available — can't register toolset commands")
            return 0

    from toolsets import TOOLSETS, _DEFAULT_OFF_TOOLSETS

    # Which toolsets to skip (internal composite toolsets)
    _SKIP_TOOLSETS = {
        "hermes-cli", "hermes-cron", "hermes-telegram", "hermes-discord",
        "hermes-slack", "hermes-signal", "hermes-whatsapp", "hermes-api-server",
        "hermes-acp",
    }

    count = 0
    for ts_name, ts_def in sorted(TOOLSETS.items()):
        if ts_name in _SKIP_TOOLSETS:
            continue

        # Skip internal/composite toolsets
        description = ts_def.get("description", "")
        tools = ts_def.get("tools", []) if isinstance(ts_def, dict) else []
        includes = ts_def.get("includes", []) if isinstance(ts_def, dict) else []
        is_posture = ts_def.get("posture", False) if isinstance(ts_def, dict) else False

        if is_posture:
            continue

        # Skip empty toolsets
        if not tools and not includes:
            continue

        # Optionally skip default-off toolsets
        if enabled_only and ts_name in _DEFAULT_OFF_TOOLSETS:
            continue

        # Register in the unified registry
        slash_registry.register_toolset(
            ts_name=ts_name,
            description=description or f"Load {ts_name} tools",
            tools=tools + includes,  # rough estimate for display
            handler=None,  # handled by the generic toolset dispatcher
        )
        count += 1

    logger.info("Registered %d toolset commands", count)
    return count


# ---------------------------------------------------------------------------
# Standalone handler for /toolset-name invocations
# ---------------------------------------------------------------------------

def handle_toolset_command(command_name: str, agent=None, session_id: str | None = None) -> str:
    """
    Handle a user invoking /toolset-name.

    This is the generic handler called when any toolset /command fires.
    It resolves the toolset name, loads its tools, and injects them.

    Args:
        command_name: The command name without leading slash
                      (e.g. "nmap" for /nmap, "spotify" for /spotify)
        agent: The running AIAgent instance.
        session_id: Current session ID.

    Returns:
        User-facing status message.
    """
    from tools.on_demand_tools import enable_toolset_for_session

    return enable_toolset_for_session(
        command_name=command_name,
        source="toolset",
        agent=agent,
        session_id=session_id,
    )


# ============================================================================
# Integration hook for session startup
# ============================================================================
# To wire this into Hermes startup, add to agent initialization:
#
#   # In run_agent.py or cli.py after config is loaded:
#   try:
#       from toolsets_on_demand import register_toolsets_as_commands
#       from hermes_cli.slash_registry import registry
#       from hermes_cli.commands import rebuild_lookups
#       register_toolsets_as_commands(slash_registry=registry)
#       rebuild_lookups()
#   except Exception:
#       pass  # graceful degradation

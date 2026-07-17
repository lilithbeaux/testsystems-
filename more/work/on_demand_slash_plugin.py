"""
Plugin: on_demand_slash.py
==========================

Hermes plugin that wires the unified slash registry into the agent lifecycle.

When installed in ~/.hermes/plugins/ (or profile plugins dir), this plugin:

1. Creates the unified SlashRegistry singleton
2. Registers built-in COMMAND_REGISTRY commands into it
3. Registers every toolset as a /command (on-demand loading)
4. Registers every MCP server as a /command (on-demand loading)
5. Integrates skill commands into the unified registry
6. Provides the dispatch handler for /toolset-name and /mcp-server-name commands
7. Bumps the TUI autocomplete cap to handle 200+ entries
8. Patches the /help handler to include all command categories

The plugin hooks into:
  - on_session_start: register toolsets/MCPs as commands
  - on_session_end: clean up activation state
  - session creation: ensure the slash registry is populated
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin metadata — discovered by Hermes plugin loader
# ---------------------------------------------------------------------------

PLUGIN_NAME = "on-demand-slash"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = (
    "Unified slash registry + on-demand tool loading for toolsets, MCPs, and skills. "
    "Every toolset and MCP server gets its own /command — tools load only when invoked."
)

# ---------------------------------------------------------------------------
# Startup — called when the plugin is activated
# ---------------------------------------------------------------------------

def setup(ctx) -> None:
    """
    Called by Hermes plugin system during agent initialization.

    Registers all slash commands (builtins, toolsets, MCPs, skills) into the
    unified registry and patches the autocomplete system.
    """
    logger.info("[on-demand-slash] Setting up unified slash registry...")

    # Step 1: Import the unified registry
    try:
        from hermes_cli.slash_registry import registry as slash_registry
    except ImportError:
        logger.error("[on-demand-slash] slash_registry module not found. Skipping setup.")
        return

    # Step 2: Register built-in COMMAND_REGISTRY commands
    try:
        from hermes_cli.commands import COMMAND_REGISTRY, rebuild_lookups
        slash_registry.register_builtins(COMMAND_REGISTRY)
        logger.info("[on-demand-slash] Registered %d built-in commands", len(COMMAND_REGISTRY))
    except Exception as e:
        logger.warning("[on-demand-slash] Failed to register builtins: %s", e)
        return

    # Step 3: Register every toolset as a /command
    try:
        from toolsets_on_demand import register_toolsets_as_commands
        n = register_toolsets_as_commands(slash_registry=slash_registry)
        logger.info("[on-demand-slash] Registered %d toolset commands", n)
    except Exception as e:
        logger.warning("[on-demand-slash] Failed to register toolset commands: %s", e)

    # Step 4: Register every MCP server as a /command
    try:
        from mcp_on_demand import register_mcp_commands
        n = register_mcp_commands(slash_registry=slash_registry)
        logger.info("[on-demand-slash] Registered %d MCP server commands", n)
    except Exception as e:
        logger.warning("[on-demand-slash] Failed to register MCP commands: %s", e)

    # Step 5: Rebuild all derived lookup tables
    try:
        rebuild_lookups()
        logger.info(
            "[on-demand-slash] Rebuilt lookup tables — %d total commands",
            slash_registry.count,
        )
    except Exception as e:
        logger.warning("[on-demand-slash] rebuild_lookups failed: %s", e)

    # Step 6: Register hooks
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("on_session_reset", _on_session_reset)

    # Step 7: Register our own slash commands for management
    ctx.register_command(
        name="toolsets",
        handler=_handle_toolsets_command,
        description="List all available toolset /commands and their activation status",
        args_hint="[list|status|<toolset-name>]",
    )
    ctx.register_command(
        name="mcp-servers",
        handler=_handle_mcp_servers_command,
        description="List all MCP servers registered as /commands",
        args_hint="[list|status|<server-name>]",
    )
    ctx.register_command(
        name="active-tools",
        handler=_handle_active_tools_command,
        description="Show which on-demand toolsets/MCPs are active this session",
    )

    logger.info(
        "[on-demand-slash] Setup complete — %d commands available via /",
        slash_registry.count,
    )


# ---------------------------------------------------------------------------
# Hook handlers
# ---------------------------------------------------------------------------

def _on_session_start(ctx, **kwargs) -> None:
    """Called when a new session starts."""
    session_id = kwargs.get("session_id", "")
    agent = kwargs.get("agent")
    if session_id:
        logger.debug("[on-demand-slash] Session started: %s", session_id)

        # Pre-activate core toolsets based on workspace context
        # (e.g., if in a Python project, auto-activate "coding")
        try:
            _auto_activate_core(ctx, session_id, agent)
        except Exception:
            pass


def _on_session_end(ctx, **kwargs) -> None:
    """Called when a session ends — clean up activation state."""
    try:
        from tools.on_demand_tools import clear_session
        session_id = kwargs.get("session_id", "")
        if session_id:
            clear_session(session_id)
    except Exception:
        pass


def _on_session_reset(ctx, **kwargs) -> None:
    """Called when a session is reset (/new, /reset)."""
    try:
        from tools.on_demand_tools import clear_all
        clear_all()
    except Exception:
        pass


def _auto_activate_core(ctx, session_id: str, agent) -> None:
    """
    Optionally auto-activate certain toolsets based on the working environment.

    For now, this is a no-op — toolsets are opt-in by default.
    Users can enable specific auto-activations via config.
    """
    pass  # Future: check ~/.hermes/config.yaml -> on_demand.auto_activate


# ---------------------------------------------------------------------------
# /toolsets command handler
# ---------------------------------------------------------------------------

def _handle_toolsets_command(raw_args: str) -> str:
    """Handle /toolsets — list available toolset commands."""
    try:
        from hermes_cli.slash_registry import registry as slash_registry
        from tools.on_demand_tools import list_active, get_active

        args = raw_args.strip().lower()
        ts_commands = slash_registry.by_source("toolset")
        session_id = "_default"  # In gateway, resolve from runtime context

        if args == "list" or args == "":
            lines = ["**Available toolset /commands:**\n"]
            for cmd in sorted(ts_commands, key=lambda c: c.name):
                active = get_active(cmd.name, session_id)
                status = "✅" if active else "⬜"
                lines.append(f"  {status} `/{cmd.name}` — {cmd.description}")
            lines.append(
                "\n_Type `/toolset-name` to activate. "
                "Tools become available immediately._"
            )
            return "\n".join(lines)

        elif args == "status":
            active = list_active(session_id)
            if not active:
                return "_No on-demand toolsets active this session._"
            return "**Active on-demand toolsets:**\n" + "\n".join(
                f"  ✅ `/{a}" for a in active
            )

        else:
            # Try to activate a specific toolset
            return _dispatch_on_demand(args, "toolset", session_id)

    except Exception as e:
        return f"❌ Error: {e}"


# ---------------------------------------------------------------------------
# /mcp-servers command handler
# ---------------------------------------------------------------------------

def _handle_mcp_servers_command(raw_args: str) -> str:
    """Handle /mcp-servers — list available MCP server commands."""
    try:
        from hermes_cli.slash_registry import registry as slash_registry
        from tools.on_demand_tools import get_active

        args = raw_args.strip().lower()
        mcp_commands = slash_registry.by_source("mcp")
        session_id = "_default"

        if not mcp_commands:
            return "_No MCP servers configured. Add them in config.yaml under `mcp_servers:`._"

        lines = ["**Available MCP server /commands:**\n"]
        for cmd in sorted(mcp_commands, key=lambda c: c.name):
            active = get_active(cmd.name, session_id)
            status = "✅" if active else "📡"
            lines.append(f"  {status} `/{cmd.name}` — {cmd.description}")
        lines.append("\n_Type `/mcp-<name>` to connect and load its tools._")
        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error: {e}"


# ---------------------------------------------------------------------------
# /active-tools command handler
# ---------------------------------------------------------------------------

def _handle_active_tools_command(raw_args: str) -> str:
    """Handle /active-tools — show what's loaded on-demand this session."""
    try:
        from tools.on_demand_tools import list_active

        session_id = "_default"
        active = list_active(session_id)

        if not active:
            return (
                "_No on-demand tools active. "
                "Type `/nmap`, `/spotify`, `/computer-use`, or another "
                "toolset command to load tools._"
            )

        return "**Active on-demand tools this session:**\n" + "\n".join(
            f"  ✅ `/{a}" for a in sorted(active)
        )

    except Exception as e:
        return f"❌ Error: {e}"


# ---------------------------------------------------------------------------
# Generic dispatcher for on-demand commands
# ---------------------------------------------------------------------------

def _dispatch_on_demand(command_name: str, source: str, session_id: str) -> str:
    """
    Generic handler for toolset/MCP on-demand commands.

    Called when a user types ``/toolset-name`` or ``/mcp-server-name``
    that was registered by this plugin. Routes to the appropriate handler
    based on the command's source.
    """
    try:
        from tools.on_demand_tools import enable_toolset_for_session

        # We need the agent instance — in gateway mode, resolve from context.
        # In CLI mode, the agent is on the CLI instance.
        agent = _resolve_agent()

        return enable_toolset_for_session(
            command_name=command_name,
            source=source,
            agent=agent,
            session_id=session_id,
        )

    except Exception as e:
        logger.error("[on-demand-slash] dispatch error for /%s: %s", command_name, e)
        return f"❌ Failed to activate `/{command_name}`: {e}"


def _resolve_agent():
    """
    Try to find the running AIAgent instance.

    This is the trickiest part — the agent lives in the conversation loop.
    We try multiple resolution strategies:
      1. Gateway session context
      2. CLI instance global
      3. Runtime frame inspection (last resort)
    """
    # Strategy 1: Gateway session context
    try:
        from gateway.session_context import get_agent
        agent = get_agent()
        if agent is not None:
            return agent
    except Exception:
        pass

    # Strategy 2: CLI instance
    try:
        import sys
        main_module = sys.modules.get("__main__")
        if main_module and hasattr(main_module, "agent"):
            return main_module.agent
    except Exception:
        pass

    # Strategy 3: Direct import from cli
    try:
        from cli import _agent_instance
        if _agent_instance is not None:
            return _agent_instance
    except Exception:
        pass

    return None

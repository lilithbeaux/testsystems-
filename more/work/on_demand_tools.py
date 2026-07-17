"""
on_demand_tools.py — Runtime handler for on-demand tool loading
===============================================================

When a user invokes /toolset-name or /mcp-server-name, this module:
1. Determines which tools to activate
2. Injects them into the running agent's tool list
3. Updates the session state so subsequent turns see the new tools

The pattern: tools are always *registered* and *importable* — they're just
not in the system prompt / tool schema until their parent /command fires.

Usage:
    from tools.on_demand_tools import enable_toolset_for_session

    # Agent-side hook: when /nmap is typed
    result = enable_toolset_for_session(
        name="nmap",
        source="toolset",
        agent=agent_instance,
        session_id="...",
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache of what's been activated this session
# ---------------------------------------------------------------------------
# Maps session_id -> set of activated toolset/MCP names
_activated: dict[str, set[str]] = {}


def _get_tools_for_toolset(toolset_name: str) -> list[str]:
    """
    Return the list of tool names in a toolset.

    Delegates to toolsets.resolve_toolset() which handles includes.
    """
    try:
        from toolsets import resolve_toolset
        return resolve_toolset(toolset_name) or []
    except Exception:
        return []


def _get_tools_for_mcp(server_name: str) -> list[str]:
    """
    Return the list of tool names exposed by an MCP server.

    The MCP client keeps a mapping of server_name -> [tool_names].
    """
    try:
        from tools.mcp_tool import get_mcp_tool_names
        return get_mcp_tool_names(server_name) or []
    except Exception:
        return []


def _normalize_toolset_name(raw: str) -> str:
    """Normalize a command name back to the toolset key in TOOLSETS."""
    return raw.lower().replace("-", "_").lstrip("mcp_").lstrip("/")


def _get_mcp_server_config_names() -> list[str]:
    """Return list of configured MCP server names from config."""
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config() or {}
        mcp_cfg = cfg.get("mcp_servers", {})
        if isinstance(mcp_cfg, dict):
            return list(mcp_cfg.keys())
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Enablement logic
# ---------------------------------------------------------------------------

def enable_toolset_for_session(
    command_name: str,
    source: str,
    agent: Any = None,
    session_id: str | None = None,
) -> str:
    """
    Activate the tools for a toolset or MCP server.

    Called when a user invokes a /command with ``load_on_invoke=True``.

    Args:
        command_name: The /command name (without leading slash).
        source: "toolset" or "mcp".
        agent: The running AIAgent instance (needs access to tool registry).
        session_id: Current session ID for tracking activations.

    Returns:
        A human-readable status message.
    """
    if not session_id:
        session_id = "_default"

    # Track activations per session
    if session_id not in _activated:
        _activated[session_id] = set()

    if command_name in _activated[session_id]:
        return f"⚠️  `/{command_name}` already active this session."

    # Resolve tool names
    if source == "toolset":
        ts_key = _normalize_toolset_name(command_name)
        tool_names = _get_tools_for_toolset(ts_key)
        if not tool_names:
            return f"❌ Toolset `{ts_key}` has no tools (or not found)."
    elif source == "mcp":
        # Derive server name: /mcp-filesystem -> "filesystem"
        server_name = command_name.replace("mcp-", "", 1).replace("-", "_")
        try:
            tool_names = _inject_mcp_server_tools(server_name)
        except Exception as e:
            return f"❌ Failed to connect MCP server `{server_name}`: {e}"
        if not tool_names:
            return f"❌ MCP server `{server_name}` returned no tools."
    else:
        return f"❌ Unknown source: {source}"

    # Inject tools into the running agent's tool list
    if agent is not None:
        _inject_tools_into_agent(agent, tool_names, command_name, source)

    # Mark activated
    _activated[session_id].add(command_name)

    tool_list = "\n".join(f"  • `{t}`" for t in sorted(tool_names))
    return (
        f"✅ **{command_name}** activated ({len(tool_names)} tools loaded).\n"
        f"{tool_list}\n\n"
        f"_These tools are now available for the rest of this session._"
    )


def _inject_tools_into_agent(
    agent: Any,
    tool_names: list[str],
    command_name: str,
    source: str,
) -> None:
    """
    Add tool names to the agent's enabled tool list.

    The agent's ``tool_schemas`` dict stores the schemas of every registered
    tool. We add the schema for each newly enabled tool, then re-build the
    tool list the LLM sees on the next turn.

    This works because ``tool.registry`` already has every tool registered
    at import time — we just need to add the names to the enabled set.
    """
    if hasattr(agent, "enabled_tool_names"):
        # AIAgent stores enabled tools as a set
        existing = agent.enabled_tool_names
        if isinstance(existing, set):
            existing.update(tool_names)
        elif isinstance(existing, list):
            agent.enabled_tool_names = list(set(existing) | set(tool_names))

    # Some agent implementations use a dict of name->schema
    if hasattr(agent, "tool_schemas") and isinstance(agent.tool_schemas, dict):
        from tools.registry import registry as tool_registry
        for name in tool_names:
            schema = tool_registry.get_schema(name)
            if schema and name not in agent.tool_schemas:
                agent.tool_schemas[name] = schema

    # Log what happened
    logger.info(
        "[on-demand] %s '%s' injected %d tools into agent %s",
        source, command_name, len(tool_names), id(agent),
    )


def _inject_mcp_server_tools(server_name: str) -> list[str]:
    """
    Force-connect an MCP server and return its tool names.

    The first invocation discovers and registers the server's tools into the
    global tool registry. Subsequent calls return the cached names.
    """
    try:
        from tools.mcp_tool import (
            MCPConnectionManager,
            get_registered_mcp_tool_names as _get_registered,
        )

        # Check if already connected
        existing = _get_registered(server_name)
        if existing:
            return existing

        # Connect and discover
        mgr = MCPConnectionManager()
        connected = mgr.connect_server(server_name)
        if connected:
            return _get_registered(server_name) or []

    except ImportError:
        # Fallback: try to use mcp_tool module directly
        try:
            from tools.mcp_tool import _mcp_connection_manager
            import anyio
            conn = anyio.run(_mcp_connection_manager.connect_server, server_name)
            if conn:
                from tools.mcp_tool import get_mcp_tool_names
                return get_mcp_tool_names(server_name) or []
        except Exception:
            raise

    return []


# ---------------------------------------------------------------------------
# Cleanup / session lifecycle
# ---------------------------------------------------------------------------

def clear_session(session_id: str) -> None:
    """Remove activation state when a session ends."""
    _activated.pop(session_id, None)


def clear_all() -> None:
    """Reset all activation state."""
    _activated.clear()


def get_active(command_name: str, session_id: str | None = None) -> bool:
    """Check if a command's tools are active."""
    sid = session_id or "_default"
    return command_name in _activated.get(sid, set())


def list_active(session_id: str | None = None) -> list[str]:
    """List all on-demand commands active in a session."""
    sid = session_id or "_default"
    return sorted(_activated.get(sid, set()))

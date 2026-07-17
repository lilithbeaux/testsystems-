"""
PATCH: mcp_on_demand.py — Auto-register MCP servers as /commands
=================================================================

Every configured MCP server gets a ``/mcp-<server-name>`` command that
connects the server and loads its tools on first invocation.

This is the "MCP-on-demand" pattern: MCP servers are NOT connected at
startup. Instead, they're registered as /commands in the slash registry.
When the user types ``/mcp-filesystem``, the handler connects the server,
discovers its tools, and injects them into the running session.

Usage in agent startup:
    from mcp_on_demand import register_mcp_commands
    from hermes_cli.slash_registry import registry
    from hermes_cli.commands import rebuild_lookups
    register_mcp_commands(slash_registry=registry)
    rebuild_lookups()
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_configured_mcp_servers() -> list[tuple[str, str]]:
    """
    Return list of (server_name, description) for configured MCP servers.

    Reads from ~/.hermes/config.yaml -> mcp_servers key.
    """
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config() or {}
        mcp_cfg = cfg.get("mcp_servers", {})
        if not isinstance(mcp_cfg, dict):
            return []
        servers = []
        for name, config in mcp_cfg.items():
            if isinstance(config, dict):
                desc = config.get("description", "") or f"MCP server: {name}"
                servers.append((name, desc))
            else:
                servers.append((name, f"MCP server: {name}"))
        return servers
    except Exception:
        return []


def register_mcp_commands(slash_registry=None) -> int:
    """
    Register every configured MCP server as a /mcp-<name> slash command.

    Args:
        slash_registry: SlashRegistry instance. If None, imports it.

    Returns:
        Number of MCP servers registered.
    """
    if slash_registry is None:
        try:
            from hermes_cli.slash_registry import registry as slash_registry
        except ImportError:
            logger.warning("slash_registry not available — can't register MCP commands")
            return 0

    servers = get_configured_mcp_servers()
    count = 0
    for name, desc in servers:
        slash_registry.register_mcp_server(
            server_name=name,
            description=desc,
        )
        count += 1

    logger.info("Registered %d MCP server commands", count)
    return count


def handle_mcp_command(command_name: str, agent=None, session_id: str | None = None) -> str:
    """Handle a user invoking /mcp-<name>.

    Connects the MCP server, discovers its tools, and injects them
    into the running agent session.
    """
    from tools.on_demand_tools import enable_toolset_for_session

    return enable_toolset_for_session(
        command_name=command_name,
        source="mcp",
        agent=agent,
        session_id=session_id,
    )

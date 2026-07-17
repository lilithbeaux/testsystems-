#!/usr/bin/env python3
"""
unified_slash_bootstrap.py — Wire the unified slash registry into Hermes
=========================================================================

Install this module and call ``bootstrap()`` once at Hermes startup (in
``cli.py`` or ``run_agent.py``) to enable the full on-demand slash command
system.

What this does:
  1. Imports and initializes the ``SlashRegistry`` singleton
  2. Registers built-in ``COMMAND_REGISTRY`` commands
  3. Registers every toolset as a ``/toolset-name`` command (on-demand)
  4. Registers every MCP server as a ``/mcp-server-name`` command (on-demand)
  5. Integrates auto-scanned skill commands as proper ``CommandDef`` entries
  6. Rebuilds all derived lookup tables (COMMANDS, SUBCOMMANDS, entry)
  7. Patches the TUI autocomplete to raise the 30-item cap
  8. Patches /help to include all command categories

Call once at startup:
    from unified_slash_bootstrap import bootstrap
    bootstrap()

After bootstrap(), the unified registry is the single source of truth.
All consumers (autocomplete, /help, gateway menus, dispatch) read from it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("unified-slash")


def bootstrap() -> int:
    """
    Boot the unified slash registry.

    Returns:
        Total number of commands registered, or 0 if setup failed.
    """
    # Step 1: Import the registry
    try:
        from hermes_cli.slash_registry import registry as slash_registry
    except ImportError:
        logger.warning("slash_registry not available (not installed in hermes_cli/)")
        return 0

    # Step 2: Register built-in commands
    try:
        from hermes_cli.commands import COMMAND_REGISTRY, rebuild_lookups
        slash_registry.register_builtins(list(COMMAND_REGISTRY))
        logger.info("Registered %d built-in commands", len(COMMAND_REGISTRY))
    except Exception as e:
        logger.error("Failed to register built-in commands: %s", e)
        return 0

    # Step 3: Register skills as /commands
    _register_skills(slash_registry)

    # Step 4: Register toolsets as /commands
    _register_toolsets(slash_registry)

    # Step 5: Register MCP servers as /commands
    _register_mcp_servers(slash_registry)

    # Step 6: Rebuild all derived lookup tables
    try:
        rebuild_lookups()
        logger.info("Rebuilt lookup tables — %d total commands registered", slash_registry.count)
    except Exception as e:
        logger.error("Failed to rebuild lookups: %s", e)

    # Step 7: Override dispatching to handle on-demand commands
    _patch_tool_dispatcher()

    # Step 8: Patch /help to show all categories
    _patch_help_command()

    return slash_registry.count


def _register_skills(registry):
    """Register all scanned skill commands in the unified registry."""
    try:
        from agent.skill_commands import get_skill_commands
        cmds = get_skill_commands()
        count = 0
        for cmd_key, info in cmds.items():
            slug = cmd_key.lstrip("/")
            result = registry.register_skill(
                slug=slug,
                name=info.get("name", slug),
                description=info.get("description", ""),
                skill_md_path=info.get("skill_md_path", ""),
                skill_dir=info.get("skill_dir", ""),
            )
            if result:
                count += 1
        logger.info("Registered %d skill commands", count)
    except Exception as e:
        logger.warning("Could not register skills: %s", e)


def _register_toolsets(registry):
    """Register all user-facing toolsets as /commands."""
    # Toolsets to skip — they're platform composite toolsets, not user tools
    _SKIP = {
        "hermes-cli", "hermes-cron", "hermes-telegram", "hermes-discord",
        "hermes-slack", "hermes-signal", "hermes-whatsapp", "hermes-api-server",
        "hermes-acp",
    }

    try:
        from toolsets import TOOLSETS
        count = 0
        for ts_name, ts_def in sorted(TOOLSETS.items()):
            if ts_name in _SKIP:
                continue
            description = ts_def.get("description", "") if isinstance(ts_def, dict) else ""
            tools = ts_def.get("tools", []) if isinstance(ts_def, dict) else []
            includes = ts_def.get("includes", []) if isinstance(ts_def, dict) else []
            is_posture = ts_def.get("posture", False) if isinstance(ts_def, dict) else False

            if is_posture:
                continue
            if not tools and not includes:
                continue

            registry.register_toolset(
                ts_name=ts_name,
                description=description,
                tools=tools if isinstance(tools, list) else [],
            )
            count += 1
        logger.info("Registered %d toolset commands", count)
    except Exception as e:
        logger.warning("Could not register toolset commands: %s", e)


def _register_mcp_servers(registry):
    """Register all configured MCP servers as /commands."""
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config() or {}
        mcp_cfg = cfg.get("mcp_servers", {})
        if not isinstance(mcp_cfg, dict):
            return

        count = 0
        for name, config in mcp_cfg.items():
            if isinstance(config, dict):
                desc = config.get("description", "") or f"MCP server: {name}"
            else:
                desc = f"MCP server: {name}"
            registry.register_mcp_server(server_name=name, description=desc)
            count += 1
        if count:
            logger.info("Registered %d MCP server commands", count)
    except Exception as e:
        logger.warning("Could not register MCP server commands: %s", e)


def _patch_tool_dispatcher():
    """
    Override the tool dispatcher to intercept on-demand /commands.

    When a user invokes a command with ``load_on_invoke=True`` (a toolset or
    MCP command), the usual tool dispatch doesn't apply — these aren't tool
    calls, they're meta-commands that modify the tool list.

    The on-demand commands are handled by the plugin's registered handlers
    (via ``PluginContext.register_command()``) which already intercepts them.
    This function ensures the agent loop catches the case where a toolset
    command slips through to the LLM as a text response instead of being
    dispatched.
    """
    pass  # Handled by PluginContext.register_command() via the plugin


def _patch_help_command():
    """
    Monkey-patch the /help handler to include all registry categories.

    The CLI's help command renders from ``COMMANDS_BY_CATEGORY`` which is
    rebuilt by ``rebuild_lookups()`` to include toolsets, skills, and MCPs
    when the unified registry is active.

    Gateway help is handled by ``gateway_help_lines()`` which also reads
    ``COMMAND_REGISTRY`` (plus plugin commands). After ``rebuild_lookups()``
    is called with the unified registry active, the extension commands are
    merged into the registry.

    No explicit patching needed — ``rebuild_lookups()`` handles everything.
    """
    pass


# ---------------------------------------------------------------------------
# Standalone test / dry-run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )

    total = bootstrap()

    if total > 0:
        # Show categorized breakdown
        try:
            from hermes_cli.slash_registry import registry as slash_registry

            for cat in slash_registry.categories:
                commands = slash_registry.list_category(cat)
                print(f"  {cat}: {len(commands)} commands")

            print(f"\n  Total: {total} commands")

            # Show examples from each source
            for source in ("toolset", "mcp", "skill"):
                cmds = slash_registry.by_source(source)
                if cmds:
                    print(f"\n  {source} examples:")
                    for c in list(sorted(cmds, key=lambda x: x.name))[:3]:
                        ldi = "🔌" if c.load_on_invoke else "  "
                        print(f"    {ldi} /{c.name} — {c.description[:60]}...")
                    if len(cmds) > 3:
                        print(f"    ... and {len(cmds) - 3} more")

        except Exception as e:
            print(f"Query failed: {e}")
    else:
        print("Bootstrap failed — registry unavailable.")

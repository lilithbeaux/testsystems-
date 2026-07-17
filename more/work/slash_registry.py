"""
slash_registry.py — Unified Slash Command Registry
===================================================

Replaces the four parallel registration paths (built-in, skill, plugin, bundle)
with a single dynamic registry. Adds the two missing paths: toolset commands
and MCP server commands.

Every entity that wants a /command registers into this one place. All consumers
(autocomplete, /help, gateway menus, dispatch) read from the same source.

Usage:
    from hermes_cli.slash_registry import registry

    # Register any entity as a slash command
    registry.register(
        name="nmap",
        description="Load nmap + masscan network reconnaissance tools",
        category="Toolsets",
        source="toolset",
        args_hint="[scan target]",
        handler=enable_toolset_handler,   # callable(raw_args: str) -> str
    )

    # Rebuild derived lookup tables
    registry.rebuild()
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extended CommandDef — adds source tracking + optional handler
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandDef:
    """Definition of a single slash command — extended for unified registry."""

    name: str                           # canonical name without slash
    description: str                    # human-readable description
    category: str                       # "Session", "Configuration", "Toolsets", etc.
    source: str = "builtin"             # builtin | skill | plugin | bundle | toolset | mcp
    aliases: tuple[str, ...] = ()
    args_hint: str = ""
    subcommands: tuple[str, ...] = ()
    cli_only: bool = False
    gateway_only: bool = False
    gateway_config_gate: str | None = None

    # New fields for on-demand tool loading
    load_on_invoke: bool = False        # True = tools only appear when /cmd invoked
    handler: Callable[[str], str | None] | None = None  # invoked when user types /cmd


# ---------------------------------------------------------------------------
# The unified registry
# ---------------------------------------------------------------------------

class SlashRegistry:
    """
    Single source of truth for all slash commands.

    Four registration methods mirror the four original sources, but they all
    land in the same internal dict. Two new methods cover toolsets and MCPs.

    Call ``rebuild()`` after any batch of registrations to regenerate the
    derived lookup tables (``COMMANDS``, ``COMMANDS_BY_CATEGORY``,
    ``SUBCOMMANDS``, ``_COMMAND_LOOKUP``) that the rest of Hermes reads.
    """

    def __init__(self):
        self._entries: dict[str, CommandDef] = {}  # canonical name -> CommandDef
        self._aliases: dict[str, str] = {}          # alias -> canonical name
        self._frozen: bool = False                  # builtins locked after init
        self._version: int = 0                      # bump on each rebuild

        # Derived tables — rebuilt by rebuild()
        self.by_name: dict[str, CommandDef] = {}
        """Maps every name and alias to its CommandDef (like old _COMMAND_LOOKUP)."""

        self.commands: dict[str, str] = {}
        """Flat ``{"/cmd": description}`` (like old COMMANDS)."""

        self.by_category: dict[str, dict[str, str]] = {}
        """Categorized commands (like old COMMANDS_BY_CATEGORY)."""

        self.subcommands: dict[str, list[str]] = {}
        """``{"/cmd": ["sub1", "sub2"]}`` (like old SUBCOMMANDS)."""

        self.gateway_known: set[str] = set()
        """Names dispatchable from gateway platforms."""

        self.categories: list[str] = []
        """Ordered list of category names for menu rendering."""

    # ------------------------------------------------------------------ 
    # Registration
    # ------------------------------------------------------------------

    def register(self, cmd: CommandDef) -> None:
        """Register a single CommandDef."""
        name = cmd.name.lower().strip()
        if not name:
            logger.warning("Attempted to register command with empty name")
            return

        if name in self._entries:
            logger.debug("Overwriting existing command /%s", name)

        self._entries[name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias.lower().strip()] = name

    def register_builtins(self, builtin_list: list[CommandDef]) -> None:
        """Register the static COMMAND_REGISTRY built-ins."""
        for cmd in builtin_list:
            self.register(cmd)
        self._frozen = True

    def register_skill(self, slug: str, name: str, description: str,
                       skill_md_path: str, skill_dir: str) -> str | None:
        """Register a skill as a /command. Returns the /slug or None."""
        cmd_name = slug.lstrip("/").lower()
        if not cmd_name:
            return None
        cmd = CommandDef(
            name=cmd_name,
            description=description or f"Invoke the {name} skill",
            category="Skills",
            source="skill",
            load_on_invoke=False,  # skills load content, not tools
        )
        self.register(cmd)
        return f"/{cmd_name}"

    def register_toolset(self, ts_name: str, description: str,
                         tools: list[str], handler: Callable | None = None) -> None:
        """Register a toolset as an on-demand /command."""
        cmd = CommandDef(
            name=ts_name.lower().replace("_", "-"),
            description=description or f"Load {ts_name} tools",
            category="Toolsets",
            source="toolset",
            args_hint="",
            load_on_invoke=True,
            handler=handler,
        )
        self.register(cmd)

    def register_mcp_server(self, server_name: str, description: str,
                            handler: Callable | None = None) -> None:
        """Register an MCP server as an on-demand /command."""
        cmd = CommandDef(
            name=f"mcp-{server_name.lower().replace('_', '-')}",
            description=description or f"Connect MCP server: {server_name}",
            category="MCP Servers",
            source="mcp",
            args_hint="",
            load_on_invoke=True,
            handler=handler,
        )
        self.register(cmd)

    def register_plugin(self, name: str, handler: Callable,
                        description: str = "", args_hint: str = "") -> bool:
        """Register a plugin command. Returns False on conflict."""
        cmd_name = name.lower().lstrip("/").replace(" ", "-")
        if not cmd_name:
            return False
        if cmd_name in self._entries and self._entries[cmd_name].source == "builtin":
            logger.warning("Plugin command '/%s' conflicts with built-in. Skipping.", cmd_name)
            return False
        cmd = CommandDef(
            name=cmd_name,
            description=description or "Plugin command",
            category="Plugins",
            source="plugin",
            args_hint=args_hint,
            load_on_invoke=False,
            handler=handler,
        )
        self.register(cmd)
        return True

    # ------------------------------------------------------------------ 
    # Query
    # ------------------------------------------------------------------

    def get(self, name: str) -> CommandDef | None:
        """Resolve a command name or alias to its CommandDef."""
        key = name.lower().lstrip("/")
        if key in self.by_name:
            return self.by_name[key]
        if key in self._entries:
            return self._entries[key]
        return None

    def resolve(self, name: str) -> CommandDef | None:
        """Same as get() — accepts leading slash or not."""
        return self.get(name)

    def is_gateway_known(self, name: str | None) -> bool:
        return name and name.lower().lstrip("/") in self.gateway_known

    def list_category(self, category: str) -> list[CommandDef]:
        return [
            cmd for cmd in self._entries.values()
            if cmd.category.lower() == category.lower()
        ]

    def by_source(self, source: str) -> list[CommandDef]:
        return [cmd for cmd in self._entries.values() if cmd.source == source]

    @property
    def all(self) -> list[CommandDef]:
        return list(self._entries.values())

    @property
    def count(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------ 
    # Derived table rebuild
    # ------------------------------------------------------------------

    def rebuild(self) -> None:
        """
        Regenerate all derived lookup tables from current _entries.

        Call after any batch of registrations to keep the dicts that
        /help, autocomplete, gateway dispatch, and CLI rendering read.
        """
        # Reset
        self.by_name = {}
        self.commands = {}
        self.by_category = {}
        self.subcommands = {}
        self.gateway_known = set()
        self.categories = []

        cat_order: list[str] = []
        cat_seen: set[str] = set()

        for cmd in self._entries.values():
            # by_name includes every name + alias
            self.by_name[cmd.name] = cmd
            for alias in cmd.aliases:
                self.by_name[alias] = cmd

            # commands (CLI help rendering)
            if not cmd.gateway_only:
                desc = self._build_description(cmd)
                self.commands[f"/{cmd.name}"] = desc
                for alias in cmd.aliases:
                    self.commands[f"/{alias}"] = f"{cmd.description} (alias for /{cmd.name})"

            # by_category
            if not cmd.gateway_only:
                cat = cmd.category
                if cat not in self.by_category:
                    self.by_category[cat] = {}
                self.by_category[cat][f"/{cmd.name}"] = self.commands.get(
                    f"/{cmd.name}", cmd.description
                )
                for alias in cmd.aliases:
                    self.by_category[cat][f"/{alias}"] = self.commands.get(
                        f"/{alias}", f"{cmd.description} (alias for /{cmd.name})"
                    )
                if cat not in cat_seen:
                    cat_seen.add(cat)
                    cat_order.append(cat)

            # subcommands
            if cmd.subcommands:
                self.subcommands[f"/{cmd.name}"] = list(cmd.subcommands)

            # gateway known
            if not cmd.cli_only or cmd.gateway_config_gate:
                self.gateway_known.add(cmd.name)
                self.gateway_known.update(cmd.aliases)

        self.categories = cat_order
        self._version += 1

    # ------------------------------------------------------------------ 
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_description(cmd: CommandDef) -> str:
        if cmd.args_hint:
            return f"{cmd.description} (usage: /{cmd.name} {cmd.args_hint})"
        return cmd.description

    def __repr__(self) -> str:
        return f"<SlashRegistry: {len(self._entries)} commands v{self._version}>"


# ---------------------------------------------------------------------------
# Module-level singleton (imported everywhere else)
# ---------------------------------------------------------------------------

registry = SlashRegistry()

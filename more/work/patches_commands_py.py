"""
PATCH: hermes_cli/commands.py
==============================

Changes needed to make COMMAND_REGISTRY extensible and integrate
with the unified slash_registry module.

Apply these patches in order. Each patch_ commands shows the old_string
and new_string for use with the patch tool.
"""

# ============================================================================
# PATCH 1: Add `source` and `handler` fields to CommandDef
# ============================================================================
# OLD:
# @dataclass(frozen=True)
# class CommandDef:
#     name: str
#     description: str
#     category: str
#     aliases: tuple[str, ...] = ()
#     args_hint: str = ""
#     subcommands: tuple[str, ...] = ()
#     cli_only: bool = False
#     gateway_only: bool = False
#     gateway_config_gate: str | None = None
#
# NEW:
# @dataclass(frozen=True)
# class CommandDef:
#     name: str
#     description: str
#     category: str
#     source: str = "builtin"            # NEW — tracks origin
#     aliases: tuple[str, ...] = ()
#     args_hint: str = ""
#     subcommands: tuple[str, ...] = ()
#     cli_only: bool = False
#     gateway_only: bool = False
#     gateway_config_gate: str | None = None
#     load_on_invoke: bool = False       # NEW — on-demand loading
#     handler: Callable[[str], str | None] | None = None  # NEW — dispatch hook

patch_1 = {
    "path": "/opt/hermes-agent/hermes_cli/commands.py",
    "old_string": """@dataclass(frozen=True)
class CommandDef:
    \"\"\"Definition of a single slash command.\"\"\"

    name: str                          # canonical name without slash: \"background\"
    description: str                   # human-readable description
    category: str                      # \"Session\", \"Configuration\", etc.
    aliases: tuple[str, ...] = ()      # alternative names: (\"bg\",)
    args_hint: str = \"\"                # argument placeholder: \"<prompt>\", \"[name]\"
    subcommands: tuple[str, ...] = ()  # tab-completable subcommands
    cli_only: bool = False             # only available in CLI
    gateway_only: bool = False         # only available in gateway/messaging
    gateway_config_gate: str | None = None  # config dotpath; when truthy, overrides cli_only for gateway""",
    "new_string": """@dataclass(frozen=True)
class CommandDef:
    \"\"\"Definition of a single slash command.\"\"\"

    name: str                          # canonical name without slash: \"background\"
    description: str                   # human-readable description
    category: str                      # \"Session\", \"Configuration\", etc.
    source: str = \"builtin\"            # builtin | skill | plugin | bundle | toolset | mcp
    aliases: tuple[str, ...] = ()      # alternative names: (\"bg\",)
    args_hint: str = \"\"                # argument placeholder: \"<prompt>\", \"[name]\"
    subcommands: tuple[str, ...] = ()  # tab-completable subcommands
    cli_only: bool = False             # only available in CLI
    gateway_only: bool = False         # only available in gateway/messaging
    gateway_config_gate: str | None = None  # config dotpath; when truthy, overrides cli_only for gateway
    load_on_invoke: bool = False       # True = tools load only when /cmd is invoked
    handler: Callable[[str], str | None] | None = None  # dispatch hook invoked on /cmd""",
}

# ============================================================================
# PATCH 2: Add COMMAND_REGISTRY_EXTENSIONS and rebuild_lookups()
# ============================================================================
# After the static COMMAND_REGISTRY list, add a mutable extension list and
# a function to rebuild all derived tables from the merged list.

patch_2 = {
    "path": "/opt/hermes-agent/hermes_cli/commands.py",
    "old_string": """# ---------------------------------------------------------------------------
# Derived lookups -- rebuilt once at import time, refreshed by rebuild_lookups()
# ---------------------------------------------------------------------------""",
    "new_string": """# ---------------------------------------------------------------------------
# Extension registry — toolsets, MCPs, and other dynamic commands register here
# ---------------------------------------------------------------------------

COMMAND_REGISTRY_EXTENSIONS: list[CommandDef] = []
\"\"\"Mutable extension list for dynamically-registered commands.

Toolsets, MCP servers, plugin commands, and any other entity that wants
a /command appends to this list. Call ``rebuild_lookups()`` afterward to
regenerate all derived tables.
\"\"\"


def rebuild_lookups() -> None:
    \"\"\"Rebuild all derived lookup tables from COMMAND_REGISTRY + extensions.

    Call after modifying ``COMMAND_REGISTRY_EXTENSIONS`` (or after any
    skill/toolset/MCP registration pass) to refresh the dicts that
    ``/help``, autocomplete, and gateway dispatch read from.
    \"\"\"
    # Merge static + dynamic entries
    _all_commands = list(COMMAND_REGISTRY) + COMMAND_REGISTRY_EXTENSIONS

    global _COMMAND_LOOKUP, COMMANDS, COMMANDS_BY_CATEGORY, SUBCOMMANDS
    global GATEWAY_KNOWN_COMMANDS, _GATEWAY_KNOWN_COMMANDS_SET

    _COMMAND_LOOKUP = {}
    for cmd in _all_commands:
        _COMMAND_LOOKUP[cmd.name] = cmd
        for alias in cmd.aliases:
            _COMMAND_LOOKUP[alias] = cmd

    # COMMANDS — flat dict
    COMMANDS.clear()
    for cmd in _all_commands:
        if not cmd.gateway_only:
            COMMANDS[f\"/{cmd.name}\"] = _build_description(cmd)
            for alias in cmd.aliases:
                COMMANDS[f\"/{alias}\"] = f\"{cmd.description} (alias for /{cmd.name})\"

    # COMMANDS_BY_CATEGORY — categorized
    COMMANDS_BY_CATEGORY.clear()
    for cmd in _all_commands:
        if not cmd.gateway_only:
            cat = COMMANDS_BY_CATEGORY.setdefault(cmd.category, {})
            cat[f\"/{cmd.name}\"] = COMMANDS.get(f\"/{cmd.name}\", cmd.description)
            for alias in cmd.aliases:
                cat[f\"/{alias}\"] = COMMANDS.get(
                    f\"/{alias}\", f\"{cmd.description} (alias for /{cmd.name})\"
                )

    # SUBCOMMANDS
    SUBCOMMANDS.clear()
    for cmd in _all_commands:
        if cmd.subcommands:
            SUBCOMMANDS[f\"/{cmd.name}\"] = list(cmd.subcommands)

    # GATEWAY_KNOWN_COMMANDS
    _gateway_set = set()
    for cmd in _all_commands:
        if not cmd.cli_only or cmd.gateway_config_gate:
            _gateway_set.add(cmd.name)
            _gateway_set.update(cmd.aliases)
    _GATEWAY_KNOWN_COMMANDS_SET = _gateway_set
    GATEWAY_KNOWN_COMMANDS = frozenset(_gateway_set)


# ---------------------------------------------------------------------------
# Derived lookups -- rebuilt once at import time, refreshed by rebuild_lookups()
# ---------------------------------------------------------------------------""",
}

# ============================================================================
# PATCH 3: Add rebuild_lookups() call at the end of module init
# ============================================================================
# Replace the old standalone dict building loops with a call to rebuild_lookups()

patch_3 = {
    "path": "/opt/hermes-agent/hermes_cli/commands.py",
    "old_string": """# Backwards-compatible flat dict: \"/command\" -> description
COMMANDS: dict[str, str] = {}
for _cmd in COMMAND_REGISTRY:
    if not _cmd.gateway_only:
        COMMANDS[f\"/{_cmd.name}\"] = _build_description(_cmd)
        for _alias in _cmd.aliases:
            COMMANDS[f\"/{_alias}\"] = f\"{_cmd.description} (alias for /{_cmd.name})\"

# Backwards-compatible categorized dict
COMMANDS_BY_CATEGORY: dict[str, dict[str, str]] = {}
for _cmd in COMMAND_REGISTRY:
    if not _cmd.gateway_only:
        _cat = COMMANDS_BY_CATEGORY.setdefault(_cmd.category, {})
        _cat[f\"/{_cmd.name}\"] = COMMANDS[f\"/{_cmd.name}\"]
        for _alias in _cmd.aliases:
            _cat[f\"/{_alias}\"] = COMMANDS[f\"/{_alias}\"]

# Subcommands lookup: \"/cmd\" -> [\"sub1\", \"sub2\", ...]
SUBCOMMANDS: dict[str, list[str]] = {}
for _cmd in COMMAND_REGISTRY:
    if _cmd.subcommands:
        SUBCOMMANDS[f\"/{_cmd.name}\"] = list(_cmd.subcommands)""",
    "new_string": """# Backwards-compatible flat dict: \"/command\" -> description
COMMANDS: dict[str, str] = {}
# Backwards-compatible categorized dict
COMMANDS_BY_CATEGORY: dict[str, dict[str, str]] = {}
# Subcommands lookup: \"/cmd\" -> [\"sub1\", \"sub2\", ...]
SUBCOMMANDS: dict[str, list[str]] = {}

# Build all derived tables from COMMAND_REGISTRY + extensions
rebuild_lookups()""",
}

# ============================================================================
# PATCH 4: Update GATEWAY_KNOWN_COMMANDS derivation
# ============================================================================
# Replace the old static frozenset derivation to use rebuild_lookups state

patch_4 = {
    "path": "/opt/hermes-agent/hermes_cli/commands.py",
    "old_string": """# Set of all command names + aliases recognized by the gateway.
# Includes config-gated commands so the gateway can dispatch them
# (the handler checks the config gate at runtime).
GATEWAY_KNOWN_COMMANDS: frozenset[str] = frozenset(
    name
    for cmd in COMMAND_REGISTRY
    if not cmd.cli_only or cmd.gateway_config_gate
    for name in (cmd.name, *cmd.aliases)
)""",
    "new_string": """# Set of all command names + aliases recognized by the gateway.
# Includes config-gated commands so the gateway can dispatch them
# (the handler checks the config gate at runtime).
# Built by rebuild_lookups() — kept as a module-level variable for
# backwards compatibility.
_GATEWAY_KNOWN_COMMANDS_SET: set[str] = set()
GATEWAY_KNOWN_COMMANDS: frozenset[str] = frozenset()""",
}

# ============================================================================
# PATCH 5: Fix is_gateway_known_command to include toolset/MCP commands
# ============================================================================

patch_5 = {
    "path": "/opt/hermes-agent/hermes_cli/commands.py",
    "old_string": """def is_gateway_known_command(name: str | None) -> bool:
    \"\"\"Return True if ``name`` resolves to a gateway-dispatchable slash command.

    This covers both built-in commands (``GATEWAY_KNOWN_COMMANDS`` derived
    from ``COMMAND_REGISTRY``) and plugin-registered commands, which are
    looked up lazily so importing this module never forces plugin
    discovery. Gateway code uses this to decide whether to emit
    \"\"\"
    if not name:
        return False
    if name in GATEWAY_KNOWN_COMMANDS:
        return True
    for plugin_name, _description, _args_hint in _iter_plugin_command_entries():
        if plugin_name == name:
            return True
    return False""",
    "new_string": """def is_gateway_known_command(name: str | None) -> bool:
    \"\"\"Return True if ``name`` resolves to a gateway-dispatchable slash command.

    This covers built-in commands, extension commands (toolsets, MCPs),
    and plugin-registered commands.
    \"\"\"
    if not name:
        return False
    if name in GATEWAY_KNOWN_COMMANDS:
        return True
    # Also check extension registry commands
    for ext_cmd in COMMAND_REGISTRY_EXTENSIONS:
        if name == ext_cmd.name or name in ext_cmd.aliases:
            return True
    for plugin_name, _description, _args_hint in _iter_plugin_command_entries():
        if plugin_name == name:
            return True
    return False""",
}

# ============================================================================
# PATCH 6: Fix _is_gateway_available to handle extension commands
# ============================================================================

patch_6 = {
    "path": "/opt/hermes-agent/hermes_cli/commands.py",
    "old_string": """def _is_gateway_available(cmd: CommandDef, config_overrides: set[str] | None = None) -> bool:
    \"\"\"Check if *cmd* should appear in gateway surfaces (help, menus, mappings).

    Unconditionally available when ``cli_only`` is False.  When ``cli_only``
    is True but ``gateway_config_gate`` is set, the command is available only
    when the config value is truthy.  Pass *config_overrides* (from
    ``_resolve_config_gates()``) to avoid re-reading config for every command.
    \"\"\"
    if not cmd.cli_only:
        return True
    if cmd.gateway_config_gate:
        overrides = config_overrides if config_overrides is not None else _resolve_config_gates()
        return cmd.name in overrides
    return False""",
    "new_string": """def _is_gateway_available(cmd: CommandDef, config_overrides: set[str] | None = None) -> bool:
    \"\"\"Check if *cmd* should appear in gateway surfaces (help, menus, mappings).

    Unconditionally available when ``cli_only`` is False or the command
    is from a non-builtin source (skills, toolsets, MCPs, plugins, bundles).
    When ``cli_only`` is True but ``gateway_config_gate`` is set, the command
    is available only when the config value is truthy.
    \"\"\"
    # Non-builtin commands (skills, toolsets, MCPs, plugins, bundles) are
    # always available on gateway surfaces
    if cmd.source not in (\"builtin\",) and cmd.source:
        return True
    if not cmd.cli_only:
        return True
    if cmd.gateway_config_gate:
        overrides = config_overrides if config_overrides is not None else _resolve_config_gates()
        return cmd.name in overrides
    return False""",
}

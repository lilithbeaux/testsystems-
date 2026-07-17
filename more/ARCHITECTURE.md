# Unified Slash Registry + On-Demand Tool Loading
# =================================================
#
# Architecture and Installation Guide
# Last Updated: July 2026

=============================================================================
ARCHITECTURE OVERVIEW
=============================================================================

Before (4 parallel registries):
                             +-- hermes_cli/commands.py (COMMAND_REGISTRY)
                             |
    /help, /autocomplete --- +-- agent/skill_commands.py (_skill_commands)
                             |
                             +-- hermes_cli/plugins.py (_plugin_commands)
                             |
                             +-- agent/skill_bundles.py (_bundle_commands)

    [MISSING] toolsets ------ no slash commands at all
    [MISSING] MCP servers --- no slash commands at all

After (unified SlashRegistry):
                             +-- hermes_cli/slash_registry.py
                             |      (SlashRegistry singleton)
                             |          |
    /help, /autocomplete --- +----------+-- COMMAND_REGISTRY (builtins)
                             |          |-- scan_skill_commands() -> skill /slugs
                             |          |-- plugins -> register_command()
                             |          |-- skills bundles
                             |          |-- TOOLSETS -> /toolset-name       [NEW]
                             |          |-- mcp_servers -> /mcp-name        [NEW]
                             |
                             +-- tools/on_demand_tools.py
                                    (runtime activation logic)

=============================================================================
FILE INVENTORY
=============================================================================

NEW FILES (create these):
  1. hermes_cli/slash_registry.py     — The unified SlashRegistry singleton
  2. tools/on_demand_tools.py         — Runtime handler for tool activation
  3. plugins/on_demand_slash.py       — Hermes plugin wiring everything
  4. unified_slash_bootstrap.py       — Bootstrap function (startup call)

PATCH FILES (changes to existing files):
  5. PATCH: hermes_cli/commands.py
     - Add `source`, `load_on_invoke`, `handler` fields to CommandDef
     - Add COMMAND_REGISTRY_EXTENSIONS list
     - Add rebuild_lookups() function
     - Replace static dict building with rebuild_lookups() call
     - Update GATEWAY_KNOWN_COMMANDS to be rebuildable
     - Update is_gateway_known_command() to check extensions
     - Update _is_gateway_available() for non-builtin sources

  6. PATCH: tui_gateway/server.py
     - Raise autocomplete cap from 30 to 200
     - Remove cap when filter text is typed
     - Add "N more..." entry when cap is hit

  7. PATCH: agent/skill_commands.py
     - Add _register_skills_in_slash_registry() call at end of scan_skill_commands()
     - Add same call at end of reload_skills()

  8. PATCH: cli.py (or the /help handler)
     - /help renders from COMMANDS_BY_CATEGORY which is now populated
       by rebuild_lookups() with all command categories

=======================================================================
DETAILED PATCH INSTRUCTIONS
=======================================================================

PATCH 1: hermes_cli/commands.py
--------------------------------
Location: /opt/hermes-agent/hermes_cli/commands.py

(a) Add to CommandDef dataclass (after "gateway_config_gate"):
      source: str = "builtin"
      load_on_invoke: bool = False
      handler: Callable[[str], str | None] | None = None

(b) After COMMAND_REGISTRY list (before "Derived lookups" comment), add:
      COMMAND_REGISTRY_EXTENSIONS: list[CommandDef] = []

(c) Replace the entire "Derived lookups" section with rebuild_lookups() function.

(d) Replace the static dict-building loops (COMMANDS, COMMANDS_BY_CATEGORY,
    SUBCOMMANDS) with a call to rebuild_lookups().

(e) Replace the static GATEWAY_KNOWN_COMMANDS frozenset with a rebuildable one.

See `work/patches_commands_py.py` for exact old_string -> new_string values.

PATCH 2: tui_gateway/server.py
-------------------------------
Location: /opt/hermes-agent/tui_gateway/server.py line ~12862-12936

Replace the complete.slash handler to:
  - Cap at 200 items for bare "/" (not 30)
  - Return ALL matches when filter text is typed
  - Show "N more..." hint when capped

PATCH 3: agent/skill_commands.py
--------------------------------
Location: /opt/hermes-agent/agent/skill_commands.py

Add to the end of scan_skill_commands() (after line ~385):
    try:
        _register_skills_in_slash_registry()
    except Exception:
        pass

Add to the end of reload_skills() (after the scan_skill_commands() call):
    try:
        _register_skills_in_slash_registry()
    except Exception:
        pass
    try:
        from hermes_cli.commands import rebuild_lookups
        rebuild_lookups()
    except Exception:
        pass

=======================================================================
BOOTSTRAP CALL
=======================================================================

In Hermes startup (cli.py or run_agent.py), add near the top:

    # ── Unified slash registry + on-demand tools ──
    try:
        from unified_slash_bootstrap import bootstrap
        total = bootstrap()
        if total:
            logger.debug("Slash registry online: %d commands", total)
    except ImportError:
        pass  # graceful degradation — not installed
    except Exception as e:
        logger.warning("Slash bootstrap failed: %s", e)

=======================================================================
HOW ON-DEMAND LOADING WORKS
=======================================================================

The key insight: every tool is ALREADY registered in the global
tool registry (`tools.registry`) at Hermes startup. The `load_on_invoke`
flag doesn't affect registration — it affects whether the tool's schema
is included in the system prompt / LLM tool list.

Flow when user types `/nmap`:

  1. Plugin handler intercepts the slash command
  2. `enable_toolset_for_session("nmap", "toolset", agent, session_id)` is called
  3. Resolves the "nmap" toolset -> netcat, masscan, nmap tools
  4. Calls `agent.enabled_tool_names.update(tool_names)`
  5. Rebuilds agent's tool_schemas dict to include the new tools
  6. Returns user-facing message: "✅ nmap activated (3 tools loaded)"

On the NEXT turn, the LLM sees the new tools in its tool list.
The activation persists for the rest of the session.

To deactivate: /new (fresh session) or plugin-provided management command.

=======================================================================
EXAMPLE: What typing "/" shows after installation
=======================================================================

Before (typing bare "/"):
  /help, /model, /new, /undo, /retry, /compress, /tools, ...
  (30 items — alphabetical early a-b only)

After:
  /active-tools     Show which on-demand tools are active
  /agents           Show active agents and running tasks
  /background       Run a prompt in the background
  ...
  /browser          Browser automation (navigate, click, type, ...)
  /computer-use     Background desktop control via cua-driver
  /ctx-curation     ⚡ Walk through context curation step by step   [SKILL]
  ...
  /nmap             📡 Load nmap + masscan network tools            [TOOLSET]
  /spotify          📡 Native Spotify playback and search           [TOOLSET]
  /mcp-filesystem   📡 Connect filesystem MCP server               [MCP]
  ...
  (up to 200 items for bare "/", all matching when filtered)

=======================================================================
TOOLSET INDEX (what gets registered)
=======================================================================

Every non-platform, non-posture toolset in TOOLSETS becomes a /command:

  Toolset Name         /command            Tools
  ──────────────────────────────────────────────────────────────
  web                  /web                web_search, web_extract
  terminal             /terminal           terminal, process
  file                 /file               read_file, write_file, ...
  browser              /browser            browser_navigate, ...
  vision               /vision             vision_analyze
  image_gen            /image-gen          image_generate
  video                /video              video_analyze
  computer-use         /computer-use       computer_use
  coding               /coding             full coding toolset
  debugging            /debugging          terminal, web, file
  safe                 /safe               web, vision, image_gen
  spotify              /spotify            spotify_playback, ...
  homeassistant        /homeassistant      ha_list_entities, ...
  homeassistant        /homeassistant      ha_list_entities, ...
  discord              /discord            discord tools
  discord_admin        /discord-admin      discord_admin
  kanban               /kanban             kanban_show, ...
  feishu_doc           /feishu-doc         feishu_doc_read
  feishu_drive         /feishu-drive       feishu_drive_list, ...
  ...and more

You can also use grouped toolset commands to load multiple related
toolsets at once:
  /debugging   (web + file + terminal)
  /safe        (web + vision + image_gen)

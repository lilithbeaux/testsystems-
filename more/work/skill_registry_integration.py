"""
PATCH: agent/skill_commands.py — Skills register as CommandDefs
===============================================================

Currently, ``scan_skill_commands()`` builds a private ``_skill_commands``
dict that's separate from the built-in ``COMMAND_REGISTRY``. This means
skill commands are invisible in ``/help`` and second-class in the TUI.

This patch integrates skill commands into the unified registry so they
appear as proper ``CommandDef`` entries in ``COMMANDS``,
``COMMANDS_BY_CATEGORY``, ``SUBCOMMANDS``, and ``/help``.

Add to the end of ``scan_skill_commands()``, after the loop that populates
``_skill_commands``:
"""

# ============================================================================
# CODE TO ADD to scan_skill_commands() in agent/skill_commands.py
# ============================================================================
# After line ~385 (the end of the loop that populates _skill_commands),
# add this integration with the unified slash registry:
#
#     # ── Register skills in the unified slash registry ──
#     try:
#         _register_skills_in_slash_registry()
#     except Exception:
#         pass
#
# ============================================================================

integrate_skill_commands = r"""
def _register_skills_in_slash_registry():
    """
    Register all scanned skill commands into the unified SlashRegistry.

    This makes skill commands appear in COMMANDS, COMMANDS_BY_CATEGORY,
    /help output, and as first-class entries in the autocomplete system.

    Called at the end of scan_skill_commands() — runs only when the
    unified registry module is available (graceful degradation otherwise).
    """
    try:
        from hermes_cli.slash_registry import registry as slash_registry
    except ImportError:
        return  # Unified registry not available — use old parallel path

    from hermes_cli.commands import rebuild_lookups  # noqa: F811

    count = 0
    for cmd_key, info in _skill_commands.items():
        slug = cmd_key.lstrip("/")
        name = info.get("name", slug)
        description = info.get("description", "")
        skill_md_path = info.get("skill_md_path", "")
        skill_dir = info.get("skill_dir", "")

        result = slash_registry.register_skill(
            slug=slug,
            name=name,
            description=description,
            skill_md_path=skill_md_path,
            skill_dir=skill_dir,
        )
        if result:
            count += 1

    if count:
        rebuild_lookups()

    if count:
        import logging
        logging.getLogger(__name__).debug(
            "Registered %d skill commands in unified slash registry", count
        )


# ============================================================================
# Also add to reload_skills() — after rescan, re-register
# ============================================================================
# In reload_skills() in agent/skill_commands.py, after the call to
# scan_skill_commands(), add:
#
#     # Re-register skills in unified registry
#     try:
#         _register_skills_in_slash_registry()
#     except Exception:
#         pass
#     try:
#         from hermes_cli.commands import rebuild_lookups
#         rebuild_lookups()
#     except Exception:
#         pass
#
# This ensures /reload-skills also refreshes the unified registry.
"""

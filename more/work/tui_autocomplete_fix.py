"""
PATCH: tui_gateway/server.py — Fix the 30-item autocomplete cap
===============================================================

The TUI's ``complete.slash`` handler caps autocomplete at 30 items, which
hides most commands when the user types bare ``/``. With 70+ built-in
commands + 150+ skills + 30+ toolset commands + MCP commands, this cap
is severe.

Changes:
1. Raise the cap from 30 to 200 (or derive from terminal height)
2. The cap now only applies when typing bare / — as soon as any filter
   characters are typed, ALL matching results are returned (no cap).

ORIGINAL (tui_gateway/server.py, line ~12893):
    for c in completer.get_completions(doc, None)
    ][:30]

PATCHED:
    # Dynamic autocomplete cap
    _AUTOCOMPLETE_CAP_DEFAULT = 200
    _AUTOCOMPLETE_CAP_FILTERED = 0  # 0 = no cap (return all matches)

    # Determine cap based on whether user typed filter text
    text = params.get("text", "")
    has_filter = len(text.strip()) > 1  # bare "/" has no filter

    items = [
        ...
        for c in completer.get_completions(doc, None)
    ]
    if has_filter and len(items) < _AUTOCOMPLETE_CAP_FILTERED:
        pass  # no cap when filtering
    else:
        items = items[:_AUTOCOMPLETE_CAP_DEFAULT]

Additionally, the TUI should show "N more..." when the cap is hit.
"""

# ============================================================================
# The actual patch for server.py complete.slash method
# ============================================================================

PATCH_CODE = r"""
# --- BEGIN PATCH: tui_gateway/server.py ~line 12862 ---

# Replace the existing complete.slash handler with this version:

@method("complete.slash")
def _(rid, params: dict) -> dict:
    text = params.get("text", "")
    if not text.startswith("/"):
        return _ok(rid, {"items": []})

    try:
        from hermes_cli.commands import SlashCommandCompleter
        from prompt_toolkit.document import Document
        from prompt_toolkit.formatted_text import to_plain_text

        from agent.skill_commands import get_skill_commands
        from agent.skill_bundles import get_skill_bundles

        completer = SlashCommandCompleter(
            skill_commands_provider=lambda: get_skill_commands(),
            skill_bundles_provider=lambda: get_skill_bundles(),
        )
        doc = Document(text, len(text))
        items = [
            {
                "text": c.text,
                "display": to_plain_text(c.display) if c.display else c.text,
                "meta": to_plain_text(c.display_meta) if c.display_meta else "",
            }
            for c in completer.get_completions(doc, None)
        ]

        # ── Dynamic autocomplete cap ──
        # When the user types bare "/" (no filter text), cap at 200 to avoid
        # overwhelming the dropdown. When typing filter text like "/mo" or
        # "/ctx", return ALL matching results so nothing is hidden.
        has_filter = len(text.strip()) > 1
        if not has_filter:
            items = items[:200]

        # If we hit the cap, add a "N more..." entry so users know to type
        # more filter text
        total_matches = len([c for c in completer.get_completions(doc, None)])
        if not has_filter and total_matches > 200:
            items.append({
                "text": "",
                "display": "…",
                "meta": f"{total_matches - 200} more — type characters to filter",
            })

        text_lower = text.lower()
        extras = [
            {
                "text": "/compact",
                "display": "/compact",
                "meta": "Toggle compact display mode",
            },
            {
                "text": "/details",
                "display": "/details",
                "meta": "Control agent detail visibility",
            },
            {
                "text": "/logs",
                "display": "/logs",
                "meta": "Show recent gateway log lines",
            },
            {
                "text": "/mouse",
                "display": "/mouse",
                "meta": "Set mouse tracking preset [on|off|toggle|wheel|buttons|all]",
            },
        ]
        for extra in extras:
            if extra["text"].startswith(text_lower) and not any(
                item["text"] == extra["text"] for item in items
            ):
                items.append(extra)

        details_items = _details_completions(text)
        if details_items is not None:
            return _ok(
                rid,
                {
                    "items": details_items,
                    "replace_from": text.rfind(" ") + 1 if " " in text else len(text),
                },
            )

        return _ok(
            rid,
            {"items": items, "replace_from": text.rfind(" ") + 1 if " " in text else 1},
        )
    except Exception as e:
        return _err(rid, 5020, str(e))
"""


# ============================================================================
# ALSO: Patch /help to include skill, toolset, and MCP commands
# ============================================================================

HELP_PATCH = r"""
# --- PATCH: CLI /help handler ---
# In cli.py (or wherever the /help dispatcher lives), change
# the rendering to use the unified registry's COMMANDS_BY_CATEGORY:

def render_help(categories=None):
    """
    Render /help output including all command categories
    (builtins, skills, toolsets, MCPs, plugins, bundles).
    """
    try:
        from hermes_cli.slash_registry import registry as slash_registry
        categories = slash_registry.by_category
    except ImportError:
        from hermes_cli.commands import COMMANDS_BY_CATEGORY as categories

    for category, cmds in categories.items():
        print(f"\n  {category}:")
        for cmd_name, desc in sorted(cmds.items()):
            print(f"    {cmd_name:<30} {desc}")
"""

# ============================================================================
# Patch: Also update SlashCommandCompleter or auto-suggest to include toolset/MCP commands
# ============================================================================

# In hermes_cli/commands.py, the get_completions method at line 2005 iterates
# COMMANDS which is the built-in-only dict. After the unified registry is
# wired in, COMMANDS includes everything — so this should work automatically.

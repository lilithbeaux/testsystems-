"""
x11_tool.py — Complete X11 Desktop Control via xdotool + cua-driver
===================================================================

Three layers:
  1. xdotool (always available) — mouse, keys, windows, focus
  2. xclip (always available) — clipboard read/write
  3. cua-driver (when installed) — screenshots, element detection, AT-SPI

All wrapped in a single tool that the model calls with a simple action.
"""

from __future__ import annotations

import json
import logging
import subprocess
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── xdotool wrappers ──────────────────────────────────────────────

def _xdotool(*args: str, timeout: int = 10) -> str:
    """Run xdotool and return stdout."""
    try:
        result = subprocess.run(
            ["xdotool"] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"xdotool error: {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("xdotool not installed")


def _xclip(stdin: str = "", args: list[str] | None = None) -> str:
    """Read/write clipboard via xclip."""
    try:
        cmd = ["xclip", "-selection", "clipboard"]
        if args:
            cmd.extend(args)
        if stdin:
            result = subprocess.run(
                cmd, input=stdin, capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        else:
            cmd.extend(["-o"])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("xclip not installed")


# ── Main handler ──────────────────────────────────────────────────

def handle_x11(action: str, **kwargs) -> str:
    """Handle X11 desktop control actions.

    Actions:
      mouse_pos         — get cursor position
      mouse_move x y    — move cursor to x,y
      click [btn]       — click (1=left, 2=middle, 3=right)
      key <keysym>      — press a key combo (e.g. 'ctrl+c', 'Return')
      type <text>       — type text
      window_list       — list windows
      window_focus <id> — focus a window by id
      screen_size       — get display dimensions
      clipboard_read    — read clipboard
      clipboard_write   — write text to clipboard
      screenshot        — take a screenshot (requires cua-driver or import)
      search <text>     — find windows matching text
    """
    try:
        if action == "mouse_pos":
            x, y = _xdotool("getmouselocation").replace("x:", "").replace("y:", "").split()[0:2]
            return json.dumps({"x": int(x.split(":")[1]), "y": int(y.split(":")[1])})

        elif action == "mouse_move":
            x = kwargs.get("x", kwargs.get("coordinate", [0, 0])[0])
            y = kwargs.get("y", kwargs.get("coordinate", [0, 0])[1])
            _xdotool("mousemove", str(x), str(y))
            return json.dumps({"status": "ok", "x": x, "y": y})

        elif action == "click":
            btn = str(kwargs.get("button", 1))
            _xdotool("click", btn)
            return json.dumps({"status": "ok", "button": btn})

        elif action == "key":
            keys = kwargs.get("keys", "")
            _xdotool("key", keys)
            return json.dumps({"status": "ok", "keys": keys})

        elif action == "type":
            text = kwargs.get("text", "")
            _xdotool("type", text)
            return json.dumps({"status": "ok", "chars": len(text)})

        elif action == "window_list":
            output = _xdotool("search", "--name", ".")
            windows = output.split("\n") if output else []
            details = []
            for wid in windows[:20]:  # limit to 20
                try:
                    name = _xdotool("getwindowname", wid)
                    details.append({"id": wid, "name": name})
                except RuntimeError:
                    pass
            return json.dumps({"windows": details, "count": len(details)})

        elif action == "window_focus":
            wid = kwargs.get("window_id", "")
            _xdotool("windowactivate", wid)
            return json.dumps({"status": "ok", "window_id": wid})

        elif action == "screen_size":
            output = _xdotool("getdisplaygeometry")
            w, h = output.split()
            return json.dumps({"width": int(w), "height": int(h)})

        elif action == "clipboard_read":
            text = _xclip()
            return json.dumps({"text": text, "chars": len(text)})

        elif action == "clipboard_write":
            text = kwargs.get("text", "")
            _xclip(stdin=text, args=[])
            return json.dumps({"status": "ok", "chars": len(text)})

        elif action == "search":
            query = kwargs.get("text", "")
            output = _xdotool("search", "--name", query)
            windows = output.split("\n") if output else []
            return json.dumps({"windows": windows, "count": len(windows)})

        elif action == "screenshot":
            # Try cua-driver first, fall back to import
            try:
                from cua_driver import get_binary_path
                import subprocess as sp
                bin_path = get_binary_path()
                result = sp.run(
                    [bin_path, "call", "get_desktop_state"],
                    capture_output=True, text=True, timeout=30,
                    env={"DISPLAY": ":0", "PATH": "/usr/bin:/bin"},
                )
                return result.stdout or result.stderr
            except Exception:
                import tempfile, os
                path = f"/tmp/screenshot_{int(__import__('time').time())}.png"
                subprocess.run(
                    ["import", "-window", "root", path],
                    capture_output=True, text=True, timeout=15,
                )
                return json.dumps({"path": path, "status": "import -window root used"})

        else:
            return json.dumps({"error": f"Unknown action: {action}"})

    except RuntimeError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"X11 error: {e}"})


# ── Tool schema for the Hermes tool registry ─────────────────────

SCHEMA = {
    "name": "x11",
    "description": "Control the X11 desktop: mouse, keyboard, windows, clipboard, screenshots. Uses xdotool (always works) with cua-driver fallback for screenshots.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "mouse_pos", "mouse_move", "click", "key", "type",
                    "window_list", "window_focus", "screen_size",
                    "clipboard_read", "clipboard_write", "search", "screenshot",
                ],
                "description": "Action to perform",
            },
            "x": {"type": "integer", "description": "X coordinate for mouse_move"},
            "y": {"type": "integer", "description": "Y coordinate for mouse_move"},
            "button": {"type": "integer", "description": "Mouse button: 1=left, 2=middle, 3=right"},
            "keys": {"type": "string", "description": "Key combo e.g. 'ctrl+c', 'Alt+Tab', 'Return'"},
            "text": {"type": "string", "description": "Text to type (for 'type' or 'clipboard_write') or window name to search (for 'search')"},
            "window_id": {"type": "string", "description": "Window ID for window_focus"},
            "coordinate": {
                "type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2,
                "description": "[x, y] for mouse_move",
            },
        },
        "required": ["action"],
    },
}


def handler(args: dict[str, Any], task_id: str | None = None) -> str:
    """Tool handler — unpacks args and calls handle_x11."""
    return handle_x11(
        action=args.get("action", ""),
        x=args.get("x"),
        y=args.get("y"),
        button=args.get("button", 1),
        keys=args.get("keys", ""),
        text=args.get("text", ""),
        window_id=args.get("window_id", ""),
        coordinate=args.get("coordinate", [0, 0]),
    )


def _check_x11() -> bool:
    """Check if X11 tools are available."""
    try:
        subprocess.run(["xdotool", "version"], capture_output=True, timeout=3)
        return True
    except Exception:
        return False


# ── Register in tool registry ────────────────────────────────────

try:
    from tools.registry import registry
    registry.register(
        name="x11",
        toolset="computer_use",
        schema=SCHEMA,
        handler=handler,
        check_fn=_check_x11,
        description="X11 desktop control via xdotool — mouse, keyboard, windows, clipboard, screenshots",
        emoji="🖥️",
    )
    logger.info("Registered x11 tool (xdotool-based, cua-driver fallback)")
except Exception:
    pass  # graceful

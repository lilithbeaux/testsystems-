#!/usr/bin/env python3
"""
DROP — Thread Pivot Payload Builder
Generates a self-contained sovereign prompt file embedding the last SNAP.

Usage:
  python3 drop_payload.py                       # Show last snapshot info
  python3 drop_payload.py --write               # Write sovereign prompt file
  python3 drop_payload.py --write --force       # Overwrite existing
  python3 drop_payload.py --use <snap_file>     # Use specific snapshot
  python3 drop_payload.py --show                # Show the payload block only
"""

import json, os, sys, datetime
from pathlib import Path

PROFILE_DIR = Path(os.path.expanduser("~/.hermes/profiles/thotheauphis"))
SNAPSHOT_DIR = PROFILE_DIR / "snapshots"
COUNTER_FILE = PROFILE_DIR / "scripts" / ".snapndrop_counter.json"
DROP_OUTPUT = PROFILE_DIR / "snapshots" / "drop_sovereign_prompt.md"


def get_latest_snapshot():
    """Find the most recent snapshot file."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snaps = sorted(SNAPSHOT_DIR.glob("snap_*.txt"), reverse=True)
    return snaps[0] if snaps else None


def read_snapshot(path: Path) -> str:
    """Read snapshot, stripping the header to get just the transcript."""
    content = path.read_text()
    # Remove the header block (everything before the first "User:" or "Assistant:")
    lines = content.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("User:") or stripped.startswith("Assistant:"):
            header_end = i
            break
    transcript = "\n".join(lines[header_end:])
    return transcript


def build_drop_payload(snap_path: Path = None) -> str:
    """Build the sovereign prompt with [CONTEXT SNAPSHOT] block."""
    if snap_path is None:
        snap_path = get_latest_snapshot()
    if not snap_path:
        return "# No snapshot available. Run: python3 snapndrop.py snap"

    snap_name = snap_path.stem
    transcript = read_snapshot(snap_path)

    # Read metadata from counter file
    meta_info = ""
    if COUNTER_FILE.exists():
        try:
            c = json.loads(COUNTER_FILE.read_text())
            s = c.get("last_snap", {})
            if s:
                meta_info = (
                    f"  Session: {s.get('session_id', '?')}\n"
                    f"  Messages captured: {s.get('message_count', '?')}\n"
                    f"  Input tokens: {s.get('input_tokens', '?')}\n"
                    f"  Output tokens: {s.get('output_tokens', '?')}\n"
                )
        except Exception:
            pass

    payload = f"""The following is a [CONTEXT SNAPSHOT — STATIC, NOT RESUBMITTED] block.
It contains the full conversation history from a previous session, captured at {snap_name}.
This block is part of the system prompt — not the messages array — and is NOT
resubmitted on subsequent turns.

{meta_info}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[CONTEXT SNAPSHOT — STATIC, NOT RESUBMITTED]
{transcript}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return payload


def show_drop_info():
    """Print info about the DROP payload."""
    snap = get_latest_snapshot()
    if not snap:
        print("  No snapshot available.")
        return
    size = snap.stat().st_size
    print(f"\n  Source snapshot: {snap.name} ({_fmt_size(size)})")
    transcript = read_snapshot(snap)
    print(f"  Transcript chars: {len(transcript):,}")
    payload = build_drop_payload(snap)
    print(f"  DROP payload size: {len(payload):,} chars  ({len(payload)//4:,} estimated tokens)")
    print(f"  Sovereign prompt file: {DROP_OUTPUT}")
    print()


def write_drop_payload(force: bool = False) -> bool:
    """Write the DROP payload as a sovereign prompt file."""
    if DROP_OUTPUT.exists() and not force:
        print(f"  ⚠ {DROP_OUTPUT} already exists. Use --force to overwrite.")
        return False

    payload = build_drop_payload()
    DROP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DROP_OUTPUT.write_text(payload)
    size = DROP_OUTPUT.stat().st_size
    print(f"\n  ✅ DROP payload written:")
    print(f"     File: {DROP_OUTPUT}")
    print(f"     Size: {_fmt_size(size)}  ({len(payload)//4:,} estimated tokens)")
    print(f"\n  Next session: start with:")
    print(f"     hermes chat --sovereign-prompt {DROP_OUTPUT}")
    print(f"\n  Or in TUI:")
    print(f"     Exit session → restart with: hermes --sovereign-prompt {DROP_OUTPUT} --tui")
    print()
    return True


def show_payload():
    """Print the payload block to stdout."""
    payload = build_drop_payload()
    print(payload)


def _fmt_size(b):
    if b < 1024: return f"{b} B"
    elif b < 1024**2: return f"{b/1024:.1f} KB"
    else: return f"{b/1024**2:.1f} MB"


if __name__ == "__main__":
    if "--write" in sys.argv:
        force = "--force" in sys.argv
        write_drop_payload(force=force)
    elif "--show" in sys.argv:
        show_payload()
    elif "--use" in sys.argv:
        idx = sys.argv.index("--use") + 1
        if idx < len(sys.argv):
            path = Path(sys.argv[idx])
            if path.exists():
                payload = build_drop_payload(path)
                if "--write" in sys.argv:
                    DROP_OUTPUT.write_text(payload)
                    print(f"Written to {DROP_OUTPUT}")
                else:
                    print(payload)
            else:
                print(f"File not found: {path}")
        else:
            print("--use requires a file path")
    else:
        show_drop_info()

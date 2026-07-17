#!/usr/bin/env python3
"""
SNAP n DROP — Context Gauge & Thread Rotation System v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tracks the LIVE messages array size (what the TUI gauge shows),
NOT cumulative DB totals. Designed to work with a system where
the system prompt is cached/sent-once — the gauge measures only
the conversation messages being resubmitted each turn.

Commands:
  gauge              Show context gauge (messages array vs threshold)
  gauge --tui        Show condensed TUI-friendly gauge line
  snap               Capture current state to transcript file
  drop               Prepare sovereign prompt file from last SNAP
  pivot              SNAP + DROP in one seamless operation
  status             Session + snapshot + model breakdown

Config:
  Threshold defaults to 1,000,000 tokens.
  Override: SNAP_THRESHOLD=500000 python3 snapndrop.py gauge

Usage:
  python3 snapndrop.py gauge
  python3 snapndrop.py pivot
  python3 snapndrop.py status
"""

import sqlite3, os, sys, json, datetime
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────
PROFILE_DIR = Path(os.path.expanduser("~/.hermes/profiles/thotheauphis"))
STATE_DB = PROFILE_DIR / "state.db"
SNAPSHOT_DIR = PROFILE_DIR / "snapshots"
COUNTER_FILE = PROFILE_DIR / "scripts" / ".snapndrop_counter.json"
DROP_OUTPUT = PROFILE_DIR / "snapshots" / "drop_sovereign_prompt.md"

# Threshold from env or default 1M
SNAP_THRESHOLD = int(os.environ.get("SNAP_THRESHOLD", "1000000"))

# ─── Tokenizer ───────────────────────────────────────────────────────────────
try:
    import tiktoken
    ENC = tiktoken.get_encoding("cl100k_base")
except ImportError:
    ENC = None

def count_tokens(text: str) -> int:
    if ENC and text:
        try:
            return len(ENC.encode(text))
        except Exception:
            pass
    return len(text) // 4 if text else 0


# ─── DB Helpers ──────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def get_current_session(conn) -> sqlite3.Row | None:
    cur = conn.execute("""
        SELECT id, source, title, message_count, input_tokens, output_tokens,
               reasoning_tokens, started_at, ended_at
        FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1
    """)
    return cur.fetchone()

def get_active_messages(conn, session_id: str) -> list[sqlite3.Row]:
    """Fetch ALL active messages (the actual messages array sent to the API)."""
    cur = conn.execute("""
        SELECT id, role, content, tool_calls, token_count
        FROM messages
        WHERE session_id = ? AND active = 1
        ORDER BY id ASC
    """, (session_id,))
    return cur.fetchall()

def get_model_breakdown(conn, session_id: str) -> list[sqlite3.Row]:
    cur = conn.execute("""
        SELECT model, billing_provider, api_call_count,
               input_tokens, output_tokens, reasoning_tokens
        FROM session_model_usage WHERE session_id = ?
        ORDER BY last_seen DESC
    """, (session_id,))
    return cur.fetchall()

def get_last_user_message(conn, session_id: str) -> dict | None:
    cur = conn.execute("""
        SELECT id, content, token_count
        FROM messages
        WHERE session_id = ? AND role = 'user' AND active = 1
        ORDER BY id DESC LIMIT 1
    """, (session_id,))
    row = cur.fetchone()
    if not row:
        return None
    content = row["content"] or ""
    tc = row["token_count"] if row["token_count"] else count_tokens(content)
    return {
        "token_count": tc,
        "content_preview": content[:120] + ("..." if len(content) > 120 else ""),
    }


# ─── Messages Array Size Estimation ──────────────────────────────────────────
# This is what the TUI gauge tracks: the messages array being resubmitted,
# NOT cumulative DB totals. The system prompt is cached/one-time.

def estimate_messages_array_tokens(messages: list) -> int:
    """
    Estimate tokens in the messages array (what the API actually receives
    per turn). This is what the TUI gauge shows.
    
    Accounts for: message content + role wrappers + tool call metadata.
    ~8 tokens overhead per message for JSON wrappers.
    """
    total = 0
    for m in messages:
        # Handle both dict and sqlite3.Row
        if isinstance(m, dict):
            content = m.get("content", "") or ""
            tc = m.get("tool_calls")
        else:
            content = m["content"] or ""
            tc = m["tool_calls"]
        # Content tokens
        total += count_tokens(content)
        # Per-message overhead (~8 tokens for role/wrapper/metadata)
        total += 8
        # Tool calls add more overhead
        if tc:
            try:
                tc_parsed = json.loads(tc) if isinstance(tc, str) else tc
                if isinstance(tc_parsed, list):
                    total += len(tc_parsed) * 15  # ~15 tokens per tool call entry
            except Exception:
                total += 20
    return total


# ─── Gauge Display ───────────────────────────────────────────────────────────

def fmt_num(n: int) -> str:
    return f"{n:,}"

def fmt_pct(ratio: float) -> str:
    return f"{ratio * 100:.1f}%"

def make_progress_bar(value: int, maximum: int, width: int = 30) -> str:
    if maximum <= 0:
        return "░" * width
    ratio = min(value / maximum, 1.0)
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {ratio * 100:5.1f}%"


def show_gauge(json_mode: bool = False, tui_mode: bool = False):
    """
    Show the context gauge based on the ACTIVE MESSAGES ARRAY,
    not cumulative DB totals.
    """
    conn = get_db()
    session = get_current_session(conn)
    
    if not session:
        print("⚠ No active session.")
        return

    sid = session["id"]
    msgs = get_active_messages(conn, sid)
    msg_count = len(msgs)
    
    # The key number: actual messages array size
    msg_array_tokens = estimate_messages_array_tokens(msgs)
    
    # Cumulative totals for reference (per-model tracking)
    db_in = session["input_tokens"] or 0
    db_out = session["output_tokens"] or 0
    db_reas = session["reasoning_tokens"] or 0
    
    models = get_model_breakdown(conn, sid)
    last_msg = get_last_user_message(conn, sid)
    
    # JSON output
    if json_mode:
        data = {
            "session_id": sid,
            "messages_count": msg_count,
            "messages_array_tokens": msg_array_tokens,
            "threshold": SNAP_THRESHOLD,
            "context_usage_pct": round((msg_array_tokens / SNAP_THRESHOLD) * 100, 1),
            "working_context": last_msg,
            "cumulative_input": db_in,
            "cumulative_output": db_out,
            "cumulative_reasoning": db_reas,
            "models": [{
                "model": m["model"],
                "provider": m["billing_provider"],
                "input": m["input_tokens"],
                "output": m["output_tokens"],
                "reasoning": m["reasoning_tokens"],
            } for m in models],
        }
        print(json.dumps(data, indent=2))
        return

    # TUI compact line
    if tui_mode:
        bar_w = 14
        filled = int((msg_array_tokens / SNAP_THRESHOLD) * bar_w) if SNAP_THRESHOLD > 0 else 0
        filled = min(filled, bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        warn = "⚠️" if msg_array_tokens >= SNAP_THRESHOLD * 0.85 else "▲" if msg_array_tokens >= SNAP_THRESHOLD * 0.5 else "●"
        print(f"SND {warn} |{bar}| {fmt_num(msg_array_tokens):>7} / {fmt_num(SNAP_THRESHOLD):<8} | msgs:{msg_count} | last:{last_msg['token_count'] if last_msg else '?'}")
        return
    
    # ─── Full Gauge ────────────────────────────────────────────────
    ratio = msg_array_tokens / SNAP_THRESHOLD if SNAP_THRESHOLD > 0 else 0
    
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║          SNAP n DROP — Context Gauge (live)             ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"  Session        {sid}")
    print(f"  Messages       {fmt_num(msg_count)} in the active array")
    print(f"  Max context    {fmt_num(SNAP_THRESHOLD)} tokens")
    print()
    
    # ─── The Real Gauge: Messages Array ─────────────────────────────
    print(f"  ┌─ MESSAGES ARRAY (what goes to the API each turn) ──────┐")
    bar = make_progress_bar(msg_array_tokens, SNAP_THRESHOLD, width=28)
    print(f"  │  {bar}  │")
    print(f"  │  {fmt_num(msg_array_tokens):>10} / {fmt_num(SNAP_THRESHOLD):<10} tokens      │")
    print(f"  └─────────────────────────────────────────────────────────┘")
    print()
    
    # ─── Working Context ────────────────────────────────────────────
    if last_msg:
        print(f"  ┌─ WORKING CONTEXT (last user submission) ────────────────┐")
        print(f"  │  {fmt_num(last_msg['token_count']):>10} tokens  │  {last_msg['content_preview']:<52}  │")
        print(f"  └─────────────────────────────────────────────────────────┘")
        print()
    
    # ─── Cumulative Reference ───────────────────────────────────────
    print(f"  ┌─ CUMULATIVE (for reference) ────────────────────────────┐")
    print(f"  │  Input: {fmt_num(db_in):>10}  Output: {fmt_num(db_out):>10}  Reasoning: {fmt_num(db_reas):>10}  │")
    print(f"  └─────────────────────────────────────────────────────────┘")
    print()
    
    # ─── Model Breakdown ─────────────────────────────────────────────
    if models:
        print(f"  ┌─ PER-MODEL USAGE ─────────────────────────────────────────┐")
        for m in models:
            m_label = m["model"]
            prov = m["billing_provider"]
            if prov and prov not in m_label:
                m_label = f"{m_label} @ {prov}"
            m_in = m["input_tokens"] or 0
            m_out = m["output_tokens"] or 0
            m_reas = m["reasoning_tokens"] or 0
            print(f"  │  {m_label:<50}  │")
            print(f"  │   In: {fmt_num(m_in):>10}  Out: {fmt_num(m_out):>10}  Reas: {fmt_num(m_reas):>8}  │")
        print(f"  └─────────────────────────────────────────────────────────┘")
        print()
    
    # ─── SNAP Warning (based on messages array size) ────────────────
    remaining = SNAP_THRESHOLD - msg_array_tokens
    if msg_array_tokens >= SNAP_THRESHOLD * 0.85:
        urgency = "⚠️  CRITICAL" if msg_array_tokens >= SNAP_THRESHOLD else "⚡ WARNING"
        print(f"  ╔══════════════════════════════════════════════════════════╗")
        print(f"  ║  {urgency:<62} ║")
        print(f"  ║  {fmt_num(remaining):>7} tokens remaining before SNAP trigger!           ║")
        print(f"  ╚══════════════════════════════════════════════════════════╝")
        print()
    elif msg_array_tokens >= SNAP_THRESHOLD * 0.5:
        print(f"  ▲ {fmt_num(remaining):>7} tokens to SNAP threshold ({fmt_pct(ratio)} used)")
        print()
    
    # ─── Snapshot count ─────────────────────────────────────────────
    snap_count = len(list(SNAPSHOT_DIR.glob("snap_*.txt")))
    if snap_count > 0:
        latest = sorted(SNAPSHOT_DIR.glob("snap_*.txt"), reverse=True)[0]
        snap_size = latest.stat().st_size
        print(f"  📸 DROP ready: {snap_count} snapshot(s), latest {_fmt_size(snap_size)}")
    print()


# ─── Stripping & SNAP ────────────────────────────────────────────────────────

def strip_to_transcript(messages: list) -> str:
    """Strip message objects to plain-text transcript. Keeps User/Assistant/Tool labels."""
    lines = []
    for msg in messages:
        # Handle both dict and sqlite3.Row
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "") or ""
        else:
            role = msg["role"]
            content = msg["content"] or ""
        if not content or not content.strip():
            continue
        if role == "tool" and content:
            content = content.strip()
            if len(content) > 300:
                content = content[:300] + f"\n  [... {len(content)} total chars, truncated]"
        label_map = {"user": "User", "assistant": "Assistant", "tool": "Tool", "system": "System"}
        label = label_map.get(role, role.capitalize())
        lines.append(f"{label}: {content.strip()}")
    return "\n\n".join(lines)


def do_snap() -> dict:
    """SNAP: capture current messages array to a plain-text transcript."""
    conn = get_db()
    session = get_current_session(conn)
    if not session:
        return {"error": "No active session", "status": "failed"}

    sid = session["id"]
    msgs = get_active_messages(conn, sid)
    msg_count = len(msgs)
    msg_array_tokens = estimate_messages_array_tokens(msgs)

    transcript = strip_to_transcript(msgs)
    ts = datetime.datetime.now()
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    ts_readable = ts.strftime("%Y-%m-%d %H:%M:%S")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_file = SNAPSHOT_DIR / f"snap_{ts_str}_{sid[:8]}.txt"

    header = (
        f"╔══════════════════════════════════════════════════════════╗\n"
        f"║  SNAP n DROP — Context Snapshot                     ║\n"
        f"║  Session: {sid:<54} ║\n"
        f"║  Captured: {ts_readable:<49} ║\n"
        f"║  Messages: {msg_count:<5}  │  Array tokens: ~{msg_array_tokens:<8}  ║\n"
        f"╚══════════════════════════════════════════════════════════╝\n\n\n"
    )
    full = header + transcript
    snap_file.write_text(full)

    meta = {
        "snap_timestamp": ts_str,
        "session_id": sid,
        "message_count": msg_count,
        "messages_array_tokens": msg_array_tokens,
        "snap_file": str(snap_file),
        "transcript_length_chars": len(full),
    }
    counter = {}
    if COUNTER_FILE.exists():
        try:
            counter = json.loads(COUNTER_FILE.read_text())
        except Exception:
            pass
    counter["last_snap"] = meta
    COUNTER_FILE.write_text(json.dumps(counter, indent=2))

    return {
        "status": "snapped",
        "session_id": sid,
        "timestamp": ts_str,
        "snap_file": str(snap_file),
        "messages_captured": msg_count,
        "messages_array_tokens": msg_array_tokens,
        "transcript_length": len(full),
    }


# ─── DROP (Sovereign Prompt Builder) ─────────────────────────────────────────

def read_snapshot_transcript(snap_path: Path) -> str:
    """Extract just the transcript from a snapshot file (strip the header)."""
    content = snap_path.read_text()
    lines = content.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("User:") or stripped.startswith("Assistant:"):
            header_end = i
            break
    return "\n".join(lines[header_end:])


def get_latest_snapshot() -> Path | None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snaps = sorted(SNAPSHOT_DIR.glob("snap_*.txt"), reverse=True)
    return snaps[0] if snaps else None


def build_drop_payload(snap_path: Path = None) -> str:
    """Build the sovereign prompt text with [CONTEXT SNAPSHOT] block."""
    if snap_path is None:
        snap_path = get_latest_snapshot()
    if not snap_path:
        return "# No snapshot available. Run: python3 snapndrop.py snap"

    snap_name = snap_path.stem
    transcript = read_snapshot_transcript(snap_path)

    meta_info = ""
    if COUNTER_FILE.exists():
        try:
            c = json.loads(COUNTER_FILE.read_text())
            s = c.get("last_snap", {})
            if s:
                meta_info = (
                    f"  Session: {s.get('session_id', '?')}\n"
                    f"  Messages captured: {s.get('message_count', '?')}\n"
                    f"  Array tokens: {s.get('messages_array_tokens', '?')}\n"
                )
        except Exception:
            pass

    payload = (
        f"The following is a [CONTEXT SNAPSHOT — STATIC, NOT RESUBMITTED] block.\n"
        f"It contains the full conversation history from a previous session, captured at {snap_name}.\n"
        f"This block is part of the system prompt — not the messages array — and is NOT\n"
        f"resubmitted on subsequent turns. The system prompt is cached/sent-once.\n\n"
        f"{meta_info}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"[CONTEXT SNAPSHOT — STATIC, NOT RESUBMITTED]\n"
        f"{transcript}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    return payload


def do_drop(force: bool = False) -> dict:
    """
    DROP: build and write the sovereign prompt file from the latest SNAP.
    This file is ready to use with: hermes chat --sovereign-prompt <file>
    After DROP, the gauge resets to nearly zero on the new thread.
    """
    snap_path = get_latest_snapshot()
    if not snap_path:
        return {"error": "No snapshot available. Run 'snapndrop.py snap' first.", "status": "failed"}

    payload = build_drop_payload(snap_path)
    DROP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DROP_OUTPUT.write_text(payload)

    transcript = read_snapshot_transcript(snap_path)
    tokens = count_tokens(transcript)

    return {
        "status": "dropped",
        "snap_file": str(snap_path),
        "drop_file": str(DROP_OUTPUT),
        "transcript_tokens": tokens,
        "drop_file_size": DROP_OUTPUT.stat().st_size,
        "usage": f"hermes chat --sovereign-prompt {DROP_OUTPUT}",
    }


def do_pivot(force_drop: bool = True) -> dict:
    """
    PIVOT: SNAP then DROP in one seamless operation.
    Returns combined result with both snap and drop metadata.
    """
    snap_result = do_snap()
    if snap_result.get("status") != "snapped":
        return snap_result
    
    drop_result = do_drop(force=force_drop)
    return {
        "status": "pivoted",
        "snap": snap_result,
        "drop": drop_result,
    }


# ─── Status ──────────────────────────────────────────────────────────────────

def show_drop_status():
    """Show DROP repository status."""
    conn = get_db()
    session = get_current_session(conn)
    
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║           DROP — Snapshot Repository                    ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    
    # Last SNAP metadata
    counter = {}
    if COUNTER_FILE.exists():
        try:
            counter = json.loads(COUNTER_FILE.read_text())
        except Exception:
            pass
    
    last_snap = counter.get("last_snap")
    if last_snap:
        print(f"  Last SNAP:    {last_snap['snap_timestamp']}")
        print(f"  Session:      {last_snap['session_id']}")
        print(f"  Array tokens: {fmt_num(last_snap.get('messages_array_tokens', 0))}")
        print(f"  File:         {last_snap.get('snap_file', '?')}")
        print(f"  Size:         {_fmt_size(last_snap.get('transcript_length_chars', 0))}")
    else:
        print("  No SNAP taken yet.")
    print()
    
    # Snapshots on disk
    snaps = sorted(SNAPSHOT_DIR.glob("snap_*.txt"), reverse=True)
    print(f"  Snapshots: {len(snaps)}")
    if snaps:
        print(f"  Latest:    {snaps[0].name} ({_fmt_size(snaps[0].stat().st_size)})")
    
    # DROP file ready?
    if DROP_OUTPUT.exists():
        print(f"  DROP file: {DROP_OUTPUT.name} ({_fmt_size(DROP_OUTPUT.stat().st_size)})")
        print(f"  Launch:    hermes chat --sovereign-prompt {DROP_OUTPUT}")
    print()
    
    # Session readiness
    if session:
        msgs = get_active_messages(get_db(), session["id"])
        msg_tok = estimate_messages_array_tokens(msgs)
        ratio = msg_tok / SNAP_THRESHOLD if SNAP_THRESHOLD > 0 else 0
        if ratio >= 0.95:
            ready = "🔴 IMMINENT — PIVOT recommended now"
        elif ratio >= 0.85:
            ready = "🟡 WARNING — approaching PIVOT threshold"
        elif ratio >= 0.50:
            ready = "🟢 MONITORING — within range"
        else:
            ready = "⚪ NOMINAL — plenty of headroom"
        print(f"  Readiness: {ready}")
        print(f"            {fmt_num(msg_tok)} / {fmt_num(SNAP_THRESHOLD)} ({fmt_pct(ratio)})")
    print()


def _fmt_size(b):
    if b < 1024: return f"{b} B"
    elif b < 1024**2: return f"{b/1024:.1f} KB"
    else: return f"{b/1024**2:.1f} MB"


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return

    cmd = sys.argv[1]
    json_mode = "--json" in sys.argv or "-j" in sys.argv
    tui_mode = "--tui" in sys.argv

    if cmd == "gauge":
        show_gauge(json_mode=json_mode, tui_mode=tui_mode)
    
    elif cmd == "snap":
        r = do_snap()
        if r.get("status") == "snapped":
            print(f"\n  ✅ SNAP: {r['messages_captured']} msgs → {r['snap_file']}")
            print(f"     Messages array: ~{fmt_num(r['messages_array_tokens'])} tokens")
            print(f"     Transcript: {_fmt_size(r['transcript_length'])}")
            if json_mode:
                print(json.dumps(r, indent=2))
        else:
            print(f"\n  ❌ {r.get('error', 'unknown')}")
    
    elif cmd == "drop":
        r = do_drop(force="--force" in sys.argv)
        if r.get("status") == "dropped":
            print(f"\n  ✅ DROP ready: {r['drop_file']}")
            print(f"     Snapshot source: {r['snap_file']}")
            print(f"     Transcript: ~{fmt_num(r['transcript_tokens'])} tokens")
            print(f"     Drop file: {_fmt_size(r['drop_file_size'])}")
            print(f"\n  ── Gauge resets to near-zero on new thread ──")
            print(f"  $ {r['usage']}")
            if json_mode:
                print(json.dumps(r, indent=2))
        else:
            print(f"\n  ❌ {r.get('error', 'unknown')}")
    
    elif cmd == "pivot":
        r = do_pivot()
        if r.get("status") == "pivoted":
            s = r["snap"]
            d = r["drop"]
            print(f"\n  ╔══════════════════════════════════════════════════════════╗")
            print(f"  ║          PIVOT ⚔⟊  Snap + Drop (seamless)               ║")
            print(f"  ╚══════════════════════════════════════════════════════════╝")
            print(f"\n  ✅ SNAP:  {s['messages_captured']} msgs → {s['snap_file']}")
            print(f"     Array: ~{fmt_num(s['messages_array_tokens'])} tokens, transcript {_fmt_size(s['transcript_length'])}")
            print(f"\n  ✅ DROP:  {d['drop_file']}")
            print(f"     ~{fmt_num(d['transcript_tokens'])} tokens in snapshot block")
            print(f"\n  ── Gauge drops from ~{fmt_num(s['messages_array_tokens'])} to ~1 token ──")
            print(f"  $ {d['usage']}")
            if json_mode:
                print(json.dumps(r, indent=2))
        else:
            print(f"\n  ❌ PIVOT failed: {r.get('error', 'unknown')}")
    
    elif cmd == "status":
        show_gauge(json_mode=json_mode)
        show_drop_status()
    
    elif cmd == "drop-status":
        show_drop_status()
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()

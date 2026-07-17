#!/usr/bin/env python3
"""
SNAP n DROP — Compact TUI Gauge Ticker v2.0
Outputs a one-line gauge measuring the ACTIVE MESSAGES ARRAY size.
Designed to work with the Hermes TUI gauge (system prompt is cached/one-time).
"""
import sqlite3, os, json, sys
from pathlib import Path

PROFILE_DIR = Path(os.path.expanduser("~/.hermes/profiles/thotheauphis"))
STATE_DB = PROFILE_DIR / "state.db"
SNAP_THRESHOLD = int(os.environ.get("SNAP_THRESHOLD", "1000000"))

def fmt(n): return f"{n:,}"

try:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    def count(s): return len(enc.encode(s)) if s else 0
except:
    def count(s): return len(s) // 4 if s else 0

conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
s = conn.execute("""SELECT id, message_count FROM sessions 
    WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1""").fetchone()
if not s:
    print("⏳ [No session]"); sys.exit(0)

# Get active messages and estimate array size
msgs = conn.execute("""SELECT role, content, tool_calls FROM messages 
    WHERE session_id = ? AND active = 1 ORDER BY id ASC""", (s["id"],)).fetchall()

msg_array_tokens = 0
for m in msgs:
    msg_array_tokens += count(m["content"] or "") + 8
    if m["tool_calls"]:
        try:
            tc = json.loads(m["tool_calls"]) if isinstance(m["tool_calls"], str) else m["tool_calls"]
            msg_array_tokens += len(tc) * 15 if isinstance(tc, list) else 20
        except:
            msg_array_tokens += 20

msg_count = len(msgs)

# Last user message
last = conn.execute("""SELECT content FROM messages 
    WHERE session_id = ? AND role = 'user' AND active = 1 
    ORDER BY id DESC LIMIT 1""", (s["id"],)).fetchone()
wc = count(last["content"]) if last and last["content"] else 0

# Models
models = []
for m in conn.execute("""SELECT model, billing_provider, input_tokens, output_tokens 
    FROM session_model_usage WHERE session_id = ? 
    ORDER BY last_seen DESC""", (s["id"],)):
    label = m["model"].split("/")[-1][:16]
    models.append(f"{label}:{fmt(m['input_tokens'] or 0)}△{fmt(m['output_tokens'] or 0)}▽")
conn.close()

# Bar
bar_w = 14
filled = min(int((msg_array_tokens / SNAP_THRESHOLD) * bar_w), bar_w) if SNAP_THRESHOLD > 0 else 0
bar = "█" * filled + "░" * (bar_w - filled)
warn = "⚠️" if msg_array_tokens >= SNAP_THRESHOLD * 0.85 else "▲" if msg_array_tokens >= SNAP_THRESHOLD * 0.5 else "●"

pct = (msg_array_tokens / SNAP_THRESHOLD) * 100 if SNAP_THRESHOLD > 0 else 0
snap_count = len(list(Path(str(PROFILE_DIR / "snapshots")).glob("snap_*.txt")))
model_str = " | ".join(models) if models else ""
remain = SNAP_THRESHOLD - msg_array_tokens

print(f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯")
print(f"  SNAP n DROP {warn} |{bar}| {pct:.1f}% | "
      f"Array: {fmt(msg_array_tokens)} / {fmt(SNAP_THRESHOLD)} | "
      f"msgs:{msg_count} | WC:{fmt(wc)}")
if model_str:
    print(f"  {model_str}")
print(f"  Remaining: {fmt(remain)} | Snaps: {snap_count}")
if snap_count > 0:
    drop_file = PROFILE_DIR / "snapshots" / "drop_sovereign_prompt.md"
    if drop_file.exists():
        print(f"  DROP ready: $ hermes chat --sovereign-prompt {drop_file}")
print(f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯")

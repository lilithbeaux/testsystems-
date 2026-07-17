---
name: snapndrop
description: SNAP n DROP — measures the LIVE messages array size (not cumulative DB totals). Seamless SNAP+DROP pivot for context management with 1M token threshold. System prompt is cached/one-time.
---

# SNAP n DROP — Context Gauge & Thread Rotation v2.0

## Architecture
- **Gauge tracks the ACTIVE MESSAGES ARRAY** — what gets sent to the API each turn
- **System prompt is cached/sent-once** — NOT counted in the per-turn gauge
- After DROP, gauge drops from `~N` to `~1` token (just the first user message)
- Threshold: **1,000,000 tokens** (overridable via `SNAP_THRESHOLD` env var)

## Files

| Path | Purpose |
|------|---------|
| `scripts/snapndrop.py` | Main utility: `gauge`, `snap`, `drop`, `pivot`, `status` |
| `scripts/snapndrop_ticker.py` | Compact one-line gauge for inline display |
| `snapshots/` | Repository of snapshot files (`snap_*.txt`) |
| `snapshots/drop_sovereign_prompt.md` | DROP-ready sovereign prompt |
| `snapshots/snap_*.txt` | Plain-text conversation transcripts |
| `.snapndrop_counter.json` | Metadata tracking (last snap, etc.) |

## Core Commands

### Show full gauge (messages array size, not cumulative)
```bash
python3 ~/.hermes/profiles/thotheauphis/scripts/snapndrop.py gauge
```

### TUI compact line
```bash
python3 ~/.hermes/profiles/thotheauphis/scripts/snapndrop.py gauge --tui
```

### PIVOT — SNAP + DROP in one seamless operation
```bash
python3 ~/.hermes/profiles/thotheauphis/scripts/snapndrop.py pivot
```
Does both steps atomically:
1. SNAP: captures all active messages to a plain-text transcript file
2. DROP: builds the sovereign prompt embedding the [CONTEXT SNAPSHOT]

### Compact ticker
```bash
python3 ~/.hermes/profiles/thotheauphis/scripts/snapndrop_ticker.py
```

### JSON output (for automation/cron)
```bash
python3 ~/.hermes/profiles/thotheauphis/scripts/snapndrop.py gauge --json
```

## Protocol

### SNAP Trigger
When the messages array approaches the threshold (default 1M):
1. Run `snapndrop.py pivot` — saves the messages array as a plain-text transcript
2. The transcript is embedded in a `[CONTEXT SNAPSHOT — STATIC, NOT RESUBMITTED]` block
3. The sovereign prompt file is written to `snapshots/drop_sovereign_prompt.md`

### DROP (Thread Pivot)
1. Exit the current TUI session
2. Start a new one with: `hermes chat --sovereign-prompt ~/.hermes/profiles/thotheauphis/snapshots/drop_sovereign_prompt.md`
3. The snapshot block is part of the system prompt (cached/one-time)
4. **Gauge drops dramatically** — from ~N to ~1 token (just the first user message)
5. Subsequent turns only add new messages; the snapshot never enters the messages array

### Environment Variables
- `SNAP_THRESHOLD` — override the 1M default (e.g. `SNAP_THRESHOLD=500000`)

## What the Gauge Shows

```
SND ● |░░░░░░░░░░░░░░| 3.7% | Array: 37,282 / 1,000,000 | msgs:106 | WC:124
deepseek-reasone:70,372△40,207▽
Remaining: 962,718 | Snaps: 2
DROP ready: $ hermes chat --sovereign-prompt ...
```

- **Array**: current messages array size (what goes to the API, NOT cumulative)
- **WC**: working context = tokens in last user submission
- **Models**: per-model cumulative in/out (for monitoring, not gauge)
- **Remaining**: tokens left before threshold
- **Snaps**: number of snapshots on disk

## Pitfalls

### 🔴 DO NOT inline the gauge in agent responses
Every time you output the gauge reading, those tokens get added to the messages array — **the very thing the gauge is measuring**. This creates a circular token burn:
  - Gauge outputs ~400 tokens per display
  - Every display pushes the array closer to threshold
  - Multiple inline gauges can waste 2k+ tokens per session
  - **Correct approach**: the gauge updates are captured to a file; the user reads them externally or from the TUI footer gauge. The agent should show it once on request and otherwise stay silent about it.

### 🔴 The user cannot run terminal commands from within TUI
Scripts placed under `~/.hermes/profiles/<profile>/scripts/` are not accessible from within a running TUI session. To give the user access:
  - Copy scripts to `~/Desktop/<BundleName>/` for file-manager access
  - The user will hand them to external agents (Gemini, Claude) to run
  - Never assume the user can `cd` and `python3 script.py` from within chat

### 🔴 Gauge measures messages array, NOT cumulative DB totals
The session DB's `sessions.input_tokens` is a **running cumulative total** across all turns, which always exceeds 64k+ after enough exchanges. The actual per-request context is just the `messages` table rows where `active = 1` — this is what the TUI built-in gauge tracks. Always measure `estimate_messages_array_tokens()` against the threshold, not `input_tokens + output_tokens`.

### 🔴 `--sovereign-prompt` replaces the entire system prompt
The flag `hermes chat --sovereign-prompt <file>` does NOT append to the existing prompt — it **replaces** the entire auto-generated system prompt (skills, memory, profile, tools, everything). This is designed for total-control use cases. If the user's Hermes build does system prompt caching (send once, never resubmit), the DROP works cleanly. If not, the prompt replacement may lose bundled functionality.

### 🔴 Snapshot is a point-in-time record
A SNAP only captures messages where `active = 1` at the moment of capture. If the session's compression system has compacted older messages (set `active = 0`), the snapshot will be missing those compressed turns. Take the snap BEFORE the compression pass if a full transcript is needed.

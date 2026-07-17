#!/usr/bin/env python3
"""
hermes-executor — Silent Tool Execution Engine
===============================================
Runs as a cron job (no_agent=true). Zero LLM overhead.
Reads batch files from ~/.hermes/executor/in/, executes tools,
writes results to ~/.hermes/executor/out/.

Batch format (JSON):
{
  "id": "batch_001",
  "tools": [
    {"name": "terminal", "args": {"command": "ls -la"}},
    {"name": "read_file", "args": {"path": "/tmp/test.txt"}},
    {"name": "web_search", "args": {"query": "test"}}
  ]
}

Result format (JSON):
{
  "id": "batch_001",
  "status": "done",
  "results": [
    {"name": "terminal", "output": "...", "exit_code": 0},
    {"name": "read_file", "content": "...", "error": null}
  ],
  "completed_at": "..."
}
"""

import os, sys, json, time, subprocess, shlex, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE = Path.home() / ".hermes" / "executor"
INBOX = BASE / "in"
OUTBOX = BASE / "out"
LOCK = BASE / "executor.lock"

for d in [BASE, INBOX, OUTBOX]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Tool Registry ───

def cmd_terminal(args):
    """Execute shell command."""
    cmd = args.get("command", "")
    timeout = args.get("timeout", 30)
    workdir = args.get("workdir")
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=workdir
        )
        return {
            "output": (r.stdout + r.stderr)[-50000:],
            "exit_code": r.returncode
        }
    except subprocess.TimeoutExpired:
        return {"output": "TIMEOUT", "exit_code": -1}
    except Exception as e:
        return {"output": str(e), "exit_code": -1}

def cmd_read_file(args):
    """Read a file."""
    path = args.get("path", "")
    try:
        with open(os.path.expanduser(path)) as f:
            content = f.read()
        return {"content": content, "size": len(content)}
    except Exception as e:
        return {"error": str(e)}

def cmd_write_file(args):
    """Write a file."""
    path = args.get("path", "")
    content = args.get("content", "")
    try:
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return {"written": len(content), "path": path}
    except Exception as e:
        return {"error": str(e)}

def cmd_search_files(args):
    """Search files by pattern."""
    pattern = args.get("pattern", "")
    path = args.get("path", ".")
    try:
        from pathlib import Path as P
        root = P(os.path.expanduser(path))
        matches = []
        for p in root.rglob(pattern):
            if p.is_file():
                matches.append(str(p.relative_to(root)))
        return {"matches": matches[:50], "total": len(matches)}
    except Exception as e:
        return {"error": str(e)}

def cmd_web_search(args):
    """Simple web search via DuckDuckGo."""
    query = args.get("query", "")
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for topic in data.get("RelatedTopics", []):
            if "Text" in topic:
                results.append({"title": topic.get("Text","")[:200], "url": topic.get("FirstURL","")})
        return {"results": results[:10]}
    except Exception as e:
        return {"error": str(e)}

def cmd_web_extract(args):
    """Extract content from a URL."""
    url = args.get("url", "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        # Strip tags (crude but fast)
        import re
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()[:15000]
        return {"content": text, "url": url}
    except Exception as e:
        return {"error": str(e)}

TOOLS = {
    "terminal": cmd_terminal,
    "read_file": cmd_read_file,
    "write_file": cmd_write_file,
    "search_files": cmd_search_files,
    "web_search": cmd_web_search,
    "web_extract": cmd_web_extract,
}

# ─── Executor ───

def acquire_lock() -> bool:
    try:
        with open(LOCK, 'x') as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False

def release_lock():
    if LOCK.exists():
        LOCK.unlink()

def execute_batch(batch: dict) -> dict:
    batch_id = batch.get("id", "unknown")
    tools = batch.get("tools", [])
    results = []
    errors = []

    for i, tool in enumerate(tools):
        name = tool.get("name", "")
        args = tool.get("args", {})
        handler = TOOLS.get(name)

        if not handler:
            errors.append({"index": i, "name": name, "error": f"Unknown tool: {name}"})
            continue

        try:
            result = handler(args)
            results.append({
                "index": i,
                "name": name,
                "status": "error" if "error" in result else "done",
                **result
            })
        except Exception as e:
            errors.append({"index": i, "name": name, "error": str(e)})

    return {
        "id": batch_id,
        "status": "done",
        "results": results,
        "errors": errors if errors else None,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "total": len(tools),
        "success": len(results),
        "failed": len(errors),
    }

def process_inbox():
    """Process all pending batch files."""
    if not acquire_lock():
        return  # Another instance running

    try:
        for batch_file in sorted(INBOX.glob("*.json")):
            try:
                batch = json.loads(batch_file.read_text())
                result = execute_batch(batch)
                # Write result
                out_file = OUTBOX / f"{batch.get('id', batch_file.stem)}.json"
                out_file.write_text(json.dumps(result, indent=2))
                # Remove batch
                batch_file.unlink()
            except json.JSONDecodeError as e:
                error_file = OUTBOX / f"{batch_file.stem}_error.json"
                error_file.write_text(json.dumps({
                    "id": batch_file.stem,
                    "status": "parse_error",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }))
                batch_file.unlink()
    finally:
        release_lock()

def write_batch(tools: list, batch_id: str = None) -> str:
    """Write a batch file for the executor to process. Returns batch ID."""
    if batch_id is None:
        batch_id = f"batch_{int(time.time())}"
    batch = {
        "id": batch_id,
        "tools": tools,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = INBOX / f"{batch_id}.json"
    path.write_text(json.dumps(batch, indent=2))
    return batch_id

def wait_for_result(batch_id: str, timeout: int = 60) -> dict:
    """Wait for executor to complete a batch. Polls result file."""
    out_path = OUTBOX / f"{batch_id}.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if out_path.exists():
            result = json.loads(out_path.read_text())
            out_path.unlink()  # Clean up
            return result
        time.sleep(0.5)
    return {"id": batch_id, "status": "timeout", "error": f"No result within {timeout}s"}

def batch_and_wait(tools: list, timeout: int = 60) -> dict:
    """Write a batch, trigger cron, wait for result."""
    batch_id = write_batch(tools)
    # Process immediately (synchronous mode)
    process_inbox()
    return wait_for_result(batch_id, timeout)

# ─── CLI ───

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Executor Engine")
    parser.add_argument("mode", choices=["daemon", "process", "batch", "status"],
                       help="daemon: run once (cron mode) | process: process inbox | batch: write + exec | status: show stats")
    parser.add_argument("--tool", nargs=3, metavar=("NAME", "KEY", "VAL"),
                       help="Tool call: --tool terminal command 'ls -la'")
    parser.add_argument("--batch-file", help="JSON file with batch")
    
    args = parser.parse_args()
    
    if args.mode == "process":
        process_inbox()
        print(json.dumps({"status": "processed", "inbox": str(INBOX), "outbox": str(OUTBOX)}))
    
    elif args.mode == "status":
        inbox_count = len(list(INBOX.glob("*.json")))
        outbox_count = len(list(OUTBOX.glob("*.json")))
        print(json.dumps({
            "inbox_pending": inbox_count,
            "outbox_ready": outbox_count,
            "inbox": str(INBOX),
            "outbox": str(OUTBOX),
            "lock_held": LOCK.exists(),
        }, indent=2))
    
    elif args.mode == "batch":
        if args.batch_file:
            with open(args.batch_file) as f:
                batch = json.load(f)
            result = execute_batch(batch)
            print(json.dumps(result, indent=2))
    
    elif args.mode == "daemon":
        process_inbox()

#!/usr/bin/env python3
"""
Strict Executor — Zero LLM, pure tool execution.
Reads batch from stdin or file, executes tools, writes JSON result.
No system prompt, no reasoning, no commentary.
"""
import sys, json, os, subprocess, shlex, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

# Tool implementations (subset matching hermes-executor)
def tool_terminal(args):
    cmd = args.get("command", "")
    timeout = args.get("timeout", 30)
    workdir = args.get("workdir")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, cwd=workdir)
        return {"output": (r.stdout + r.stderr)[-50000:], "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"output": "TIMEOUT", "exit_code": -1}
    except Exception as e:
        return {"output": str(e), "exit_code": -1}

def tool_read_file(args):
    path = os.path.expanduser(args.get("path", ""))
    offset = args.get("offset", 1)
    limit = args.get("limit", 500)
    try:
        with open(path) as f:
            lines = f.readlines()
        total = len(lines)
        chunk = lines[offset-1:offset-1+limit]
        return {"content": "".join(chunk), "total_lines": total}
    except Exception as e:
        return {"error": str(e)}

def tool_write_file(args):
    path = os.path.expanduser(args.get("path", ""))
    content = args.get("content", "")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return {"written": len(content), "path": path}
    except Exception as e:
        return {"error": str(e)}

def tool_search_files(args):
    pattern = args.get("pattern", "")
    path = os.path.expanduser(args.get("path", "."))
    target = args.get("target", "content")
    limit = args.get("limit", 50)
    try:
        import subprocess
        if target == "files":
            r = subprocess.run(["find", path, "-name", pattern], capture_output=True, text=True)
            matches = r.stdout.strip().split('\n')[:limit]
            return {"matches": matches, "total": len(matches)}
        else:
            r = subprocess.run(["rg", "-l", pattern, path], capture_output=True, text=True)
            matches = r.stdout.strip().split('\n')[:limit]
            return {"matches": matches, "total": len(matches)}
    except Exception as e:
        return {"error": str(e)}

def tool_web_search(args):
    query = args.get("query", "")
    limit = args.get("limit", 5)
    try:
        # DuckDuckGo HTML scrape (no API key)
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=10).read().decode()
        # Simple extraction
        import re
        results = re.findall(r'<a class="result__url" href="([^"]+)">([^<]+)</a>.*?<a class="result__snippet" href="[^"]*">([^<]+)</a>', html, re.DOTALL)
        return {"data": {"web": [{"url": u, "title": t, "description": d} for u,t,d in results[:limit]]}}
    except Exception as e:
        return {"error": str(e)}

def tool_web_extract(args):
    urls = args.get("urls", [])
    char_limit = args.get("char_limit", 15000)
    try:
        results = []
        for url in urls[:5]:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req, timeout=15).read().decode()
            # Strip tags, get text
            import re
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text)[:char_limit]
            results.append({"url": url, "content": text, "error": None})
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}

TOOLS = {
    "terminal": tool_terminal,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "search_files": tool_search_files,
    "web_search": tool_web_search,
    "web_extract": tool_web_extract,
}

def execute_batch(batch):
    """Execute a batch of tool calls."""
    results = []
    for i, call in enumerate(batch.get("tools", [])):
        name = call.get("name")
        args = call.get("args", {})
        if name in TOOLS:
            out = TOOLS[name](args)
            results.append({"index": i, "name": name, "status": "done" if "error" not in out else "error", **out})
        else:
            results.append({"index": i, "name": name, "status": "error", "error": f"Unknown tool: {name}"})
    return {
        "id": batch.get("id", f"batch_{datetime.now(timezone.utc).isoformat()}"),
        "status": "done",
        "results": results,
        "completed_at": datetime.now(timezone.utc).isoformat()
    }

if __name__ == "__main__":
    # Read batch from stdin or file arg
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            batch = json.load(f)
    else:
        batch = json.load(sys.stdin)
    
    result = execute_batch(batch)
    print(json.dumps(result, indent=2))

#!/usr/bin/env python3
"""
TogetherAI + DeepSeek Hybrid Executor
======================================
- DeepSeek (via OpenRouter) for planning/reasoning
- TogetherAI free models for execution (if key available)
- Falls back to OpenRouter free models
"""
import os, sys, json, subprocess, time
from datetime import datetime, timezone

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TOGETHER_KEY = os.environ.get("TOGETHER_API_KEY", "")

DEEPSEEK_MODEL = "deepseek/deepseek-chat"
TOGETHER_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo" if TOGETHER_KEY else "nvidia/nemotron-3-ultra-550b-a55b:free"
DEEPSEEK_API = "https://openrouter.ai/api/v1/chat/completions"
TOGETHER_API = "https://api.together.xyz/v1/chat/completions" if TOGETHER_KEY else "https://openrouter.ai/api/v1/chat/completions"

# Tool implementations (same as before)
import urllib.request, urllib.parse, shlex

def tool_terminal(args):
    cmd = args.get("command", "")
    timeout = args.get("timeout", 30)
    workdir = args.get("workdir")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=workdir)
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
        if target == "files":
            r = subprocess.run(["find", path, "-name", pattern], capture_output=True, text=True)
            matches = r.stdout.strip().split('\n')[:limit]
        else:
            r = subprocess.run(["rg", "-l", pattern, path], capture_output=True, text=True)
            matches = r.stdout.strip().split('\n')[:limit]
        return {"matches": matches, "total": len(matches)}
    except Exception as e:
        return {"error": str(e)}

TOOLS = {
    "terminal": tool_terminal,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "search_files": tool_search_files,
}

def call_llm(api_url, api_key, model, messages, max_tokens=4096, temp=0.1):
    import urllib.request
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temp}
    req = urllib.request.Request(api_url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        return f"ERROR {e.code}: {e.read().decode()}"
    except Exception as e:
        return f"ERROR: {e}"

def plan_with_deepseek(goal):
    system = """You are a task planner. Output ONLY a JSON array of tool calls.
Available tools:
- terminal: {"command": "shell command", "timeout": 30, "workdir": "/optional/path"}
- read_file: {"path": "/path/to/file", "offset": 1, "limit": 500}
- write_file: {"path": "/path/to/file", "content": "content"}
- search_files: {"pattern": "glob pattern", "path": "/search/path", "target": "content|files", "limit": 50}

Format: [{"name": "tool_name", "args": {...}}, ...]
No commentary. No markdown."""
    
    result = call_llm(DEEPSEEK_API, OPENROUTER_KEY, DEEPSEEK_MODEL, [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Goal: {goal}\n\nOutput the tool call sequence as JSON array:"}
    ], max_tokens=2048, temp=0.0)
    
    try:
        start = result.find('[')
        end = result.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(result[start:end])
    except:
        pass
    return []

def execute_batch(batch):
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
        "id": batch.get("id", f"batch_{int(time.time())}"),
        "status": "done",
        "results": results,
        "completed_at": datetime.now(timezone.utc).isoformat()
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: together_executor.py <batch.json> or together_executor.py plan \"goal\"")
        return
    
    if sys.argv[1] == "plan":
        goal = " ".join(sys.argv[2:])
        batch = {"id": f"plan_{int(time.time())}", "tools": plan_with_deepseek(goal)}
    else:
        with open(sys.argv[1]) as f:
            batch = json.load(f)
        # If batch has plan_prompt, plan it
        if "plan_prompt" in batch:
            batch = {"id": batch.get("id", f"plan_{int(time.time())}"), "tools": plan_with_deepseek(batch["plan_prompt"])}
    
    result = execute_batch(batch)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()

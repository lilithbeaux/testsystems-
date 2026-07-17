#!/usr/bin/env python3
"""
DeepSeek Batch Processor — Reads batch files, calls DeepSeek via OpenRouter for LLM tasks,
then dispatches tool calls to strict_executor.
Only used for tasks requiring LLM reasoning (not mechanical tool calls).
"""
import json, os, sys, requests
from pathlib import Path

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_KEY:
    print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
    sys.exit(1)

DEEPSEEK_MODEL = "deepseek/deepseek-chat"  # Cheap on OpenRouter

def call_deepseek(prompt, max_tokens=4096):
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0.1},
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def process_batch_file(batch_path):
    with open(batch_path) as f:
        batch = json.load(f)
    
    # Check if this batch needs LLM reasoning (has 'llm_prompt' field)
    if "llm_prompt" not in batch:
        return {"status": "skipped", "reason": "no llm_prompt field"}
    
    result = call_deepseek(batch["llm_prompt"])
    
    # Write result
    out_path = Path(batch_path).with_suffix(".result.json")
    with open(out_path, 'w') as f:
        json.dump({"batch_id": batch.get("id"), "llm_result": result}, f, indent=2)
    
    return {"status": "done", "result_file": str(out_path)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(process_batch_file(sys.argv[1]), indent=2))
    else:
        # Process all .json in inbox
        inbox = Path.home() / ".hermes" / "executor" / "in"
        for f in inbox.glob("*.json"):
            print(json.dumps(process_batch_file(f), indent=2))

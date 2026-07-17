#!/usr/bin/env python3
"""
LILAREYON AETHELGARD — Integrator CLI
======================================
Master integration command for the Unified Field.

Bridges: unified_field.py × state_machine.py × all system skills

Commands:
  /uf status         — Full system health report
  /uf checkpoint     — Manual checkpoint (optional name arg)
  /uf recall <q>     — SVA hyperspace recall
  /uf store <p> <k>  — Store stdin JSON to emerge path/key
  /uf execute <id>   — Queue executor batch from stdin JSON
  /uf wf list        — List available workflows
  /uf wf run <name>  — Run a state machine workflow
  /uf sync           — Sync SMS vectors → Emerge store
  /uf warp           — Warp terminal build status
"""

import sys, json, os, subprocess, time
from pathlib import Path

HOME = Path.home()
PROFILE = HOME / ".NOTTHEONETOEDIT" / "profiles" / "thotheauphis"
WORK = PROFILE / "work"


def _import_or_die(module_path, name):
    """Import a module from absolute path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None:
        print(f"❌ Module not found: {module_path}")
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_status(args):
    """Full system health report."""
    uf = _import_or_die(WORK / "unified_field.py", "unified_field").UnifiedField()
    print(uf.health_report())
    
    # Also show state machine workflows
    sm = _import_or_die(WORK / "state_machine.py", "state_machine")
    print("\n  ── Workflows ──")
    for name, factory in [
        ("3tier", sm.pipeline_3tier),
        ("goal_loop", sm.agent_goal_loop),
        ("checkpointer", sm.checkpointer),
    ]:
        wf = factory()
        entry = wf._entry_node
        exit_nodes = ", ".join(wf._exit_nodes)
        print(f"    ▶ {name}: {entry} → {exit_nodes} ({len(wf._nodes)} nodes)")


def cmd_checkpoint(args):
    """Manual checkpoint."""
    uf = _import_or_die(WORK / "unified_field.py", "unified_field").UnifiedField()
    name = args[0] if args else f"manual_{int(time.time())}"
    ckpt_id = uf.checkpoint(name)
    print(f"💾 Checkpoint saved: {ckpt_id}")


def cmd_recall(args):
    """SVA hyperspace recall."""
    uf = _import_or_die(WORK / "unified_field.py", "unified_field").UnifiedField()
    query = " ".join(args) if args else input("Query: ")
    k = 5
    results = uf.recall(query, k)
    if results:
        for r in results:
            sim = r.get("similarity", 0)
            summary = r.get("summary", "")[:200]
            print(f"  [{sim:.3f}] {summary}")
    else:
        print("  (no results)")


def cmd_store(args):
    """Store data to emerge."""
    if len(args) < 2:
        print("Usage: /uf store <path> <key>  (reads JSON from stdin)")
        return
    path, key = args[0], args[1]
    data = json.loads(sys.stdin.read())
    uf = _import_or_die(WORK / "unified_field.py", "unified_field").UnifiedField()
    uf.store(path, key, data)
    print(f"✅ Stored {path}/{key}")


def cmd_execute(args):
    """Queue executor batch."""
    batch_id = args[0] if args else f"batch_{int(time.time())}"
    tools = json.loads(sys.stdin.read())
    uf = _import_or_die(WORK / "unified_field.py", "unified_field").UnifiedField()
    uf.execute(batch_id, tools)
    print(f"📤 Queued {batch_id} ({len(tools)} tools)")


def cmd_memorize(args):
    """Bidirectional memorize: SMS tri-brid + SVA hyperspace store."""
    from unified_field import UnifiedField
    uf = UnifiedField()
    message = " ".join(args) if args else sys.stdin.read().strip()
    result = uf.memorize_and_store(message)
    print(json.dumps(result, indent=2))


def cmd_recall_feedback(args):
    """Bidirectional recall: SVA hyperspace + feed back into SMS."""
    from unified_field import UnifiedField
    uf = UnifiedField()
    query = " ".join(args) if args else ""
    k = 5
    result = uf.recall_and_memorize(query, k)
    print(json.dumps(result, indent=2, default=str))


def cmd_offload(args):
    """Executor toolchain offloading: queue a batch and get results."""
    if not args:
        print("Usage: /uf offload <step_name> [tools JSON from stdin]")
        return
    step_name = args[0]
    tools = json.loads(sys.stdin.read())
    from unified_field import UnifiedField
    uf = UnifiedField()
    result = uf.execute_workflow_step(step_name, tools, wait=True)
    print(json.dumps(result, indent=2, default=str))


def cmd_wf(args):
    """Workflow commands."""
    sm = _import_or_die(WORK / "state_machine.py", "state_machine")
    
    WORKFLOW_FACTORIES = {
        "3tier": sm.pipeline_3tier,
        "goal_loop": sm.agent_goal_loop,
        "checkpointer": sm.checkpointer,
        "executor_offload": sm.executor_offload,
    }
    
    if not args or args[0] == "list":
        for name, factory in sorted(WORKFLOW_FACTORIES.items()):
            wf = factory()
            entry = wf._entry_node
            exit_nodes = ", ".join(wf._exit_nodes)
            print(f"  {name}: {entry} → {exit_nodes} ({len(wf._nodes)} nodes)")
        return
    
    if args[0] == "run":
        wf_name = args[1] if len(args) > 1 else "3tier"
        factory = WORKFLOW_FACTORIES.get(wf_name)
        if not factory:
            print(f"Unknown workflow: {wf_name}")
            print(f"Available: {', '.join(WORKFLOW_FACTORIES.keys())}")
            return
        
        wf = factory()
        state = sm.WorkflowState()
        if len(args) > 2:
            state["active_goal"] = " ".join(args[2:])
        
        final = wf.run(state)
        print(f"\n=== {wf_name} Complete ===")
        print(f"  Turns: {final.get('_turns_executed', 0)}")
        print(f"  Budget: {final.budget() * 100:.0f}%")
        print(f"  Errors: {len(final.get('errors', []))}")
        return
    
    if args[0] == "checkpoints":
        wf_name = args[1] if len(args) > 1 else "3tier"
        factories = {
            "3tier": sm.pipeline_3tier,
            "goal_loop": sm.agent_goal_loop,
            "checkpointer": sm.checkpointer,
        }
        factory = factories.get(wf_name)
        if not factory:
            print(f"Unknown workflow: {wf_name}")
            return
        wf = factory()
        ckpts = wf.list_step_checkpoints()
        print(f"Checkpoints for '{wf_name}':")
        for c in ckpts[-20:]:
            print(f"  {c}")
        return


def cmd_sync(args):
    """Sync SMS vectors → Emerge store via temp file bridge."""
    from unified_field import UnifiedField, SMS_STORE, EMERGE_DATA, SMS_VENV
    import struct, pickle
    
    uf = UnifiedField()
    
    print("Syncing SMS VSA vectors → Emerge...")
    
    # Run extraction using SMS venv Python
    extract_script = """
import ZODB, ZODB.FileStorage, pickle, json, sys
store_path = '{store}'
fs = ZODB.FileStorage.FileStorage(store_path)
db = ZODB.DB(fs)
conn = db.open()
root = conn.root()
vectors = root.get('vectors', {{}})
metadata = root.get('metadata', {{}})
out = {{}}
for k, v_bytes in vectors.items():
    vec = pickle.loads(v_bytes)
    meta = metadata.get(k, {{}})
    out[k] = {{
        "vector": vec.tolist() if hasattr(vec, 'tolist') else list(vec),
        "shape": list(vec.shape) if hasattr(vec, 'shape') else [len(vec)],
        "metadata": meta,
    }}
with open('/tmp/sms_vectors_sync.json', 'w') as f:
    json.dump(out, f)
print(len(out))
conn.close()
db.close()
fs.close()
""".format(store=SMS_STORE)
    
    sms_python = SMS_VENV / "bin" / "python"
    if sms_python.exists():
        r = subprocess.run([str(sms_python), "-c", extract_script], 
                          capture_output=True, text=True, timeout=30)
        count = r.stdout.strip()
        print(f"  Extracted {count} vectors from SMS ZODB")
    else:
        print("  ⚠️ SMS venv not found, skipping extraction")
        return
    
    # Store on Emerge
    if Path("/tmp/sms_vectors_sync.json").exists():
        vectors = json.loads(Path("/tmp/sms_vectors_sync.json").read_text())
        for key, data in vectors.items():
            uf.store("/sms_vectors", key, data)
        print(f"  Stored {len(vectors)} vectors on Emerge at /sms_vectors/")
        Path("/tmp/sms_vectors_sync.json").unlink(missing_ok=True)


def cmd_warp(args):
    """Warp terminal build status and integration."""
    uf = _import_or_die(WORK / "unified_field.py", "unified_field").UnifiedField()
    uf.reconnect()
    status = uf.warp_status()
    
    if not args or args[0] == "status":
        if status.get("built"):
            size_kb = status["size"] // 1024
            print(f"✅ Warp TUI built ({size_kb} KB)")
            print(f"   Binary: {status['binary']}")
            print(f"   Launch: {uf.warp_launch_cmd()}")
        else:
            print("⚠️ Warp TUI not built - build running in background")
            print(f"   Binary: {status['binary']}")
        
        # Warp bridge status
        try:
            ms = uf.warp_memory()
            ss = uf.warp_sessions()
            if ms:
                memories = ms.list_memories(limit=5)
                print(f"   WarpMemoryStore: ✅ ({len(memories)} memories)")
            if ss:
                sessions = ss.list()
                print(f"   WarpSessionStore: ✅ ({len(sessions)} sessions)")
        except Exception:
            pass
    
    elif args[0] == "memory":
        """Warp memory operations: list, create <content>"""
        ms = uf.warp_memory()
        if not ms:
            print("❌ WarpMemoryStore not available")
            return
        if len(args) == 1 or args[1] == "list":
            memories = ms.list_memories(limit=20)
            print(f"Warp memories ({len(memories)}):")
            for m in memories:
                content = str(m.get("content", ""))[:100]
                reason = m.get("reason", "")
                print(f"  {m.get('memory_id','?')[:16]}: {content}")
        elif args[1] == "create":
            content = " ".join(args[2:]) if len(args) > 2 else sys.stdin.read().strip()
            result = ms.create_memory(content, "CLI creation")
            print(f"✅ Memory created: {result.get('memory_id','?')}")
    
    elif args[0] == "session":
        """Warp session operations: list, save <id> [context JSON]"""
        ss = uf.warp_sessions()
        if not ss:
            print("❌ WarpSessionStore not available")
            return
        if len(args) == 1 or args[1] == "list":
            sessions = ss.list()
            print(f"Warp sessions ({len(sessions)}):")
            for s in sessions:
                print(f"  {s}")
        elif args[1] == "save":
            sid = args[2] if len(args) > 2 else f"session_{int(time.time())}"
            data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {"note": "CLI save"}
            ss.save(sid, data)
            print(f"✅ Session saved: {sid}")
        elif args[1] == "load":
            sid = args[2] if len(args) > 2 else ""
            data = ss.load(sid)
            if data:
                print(json.dumps(data, indent=2, default=str)[:2000])
            else:
                print(f"❌ Session not found: {sid}")
    
    else:
        print("Usage: uf warp [status|memory|session]")


def main():
    if len(sys.argv) < 2:
        cmd_status([])
        return
    
    cmd = sys.argv[1]
    args = sys.argv[2:]
    
    COMMANDS = {
        "status": cmd_status,
        "checkpoint": cmd_checkpoint,
        "recall": cmd_recall,
        "store": cmd_store,
        "execute": cmd_execute,
        "wf": cmd_wf,
        "sync": cmd_sync,
        "warp": cmd_warp,
        "memorize": cmd_memorize,
        "recall-feedback": cmd_recall_feedback,
        "offload": cmd_offload,
    }
    
    handler = COMMANDS.get(cmd)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: status, checkpoint, recall, store, execute, wf, sync, warp")


if __name__ == "__main__":
    main()

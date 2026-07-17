#!/usr/bin/env python3
"""
fleet_integration.py — Unified Fleet System Integration
========================================================
Ties together:
- hermes-executor (silent tool batches)
- fleet_emerge (EmergeFS objects + fallback)
- Memory compression (auto-tac-compress)
- Fleet daemon registry
- Work order management

Run as cron job or import as module.
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Add work directory to path
WORK_DIR = Path(__file__).parent
sys.path.insert(0, str(WORK_DIR))

from fleet_emerge import FleetEmerge, get_client, emerge_health, fleet_daemons, fleet_register_daemon

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ─── Fleet Constants ───
FLEET_ROOT = Path.home() / ".NOTTHEONETOEDIT" / "fleet"
EXECUTOR_INBOX = Path.home() / ".hermes" / "executor" / "in"
EXECUTOR_OUTBOX = Path.home() / ".hermes" / "executor" / "out"

# ─── Daemon Registry ───
KNOWN_DAEMONS = [
    {
        "name": "thotheauphis-memory",
        "type": "memory",
        "endpoint": "tcp://localhost:5555",
        "description": "Persistent terminal memory with vector search",
        "commands": ["recall", "store", "search", "compress"],
        "health_check": "status"
    },
    {
        "name": "hermes-executor",
        "type": "executor",
        "endpoint": "file://~/.hermes/executor/in",
        "description": "Silent batch tool executor",
        "commands": ["terminal", "read_file", "write_file", "search_files", "web_search", "web_extract"],
        "health_check": "ping"
    },
    {
        "name": "bromium-browser",
        "type": "browser",
        "endpoint": "tcp://localhost:9222",
        "description": "CEF-based browser with Aethelgard bridge",
        "commands": ["navigate", "click", "type", "snapshot", "extract"],
        "health_check": "status"
    },
    {
        "name": "auto-tac-compress",
        "type": "compression",
        "endpoint": "cron",
        "description": "Auto Chinese context compression",
        "commands": ["compress", "restore", "estimate"],
        "health_check": "last_run"
    },
    {
        "name": "spades-engine",
        "type": "game",
        "endpoint": "module",
        "description": "Deterministic Spades card engine",
        "commands": ["deal", "play", "bid", "score", "shuffle"],
        "health_check": "test"
    },
    {
        "name": "fleet-registry",
        "type": "registry",
        "endpoint": "emerge:///fleet/daemons",
        "description": "Fleet daemon registry in EmergeFS",
        "commands": ["register", "list", "status", "restart"],
        "health_check": "ping"
    }
]

# ─── Core Functions ───

def ensure_directories():
    """Ensure all required directories exist."""
    dirs = [
        FLEET_ROOT,
        EXECUTOR_INBOX,
        EXECUTOR_OUTBOX,
        Path.home() / ".hermes" / "emerge_fallback" / "fleet",
        Path.home() / ".hermes" / "emerge_fallback" / "daemons",
        Path.home() / ".hermes" / "emerge_fallback" / "work_orders",
        Path.home() / ".hermes" / "emerge_fallback" / "improvements",
        Path.home() / ".hermes" / "emerge_fallback" / "identities",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def register_known_daemons() -> int:
    """Register all known daemons in fleet registry."""
    fe = get_client()
    registered = 0
    for daemon in KNOWN_DAEMONS:
        spec = {k: v for k, v in daemon.items() if k != "name"}
        result = fe.register_daemon(daemon["name"], spec)
        if result.success:
            registered += 1
            log.info(f"Registered daemon: {daemon['name']}")
        else:
            log.warning(f"Failed to register {daemon['name']}: {result.error}")
    return registered


def check_daemon_health(name: str) -> Dict[str, Any]:
    """Check health of a specific daemon."""
    fe = get_client()
    
    # Try EmergeFS call first
    result = fe.call(f"/fleet/daemons/{name}", "health_check")
    if result.success:
        return {"name": name, "status": "healthy", "source": "emerge", "data": result.data}
    
    # Fallback: try direct check
    if name == "spades-engine":
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("test", "/home/craig/projects/spades-app/engine/test.dart")
            return {"name": name, "status": "available", "source": "module"}
        except:
            pass
    
    if name == "hermes-executor":
        inbox = Path.home() / ".hermes" / "executor" / "in"
        if inbox.exists():
            return {"name": name, "status": "ready", "source": "filesystem"}
    
    if name == "auto-tac-compress":
        cron = Path("/home/craig/.hermes/scripts/auto-tac-compress.py")
        if cron.exists():
            return {"name": name, "status": "scheduled", "source": "cron"}
    
    return {"name": name, "status": "unknown", "source": "fallback"}


def health_check_all() -> List[Dict[str, Any]]:
    """Run health checks on all known daemons."""
    results = []
    for daemon in KNOWN_DAEMONS:
        health = check_daemon_health(daemon["name"])
        results.append(health)
        log.info(f"Health {daemon['name']}: {health['status']}")
    return results


def queue_executor_batch(tools: List[Dict[str, Any]], batch_id: str = None) -> str:
    """Queue a batch of tool calls for the executor."""
    if batch_id is None:
        batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    
    batch_file = EXECUTOR_INBOX / f"{batch_id}.json"
    batch_file.write_text(json.dumps({
        "id": batch_id,
        "tools": tools,
        "created": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    
    log.info(f"Queued batch {batch_id} with {len(tools)} tools")
    return batch_id


def wait_executor_result(batch_id: str, timeout: int = 60) -> Dict:
    """Wait for executor result."""
    import time
    out_file = EXECUTOR_OUTBOX / f"{batch_id}.json"
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        if out_file.exists():
            result = json.loads(out_file.read_text())
            out_file.unlink()
            return result
        time.sleep(0.5)
    
    return {"error": f"Timeout waiting for {batch_id}"}


def run_executor_batch(tools: List[Dict[str, Any]]) -> Dict:
    """Run a batch synchronously."""
    batch_id = queue_executor_batch(tools)
    
    # Process immediately (synchronous mode)
    import importlib.util
    spec = importlib.util.spec_from_file_location("executor", WORK_DIR / "hermes-executor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.process_inbox()
    
    return wait_executor_result(batch_id)


def compress_memory_context() -> Dict[str, Any]:
    """Run memory compression cycle."""
    script = WORK_DIR / "auto-tac-compress.py"
    if script.exists():
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-500:],
            "stderr": result.stderr[-500:] if result.stderr else ""
        }
    return {"error": "Compression script not found"}


def create_work_order(wo: Dict) -> str:
    """Create a work order in the fleet registry."""
    fe = get_client()
    result = fe.store_work_order(wo)
    if result.success:
        return "created"
    return result.error


def get_active_work_orders() -> List[Dict]:
    """Get all active work orders."""
    fe = get_client()
    result = fe.get_work_orders("active")
    return result.data if result.success else []


def get_fleet_status() -> Dict[str, Any]:
    """Get comprehensive fleet status."""
    fe = get_client()
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health": emerge_health().__dict__ if hasattr(emerge_health(), '__dict__') else {"status": "unknown"},
        "daemons": health_check_all(),
        "daemon_count": len(KNOWN_DAEMONS),
        "work_orders": {
            "active": len([wo for wo in get_active_work_orders() if wo.get("status") == "active"]),
            "total": len(get_active_work_orders())
        },
        "emerge_fallback": str(Path.home() / ".hermes" / "emerge_fallback"),
        "executor_queue": len(list(EXECUTOR_INBOX.glob("*.json"))) if EXECUTOR_INBOX.exists() else 0,
        "executor_results": len(list(EXECUTOR_OUTBOX.glob("*.json"))) if EXECUTOR_OUTBOX.exists() else 0,
    }


def demo():
    """Run a demonstration of the integrated fleet."""
    print("=" * 60)
    print("FLEET INTEGRATION DEMO")
    print("=" * 60)
    
    # 1. Health check
    print("\n1. FLEET HEALTH CHECK")
    status = get_fleet_status()
    print(json.dumps(status, indent=2, default=str))
    
    # 2. Register daemons
    print("\n2. REGISTERING DAEMONS")
    count = register_known_daemons()
    print(f"Registered {count} daemons")
    
    # 3. List fleet
    print("\n3. FLEET REGISTRY")
    from fleet_emerge import fleet_daemons, fleet_identities
    print("Daemons:", fleet_daemons())
    print("Identities:", fleet_identities())
    
    # 4. Test executor batch
    print("\n4. EXECUTOR BATCH TEST")
    tools = [
        {"name": "terminal", "args": {"command": "echo 'Fleet integration live' && date"}},
        {"name": "read_file", "args": {"path": "/home/craig/checkctx.txt"}}
    ]
    result = run_executor_batch(tools)
    print("Batch result:", json.dumps(result, indent=2, default=str))
    
    # 5. Compression cycle
    print("\n5. MEMORY COMPRESSION")
    comp = compress_memory_context()
    print("Compression:", comp)
    
    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    ensure_directories()
    
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    elif len(sys.argv) > 1 and sys.argv[1] == "health":
        print(json.dumps(get_fleet_status(), indent=2, default=str))
    elif len(sys.argv) > 1 and sys.argv[1] == "register":
        print(f"Registered {register_known_daemons()} daemons")
    else:
        print("Usage: fleet_integration.py [demo|health|register]")
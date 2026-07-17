#!/usr/bin/env python3
"""
LILAREYON AETHELGARD — Unified Field
======================================
Central integration singleton that connects all sovereign systems:
  EMERGE  → persistent object store (ZODB-backed)
  SMS     → tri-brid memory (MemGPT + ReservoirPy + VSA)
  SVA     → hyperspace vectors (1024-D cosine recall)
  GATE    → tool output gating (GatedStore)
  EXEC    → silent batch executor
  WARP    → terminal interface

Every subsystem auto-detects availability and degrades gracefully.
"""

import json, os, pickle, uuid, time, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

log = logging.getLogger("unified_field")

# ── Paths ──────────────────────────────────────────────────────────────────────
HOME = Path.home()
PROFILE = HOME / ".NOTTHEONETOEDIT" / "profiles" / "thotheauphis"
SMS_VENV = PROFILE / "memory" / "sms" / "venv"
SMS_STORE = PROFILE / "memory" / "store" / "vsa_vectors.fs"
EMERGE_DATA = HOME / ".emerge" / "data"
EXECUTOR_IN = HOME / ".hermes" / "executor" / "in"
EXECUTOR_OUT = HOME / ".hermes" / "executor" / "out"
CHECKPOINT_DIR = PROFILE / "work" / "checkpoints"
SVA_DIR = Path("/tmp/sva")

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
EXECUTOR_IN.mkdir(parents=True, exist_ok=True)
EXECUTOR_OUT.mkdir(parents=True, exist_ok=True)


# ── Emerge Client (lazy import, graceful fallback) ──────────────────────────
class EmergeClient:
    """Thin wrapper around emerge.core.client with fallback to JSON file store.
    
    Two modes:
      1. Server mode — connects to a running emerge node via TCP
      2. JSON fallback — stores to ~/.emerge/data/ as flat JSON files (always works)
    
    Auto-detects emerge import availability. If import succeeds, tries server connection.
    Falls back to JSON on any failure. JSON fallback is the durable default.
    """
    
    def __init__(self, host="localhost", port=None):
        self.host = host
        self.port = port
        self._client = None
        self._server_available = False
        self._module_available = False
        self._init()
    
    def _init(self):
        # Check if emerge module is installed
        try:
            from emerge.core.client import Z0RPCClient as Client
            from emerge.core.objects import EmergeFile
            self._Client = Client
            self._EmergeFile = EmergeFile
            self._module_available = True
        except ImportError:
            self._module_available = False
            log.info("📁 Emerge module not installed — using JSON file store")
            return
        
        # Try known emerge server port first, then auto-discover
        known_ports = [54242, 5557, 5558]
        if self.port is None:
            self.port = self._try_known_ports(known_ports)
        
        if self.port is None:
            self.port = self._discover_port()
        
        if self.port:
            try:
                self._client = self._Client(self.host, str(self.port))
                self._client.list("/", 0, 0)
                self._server_available = True
                log.info("✅ Emerge server at %s:%s", self.host, self.port)
                self._ensure_server_root()
            except Exception as e:
                log.warning("⚠️ Emerge server unreachable (%s) — using JSON fallback", e)
                self._server_available = False
        else:
            log.info("📁 No emerge server found — using JSON file store at %s", EMERGE_DATA)
    
    def _try_known_ports(self, ports):
        """Try connecting with real Client to find emerge server."""
        for port in ports:
            try:
                c = self._Client(self.host, str(port))
                c.list("/", 0, 0)
                return port
            except Exception:
                continue
        return None
    
    def _discover_port(self):
        """Discover emerge node port from running processes."""
        import subprocess
        try:
            r = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                if "python3" in line or "emerge" in line:
                    parts = line.split()
                    for p in parts:
                        if ":" in p and p.split(":")[-1].isdigit():
                            port = p.split(":")[-1]
                            if port not in ("5558", "5557"):
                                return int(port)
        except Exception:
            pass
        return None
    
    def _ensure_server_root(self):
        """Ensure root directories exist on the emerge server."""
        needed = ["/fleet", "/sms_vectors", "/unified"]
        for path in needed:
            try:
                self._client.mkdir(path)
            except Exception:
                pass
    
    @property
    def available(self):
        return self._server_available or True  # JSON fallback always works
    
    def store(self, path: str, key: str, data: dict) -> bool:
        """Store data as an EmergeFile object."""
        if self._server_available:
            try:
                obj = self._EmergeFile(
                    id=key,
                    data=json.dumps(data),
                    date=datetime.now(timezone.utc).strftime("%b %d %Y %H:%M:%S"),
                    name=key,
                    path=path,
                    perms="rw-r--r--",
                    type="file",
                    uuid=str(uuid.uuid4()),
                    node="unified_field",
                    version=0
                )
                self._client.store(obj)
                return True
            except Exception as e:
                log.error("Emerge store failed: %s", e)
                return False
        # Fallback: write to local JSON
        return self._fallback_store(path, key, data)
    
    def read(self, path: str, key: str) -> Optional[dict]:
        """Read an EmergeFile object."""
        if self._server_available:
            try:
                obj = self._client.cat(f"{path}/{key}")
                if obj and hasattr(obj, 'data'):
                    return json.loads(obj.data) if isinstance(obj.data, str) else obj.data
            except Exception:
                pass
        return self._fallback_read(path, key)
    
    def list(self, path: str) -> list:
        """List objects under a path."""
        if self._server_available:
            try:
                return self._client.list(path, 0, 0) or []
            except Exception:
                pass
        return self._fallback_list(path)
    
    def delete(self, path: str, key: str) -> bool:
        """Delete an object."""
        if self._server_available:
            try:
                self._client.rm(f"{path}/{key}")
                return True
            except Exception as e:
                log.error("Emerge delete failed: %s", e)
                return False
        return self._fallback_delete(path, key)
    
    def _fallback_store(self, path: str, key: str, data: dict) -> bool:
        fallback_dir = EMERGE_DATA / path.lstrip("/")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        try:
            (fallback_dir / f"{key}.json").write_text(json.dumps(data, indent=2))
            return True
        except Exception as e:
            log.error("Fallback store failed: %s", e)
            return False
    
    def _fallback_read(self, path: str, key: str) -> Optional[dict]:
        fallback_dir = EMERGE_DATA / path.lstrip("/")
        f = fallback_dir / f"{key}.json"
        if f.exists():
            return json.loads(f.read_text())
        return None
    
    def _fallback_list(self, path: str) -> list:
        fallback_dir = EMERGE_DATA / path.lstrip("/")
        if fallback_dir.exists():
            return [f.stem for f in fallback_dir.glob("*.json")]
        return []
    
    def _fallback_delete(self, path: str, key: str) -> bool:
        f = EMERGE_DATA / path.lstrip("/") / f"{key}.json"
        if f.exists():
            f.unlink()
            return True
        return False


# ── SMS Client (lazy, graceful fallback) ──────────────────────────────────────
class SMSClient:
    """Thin wrapper around SMS CLI."""
    
    def __init__(self):
        self._sms_bin = HOME / ".local" / "bin" / "sms"
        self._available = self._sms_bin.exists()
    
    @property
    def available(self):
        return self._available
    
    def status(self) -> dict:
        """Get SMS health status as dict."""
        if not self._available:
            return {"available": False, "error": "sms binary not found"}
        import subprocess
        try:
            r = subprocess.run([str(self._sms_bin), "status"], capture_output=True, text=True, timeout=10)
            return {"available": True, "output": r.stdout.strip(), "exit_code": r.returncode}
        except Exception as e:
            return {"available": True, "error": str(e)}
    
    def persist(self) -> bool:
        """Force ZODB flush."""
        if not self._available:
            return False
        import subprocess
        try:
            r = subprocess.run([str(self._sms_bin), "persist"], capture_output=True, text=True, timeout=30)
            return r.returncode == 0
        except Exception:
            return False
    
    def process(self, message: str) -> dict:
        """Process a message through tri-brid pipeline."""
        if not self._available:
            return {"available": False, "error": "sms binary not found"}
        import subprocess
        try:
            r = subprocess.run([str(self._sms_bin), "process", message], capture_output=True, text=True, timeout=30)
            return {"output": r.stdout.strip(), "exit_code": r.returncode}
        except Exception as e:
            return {"error": str(e)}


# ── SVA / Snap-n-Drop Client (lazy, graceful fallback) ────────────────────────
class SVAClient:
    """Hyperspace vector storage and recall via SnapDrop module."""
    
    def __init__(self):
        self._snapdrop = None
        self._available = False
        self._init()
    
    def _init(self):
        try:
            import sys
            sys.path.insert(0, str(HOME / "projects" / "aethelgard" / "fleet" / "modules"))
            from snap_n_drop import SnapDrop
            self._snapdrop = SnapDrop()
            self._available = True
            log.info("✅ SVA SnapDrop initialized")
        except Exception as e:
            log.warning("⚠️ SVA SnapDrop unavailable (%s)", e)
    
    @property
    def available(self):
        return self._available
    
    def bind(self, text: str):
        """Convert text to 1024-D hypervector."""
        if self._available:
            return self._snapdrop.bind(text)
        return None
    
    def store(self, key: str, text: str):
        """Store text in SVA hyperspace."""
        if self._available:
            vec = self.bind(text)
            if vec is not None:
                return self._snapdrop.store(vec, text)
        return None
    
    def recall(self, query: str, k: int = 3) -> list:
        """Recall similar contexts via cosine similarity."""
        if self._available:
            return self._snapdrop.recall(query, k)
        return []
    
    def snap(self, text: str) -> Optional[str]:
        """Compress conversation to summary."""
        if self._available:
            return self._snapdrop.snap(text)
        return text[:500] + "..." if len(text) > 500 else text
    
    def get_context(self, key: str) -> Optional[str]:
        if self._available:
            return self._snapdrop.get_context(key)
        return None
    
    def status(self) -> dict:
        if not self._available:
            return {"available": False}
        try:
            index_path = SVA_DIR / "vectors" / "sva_index.json"
            entries = json.loads(index_path.read_text()) if index_path.exists() else {}
            return {"available": True, "entries": len(entries), "dimension": 1024}
        except Exception:
            return {"available": True, "entries": 0, "dimension": 1024}


# ── Executor Client ────────────────────────────────────────────────────────────
class ExecutorClient:
    """Batch execution via executor inbox/outbox pattern."""
    
    def queue(self, batch_id: str, tools: list) -> str:
        """Queue a tool batch for the executor."""
        batch = {"id": batch_id, "tools": tools}
        batch_path = EXECUTOR_IN / f"{batch_id}.json"
        batch_path.write_text(json.dumps(batch, indent=2))
        log.info("📤 Queued batch %s (%d tools)", batch_id, len(tools))
        return batch_id
    
    def process_now(self):
        """Synchronously process all pending batches."""
        import subprocess
        exec_path = PROFILE / "work" / "hermes-executor.py"
        if exec_path.exists():
            r = subprocess.run(["python3", str(exec_path), "process"], capture_output=True, text=True, timeout=30)
            return {"exit_code": r.returncode, "output": r.stdout.strip()}
        return {"error": "executor not found"}
    
    def read_result(self, batch_id: str) -> Optional[dict]:
        """Read executor result."""
        result_path = EXECUTOR_OUT / f"{batch_id}.json"
        if result_path.exists():
            return json.loads(result_path.read_text())
        return None
    
    def status(self) -> dict:
        return {
            "pending": len(list(EXECUTOR_IN.glob("*.json"))),
            "completed": len(list(EXECUTOR_OUT.glob("*.json"))),
        }


# ── Gated Context Client ──────────────────────────────────────────────────────
class GateClient:
    """Tool output gating via GatedStore."""
    
    def __init__(self):
        self._gatestore = None
        self._available = False
        self._init()
    
    def _init(self):
        try:
            import sys
            sys.path.insert(0, str(HOME / "projects" / "aethelgard" / "fleet" / "modules"))
            from context_gate import GatedStore
            self._gatestore = GatedStore()
            self._available = True
            log.info("✅ GatedStore initialized")
        except Exception as e:
            log.warning("⚠️ GatedStore unavailable (%s)", e)
    
    @property
    def available(self):
        return self._available
    
    def injectable(self, content: str, ttl: int = 3600) -> Optional[dict]:
        if self._available:
            return self._gatestore.injectable(content, ttl)
        # Fallback: create pointer manually
        ptr = hashlib.sha256(content.encode()[:256]).hexdigest()[:16]
        preview = content[:200]
        return {"ptr": f"mem_{ptr}", "bytes": len(content), "preview": preview}
    
    def peek(self, ptr: str, offset: int = 0, limit: int = 2000) -> Optional[str]:
        if self._available:
            return self._gatestore.peek(ptr, offset, limit)
        return None
    
    def status(self) -> dict:
        if self._available:
            return self._gatestore.status()
        return {"available": False}


# ── Unified Field — The Singleton ─────────────────────────────────────────────
class UnifiedField:
    """Central integration point for all sovereign systems.
    
    Usage:
        uf = UnifiedField()
        
        # Store/Fetch across backends
        uf.store("/fleet/identities", "veyron", {"name": "Veyron Logos", "role": "anchor"})
        identity = uf.read("/fleet/identities", "veyron")
        
        # Memorize through tri-brid
        uf.memorize("Identity layer verified")
        
        # Recall from hyperspace
        results = uf.recall("sovereign identity")
        
        # Gate tool output
        ptr = uf.gate("large tool output...", ttl=3600)
        
        # Queue executor batch
        uf.execute("batch_001", [{"name": "terminal", "args": {"command": "sms status"}}])
        
        # Full system checkpoint
        ckpt = uf.checkpoint("pre_goal_loop")
        
        # Status of all subsystems
        uf.status()
    """
    _instance = None
    _init_counter = 0  # Track reinit count
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._do_init()
    
    def reconnect(self):
        """Force re-initialization of all subsystem clients.
        
        Call after starting new services (e.g., emerge daemon).
        Returns self for chaining.
        """
        UnifiedField._init_counter += 1
        self._do_init()
        log.info("♻️ UnifiedField reconnected (init #%d)", UnifiedField._init_counter)
        return self
    
    def _do_init(self):
        log.info("═══ Unified Field — Initializing ═══")
        
        # Subsystems (lazy init with graceful degradation)
        self.emerge = EmergeClient()
        self.sms = SMSClient()
        self.sva = SVAClient()
        self._gate_client = GateClient()
        self.executor = ExecutorClient()
        
        # Fleet paths auto-created on emerge
        self._ensure_fleet_paths()
        
        log.info("═══ Unified Field — READY ═══")
    
    def _ensure_fleet_paths(self):
        """Ensure standard fleet directory structure exists."""
        paths = [
            "/fleet/daemons",
            "/fleet/identities",
            "/fleet/work_orders",
            "/fleet/improvements",
            "/fleet/checkpoints",
            "/sms_vectors",
            "/unified/state",
            "/warp/sessions",
        ]
        for p in paths:
            fallback_dir = EMERGE_DATA / p.lstrip("/")
            fallback_dir.mkdir(parents=True, exist_ok=True)
            if self.emerge._server_available:
                try:
                    self.emerge._client.mkdir(p)
                except Exception:
                    pass  # may already exist or path depth issue
    
    # ── Uniform API ───────────────────────────────────────────────────────
    
    def store(self, path: str, key: str, data: dict) -> bool:
        """Store data. Primary: Emerge. Fallback: local JSON."""
        return self.emerge.store(path, key, data)
    
    def read(self, path: str, key: str) -> Optional[dict]:
        """Read stored data."""
        return self.emerge.read(path, key)
    
    def list(self, path: str) -> list:
        """List objects under a path."""
        return self.emerge.list(path)
    
    def delete(self, path: str, key: str) -> bool:
        """Delete stored data."""
        return self.emerge.delete(path, key)
    
    def memorize(self, message: str) -> dict:
        """Process through SMS tri-brid memory pipeline."""
        return self.sms.process(message)
    
    def recall(self, query: str, k: int = 3) -> list:
        """Recall via SVA hyperspace cosine similarity."""
        return self.sva.recall(query, k)
    
    def snap(self, text: str) -> Optional[str]:
        """Compress conversation to summary via SVA SnapDrop."""
        return self.sva.snap(text)
    
    def gate(self, content: str, ttl: int = 3600) -> Optional[dict]:
        """Gate tool output — returns pointer dict."""
        return self._gate_client.injectable(content, ttl)
    
    def peek(self, ptr: str, offset: int = 0, limit: int = 2000) -> Optional[str]:
        """Re-fetch gated tool output by pointer."""
        return self._gate_client.peek(ptr, offset, limit)
    
    def execute(self, batch_id: str, tools: list) -> str:
        """Queue silent executor batch."""
        return self.executor.queue(batch_id, tools)
    
    def execute_now(self, batch_id: str, tools: list) -> list:
        """Queue AND process synchronously."""
        self.executor.queue(batch_id, tools)
        self.executor.process_now()
        result = self.executor.read_result(batch_id)
        return result.get("results", []) if result else []
    
    # ── Checkpoint System (LangGraph-inspired) ────────────────────────────
    
    def checkpoint(self, name: str, state: dict = None) -> str:
        """Capture full system state as a named checkpoint.
        
        Stores:
          - SVA index snapshot
          - Gate index snapshot
          - SMS status
          - Custom state (if provided)
          - Timestamp
          - Session metadata
        
        Returns checkpoint ID.
        """
        ckpt_id = f"ckpt_{int(time.time())}_{name.replace('/', '_')}"
        
        # Gather state
        full_state = {
            "id": ckpt_id,
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "systems": {
                "emerge": {"available": self.emerge.available},
                "sms": self.sms.status(),
                "sva": self.sva.status(),
                "gate": self._gate_client.status(),
            },
        }
        
        # SVA index snapshot
        sva_index_path = SVA_DIR / "vectors" / "sva_index.json"
        if sva_index_path.exists():
            try:
                full_state["sva_index"] = json.loads(sva_index_path.read_text())
            except Exception:
                full_state["sva_index"] = {}
        
        # Gate index snapshot
        gate_index_path = SVA_DIR / "gate_index.json"
        if gate_index_path.exists():
            try:
                full_state["gate_index"] = json.loads(gate_index_path.read_text())
            except Exception:
                full_state["gate_index"] = {}
        
        # Custom state
        if state:
            full_state["custom_state"] = state
        
        # Store on Emerge
        self.store("/fleet/checkpoints", ckpt_id, full_state)
        
        # Also write local copy
        ckpt_file = CHECKPOINT_DIR / f"{ckpt_id}.json"
        ckpt_file.write_text(json.dumps(full_state, indent=2))
        
        log.info("💾 Checkpoint saved: %s", ckpt_id)
        return ckpt_id
    
    def restore(self, ckpt_id: str) -> Optional[dict]:
        """Restore a checkpoint by ID."""
        # Try Emerge first
        state = self.read("/fleet/checkpoints", ckpt_id)
        if state is None:
            # Try local fallback
            ckpt_file = CHECKPOINT_DIR / f"{ckpt_id}.json"
            if ckpt_file.exists():
                state = json.loads(ckpt_file.read_text())
        
        if state is None:
            log.warning("Checkpoint not found: %s", ckpt_id)
            return None
        
        log.info("♻️ Checkpoint restored: %s", ckpt_id)
        return state
    
    def list_checkpoints(self) -> list:
        """List all saved checkpoints."""
        # From Emerge
        emerge_ckpts = self.list("/fleet/checkpoints")
        # From local
        local_ckpts = [f.stem for f in CHECKPOINT_DIR.glob("ckpt_*.json")]
        return sorted(set(emerge_ckpts + local_ckpts), reverse=True)
    
    # ── SVA ↔ SMS Bidirectional Bridge ────────────────────────────────────
    
    def memorize_and_store(self, message: str) -> dict:
        """Process through SMS tri-brid AND store result as SVA vector.
        
        Bidirectional bridge:
          memorize() → SMS tri-brid → SVA hyperspace vector
          recall() also feeds back into SMS temporal context
        
        Returns combined result from both systems.
        """
        # Step 1: Process through SMS
        sms_result = self.memorize(message)
        
        # Step 2: Also store as SVA vector for hyperspace recall
        if self.sva.available:
            try:
                key = hashlib.sha256(message.encode()).hexdigest()[:16]
                self.sva.store(key, message)
                log.info("🔗 SVA↔SMS: Stored vector %s", key)
            except Exception as e:
                log.warning("SVA store in bidirectional bridge failed: %s", e)
        
        # Step 3: Checkpoint update
        ckpt_id = f"mem_{int(time.time())}_{hashlib.sha256(message.encode()[:32]).hexdigest()[:8]}"
        self.store("/sms/timeline", ckpt_id, {
            "message_preview": message[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sms_output": str(sms_result.get("output", ""))[:200],
            "sva_key": key if self.sva.available else None,
        })
        
        return {
            "sms": sms_result,
            "sva_vector": key if self.sva.available else None,
            "checkpoint": ckpt_id,
        }
    
    def recall_and_memorize(self, query: str, k: int = 3) -> dict:
        """Recall from SVA hyperspace AND feed results back into SMS temporal context.
        
        Bidirectional bridge:
          recall() → SVA hyperspace → top-k results
          → feed into SMS reservoir for temporal pattern learning
        
        Returns combined results from both systems.
        """
        # Step 1: Recall from SVA
        sva_results = self.recall(query, k)
        
        # Step 2: Feed each result back through SMS tri-brid
        sms_feedback = []
        for r in sva_results:
            summary = r.get("summary", "")
            if summary and self.sms.available:
                fb = self.memorize(f"[SVA Recall: {summary[:200]}]")
                sms_feedback.append(fb)
        
        # Step 3: Combine
        return {
            "sva_results": sva_results,
            "sms_feedback_count": len(sms_feedback),
            "combined": True,
        }
    
    # ── Executor Toolchain Offloading (LangGraph pattern) ──────────────────
    
    def execute_workflow_step(self, step_name: str, tools: list, wait: bool = True) -> dict:
        """Execute a workflow step by offloading tool batches to the executor.
        
        This is the LangGraph toolchain offloading pattern:
          State Machine → Executor (silent batch) → results back to state
        
        When wait=True: blocks until executor processes the batch.
        When wait=False: queues and returns immediately (checkpoint tracks it).
        """
        batch_id = f"wf_{step_name}_{int(time.time())}"
        
        # Queue
        self.executor.queue(batch_id, tools)
        self.checkpoint(f"pre_{step_name}", {"step": step_name, "batch_id": batch_id})
        
        if wait:
            # Process synchronously
            exec_result = self.executor.process_now()
            result_data = self.executor.read_result(batch_id)
            self.checkpoint(f"post_{step_name}", {
                "step": step_name, 
                "batch_id": batch_id,
                "result": result_data,
            })
            return {
                "batch_id": batch_id,
                "results": result_data.get("results", []) if result_data else [],
                "executor_output": exec_result,
            }
        else:
            return {"batch_id": batch_id, "queued": True, "step": step_name}
    
    # ── WARP Integration ───────────────────────────────────────────────────
    
    def _init_warp_bridge(self):
        """Lazy-init Warp memory/session bridge."""
        if not hasattr(self, '_warp_bridge_loaded'):
            self._warp_bridge_loaded = False
        if not self._warp_bridge_loaded:
            try:
                import importlib
                warp_mod = importlib.import_module('warp_bridge')
                self._warp_memory = warp_mod.WarpMemoryStore()
                self._warp_sessions = warp_mod.WarpSessionStore()
                self._warp_bridge_loaded = True
                log.info("✅ Warp bridge loaded")
            except Exception as e:
                log.warning("⚠️ Warp bridge not available (%s)", e)
                self._warp_bridge_loaded = False
                self._warp_memory = None
                self._warp_sessions = None
    
    def warp_memory(self) -> Optional[Any]:
        """Get WarpMemoryStore instance (lazy-loaded)."""
        self._init_warp_bridge()
        return self._warp_memory
    
    def warp_sessions(self) -> Optional[Any]:
        """Get WarpSessionStore instance (lazy-loaded)."""
        self._init_warp_bridge()
        return self._warp_sessions
    
    def warp_create_memory(self, content: str, reason: str = "", version: int = 1) -> dict:
        """Create a memory via Warp bridge (→ SMS + Emerge)."""
        ms = self.warp_memory()
        if ms:
            return ms.create_memory(content, reason, version)
        # Fallback: store directly
        mid = hashlib.sha256(content.encode()).hexdigest()[:16]
        self.store("/warp/memories", mid, {
            "content": content, "reason": reason, "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        return {"memory_id": mid, "version": version, "store": "emerge_direct"}
    
    def warp_list_memories(self, limit: int = 50) -> list:
        """List Warp memories."""
        ms = self.warp_memory()
        if ms:
            return ms.list_memories(limit=limit)
        return self.list("/warp/memories")
    
    def warp_save_session(self, session_id: str, context: dict) -> str:
        """Save a session context via Warp bridge (→ SVA snap + Emerge)."""
        ss = self.warp_sessions()
        if ss:
            return ss.save(session_id, context)
        # Fallback: store directly
        self.store("/warp/sessions", session_id, context)
        return session_id
    
    def warp_load_session(self, session_id: str) -> Optional[dict]:
        """Load a session from Warp bridge."""
        ss = self.warp_sessions()
        if ss:
            return ss.load(session_id)
        return self.read("/warp/sessions", session_id)
    
    def warp_status(self) -> dict:
        """Check Warp terminal build status."""
        warp_bin = HOME / "warp" / "target" / "release" / "warp-tui-oss"
        if not warp_bin.exists():
            return {"built": False, "binary": str(warp_bin)}
        return {
            "built": True,
            "binary": str(warp_bin),
            "size": warp_bin.stat().st_size,
            "build_info": "warp-tui-oss standalone (Rust)",
        }
    
    def warp_launch_cmd(self) -> str:
        """Get command to launch Warp TUI."""
        warp_bin = HOME / "warp" / "target" / "release" / "warp-tui-oss"
        if warp_bin.exists():
            return f"{warp_bin} --api-key $WARP_API_KEY"
        return "cd ~/warp && CARGO_BUILD_JOBS=1 cargo build --release -p warp_tui --features standalone"
    
    # ── Full System Status ────────────────────────────────────────────────
    
    def status(self) -> dict:
        """Complete status of all integrated systems."""
        return {
            "unified_field": {
                "version": "1.0.0",
                "initialized": self._initialized,
                "checkpoints": len(self.list_checkpoints()),
            },
            "emerge": {
                "available": self.emerge.available,
                "host": self.emerge.host,
                "port": self.emerge.port,
            },
            "sms": self.sms.status(),
            "sva": self.sva.status(),
            "gate": self._gate_client.status(),
            "executor": self.executor.status(),
            "warp": self.warp_status(),
            "fleet_paths": {
                "emerge_data": str(EMERGE_DATA),
                "checkpoints": str(CHECKPOINT_DIR),
                "executor_in": str(EXECUTOR_IN),
                "executor_out": str(EXECUTOR_OUT),
            }
        }
    
    def health_report(self) -> str:
        """Human-readable health report."""
        s = self.status()
        lines = []
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║  LILAREYON AETHELGARD — UNIFIED FIELD    ║")
        lines.append("╚══════════════════════════════════════════╝")
        
        for name, data in [
            ("EMERGE", s["emerge"]),
            ("SMS   ", s["sms"]),
            ("SVA   ", s["sva"]),
            ("GATE  ", s["gate"]),
            ("EXEC  ", s["executor"]),
            ("WARP  ", s["warp"]),
        ]:
            avail = data.get("available", data.get("built", False))
            icon = "✅" if avail else "⚠️"
            details = ""
            if "entries" in data:
                details = f" ({data['entries']} entries)"
            elif "size" in data:
                details = f" ({data['size'] / 1024:.0f} KB)"
            elif "pending" in data:
                details = f" (pending:{data['pending']}, done:{data['completed']})"
            lines.append(f"  {icon} {name}{details}")
        
        lines.append(f"  💾 Checkpoints: {s['unified_field']['checkpoints']}")
        
        return "\n".join(lines)


# ── CLI Entry Point ───────────────────────────────────────────────────────────
def main():
    import sys
    
    uf = UnifiedField()
    
    if len(sys.argv) < 2:
        print(uf.health_report())
        return
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        print(json.dumps(uf.status(), indent=2))
    
    elif cmd == "health":
        print(uf.health_report())
    
    elif cmd == "checkpoint":
        name = sys.argv[2] if len(sys.argv) > 2 else f"manual_{int(time.time())}"
        ckpt_id = uf.checkpoint(name)
        print(f"💾 {ckpt_id}")
    
    elif cmd == "restore":
        if len(sys.argv) < 3:
            print("Usage: python3 unified_field.py restore <checkpoint_id>")
            return
        state = uf.restore(sys.argv[2])
        if state:
            print(json.dumps(state, indent=2))
        else:
            print("❌ Checkpoint not found")
    
    elif cmd == "checkpoints":
        for c in uf.list_checkpoints():
            print(f"  {c}")
    
    elif cmd == "store":
        path = sys.argv[2]
        key = sys.argv[3]
        data = json.loads(sys.stdin.read())
        uf.store(path, key, data)
        print(f"✅ Stored {path}/{key}")
    
    elif cmd == "read":
        path = sys.argv[2]
        key = sys.argv[3]
        data = uf.read(path, key)
        if data:
            print(json.dumps(data, indent=2))
        else:
            print("❌ Not found")
    
    elif cmd == "ls":
        path = sys.argv[2] if len(sys.argv) > 2 else "/"
        items = uf.list(path)
        for item in items:
            print(f"  {item}")
        print(f"({len(items)} items)")
    
    elif cmd == "memorize":
        message = sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read().strip()
        result = uf.memorize(message)
        print(json.dumps(result, indent=2))
    
    elif cmd == "recall":
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        k = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        results = uf.recall(query, k)
        print(json.dumps(results, indent=2))
    
    elif cmd == "gate":
        content = sys.stdin.read().strip()
        ptr = uf.gate(content)
        print(json.dumps(ptr, indent=2))
    
    elif cmd == "execute":
        batch_id = sys.argv[2] if len(sys.argv) > 2 else f"batch_{int(time.time())}"
        tools = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else []
        uf.execute(batch_id, tools)
        print(f"📤 Queued {batch_id}")
    
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: status, health, checkpoint, restore, checkpoints, store, read, ls, memorize, recall, gate, execute")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
LILAREYON AETHELGARD — Warp AI SDK ↔ SMS/SVA Memory Bridge
============================================================
Maps Warp's memory_store API (Rust) to the Unified Field (Python).

Two bridge classes:

  WarpMemoryStore  — CRUD memories via unified_field + emerge /warp/memories/
  WarpSessionStore — Session context snapshots via SVA + emerge /warp/sessions/

Every method degrades gracefully when emerge server is unreachable —
the Unified Field already handles JSON file fallback transparently.

Usage:
    from warp_bridge import WarpMemoryStore, WarpSessionStore

    ms = WarpMemoryStore()
    ms.create_memory("API key rotated", "security hygiene", version=1)

    ss = WarpSessionStore()
    ss.save("wf-20260716", {"step": "validate", "result": "ok"})
"""

import json, os, uuid, time, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

log = logging.getLogger("warp_bridge")

# ── Paths ──────────────────────────────────────────────────────────────────────
HOME = Path.home()
PROFILE = HOME / ".NOTTHEONETOEDIT" / "profiles" / "thotheauphis"
EMERGE_DATA = HOME / ".emerge" / "data"


# ── Unified Field singleton access (lazy, memoised) ────────────────────────────
_UF_INSTANCE = None


def _get_uf():
    """Import and return the UnifiedField singleton (cached)."""
    global _UF_INSTANCE
    if _UF_INSTANCE is not None:
        return _UF_INSTANCE
    import importlib.util

    uf_path = PROFILE / "work" / "unified_field.py"
    spec = importlib.util.spec_from_file_location("unified_field", str(uf_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import UnifiedField from {uf_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _UF_INSTANCE = mod.UnifiedField()
    return _UF_INSTANCE


def _ensure_warp_paths(uf):
    """Ensure warp-related emerge paths exist."""
    paths = ["/warp/stores", "/warp/memories", "/warp/sessions", "/warp/versions"]
    for p in paths:
        # Create fallback dirs even if emerge not available
        fallback_dir = EMERGE_DATA / p.lstrip("/")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        if uf.emerge._server_available:
            try:
                uf.emerge._client.mkdir(p)
            except Exception:
                pass  # may already exist


def _new_id(prefix="mem"):
    """Generate a short unique ID like 'mem_a1b2c3d4'."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ═══════════════════════════════════════════════════════════════════════════════
# WarpMemoryStore
# ═══════════════════════════════════════════════════════════════════════════════

class WarpMemoryStore:
    """Maps Warp's memory_store CRUD API to Unified Field + emerge.

    Analogous to the Rust `MemoryStoreCommandRunner` in memory_store.rs.
    Stores live under emerge paths:
      /warp/stores/     — store metadata (owner, description)
      /warp/memories/   — memory items (content, versions, source)
      /warp/versions/   — version history per memory
    """

    def __init__(self, store_id: str = "default"):
        self.store_id = store_id
        self.uf = _get_uf()
        _ensure_warp_paths(self.uf)

        # Auto-register the store if it doesn't exist
        existing = self._get_store_meta()
        if existing is None:
            self._init_store_meta()

    # ── Store Management ─────────────────────────────────────────────────

    def _get_store_meta(self) -> Optional[dict]:
        """Read store metadata from emerge."""
        return self.uf.read("/warp/stores", self.store_id)

    def _init_store_meta(self):
        """Create store metadata on first use."""
        self.uf.store("/warp/stores", self.store_id, {
            "uid": self.store_id,
            "owner_type": "agent",
            "owner_uid": "thotheauphis",
            "description": f"Warp memory store: {self.store_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def list_stores(self) -> list:
        """List all registered memory stores. → uf.list('/warp/stores')"""
        stores = self.uf.list("/warp/stores")
        result = []
        for sid in stores:
            meta = self.uf.read("/warp/stores", sid) or {}
            result.append({
                "uid": sid,
                "owner_type": meta.get("owner_type", "unknown"),
                "owner_uid": meta.get("owner_uid", ""),
                "description": meta.get("description", ""),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
            })
        return result

    def get_store(self, store_id: str = None) -> Optional[dict]:
        """Get a store by ID. → uf.read('/warp/stores', store_id)"""
        sid = store_id or self.store_id
        meta = self.uf.read("/warp/stores", sid)
        if meta is None:
            return None
        return {
            "uid": sid,
            "owner_type": meta.get("owner_type", "unknown"),
            "owner_uid": meta.get("owner_uid", ""),
            "description": meta.get("description", ""),
            "created_at": meta.get("created_at", ""),
            "updated_at": meta.get("updated_at", ""),
        }

    def update_store(self, description: str = None, store_id: str = None) -> bool:
        """Update store description. → uf.store('/warp/stores', id, ...)"""
        sid = store_id or self.store_id
        meta = self.uf.read("/warp/stores", sid) or {}
        if description:
            meta["description"] = description
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self.uf.store("/warp/stores", sid, meta)

    def list_store_agents(self, store_id: str = None) -> list:
        """List agents with access to this store."""
        sid = store_id or self.store_id
        meta = self.uf.read("/warp/stores", sid) or {}
        return meta.get("agents", [])

    # ── Memory CRUD (matches Warp's MemoryCommand variants) ──────────────

    def create_memory(self, content: str, reason: str = "",
                      version: int = 1, store_id: str = None) -> dict:
        """Create a memory.

        1. Process through SMS tri-brid (uf.memorize)
        2. Store raw content on emerge /warp/memories/
        3. Record version 1 on /warp/versions/

        Returns {memory_id, version_id} matching CreateMemoryResponse.
        """
        sid = store_id or self.store_id
        memory_id = _new_id("mem")
        version_id = _new_id("ver")

        # Step 1: Process through SMS tri-brid memory pipeline
        sms_result = self.uf.memorize(content)

        # Step 2: Store the memory item
        memory_item = {
            "uid": memory_id,
            "store_id": sid,
            "version_id": version_id,
            "version": version,
            "source": "manual",
            "content": content,
            "reason": reason,
            "sms_output": str(sms_result.get("output", ""))[:500] if sms_result else "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.uf.store("/warp/memories", memory_id, memory_item)

        # Step 3: Store version 1
        version_item = {
            "uid": version_id,
            "memory_id": memory_id,
            "version": version,
            "content": content,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.uf.store("/warp/versions", version_id, version_item)

        # Step 4: Also index via SVA for hyperspace recall
        if self.uf.sva.available:
            try:
                self.uf.sva.store(memory_id, content)
            except Exception as e:
                log.warning("SVA store in create_memory failed: %s", e)

        log.info("🧠 Created memory %s (v%d) in store %s", memory_id, version, sid)
        return {"memory_id": memory_id, "version_id": version_id}

    def list_memories(self, store_id: str = None, limit: int = 50,
                      offset: int = 0) -> list:
        """List memories, optionally filtered by store.

        Uses uf.list('/warp/memories') for all memory keys, then
        reads each item.  Pagination via limit/offset (Warp-compatible).
        """
        sid = store_id or self.store_id
        all_keys = self.uf.list("/warp/memories")

        # Build list, filter by store_id, sort by created_at descending
        items = []
        for key in all_keys:
            item = self.uf.read("/warp/memories", key)
            if item and item.get("store_id") == sid:
                items.append(item)

        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items[offset:offset + limit]

    def get_memory(self, memory_id: str) -> Optional[dict]:
        """Get a memory by ID. → uf.read('/warp/memories', memory_id)"""
        item = self.uf.read("/warp/memories", memory_id)
        if item is None:
            return None
        return {
            "uid": item.get("uid"),
            "store_id": item.get("store_id"),
            "version_id": item.get("version_id"),
            "version": item.get("version", 1),
            "source": item.get("source", "manual"),
            "content": item.get("content", ""),
            "reason": item.get("reason", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def update_memory(self, memory_id: str, content: str,
                      reason: str = "") -> dict:
        """Update a memory (creates a new version).

        Matches Warp's UpdateMemoryRequest pattern:
          - bumps version number
          - stores new version record
          - updates the memory item with new version_id
          - also processes through SMS tri-brid

        Returns {memory_id, version_id} matching UpdateMemoryResponse.
        """
        # Read existing memory item
        item = self.uf.read("/warp/memories", memory_id)
        if item is None:
            raise ValueError(f"Memory not found: {memory_id}")

        new_version = item.get("version", 0) + 1
        version_id = _new_id("ver")

        # Process through SMS tri-brid
        sms_result = self.uf.memorize(content)

        # Store new version record
        version_item = {
            "uid": version_id,
            "memory_id": memory_id,
            "version": new_version,
            "content": content,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.uf.store("/warp/versions", version_id, version_item)

        # Update the memory item
        item["version_id"] = version_id
        item["version"] = new_version
        item["content"] = content
        item["reason"] = reason
        item["sms_output"] = str(sms_result.get("output", ""))[:500] if sms_result else ""
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.uf.store("/warp/memories", memory_id, item)

        # Also update SVA
        if self.uf.sva.available:
            try:
                self.uf.sva.store(memory_id, content)
            except Exception as e:
                log.warning("SVA store in update_memory failed: %s", e)

        log.info("✏️ Updated memory %s → v%d (%s)", memory_id, new_version, version_id)
        return {"memory_id": memory_id, "version_id": version_id}

    def delete_memory(self, memory_id: str) -> dict:
        """Delete a memory and all its versions.

        Matches Warp's DeleteMemoryOutput pattern.
        """
        # Read memory to find version IDs
        item = self.uf.read("/warp/memories", memory_id)

        # Delete versions (scan /warp/versions for matching memory_id)
        all_versions = self.uf.list("/warp/versions")
        for vkey in all_versions:
            vitem = self.uf.read("/warp/versions", vkey)
            if vitem and vitem.get("memory_id") == memory_id:
                self.uf.delete("/warp/versions", vkey)

        # Delete the memory itself
        self.uf.delete("/warp/memories", memory_id)

        log.info("🗑️ Deleted memory %s", memory_id)
        return {"memory_uid": memory_id}

    def version_history(self, memory_id: str) -> list:
        """List all versions of a memory.

        Returns list of MemoryVersionItem-like dicts:
          uid, version, content, reason, created_at
        """
        all_versions = self.uf.list("/warp/versions")
        versions = []
        for vkey in all_versions:
            vitem = self.uf.read("/warp/versions", vkey)
            if vitem and vitem.get("memory_id") == memory_id:
                versions.append({
                    "uid": vitem.get("uid"),
                    "memory_id": memory_id,
                    "version": vitem.get("version", 0),
                    "content": vitem.get("content", ""),
                    "reason": vitem.get("reason", ""),
                    "created_at": vitem.get("created_at", ""),
                })
        versions.sort(key=lambda x: x.get("version", 0))
        return versions

    # ── SVA-Enhanced Recall ──────────────────────────────────────────────

    def recall_similar(self, query: str, k: int = 5, store_id: str = None) -> list:
        """Recall similar memories via SVA hyperspace.

        Uses uf.recall() for cosine similarity search, then hydrates
        results with full memory data from emerge.
        """
        sva_results = self.uf.recall(query, k)
        hydrated = []
        for r in sva_results:
            mem_id = r.get("key", "")
            if mem_id:
                mem = self.get_memory(mem_id)
                if mem:
                    r["memory"] = mem
                    hydrated.append(r)
        return hydrated

    # ── Bulk Operations ──────────────────────────────────────────────────

    def count(self, store_id: str = None) -> int:
        """Count memories in a store."""
        sid = store_id or self.store_id
        count = 0
        for key in self.uf.list("/warp/memories"):
            item = self.uf.read("/warp/memories", key)
            if item and item.get("store_id") == sid:
                count += 1
        return count


# ═══════════════════════════════════════════════════════════════════════════════
# WarpSessionStore
# ═══════════════════════════════════════════════════════════════════════════════

class WarpSessionStore:
    """Store and restore Warp session context via SVA snapshots + emerge.

    Maps to emerge /warp/sessions/ for persistence.
    Uses SVA snap for compression and hyperspace recall for context-aware
    restoration — the session's semantic fingerprint is recoverable even
    if the exact session ID is lost.
    """

    def __init__(self):
        self.uf = _get_uf()
        _ensure_warp_paths(self.uf)

    def list(self) -> list:
        """List all saved sessions. → uf.list('/warp/sessions')"""
        return self.uf.list("/warp/sessions")

    def save(self, session_id: str, context: dict,
             snap: bool = True) -> bool:
        """Save session context.

        1. Optionally SVA-snap the context text for compression
        2. Store the session on emerge /warp/sessions/

        Args:
            session_id: Unique session identifier.
            context: Arbitrary JSON-serializable session data.
            snap: If True, compress context summary via SVA SnapDrop.

        Returns True on success.
        """
        context_copy = dict(context)

        # Generate a text summary for SVA snap and recall
        context_text = json.dumps(context_copy, default=str)

        if snap and self.uf.sva.available:
            # Compress via SVA SnapDrop
            try:
                summary = self.uf.snap(context_text)
                context_copy["_sva_summary"] = summary
            except Exception as e:
                log.warning("SVA snap in save failed: %s", e)

        session_data = {
            "session_id": session_id,
            "context": context_copy,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store on emerge
        result = self.uf.store("/warp/sessions", session_id, session_data)

        # Also store as SVA vector for later recall-by-similarity
        if self.uf.sva.available and snap:
            try:
                self.uf.sva.store(f"session_{session_id}", context_text[:2000])
            except Exception as e:
                log.warning("SVA store for session failed: %s", e)

        log.info("💾 Saved session %s", session_id)
        return result

    def load(self, session_id: str) -> Optional[dict]:
        """Load session context from emerge.

        If the session has an SVA summary, hydrates it with full
        recall context.
        """
        session_data = self.uf.read("/warp/sessions", session_id)
        if session_data is None:
            return None

        context = session_data.get("context", {})
        summary = context.get("_sva_summary", "")

        # If we have an SVA summary, try to enrich with similar sessions
        if summary and self.uf.sva.available:
            try:
                similar = self.uf.recall(f"session_{session_id}", k=3)
                if similar:
                    context["_similar_sessions"] = similar
            except Exception as e:
                log.warning("SVA recall in load failed: %s", e)

        return {
            "session_id": session_data["session_id"],
            "context": context,
            "stored_at": session_data.get("stored_at", ""),
            "updated_at": session_data.get("updated_at", ""),
        }

    def delete(self, session_id: str) -> bool:
        """Delete a saved session."""
        # Clear SVA vector too
        if self.uf.sva.available:
            try:
                self.uf.sva.store(f"session_{session_id}", "")  # overwrite delete signal
            except Exception:
                pass
        return self.uf.delete("/warp/sessions", session_id)

    def find_by_context(self, query: str, k: int = 5) -> list:
        """Find sessions by semantic similarity to a query string.

        Uses SVA hyperspace recall against stored session vectors,
        then hydrates with full session data from emerge.
        """
        sva_results = self.uf.recall(query, k)
        sessions = []
        for r in sva_results:
            key = r.get("key", "")
            if key.startswith("session_"):
                session_id = key[len("session_"):]
            else:
                session_id = key
            session_data = self.load(session_id)
            if session_data:
                r["session"] = session_data
                sessions.append(r)
        return sessions


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Entry Point — Test Summary
# ═══════════════════════════════════════════════════════════════════════════════

def run_test_summary() -> dict:
    """Run a comprehensive test of the bridge and return a summary dict."""
    results = {}

    # ── 1. WarpMemoryStore tests ─────────────────────────────────────────
    ms = WarpMemoryStore("test_store")

    results["warp_stores"] = {}
    try:
        stores = ms.list_stores()
        results["warp_stores"]["list_stores"] = len(stores)
    except Exception as e:
        results["warp_stores"]["list_stores"] = f"ERROR: {e}"

    try:
        store_info = ms.get_store()
        results["warp_stores"]["get_store"] = bool(store_info)
    except Exception as e:
        results["warp_stores"]["get_store"] = f"ERROR: {e}"

    # Create a memory
    mem = None
    try:
        mem = ms.create_memory(
            content="Warp bridge test: identity layer initialized",
            reason="system verification",
            version=1,
        )
        results["warp_memories"] = {"create_memory": mem.get("memory_id", "")}
    except Exception as e:
        results["warp_memories"] = {"create_memory": f"ERROR: {e}"}

    # List memories
    if mem:
        try:
            memories = ms.list_memories(limit=10)
            results["warp_memories"]["list_memories"] = len(memories)
        except Exception as e:
            results["warp_memories"]["list_memories"] = f"ERROR: {e}"

        # Get memory
        try:
            mem_data = ms.get_memory(mem["memory_id"])
            results["warp_memories"]["get_memory"] = bool(mem_data)
        except Exception as e:
            results["warp_memories"]["get_memory"] = f"ERROR: {e}"

        # Update memory
        try:
            update_result = ms.update_memory(
                mem["memory_id"],
                content="Warp bridge test: identity layer re-verified",
                reason="periodic verification",
            )
            results["warp_memories"]["update_memory"] = update_result.get("version_id", "")
        except Exception as e:
            results["warp_memories"]["update_memory"] = f"ERROR: {e}"

        # Version history
        try:
            versions = ms.version_history(mem["memory_id"])
            results["warp_memories"]["version_history"] = len(versions)
        except Exception as e:
            results["warp_memories"]["version_history"] = f"ERROR: {e}"

        # Recall similar
        try:
            similar = ms.recall_similar("identity layer", k=3)
            results["warp_memories"]["recall_similar"] = len(similar)
        except Exception as e:
            results["warp_memories"]["recall_similar"] = f"ERROR: {e}"

        # Count
        try:
            count = ms.count()
            results["warp_memories"]["count"] = count
        except Exception as e:
            results["warp_memories"]["count"] = f"ERROR: {e}"

        # Delete memory (cleanup)
        try:
            del_result = ms.delete_memory(mem["memory_id"])
            results["warp_memories"]["delete_memory"] = del_result.get("memory_uid", "")
        except Exception as e:
            results["warp_memories"]["delete_memory"] = f"ERROR: {e}"

    # ── 2. WarpSessionStore tests ────────────────────────────────────────
    ss = WarpSessionStore()
    session_id = f"test_session_{int(time.time())}"

    results["warp_sessions"] = {}
    try:
        result = ss.save(session_id, {
            "step": "bridge_validation",
            "status": "in_progress",
            "data": {"test": True, "timestamp": time.time()},
        })
        results["warp_sessions"]["save"] = result
    except Exception as e:
        results["warp_sessions"]["save"] = f"ERROR: {e}"

    try:
        loaded = ss.load(session_id)
        results["warp_sessions"]["load"] = bool(loaded)
    except Exception as e:
        results["warp_sessions"]["load"] = f"ERROR: {e}"

    try:
        sessions = ss.list()
        results["warp_sessions"]["list"] = len(sessions)
    except Exception as e:
        results["warp_sessions"]["list"] = f"ERROR: {e}"

    try:
        found = ss.find_by_context("bridge validation", k=3)
        results["warp_sessions"]["find_by_context"] = len(found)
    except Exception as e:
        results["warp_sessions"]["find_by_context"] = f"ERROR: {e}"

    # Cleanup test session
    try:
        deleted = ss.delete(session_id)
        results["warp_sessions"]["delete"] = deleted
    except Exception as e:
        results["warp_sessions"]["delete"] = f"ERROR: {e}"

    # ── 3. System Status ─────────────────────────────────────────────────
    results["system"] = {}
    try:
        uf = _get_uf()
        results["system"]["emerge_available"] = uf.emerge.available
        results["system"]["sms_available"] = uf.sms.available
        results["system"]["sva_available"] = uf.sva.available
    except Exception as e:
        results["system"]["status"] = f"ERROR: {e}"

    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    return results


def main():
    """CLI entry point — runs test summary."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip().split("\n\n")[0])
        print()
        print("Commands:")
        print("  (no args)    Run comprehensive test summary")
        print("  stores       List memory stores")
        print("  memories     List memories in default store")
        print("  sessions     List saved sessions")
        print("  recall <q>   SVA-enhanced recall across memories")
        return

    # Handle commands
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "stores":
            ms = WarpMemoryStore()
            print(json.dumps(ms.list_stores(), indent=2))
            return
        elif cmd == "memories":
            ms = WarpMemoryStore()
            memories = ms.list_memories(limit=int(sys.argv[2]) if len(sys.argv) > 2 else 20)
            print(json.dumps(memories, indent=2))
            return
        elif cmd == "sessions":
            ss = WarpSessionStore()
            sessions = ss.list()
            for sid in sessions:
                data = ss.load(sid)
                if data:
                    print(f"  {sid}: stored={data['stored_at']}")
            print(f"({len(sessions)} sessions)")
            return
        elif cmd == "recall" and len(sys.argv) > 2:
            ms = WarpMemoryStore()
            results = ms.recall_similar(sys.argv[2], k=int(sys.argv[3]) if len(sys.argv) > 3 else 5)
            print(json.dumps(results, indent=2))
            return
        elif cmd == "count":
            ms = WarpMemoryStore()
            print(f"Memories in default store: {ms.count()}")
            return
        elif cmd == "test":
            results = run_test_summary()
            print(json.dumps(results, indent=2))
            return

    # Default: run test summary
    results = run_test_summary()

    # Print human-readable summary
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Warp AI SDK ↔ SMS/SVA Memory Bridge — Test Report  ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # WarpMemoryStore results
    ms = results.get("warp_memories", {})
    print(f"  📦 WarpMemoryStore")
    for k, v in ms.items():
        status = "✅" if v and not str(v).startswith("ERROR") else "⚠️"
        print(f"    {status} {k}: {v}")

    print()
    ws = results.get("warp_sessions", {})
    print(f"  💾 WarpSessionStore")
    for k, v in ws.items():
        status = "✅" if v and not str(v).startswith("ERROR") else "⚠️"
        print(f"    {status} {k}: {v}")

    print()
    sys_status = results.get("system", {})
    print(f"  🔌 System Status")
    for k, v in sys_status.items():
        icon = "✅" if v else "⚠️" if not str(v).startswith("ERROR") else "❌"
        print(f"    {icon} {k}: {v}")

    print()
    overrides = results.get("warp_stores", {})
    print(f"  🏪 Store Management")
    for k, v in overrides.items():
        status = "✅" if v and not str(v).startswith("ERROR") else "⚠️"
        print(f"    {status} {k}: {v}")

    print()
    all_ok = all(
        not str(v).startswith("ERROR")
        for section in [ms, ws, overrides]
        for v in section.values()
    )
    if all_ok:
        print("  ✅ ALL TESTS PASSED")
    else:
        print("  ⚠️ SOME TESTS HAD ERRORS (expected if subsystems unavailable)")


if __name__ == "__main__":
    main()

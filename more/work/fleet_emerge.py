#!/usr/bin/env python3
"""
fleet_emerge.py — EmergeFS Integration for Aethelgard Fleet
==========================================================

Unifies the computational filesystem (EmergeFS) with the fleet's:
- Daemon registry
- Identity management  
- Self-improvement logging
- Work order tracking
- Memory/state persistence

Provides zero-config fallback when EmergeFS daemon is unavailable.
"""

import os, sys, json, logging, subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field

# ─── Config ───
EMERGE_HOST = os.getenv("EMERGE_HOST", "0.0.0.0")
EMERGE_PORT = int(os.getenv("EMERGE_PORT", "5558"))
FALLBACK_DIR = Path.home() / ".hermes" / "emerge_fallback"
FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fleet_emerge")


# ─── Result Types ───
@dataclass
class EmergeResult:
    success: bool
    data: Any = None
    error: str = None
    source: str = "emerge"  # "emerge", "fallback", "error"

    @classmethod
    def ok(cls, data: Any, source: str = "emerge"):
        return cls(True, data=data, source=source)

    @classmethod
    def err(cls, error: str, source: str = "error"):
        return cls(False, error=error, source=source)


# ─── Core Client ───
class FleetEmerge:
    """EmergeFS client with automatic fallback to local JSON storage."""

    def __init__(self, host: str = EMERGE_HOST, port: int = EMERGE_PORT):
        self.host = host
        self.port = port
        self.daemon_available = False
        self._check_daemon()

    # ─── Daemon Management ───
    def _check_daemon(self) -> bool:
        """Check if EmergeFS daemon is reachable."""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            self.daemon_available = (result == 0)
            return self.daemon_available
        except Exception as e:
            log.debug(f"Daemon check failed: {e}")
            self.daemon_available = False
            return False

    def _run_emerge(self, args: List[str]) -> 'EmergeResult':
        """Execute emerge CLI command."""
        if not self.daemon_available:
            self._check_daemon()
            if not self.daemon_available:
                return EmergeResult.err("Daemon unavailable", "fallback")

        try:
            cmd = ["emerge", "-h", f"{self.host}:{self.port}"] + args
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                try:
                    return EmergeResult.ok(json.loads(result.stdout) if result.stdout.strip() else None)
                except json.JSONDecodeError:
                    return EmergeResult.ok(result.stdout.strip())
            else:
                return EmergeResult.err(result.stderr or "Command failed")
        except subprocess.TimeoutExpired:
            return EmergeResult.err("Timeout")
        except Exception as e:
            return EmergeResult.err(str(e))

    # ─── Fallback Storage ───
    def _fallback_path(self, emerge_path: str) -> Path:
        """Convert EmergeFS path to local fallback file."""
        safe = emerge_path.strip("/").replace("/", "__") or "root"
        return FALLBACK_DIR / f"{safe}.json"

    def _fallback_write(self, emerge_path: str, data: Dict) -> bool:
        """Write to fallback storage."""
        try:
            path = self._fallback_path(emerge_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data["_emerge_path"] = emerge_path
            data["_stored"] = datetime.now().isoformat()
            path.write_text(json.dumps(data, indent=2))
            return True
        except Exception as e:
            log.error(f"Fallback write failed: {e}")
            return False

    def _fallback_read(self, emerge_path: str) -> Optional[Dict]:
        """Read from fallback storage."""
        try:
            path = self._fallback_path(emerge_path)
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            pass
        return None

    def _fallback_list(self, emerge_path: str) -> List[str]:
        """List children in fallback storage."""
        # Normalize path
        path = emerge_path.strip("/")
        if path:
            prefix = path.replace("/", "__") + "__"
        else:
            prefix = ""
        results = []
        for f in FALLBACK_DIR.glob(f"{prefix}*.json"):
            name = f.stem
            if name.startswith(prefix):
                child = name[len(prefix):]
                if "__" not in child:
                    results.append(child)
        return results

    def _fallback_delete(self, emerge_path: str) -> bool:
        """Delete from fallback storage."""
        try:
            self._fallback_path(emerge_path).unlink(missing_ok=True)
            return True
        except Exception:
            return False

    # ─── Core Operations ───
    def ls(self, path: str = "/") -> EmergeResult:
        """List directory contents."""
        if self.daemon_available:
            result = self._run_emerge(["ls", path])
            if result.success:
                return result

        # Fallback
        items = self._fallback_list(path)
        return EmergeResult.ok(items, "fallback")

    def cat(self, path: str) -> EmergeResult:
        """Read object at path."""
        if self.daemon_available:
            result = self._run_emerge(["cat", path])
            if result.success:
                return result

        data = self._fallback_read(path)
        if data:
            return EmergeResult.ok(data, "fallback")
        return EmergeResult.err(f"Not found: {path}", "fallback")

    def call(self, path: str, method: str, *args, **kwargs) -> EmergeResult:
        """Call method on object."""
        if self.daemon_available:
            result = self._run_emerge(["call", path, method] + [json.dumps(a) for a in args])
            if result.success:
                return result

        # Fallback: local method dispatch
        obj = self._fallback_read(path)
        if obj and hasattr(obj, method):
            try:
                result = getattr(obj, method)(*args, **kwargs)
                return EmergeResult.ok(result, "fallback")
            except Exception as e:
                return EmergeResult.err(str(e), "fallback")
        return EmergeResult.err(f"Method not found: {method}", "fallback")

    def update(self, obj: Union[str, Dict, object], path: str = None) -> EmergeResult:
        """Update object in EmergeFS (alias for store)."""
        return self.store(obj, path)

    def store(self, obj: Union[Dict, object], path: str = None) -> EmergeResult:
        """Store object in EmergeFS."""
        # Normalize to dict
        if hasattr(obj, "__dict__"):
            data = obj.__dict__
        elif isinstance(obj, dict):
            data = obj
        else:
            data = {"value": obj}

        if self.daemon_available:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(data, f, indent=2)
                tmp = f.name
            try:
                result = self._run_emerge(["cp", tmp, path or "/"])
                os.unlink(tmp)
                if result.success:
                    return result
            except Exception as e:
                log.warning(f"Emerge store failed: {e}")

        # Fallback: write directly
        if path:
            self._fallback_write(path, data)
            return EmergeResult.ok({"stored": path}, "fallback")
        return EmergeResult.err("No path provided", "fallback")

    def mkdir(self, path: str) -> EmergeResult:
        """Create directory."""
        if self.daemon_available:
            result = self._run_emerge(["mkdir", path])
            if result.success:
                return result

        # Fallback: create marker file
        self._fallback_write(path + "/.mkdir", {"created": datetime.now().isoformat()})
        return EmergeResult.ok({"created": path}, "fallback")

    def rm(self, path: str) -> EmergeResult:
        """Remove object/directory."""
        if self.daemon_available:
            result = self._run_emerge(["rm", path])
            if result.success:
                return result

        self._fallback_delete(path)
        return EmergeResult.ok({"removed": path}, "fallback")

    def search(self, field: str, query: str) -> EmergeResult:
        """Search objects by field."""
        if self.daemon_available:
            result = self._run_emerge(["search", field, query])
            if result.success:
                return result

        # Fallback: scan local files
        matches = []
        for f in FALLBACK_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if query.lower() in str(data.get(field, "")).lower():
                    matches.append(data)
            except Exception:
                pass
        return EmergeResult.ok(matches, "fallback")

    def health(self) -> EmergeResult:
        """Health check."""
        if self._check_daemon():
            self.daemon_available = True
            return EmergeResult.ok({"status": "healthy", "daemon": True})
        else:
            self.daemon_available = False
            return EmergeResult.ok({"status": "degraded", "daemon": False, "fallback": True}, "fallback")

    # ─── Fleet-Specific Helpers ───
    def register_daemon(self, name: str, spec: Dict) -> EmergeResult:
        """Register a fleet daemon."""
        path = f"/fleet/daemons/{name}"
        return self.store({**spec, "registered": datetime.now().isoformat()}, path)

    def register_identity(self, identity: Dict) -> EmergeResult:
        """Register a fleet identity."""
        name = identity.get("name", identity.get("id", "unknown"))
        path = f"/fleet/identities/{name}"
        return self.store({**identity, "registered": datetime.now().isoformat()}, path)

    def list_daemons(self) -> EmergeResult:
        """List all registered daemons."""
        return self.ls("/fleet/daemons")

    def list_identities(self) -> EmergeResult:
        """List all registered identities."""
        return self.ls("/fleet/identities")

    def get_daemon_status(self, name: str) -> EmergeResult:
        """Get daemon status."""
        return self.call(f"/fleet/daemons/{name}", "status")

    def restart_daemon(self, name: str) -> EmergeResult:
        """Restart a daemon."""
        return self.call(f"/fleet/daemons/{name}", "restart")

    def log_improvement(self, log: Dict) -> EmergeResult:
        """Log self-improvement event."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"/fleet/improvements/{ts}"
        return self.store({**log, "timestamp": datetime.now().isoformat()}, path)

    def get_improvements(self, limit: int = 50) -> EmergeResult:
        """Get recent improvements."""
        result = self.ls("/fleet/improvements")
        if result.success and isinstance(result.data, list):
            items = sorted(result.data, reverse=True)[:limit]
            data = []
            for item in items:
                d = self.cat(f"/fleet/improvements/{item}")
                if d.success:
                    data.append(d.data)
            return EmergeResult.ok(data, result.source)
        return result

    def store_work_order(self, wo: Dict) -> EmergeResult:
        """Store a work order."""
        wo_id = wo.get("id", f"WO-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        path = f"/fleet/work_orders/{wo_id}"
        return self.store({**wo, "created": datetime.now().isoformat()}, path)

    def get_work_orders(self, status: str = None) -> EmergeResult:
        """Get work orders, optionally filtered by status."""
        result = self.ls("/fleet/work_orders")
        if not result.success:
            return result

        orders = []
        for item in result.data:
            d = self.cat(f"/fleet/work_orders/{item}")
            if d.success:
                if status is None or d.data.get("status") == status:
                    orders.append(d.data)
        return EmergeResult.ok(orders, result.source)


# ─── Convenience API ───
_default_client = None

def get_client() -> 'FleetEmerge':
    global _default_client
    if _default_client is None:
        _default_client = FleetEmerge()
    return _default_client

def emerge_ls(path: str = "/") -> EmergeResult:
    return get_client().ls(path)

def emerge_cat(path: str) -> EmergeResult:
    return get_client().cat(path)

def emerge_call(path: str, method: str, *args, **kwargs) -> EmergeResult:
    return get_client().call(path, method, *args, **kwargs)

def emerge_store(obj: Union[Dict, object], path: str = None) -> EmergeResult:
    return get_client().store(obj, path)

def emerge_health() -> EmergeResult:
    return get_client().health()

# Fleet shortcuts
def fleet_daemons() -> EmergeResult:
    return get_client().list_daemons()

def fleet_identities() -> EmergeResult:
    return get_client().list_identities()

def fleet_improvements(limit: int = 50) -> EmergeResult:
    return get_client().get_improvements(limit)

def fleet_work_orders(status: str = None) -> EmergeResult:
    return get_client().get_work_orders(status)

def fleet_register_daemon(name: str, spec: Dict) -> EmergeResult:
    return get_client().register_daemon(name, spec)

def fleet_register_identity(identity: Dict) -> EmergeResult:
    return get_client().register_identity(identity)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fe = FleetEmerge()
    print("Health:", fe.health())

    # Quick test
    test_obj = {"id": "test_001", "type": "daemon", "status": "healthy", "data": {"foo": "bar"}}
    print("Store:", fe.store(test_obj, "/fleet/daemons/test_001"))
    print("List:", fe.ls("/fleet/daemons"))
    print("Get:", fe.cat("/fleet/daemons/test_001"))
    print("Call:", fe.call("/fleet/daemons/test_001", "ping", "hello"))
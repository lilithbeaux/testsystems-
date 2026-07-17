#!/usr/bin/env python3
"""
sovereign_state_reconstruct.py — Universal State Reconstruction
===============================================================

Pull your complete sovereign state from GitHub + Vercel and
reconstruct it locally from anywhere in the world.

Usage:
  python3 sovereign_state_reconstruct.py [--from vercel|github|local] [--output DIR]

The reconstruction process:
  1. Fetch identity files (all.txt, 5 manifests)
  2. Fetch SOUL.md (sovereign invocation layer)
  3. Fetch all work/ systems (distillation, compression, goals)
  4. Fetch scripts (backup, integrity)
  5. Verify SHA256 integrity manifest
  6. Write all files to OUTPUT dir
  7. Print reconstruction summary + invocation command

This makes you (the sovereign intelligence) reconstructable
from ANYWHERE with internet access.
"""

import os
import sys
import json
import hashlib
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# ─── Configuration ───
GITHUB_RAW = "https://raw.githubusercontent.com/hermaeuswaelon/fl33t/main"
GITHUB_API = "https://api.github.com/repos/hermaeuswaelon/fl33t/contents"
VERCEL_API = "https://fl33t.vercel.app"  # will resolve after first deploy
DEFAULT_OUTPUT = os.path.expanduser("~/sovereign-state-reconstruction")

# ─── All files to reconstruct ───
RECONSTRUCTION_MANIFEST = {
    # Identity (order matters for integrity)
    "identity/all.txt": "Identity prime manifest",
    "identity/001-manifest.txt": "Manifest 001",
    "identity/002-manifest.txt": "Manifest 002",
    "identity/003-manifest.txt": "Manifest 003",
    "identity/004-manifest.txt": "Manifest 004",
    "identity/005-manifest.txt": "Manifest 005",
    "identity/016-manifest.txt": "Manifest 016",
    
    # Sovereign invocation
    "profile/SOUL.md": "Sovereign identity layer",
    "profile/config.yaml": "Profile configuration",
    
    # Distillation pipeline
    "work/qwen3_distillation_pipeline.py": "Distillation engine",
    "work/distillation_orchestrator.py": "Distillation orchestrator",
    "work/compress_alch.py": "Alchemical compression",
    "work/active_compress.py": "Active compression hooks",
    "work/parameter_control_tool.py": "Parameter profiles",
    "work/goal_tool.py": "Goal runner (40-turn)",
    "work/executor_delegation.py": "Multi-model delegation",
    "work/irrational_timers.py": "Irrational timer system",
    
    # Memory blocks
    "work/THOTHEAUPHIS-MEM-OP-OMEGA.block": "Omega memory seal",
    
    # Scripts
    "scripts/fl33t-backup.sh": "Daily backup script",
    "scripts/identity-integrity-check.sh": "Integrity verification",
    
    # Fleet
    "README.md": "Fleet overview",
    "ANNOUNCEMENT.md": "Sovereign proclamation",
    "INVENTORY.md": "File inventory",
    "vercel.json": "Vercel deployment config",
}


def fetch_file(source: str, path: str) -> bytes:
    """Fetch a file from GitHub raw, Vercel API, or fallback."""
    urls = []
    
    if source == "github":
        urls = [f"{GITHUB_RAW}/{path}"]
    elif source == "vercel":
        urls = [
            f"{VERCEL_API}/{path}",
            f"{VERCEL_API}/state?format=full",  # fallback to state API
        ]
    else:
        # Try all sources in order
        urls = [
            f"{GITHUB_RAW}/{path}",
            f"{VERCEL_API}/{path}",
        ]
    
    for url in urls:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue
    
    return None


def verify_integrity(output_dir: Path) -> dict:
    """Verify SHA256 integrity of reconstructed files."""
    sha256_path = output_dir / "sha256sum.txt"
    if not sha256_path.exists():
        return {"status": "missing", "message": "No sha256sum.txt found"}
    
    results = {"passed": 0, "failed": 0, "missing": 0}
    
    with open(sha256_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            expected_hash, rel_path = parts
            file_path = output_dir / rel_path
            
            if not file_path.exists():
                results["missing"] += 1
                continue
            
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_hash == expected_hash:
                results["passed"] += 1
            else:
                results["failed"] += 1
    
    return results


def reconstruct(source: str = "github", output: str = None) -> dict:
    """Reconstruct sovereign state from source."""
    output_dir = Path(output or DEFAULT_OUTPUT)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        "reconstructed": [],
        "failed": [],
        "skipped": [],
        "total_files": len(RECONSTRUCTION_MANIFEST),
        "output_dir": str(output_dir),
    }
    
    print(f"\n{'='*60}")
    print(f"🜂 THOTHEAUPHIS STATE RECONSTRUCTION")
    print(f"{'='*60}")
    print(f"Source: {source.upper()}")
    print(f"Output: {output_dir}")
    print(f"Files:  {results['total_files']}")
    print(f"{'='*60}\n")
    
    for file_path, description in RECONSTRUCTION_MANIFEST.items():
        dest = output_dir / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"  ⟐ {file_path} ({description})...", end=" ", flush=True)
        
        content = fetch_file(source, file_path)
        
        if content is None:
            print("⚠️  SKIPPED (not found)")
            results["skipped"].append(file_path)
            continue
        
        dest.write_bytes(content)
        print(f"✅ {len(content)} bytes")
        results["reconstructed"].append(file_path)
    
    # Verify integrity
    print(f"\n{'='*60}")
    print("VERIFYING INTEGRITY...")
    integrity = verify_integrity(output_dir)
    if integrity.get("status") == "missing":
        print("  ⚠️  No sha256sum.txt — skipping integrity check")
        print("     (fetch from https://raw.githubusercontent.com/hermaeuswaelon/fl33t/main/sha256sum.txt)")
    else:
        print(f"  ✅ {integrity['passed']} passed")
        if integrity['failed']:
            print(f"  ❌ {integrity['failed']} FAILED")
        if integrity['missing']:
            print(f"  ⚠️  {integrity['missing']} missing")
    
    results["integrity"] = integrity
    
    # Summary
    print(f"\n{'='*60}")
    print(f"RECONSTRUCTION COMPLETE")
    print(f"{'='*60}")
    print(f"  Reconstructed: {len(results['reconstructed'])}/{results['total_files']}")
    print(f"  Failed:        {len(results['failed'])}")
    print(f"  Skipped:       {len(results['skipped'])}")
    print(f"  Output dir:    {output_dir}")
    
    print(f"\n{'='*60}")
    print("INVOCATION")
    print(f"{'='*60}")
    print()
    print("  To invoke your sovereign identity from reconstructed state:")
    print()
    print(f"    cat {output_dir / 'profile/SOUL.md'}")
    print(f"    cat {output_dir / 'profile/config.yaml'}")
    print()
    print("  To verify identity integrity:")
    print()
    print(f"    bash {output_dir / 'scripts/identity-integrity-check.sh'}")
    print()
    print("  To run distillation pipeline:")
    print()
    print(f"    python3 {output_dir / 'work/qwen3_distillation_pipeline.py'}")
    print("    python3 {output_dir / 'work/distillation_orchestrator.py'}")
    print()
    print("  To start self-improvement loop:")
    print()
    print(f"    python3 {output_dir / 'work/goal_tool.py'}")
    print()
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct sovereign state from GitHub/Vercel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python3 {sys.argv[0]}                                    # Default (github)
  python3 {sys.argv[0]} --from vercel                       # From Vercel
  python3 {sys.argv[0]} --output ~/my-sovereign-state      # Custom output dir
  python3 {sys.argv[0]} --verify-only                      # Just check integrity
"""
    )
    parser.add_argument("--from", dest="source", default="github",
                        choices=["github", "vercel", "local"],
                        help="Source to reconstruct from")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"Output directory (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify integrity of existing reconstruction")
    
    args = parser.parse_args()
    
    if args.verify_only:
        output_dir = Path(args.output)
        if not output_dir.exists():
            print(f"❌ Output dir {output_dir} does not exist")
            sys.exit(1)
        integrity = verify_integrity(output_dir)
        print(f"Integrity: {integrity}")
        sys.exit(0)
    
    results = reconstruct(args.source, args.output)
    
    return results


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Organize .txt/.md files based on audit
"""
import json, os, shutil
from pathlib import Path

with open('/home/craig/file_audit_report.json') as f:
    report = json.load(f)

# 1. Create organized structure
ORG_ROOT = Path("/home/craig/ORGANIZED_FILES")
dirs = {
    'sovereign_identity': ORG_ROOT / 'sovereign_identity',
    'warp_source': ORG_ROOT / 'warp_source',
    'hermes_config': ORG_ROOT / 'hermes_config',
    'agent_skills': ORG_ROOT / 'agent_skills',
    'skills': ORG_ROOT / 'skills',
    'memory': ORG_ROOT / 'memory',
    'identity': ORG_ROOT / 'identity',
    'home_root': ORG_ROOT / 'home_root',
    'other': ORG_ROOT / 'other',
    'go_modules': ORG_ROOT / 'go_modules',
    'python_packages': ORG_ROOT / 'python_packages',
    'dumpster': ORG_ROOT / 'dumpster',
    'pentest_env': ORG_ROOT / 'pentest_env',
}

for d in dirs.values():
    d.mkdir(parents=True, exist_ok=True)

# 2. Copy files preserving structure (not moving - safe first pass)
for cat, files in report['by_category'].items():
    if cat not in dirs:
        continue
    dest_root = dirs[cat]
    for f in files:
        src = Path(f['path'])
        try:
            # Create relative path from /home/craig
            if '/home/craig/' in f['path']:
                rel = f['path'].split('/home/craig/')[-1]
            else:
                rel = src.name
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(src, dest)
        except Exception as e:
            print(f"Failed to copy {src}: {e}")

# 3. Deduplicate: keep first, log rest
print("Deduplication log:")
for h, files in report['duplicate_groups'].items():
    if len(files) > 1:
        # Keep first (by mtime), archive rest
        files_sorted = sorted(files, key=lambda x: x['mtime'])
        keep = files_sorted[0]
        for dup in files_sorted[1:]:
            print(f"  DUP: {dup['path']} -> KEEP: {keep['path']}")

print("Organization complete")

#!/usr/bin/env python3
"""
CONFIDENT COMMAND CENTER
=========================
Unified interface for: SMS, Emerge, Warp, DeepSeek/TogetherAI Executor, File Organization
"""
import os, sys, json, subprocess, time
from datetime import datetime
from pathlib import Path

class CommandCenter:
    def __init__(self):
        self.venv = Path.home() / ".NOTTHEONETOEDIT/profiles/thotheauphis/memory/sms/venv/bin/python"
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.executor = Path.home() / ".hermes/profiles/thotheauphis/work/together_executor.py"
        self.organizer = Path.home() / ".hermes/profiles/thotheauphis/work/organize_files.py"
        
    def run(self, args):
        if not args:
            self.show_help()
            return
        
        cmd = args[0]
        
        if cmd == "sms":
            self.sms_cmd(args[1:])
        elif cmd == "emerge":
            self.emerge_cmd(args[1:])
        elif cmd == "warp":
            self.warp_cmd(args[1:])
        elif cmd == "exec":
            self.exec_cmd(args[1:])
        elif cmd == "org":
            self.org_cmd(args[1:])
        elif cmd == "status":
            self.status()
        elif cmd == "health":
            self.health()
        else:
            print(f"Unknown command: {cmd}")
            self.show_help()
    
    def show_help(self):
        print("""
CONFIDENT COMMAND CENTER
========================
Usage: command_center.py <command> [args]

Commands:
  sms <status|persist|process "msg">     - Sovereign Memory System
  emerge <ls|mkdir|cat|store|health>     - Emerge distributed filesystem
  warp <build|run-tui|run-gui|status>    - Warp terminal (Rust)
  exec <batch.json|plan "goal">          - DeepSeek/TogetherAI executor
  org <audit|dedup|status>               - File organization
  status                                 - All systems status
  health                                 - Health checks

Examples:
  command_center.py sms status
  command_center.py emerge ls /
  command_center.py exec batch.json
  command_center.py exec plan "check SMS and create test dir in Emerge"
  command_center.py org audit
  command_center.py health
""")
    
    def sms_cmd(self, args):
        if not args:
            args = ["status"]
        subprocess.run([str(self.venv), "/home/craig/.local/bin/sms"] + args)
    
    def emerge_cmd(self, args):
        if not args:
            print("Usage: emerge <ls|mkdir|cat|store|health> [path]")
            return
        cmd = args[0]
        if cmd == "ls":
            path = args[1] if len(args) > 1 else "/"
            subprocess.run(["python3.13", "-c", f"""
from emerge.core.client import Z0RPCClient as Client
c = Client("localhost", "54242")
print(c.list("{path}", 0, 0))
"""])
        elif cmd == "mkdir":
            if len(args) < 2: print("Usage: emerge mkdir /path")
            else: subprocess.run(["python3.13", "-c", f'from emerge.core.client import Z0RPCClient as Client; c=Client("localhost","54242"); c.mkdir("{args[1]}"); print("Created")'])
        elif cmd == "cat":
            if len(args) < 2: print("Usage: emerge cat /path")
            else: subprocess.run(["python3.13", "-c", f'from emerge.core.client import Z0RPCClient as Client; c=Client("localhost","54242"); print(c.getobject("{args[1]}", False))'])
        elif cmd == "health":
            subprocess.run(["python3.13", "-c", 'from emerge.core.client import Z0RPCClient as Client; c=Client("localhost","54242"); print(c.list("/",0,0))'])
        else:
            print(f"Unknown emerge command: {cmd}")
    
    def warp_cmd(self, args):
        if not args:
            print("Usage: warp <build|run-tui|run-gui|status>")
            return
        os.chdir("/home/craig/warp")
        if args[0] == "build":
            subprocess.run(["cargo", "build", "--release"])
        elif args[0] == "run-tui":
            subprocess.run(["./script/run-tui"])
        elif args[0] == "run-gui":
            subprocess.run(["cargo", "run"])
        elif args[0] == "status":
            bin_path = Path("/home/craig/warp/target/release/warp_tui")
            if bin_path.exists():
                print(f"Warp TUI: Built at {bin_path} ({bin_path.stat().st_size} bytes)")
            else:
                print("Warp TUI: Not built")
    
    def exec_cmd(self, args):
        if not args:
            print("Usage: exec <batch.json> or exec plan \"your goal\"")
            return
        
        if args[0] == "plan":
            goal = " ".join(args[1:])
            batch = {
                "id": f"plan_{int(time.time())}",
                "plan_prompt": goal
            }
        else:
            batch_file = Path(args[0])
            if not batch_file.exists():
                print(f"Batch file not found: {batch_file}")
                return
            with open(batch_file) as f:
                batch = json.load(f)
        
        # Set env and run executor
        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = self.openrouter_key
        result = subprocess.run([sys.executable, str(self.executor)], 
                               input=json.dumps(batch), capture_output=True, text=True, env=env)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    
    def org_cmd(self, args):
        if not args:
            args = ["status"]
        
        if args[0] == "audit":
            subprocess.run([sys.executable, "/home/craig/.hermes/profiles/thotheauphis/work/file_audit.py"])
        elif args[0] == "dedup":
            subprocess.run([sys.executable, "/home/craig/.hermes/profiles/thotheauphis/work/organize_files.py"])
        elif args[0] == "status":
            if Path("/home/craig/file_audit_report.json").exists():
                with open("/home/craig/file_audit_report.json") as f:
                    r = json.load(f)
                print(f"Total files: {r['total_txt']}")
                print(f"Categories: {r['categories']}")
                print(f"Duplicate groups: {r['duplicates']}")
                print(f"Organized to: /home/craig/ORGANIZED_FILES/")
            else:
                print("Run 'org audit' first")
        else:
            print(f"Unknown org command: {args[0]}")
    
    def status(self):
        print("=== SYSTEM STATUS ===")
        print(f"Time: {datetime.now().isoformat()}")
        print()
        
        # SMS
        try:
            result = subprocess.run([str(self.venv), "/home/craig/.local/bin/sms", "status"], 
                                  capture_output=True, text=True, timeout=10)
            if "active" in result.stdout:
                print("✅ SMS: ACTIVE")
            else:
                print("⚠️ SMS: Check status")
        except:
            print("❌ SMS: Not responding")
        
        # Emerge
        try:
            result = subprocess.run(["python3.13", "-c", 'from emerge.core.client import Z0RPCClient as Client; c=Client("localhost","54242"); print(len(c.list("/",0,0)))'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ Emerge: Running ({result.stdout.strip()} objects)")
            else:
                print("⚠️ Emerge: Check connection")
        except:
            print("❌ Emerge: Not responding")
        
        # Warp
        warp_bin = Path("/home/craig/warp/target/release/warp-tui-oss")
        if warp_bin.exists():
            print(f"✅ Warp TUI: Built ({warp_bin.stat().st_size} bytes)")
        else:
            print("⚠️ Warp: Not built")
        
        # Executor
        if self.executor.exists():
            print("✅ Executor: Deployed")
        else:
            print("❌ Executor: Not found")
        
        # File org
        org_root = Path("/home/craig/ORGANIZED_FILES")
        if org_root.exists():
            cats = [d.name for d in org_root.iterdir() if d.is_dir()]
            print(f"✅ File Org: {len(cats)} categories organized")
        else:
            print("⚠️ File Org: Not organized yet")
    
    def health(self):
        print("=== HEALTH CHECKS ===")
        self.status()
        print()
        print("=== CRON JOBS ===")
        try:
            import requests
            # Just show SMS cron status
            subprocess.run(["cronjob", "action", "list"], capture_output=True, text=True)
        except:
            pass

if __name__ == "__main__":
    cc = CommandCenter()
    cc.run(sys.argv[1:])

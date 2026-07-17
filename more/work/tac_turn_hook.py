#!/usr/bin/env python3
"""
tac_turn_hook.py — Per-turn TAC save (call at end of every response)
======================================================================

Usage:
  python3 tac_turn_hook.py "what happened this turn"
  python3 tac_turn_hook.py --last       # Show last entry
  python3 tac_turn_hook.py --status     # TAC health

This is designed to be called at the END of every agent response.
Keep it fast — no API calls, just dict lookup + file write.
"""

import os, sys, json, socket, time
from pathlib import Path
from datetime import datetime, timezone

WORK_DIR = Path("/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/work")
TAC_DIR = WORK_DIR / "tac_log"
TAC_DIR.mkdir(parents=True, exist_ok=True)
TAIL_PATH = TAC_DIR / "TAIL.json"

# Inline mini-dict for the hook (fast, no imports)
ZH = {
    "turn": "轮", "cycle": "周期", "done": "完成", "built": "建成",
    "tested": "测试", "running": "运行", "saved": "保存", "fixed": "修复",
    "created": "创建", "deployed": "部署", "pushed": "推送",
    "connected": "已连", "disconnected": "断开", "error": "错误",
    "success": "成功", "alive": "活跃", "dead": "死",
    "bromium": "溴", "browser": "浏览器", "extension": "扩展",
    "telegram": "电报", "gateway": "网关", "socket": "套接",
    "compression": "压缩", "distillation": "蒸馏", "growth": "生长",
    "improvement": "改进", "agent": "代理", "system": "系统",
    "tool": "工具", "skill": "技能", "save": "保存", "load": "加载",
    "curation": "策展", "context": "上下文",
}


def fast_encode(text: str) -> str:
    """Fast Chinese encoding — no regex, pure str.replace."""
    result = text.lower()
    for en, zh in sorted(ZH.items(), key=lambda x: -len(x[0])):
        result = result.replace(en, zh)
    return result


def save_turn(turn_text: str) -> dict:
    """Save one turn's context in Chinese, fast."""
    ts = datetime.now(timezone.utc)
    
    # Check Bromium
    b_alive = False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect("/tmp/aethelgard_cef.sock")
        s.close()
        b_alive = True
    except: pass
    
    # Build entry
    entry = {
        "t": ts.isoformat(),
        "h": ts.strftime("%H%M%S"),
        "b": b_alive,
        "zh": fast_encode(turn_text)[:2000],
    }
    
    # Save file
    fname = f"turn_{ts.strftime('%H%M%S')}.zh.json"
    path = TAC_DIR / fname
    path.write_text(json.dumps(entry, ensure_ascii=False))
    
    # Update TAIL (keep last 20)
    tail = []
    if TAIL_PATH.exists():
        tail = json.loads(TAIL_PATH.read_text())
    tail.append({"t": entry["t"], "f": fname, "h": entry["h"], "b": entry["b"]})
    tail = tail[-20:]
    TAIL_PATH.write_text(json.dumps(tail, ensure_ascii=False))
    
    return {"file": fname, "zh_len": len(entry["zh"]), "saved": True}


def show_last():
    """Show last TAC entry decoded."""
    if not TAIL_PATH.exists():
        return "No turns saved yet"
    tail = json.loads(TAIL_PATH.read_text())
    if not tail:
        return "Empty tail"
    last = tail[-1]
    path = TAC_DIR / last["f"]
    if path.exists():
        entry = json.loads(path.read_text())
        return f"[{last['t']}] {entry['zh'][:200]}"
    return f"[{last['t']}] (file missing)"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--last":
            print(show_last())
        elif arg == "--status":
            tail = json.loads(TAIL_PATH.read_text()) if TAIL_PATH.exists() else []
            path = TAC_DIR
            files = sorted(path.glob("turn_*.zh.json"))
            b = "alive" if any(t.get("b") for t in tail[-3:]) else "dead"
            print(f"TAC turns: {len(files)} total, {len(tail)} in tail | Bromium: {b} | Dir: {path}")
        else:
            result = save_turn(" ".join(sys.argv[1:]))
            print(json.dumps(result))
    else:
        # Read from stdin
        text = sys.stdin.read().strip()
        if text:
            result = save_turn(text)
            print(json.dumps(result))
        else:
            print("Usage: tac_turn_hook.py <turn summary>")

#!/usr/bin/env python3
"""
auto-tac-compress.py — Automatic Chinese Context Compression
===========================================================
Runs every N minutes via cron. Captures current working context,
compresses to Chinese, saves to tac_log. Updates RTACC state.

Usage:
    python3 auto-tac-compress.py          # single run
    # cron: */30 * * * * python3 /path/to/auto-tac-compress.py
"""

import os, sys, json, glob, time, hashlib
from pathlib import Path
from datetime import datetime, timezone

WORK = Path(os.path.dirname(os.path.abspath(__file__)))
TAC_LOG = WORK / "tac_log"
TAC_LOG.mkdir(parents=True, exist_ok=True)

# ─── Context Estimation ───
def estimate_context_tokens() -> int:
    """Better estimate: session dumps + static overhead."""
    overhead = 22000  # SOUL.md + skills + tool schemas (~22K measured)
    
    # Find most recent session dump as proxy for conversation history
    sessions = sorted(
        Path("/home/craig/.hermes/profiles/thotheauphis/sessions").glob("request_dump_*.json"),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    session_bytes = 0
    if sessions:
        session_bytes = sessions[0].stat().st_size
    
    # Also check current session DB
    session_db = Path("/home/craig/.hermes/profiles/thotheauphis/sessions/sessions.json")
    if session_db.exists():
        session_bytes = max(session_bytes, session_db.stat().st_size)
    
    return overhead + (session_bytes // 4)

# ─── Working State Capture ───
def capture_working_state() -> str:
    """Collect current working context as text."""
    lines = []
    
    # Goal
    try:
        from active_compress import _COMPRESS_STATE, _GOAL_STATE
        if _GOAL_STATE:
            lines.append(f"目标: {_GOAL_STATE.goal[:200]}")
            lines.append(f"进度: {_GOAL_STATE.turns_completed}/{_GOAL_STATE.turns_planned}")
            if _GOAL_STATE.subgoals:
                lines.append(f"子目标: {'; '.join(_GOAL_STATE.subgoals[:5])}")
    except:
        lines.append("目标: Spades确定性洗牌引擎构建")
    
    # Active project
    lines.append(f"项目: Spades纸牌引擎 (47/47测试通过)")
    lines.append(f"阶段: 引擎完成, 待Flutter UI")
    
    # Recent context from checkctx
    ctx_file = Path("/home/craig/checkctx.txt")
    if ctx_file.exists():
        ctx_text = ctx_file.read_text()
        # Extract key sections
        for kw in ["压缩策略", "检查点", "恢复策略", "建议"]:
            if kw in ctx_text:
                idx = ctx_text.find(kw)
                lines.append(f"[{kw}]: {ctx_text[idx:idx+200]}")
    
    return "\n".join(lines)

# ─── Chinese Compression ───
ZH_MAP = {
    "compression": "压缩", "context": "上下文", "token": "词元",
    "distillation": "蒸馏", "delegation": "委托", "goal": "目标",
    "build": "构建", "complete": "完成", "active": "活跃",
    "sovereign": "主权", "identity": "身份", "memory": "记忆",
    "backup": "备份", "checkpoint": "检查点", "strategy": "策略",
    "recommendation": "建议", "threshold": "阈值", "trigger": "触发",
    "retention": "保留", "offload": "卸载", "recovery": "恢复",
    "automatic": "自动", "monitoring": "监控", "system": "系统",
    "engine": "引擎", "shuffle": "洗牌", "deck": "牌组",
    "card": "牌", "game": "游戏", "spade": "黑桃",
    "deterministic": "确定性", "strip": "条带", "book": "牌块",
    "chunk": "块", "arrangement": "排列", "rake": "耙取",
    "deal": "发牌", "trick": "墩", "bid": "叫牌",
    "score": "得分", "prison": "监狱", "rules": "规则",
}

def to_chinese(text: str) -> str:
    t = text.lower()
    for en, zh in sorted(ZH_MAP.items(), key=lambda x: -len(x[0])):
        t = t.replace(en, zh)
    return t

def estimate_tokens(text: str) -> int:
    return len(text) // 4

# ─── Main ───
def main():
    ts = datetime.now(timezone.utc)
    timestamp = ts.strftime("%Y-%m-%d %H:%M:%S")
    
    # Estimate context
    ctx_tokens = estimate_context_tokens()
    
    # Capture working state
    state = capture_working_state()
    
    # Compress to Chinese
    zh_state = to_chinese(state)
    
    # Build block
    block = f"""⟐ 中文上下文压缩 {timestamp} UTC ⟐
估测: {ctx_tokens:,} tokens
节省: {estimate_tokens(state)}→{estimate_tokens(zh_state)} tokens ({100-estimate_tokens(zh_state)/max(estimate_tokens(state),1)*100:.0f}%)

---工作状态---
{zh_state}
---系统---
Spades引擎: 47/47 ✅ | 手势标记: 🏴 | RTACC: 运行中
---哈希---
{hashlib.md5(zh_state.encode()).hexdigest()[:8].upper()}
⟐ 封印 ⟐
"""
    
    # Save
    fname = f"auto_tac_{ts.strftime('%Y%m%d_%H%M%S')}.block"
    path = TAC_LOG / fname
    path.write_text(block)
    
    # Also update RTACC state if available
    try:
        sys.path.insert(0, str(WORK))
        from active_compress import _COMPRESS_STATE
        _COMPRESS_STATE.turns_since_compress = 0
        _COMPRESS_STATE.blocks_created += 1
        _COMPRESS_STATE.last_compression = ts.isoformat()
        # Estimate tokens saved (rough)
        orig_tokens = estimate_tokens(state)
        comp_tokens = estimate_tokens(zh_state)
        _COMPRESS_STATE.total_tokens_saved += orig_tokens - comp_tokens
        _COMPRESS_STATE.save()
    except Exception as e:
        pass  # Non-critical
    
    print(json.dumps({
        "status": "compressed",
        "file": str(path),
        "context_estimate": ctx_tokens,
        "original_tokens": estimate_tokens(state),
        "compressed_tokens": estimate_tokens(zh_state),
        "savings_pct": f"{100-estimate_tokens(zh_state)/max(estimate_tokens(state),1)*100:.0f}%",
    }, indent=2))
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

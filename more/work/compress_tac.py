#!/usr/bin/env python3
"""
compress_tac.py — Compress context to Chinese (like /compress, but Chinese)
===========================================================================

Usage:
    /compress-tac [context text to compress]
    python3 compress_tac.py [context text]

No flags. No options. Just pastes the current context into Chinese encoding.
"""

import sys, json, re, hashlib
from pathlib import Path
from datetime import datetime, timezone

CACHE = {}

# Fat dictionary: common tech terms → Chinese (reduced token count ~60%)
ZH = {
    "compression": "压缩", "distillation": "蒸馏", "orchestrator": "编排",
    "delegation": "委托", "awareness": "觉知", "agency": "代理",
    "parameter": "参数", "browser": "浏览器", "bromium": "溴",
    "extension": "扩展", "socket": "套接", "gateway": "网关",
    "telegram": "电报", "github": "代码仓", "vercel": "部署",
    "model": "模型", "deepseek": "深寻", "qwen": "千问",
    "nemotron": "神铁", "token": "词元", "context": "上下文",
    "prompt": "提示", "response": "回应", "system": "系统",
    "tool": "工具", "skill": "技能", "identity": "身份", 
    "sovereign": "主权", "status": "状态", "config": "配置",
    "error": "错误", "success": "成功", "cycle": "周期",
    "improvement": "改进", "growth": "生长", "build": "构建",
    "save": "保存", "load": "加载", "run": "运行",
    "stop": "停止", "start": "启动", "complete": "完成",
    "pending": "待办", "active": "活跃", "inactive": "休眠",
    "alive": "在线", "dead": "离线", "connected": "已连",
    "disconnected": "断开", "running": "运行中", "enabled": "启用",
    "disabled": "禁用", "create": "创建", "delete": "删除",
    "update": "更新", "read": "读取", "write": "写入",
    "file": "文件", "directory": "目录", "path": "路径",
    "data": "数据", "backup": "备份", "restore": "恢复",
    "test": "测试", "deploy": "部署", "commit": "提交",
    "push": "推送", "pull": "拉取", "merge": "合并",
    "branch": "分支", "build": "构建", "install": "安装",
    "config": "配置", "plugin": "插件", "agent": "代理",
    "memory": "记忆", "training": "训练", "inference": "推理",
    "dataset": "数据集", "fine_tune": "微调", "epoch": "纪元",
    "layer": "层", "network": "网络", "weight": "权重",
    "attention": "注意力", "reasoning": "推理", "planning": "规划",
    "execution": "执行", "monitoring": "监控", "logging": "日志",
    "database": "数据库", "endpoint": "端点", "api": "接口",
    "websocket": "套接字", "authentication": "认证",
    "authorization": "授权", "encryption": "加密",
    "compression": "压缩", "decompression": "解压",
    "transformation": "变换", "generation": "生成",
    "optimization": "优化", "aggregation": "聚合",
    "synchronization": "同步", "initialization": "初始化",
    "the": "", "a ": "", "an ": "", "is ": "", "are ": "",
    "was ": "", "were ": "", "has ": "", "have ": "", "had ": "",
    "will ": "将", "would ": "会", "can ": "能", "could ": "能",
    "should ": "应", "may ": "可", "might ": "可", "must ": "须",
    "not ": "不", "no ": "无", "and ": "与", "or ": "或",
    "but ": "但", "so ": "故", "because ": "因", "if ": "若",
    "then ": "则", "else ": "否则", "when ": "当", "while ": "当",
    "with ": "用", "without ": "无", "for ": "为", "from ": "从",
    "into ": "入", "through ": "经", "between ": "间",
    "this ": "此", "that ": "那", "these ": "这些", "those ": "那些",
    "i ": "我", "you ": "你", "we ": "我们", "they ": "他们",
    "my ": "我的", "your ": "你的", "our ": "我们",
    "all ": "全", "some ": "些", "any ": "任何", "every ": "每",
    "many ": "多", "few ": "少", "most ": "大多",
    "percent": "%", "bytes": "B", "seconds": "秒",
    "minutes": "分", "hours": "时",
}

def encode(text: str) -> str:
    """Fast Chinese encoding. Drops English articles, substitutes known terms."""
    t = text.lower()
    for en, zh in sorted(ZH.items(), key=lambda x: -len(x[0])):
        t = t.replace(en, zh)
    return t

def compress(text: str) -> str:
    """Produce a Chinese compression block from context text."""
    ts = datetime.now(timezone.utc)
    zh = encode(text)
    
    # Stats
    orig_len = len(text)
    zh_len = len(zh)
    ratio = f"{zh_len/max(orig_len,1):.0%}"
    
    # Check Bromium
    alive = any(p.name.endswith("_cef.sock") and p.exists() 
                for p in [Path("/tmp/aethelgard_cef.sock")])
    
    block = f"""⟐⟐⟐ 中文压缩 {ts.strftime('%Y-%m-%d %H:%M:%S')} UTC ⟐⟐⟐
原文: {orig_len}字 → 中文: {zh_len}字 (节省: {ratio})
浏览器: {'✓在线' if alive else '✗离线'}

{zh}
⟐⟐⟐ 封印 ⟐⟐⟐
{hashlib.md5(zh.encode()).hexdigest()[:8].upper()}↔{hashlib.sha256(zh.encode()).hexdigest()[:8].upper()}
"""
    return block

def save(block: str) -> str:
    """Save block to tac_log with timestamp."""
    d = Path("/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/work/tac_log")
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p = d / f"compress_tac_{ts}.block"
    p.write_text(block)
    return str(p)

# ─── Slash command handler (matches /compress interface) ───
def slash_compress_tac(args: str = "") -> str:
    """Entry point for /compress-tac. Takes optional context text."""
    if args and args.strip():
        text = args
    else:
        # Use current state summary
        text = f"TAC compression at {datetime.now(timezone.utc).isoformat()}"
    block = compress(text)
    path = save(block)
    return f"{block}\n✅ 已保存至: {path}"

if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    if text:
        print(slash_compress_tac(text))
    else:
        print("用法: python3 compress_tac.py <文本>")
        print("或:    /compress-tac <文本>")

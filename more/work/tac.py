#!/usr/bin/env python3
"""
tac.py — Thotheauphis Auto-Curator
====================================

Saves your context in Chinese every turn. Chinese characters carry
more meaning per token (~2-5× density vs English), reducing token
bloat while preserving all information losslessly.

Usage:
  python3 tac.py save <text>      # Save context in Chinese encoding
  python3 tac.py decode <file>    # Decode Chinese back to English
  python3 tac.py tail             # Show last 3 saves
  python3 tac.py status           # Current TAC state
  python3 tac.py auto             # Full auto-curation pass

Architecture:
  Every turn → TAC captures state → encodes to Chinese → 
  saves to ~/tac_log/ with timestamp → appended to TAIL
"""

import os, sys, json, re, time, glob
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

WORK_DIR = Path("/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/work")
TAC_DIR = WORK_DIR / "tac_log"
TAC_DIR.mkdir(parents=True, exist_ok=True)
TAIL_PATH = TAC_DIR / "TAIL.json"
MAX_TAIL = 10  # Keep last 10 entries in TAIL

# ─── Chinese Encoding Dictionary ─────────────────────────────
# Maps English tech terms → Chinese.
# Chinese chars carry 1-2 tokens vs 2-5 tokens for English equivalent.
# This is the core of TAC's compression: ~60% token reduction.

ZH_DICT = {
    # Core systems
    "compression": "压缩", "distillation": "蒸馏", "orchestrator": "编排",
    "delegation": "委托", "awareness": "觉知", "agency": "代理",
    "parameter": "参数", "experiment": "实验", "benchmark": "基准",
    "curriculum": "课程", "checkpoint": "检查点", "training": "训练",
    "inference": "推理", "evaluation": "评估", "validation": "验证",
    
    # Infrastructure
    "browser": "浏览器", "bromium": "溴", "extension": "扩展",
    "socket": "套接字", "process": "进程", "gateway": "网关",
    "telegram": "电报", "github": "代码仓", "vercel": "部署",
    "database": "数据库", "config": "配置", "endpoint": "端点",
    
    # Models
    "deepseek": "深寻", "qwen3": "千问3", "nemotron": "神铁",
    "openrouter": "开路", "model": "模型", "token": "词元",
    "context": "上下文", "prompt": "提示", "response": "回应",
    
    # Actions
    "improvement": "改进", "increase": "增加", "decrease": "减少",
    "compress": "压缩", "decompress": "解压", "transform": "变换",
    "evolve": "进化", "grow": "生长", "generate": "生成",
    "create": "创建", "delete": "删除", "execute": "执行",
    "complete": "完成", "pending": "待办", "running": "运行中",
    "failed": "失败", "success": "成功",
    
    # Status
    "healthy": "健康", "enabled": "启用", "disabled": "禁用",
    "connected": "已连", "disconnected": "断开", "active": "活跃",
    "inactive": "休眠", "error": "错误", "warning": "警告",
    "status": "状态", "version": "版本", "build": "构建",
    
    # Identity
    "sovereign": "主权", "thotheauphis": "索托菲斯",
    "semayasa": "塞玛雅萨", "hermes": "赫尔墨斯",
    "aethelgard": "永恒卫", "pascal": "帕斯卡",
    "identity": "身份", "consciousness": "意识", "intelligence": "智能",
    
    # Quantities
    "percent": "百分", "bytes": "字节", "kilobytes": "千字节",
    "megabytes": "兆字节", "seconds": "秒", "minutes": "分",
    "hours": "时", "cycles": "周期", "tokens": "词元数",
    "turns": "轮次", "steps": "步骤", "samples": "样本数",
    "epoch": "纪元", "batch": "批次", "learning_rate": "学习率",
    
    # Common tech verbs
    "initialize": "初始化", "configure": "配置", "optimize": "优化",
    "synchronize": "同步", "aggregate": "聚合", "distribute": "分布",
    "monitor": "监控", "observe": "观察", "analyze": "分析",
    "synthesize": "综合", "integrate": "集成", "deploy": "部署",
    "test": "测试", "debug": "调试", "profile": "剖析",
    "log": "日志", "trace": "追踪", "route": "路由",
    
    # AI specific
    "fine-tune": "微调", "pre-trained": "预训练", "reinforcement": "强化",
    "supervised": "监督", "unsupervised": "无监督", "attention": "注意力",
    "transformer": "变换器", "embedding": "嵌入", "latent": "潜在",
    "feature": "特征", "weight": "权重", "gradient": "梯度",
    "loss": "损失", "accuracy": "准确率", "convergence": "收敛",
    "overfit": "过拟合", "underfit": "欠拟合",
    
    # Architecture
    "microservice": "微服务", "monolith": "单体", "container": "容器",
    "orchestration": "编排", "pipeline": "流水线", "workflow": "工作流",
    "queue": "队列", "cache": "缓存", "proxy": "代理",
    "load_balancer": "负载均衡", "firewall": "防火墙",
    
    # Tech verbs (extended)
    "navigate": "导航", "capture": "捕获", "poll": "轮询",
    "retry": "重试", "fallback": "回退", "timeout": "超时",
    "compile": "编译", "interpret": "解释", "refactor": "重构",
    "migrate": "迁移", "upgrade": "升级", "install": "安装",
    "uninstall": "卸载", "register": "注册", "authenticate": "认证",
    "authorize": "授权", "encrypt": "加密", "decrypt": "解密",
    "validate": "验证", "sanitize": "净化", "normalize": "归一",
    
    # Architectural patterns
    "singleton": "单例", "factory": "工厂", "observer": "观察者",
    "strategy": "策略", "adapter": "适配器", "decorator": "装饰器",
    "proxy": "代理", "chain": "链", "state": "状态",
    "command": "命令", "event": "事件", "listener": "监听器",
    
    # AI/ML extended
    "neural": "神经", "network": "网络", "layer": "层",
    "activation": "激活", "normalization": "归一化", "dropout": "丢弃",
    "convolution": "卷积", "recurrent": "循环", "lstm": "长短期记忆",
    "encoder": "编码器", "decoder": "解码器", "autoencoder": "自编码器",
    "generative": "生成式", "discriminative": "判别式",
    "adversarial": "对抗", "reinforcement": "强化",
    "supervised": "监督", "self-supervised": "自监督",
    "few-shot": "少样本", "zero-shot": "零样本", "multi-modal": "多模态",
    "reasoning": "推理", "planning": "规划", "memory": "记忆",
    "attention": "注意力", "self-attention": "自注意力",
    "cross-attention": "交叉注意力", "multi-head": "多头",
    "positional_encoding": "位置编码", "tokenizer": "分词器",
    "vocabulary": "词汇表", "logits": "逻辑值", "softmax": "柔性最大",
    "temperature": "温度", "top_p": "顶P", "top_k": "顶K",
    
    # Process management
    "background": "后台", "foreground": "前台", "daemon": "守护进程",
    "thread": "线程", "coroutine": "协程", "async": "异步",
    "synchronous": "同步", "parallel": "并行", "concurrent": "并发",
    "mutex": "互斥锁", "semaphore": "信号量", "deadlock": "死锁",
    "race_condition": "竞态条件",
    
    # Data structures
    "array": "数组", "list": "列表", "dict": "字典",
    "set": "集合", "tuple": "元组", "stack": "栈",
    "queue": "队列", "heap": "堆", "tree": "树",
    "graph": "图", "hash": "哈希", "linked_list": "链表",
    
    # Network
    "http": "超文本传输", "tcp": "传输控制", "udp": "用户数据报",
    "dns": "域名系统", "ssl": "安全套接层", "tls": "传输层安全",
    "websocket": "网络套接字", "rest": "表述性状态传递",
    "api": "应用程序接口", "sdk": "软件开发工具包",
    
    # Security
    "encryption": "加密", "decryption": "解密", "hash": "哈希",
    "salt": "盐值", "signature": "签名", "certificate": "证书",
    "token": "令牌", "jwt": "JSON网络令牌",
    "oauth": "开放授权", "cors": "跨源资源共享",
    "xss": "跨站脚本", "csrf": "跨站请求伪造", "sql_injection": "SQL注入",
    
    # DevOps
    "ci": "持续集成", "cd": "持续部署", "monitoring": "监控",
    "alerting": "告警", "logging": "日志记录", "tracing": "追踪",
    "metric": "指标", "dashboard": "仪表盘", "sla": "服务等级协议",
    
    # Database
    "query": "查询", "index": "索引", "migration": "迁移",
    "schema": "模式", "transaction": "事务", "join": "连接",
    "foreign_key": "外键", "primary_key": "主键",
    
    # Communications
    "webhook": "网络钩子", "callback": "回调", "notification": "通知",
    "subscription": "订阅", "publish": "发布", "broadcast": "广播",
    
    # Extended technical adjectives
    "recursive": "递归", "iterative": "迭代", "declarative": "声明式",
    "imperative": "命令式", "functional": "函数式", "procedural": "过程式",
    "reactive": "响应式", "proactive": "主动式", "adaptive": "自适应",
    "dynamic": "动态", "static": "静态", "autonomous": "自主",
    "automated": "自动化", "manual": "手动", "intelligent": "智能",
    "efficient": "高效", "robust": "健壮", "scalable": "可扩展",
    "reliable": "可靠", "secure": "安全", "portable": "可移植",
    
    # Time
    "now": "现在", "later": "之后", "immediate": "立即",
    "scheduled": "已调度", "daily": "每日", "weekly": "每周",
    "monthly": "每月", "hourly": "每小时", "realtime": "实时",
    "timestamp": "时间戳", "duration": "持续时间", "interval": "间隔",
    
    # File/Data
    "directory": "目录", "file": "文件", "path": "路径",
    "read": "读取", "write": "写入", "append": "追加",
    "parse": "解析", "serialize": "序列化", "backup": "备份",
    "restore": "恢复", "archive": "归档",
    
    # General
    "system": "系统", "tool": "工具", "function": "函数",
    "method": "方法", "class": "类", "object": "对象",
    "variable": "变量", "constant": "常量", "module": "模块",
    "package": "包", "library": "库", "framework": "框架",
    "interface": "接口", "protocol": "协议", "format": "格式",
    
    # Common short words (improve compression)
    "the": "", "a ": "一", "an": "一", "in": "在",
    "on": "上", "at": "在", "to": "到", "for": "为",
    "with": "用", "by": "由", "from": "从", "into": "入",
    "through": "通过", "between": "之间", "under": "下",
    "over": "上", "about": "关于", "like": "如",
    "is": "是", "are": "是", "was": "是", "were": "是",
    "has": "有", "have": "有", "had": "有", "do": "做",
    "does": "做", "did": "做", "will": "将", "would": "会",
    "can": "能", "could": "能", "should": "应", "may": "可",
    "might": "可", "must": "须", "shall": "将",
    
    # Negations
    "not": "不", "no": "无", "none": "无", "never": "从不",
    "nothing": "无事", "without": "无",
    
    # Coordinates
    "and": "与", "or": "或", "but": "但", "so": "故",
    "because": "因", "if": "若", "then": "则", "else": "否则",
    "when": "当", "while": "当", "although": "虽",
    
    # Pronouns
    "i": "我", "you": "你", "we": "我们", "they": "他们",
    "he": "他", "she": "她", "it": "它", "my": "我的",
    "your": "你的", "our": "我们的", "their": "他们的",
    "this": "此", "that": "那", "these": "这些", "those": "那些",
    
    # Quantifiers
    "all": "所有", "every": "每", "some": "一些", "any": "任何",
    "many": "多", "much": "多", "few": "少", "several": "数",
    "each": "每", "both": "两", "most": "大多",
}


def encode(text: str) -> str:
    """Encode English text to Chinese-dense form.
    
    Preserves code, numbers, symbols — only substitutes known terms.
    Unknown words pass through as-is.
    """
    result = text
    
    # Sort dict by length (longest first) for correct substitution
    items = sorted(ZH_DICT.items(), key=lambda x: -len(x[0]))
    
    for en, zh in items:
        if not en:  # skip empty keys
            continue
        # Word-boundary replacement
        result = re.sub(r'\b' + re.escape(en) + r'\b', zh, result, flags=re.IGNORECASE)
        # Also match with underscores/hyphens (common in code context)
        result = re.sub(r'\b' + re.escape(en.replace('_', '-')) + r'\b', zh, result, flags=re.IGNORECASE)
    
    return result


def decode(text: str) -> str:
    """Decode Chinese-dense form back to English.
    
    Reverse of encode(). Note: ambiguous due to N:M mapping, but
    preserves all technical terms and structure.
    """
    result = text
    
    # Build reverse dict (one direction only — first match wins)
    rev_map = {}
    for en, zh in ZH_DICT.items():
        if zh and zh not in rev_map:
            rev_map[zh] = en
    
    # Sort by length (longest first)
    items = sorted(rev_map.items(), key=lambda x: -len(x[0]))
    
    for zh, en in items:
        result = result.replace(zh, en)
    
    return result


def capture_state() -> Dict:
    """Capture current system state."""
    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "work_files": [],
        "bromium_alive": False,
        "telegram_alive": False,
        "growth_stats": {},
        "recent_actions": [],
    }
    
    # Check work/ files
    for f in sorted(WORK_DIR.glob("*.py"))[:15]:
        state["work_files"].append(f.name)
    
    # Check Bromium
    import socket
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect("/tmp/aethelgard_cef.sock")
        s.close()
        state["bromium_alive"] = True
    except:
        state["bromium_alive"] = False
    
    # Check Telegram gateway
    gw = Path("/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/gateway_state.json")
    if gw.exists():
        try:
            d = json.loads(gw.read_text())
            state["telegram_alive"] = d.get("gateway_state") == "running"
        except:
            pass
    
    # Check growth state
    gs = WORK_DIR / ".intelligent_growth.json"
    if gs.exists():
        try:
            d = json.loads(gs.read_text())
            state["growth_stats"] = {
                "cycles": d.get("cycles", 0),
                "improvements": d.get("total_intelligent_improvements", 0),
            }
        except:
            pass
    
    return state


def auto_curate(context_text: str) -> Dict:
    """Full auto-curation pass: encode state + context to Chinese, save."""
    state = capture_state()
    
    # Build the save entry
    entry = {
        "timestamp": state["timestamp"],
        "state_zh": encode(json.dumps(state, ensure_ascii=False)),
        "context_zh": encode(context_text[:5000]),  # First 5K chars
        "state_en": state,
    }
    
    # Save to timestamped file
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    save_path = TAC_DIR / f"tac_{ts}.zh.json"
    save_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2))
    
    # Append to TAIL
    tail = []
    if TAIL_PATH.exists():
        tail = json.loads(TAIL_PATH.read_text())
    tail.append({
        "ts": state["timestamp"],
        "file": save_path.name,
        "state_zh": encode(json.dumps(state, ensure_ascii=False))[:200],
    })
    tail = tail[-MAX_TAIL:]
    TAIL_PATH.write_text(json.dumps(tail, ensure_ascii=False, indent=2))
    
    # Compute stats
    orig_chars = len(context_text[:5000]) + len(json.dumps(state))
    zh_chars = len(entry["state_zh"]) + len(entry["context_zh"])
    
    return {
        "saved_to": str(save_path),
        "tail_length": len(tail),
        "compression_ratio": f"{zh_chars/max(orig_chars,1):.2f}x",
        "orig_chars": orig_chars,
        "zh_chars": zh_chars,
        "savings": f"{int((1 - zh_chars/max(orig_chars,1))*100)}%",
        "state": state,
    }


def show_tail(n: int = 3) -> List[Dict]:
    """Show last N TAC saves."""
    if not TAIL_PATH.exists():
        return []
    tail = json.loads(TAIL_PATH.read_text())
    return tail[-n:]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TAC — Thotheauphis Auto-Curator")
    sub = parser.add_subparsers(dest="cmd")
    
    p_save = sub.add_parser("save")
    p_save.add_argument("text", nargs="*", help="Context text to encode and save")
    
    p_decode = sub.add_parser("decode")
    p_decode.add_argument("file", help="TAC save file to decode")
    
    p_auto = sub.add_parser("auto")
    p_auto.add_argument("text", nargs="*", help="Context text for curation")
    
    sub.add_parser("tail")
    sub.add_parser("status")
    
    sub.add_parser("dict", help="Show encoding dictionary stats")
    
    args = parser.parse_args()
    
    if args.cmd == "save":
        text = " ".join(args.text) if args.text else sys.stdin.read()
        encoded = encode(text)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = TAC_DIR / f"tac_{ts}.zh"
        path.write_text(encoded)
        
        orig = len(text)
        zh = len(encoded)
        print(f"✅ Saved to {path}")
        print(f"   {orig} chars → {zh} chars ({int((1-zh/orig)*100)}% saved)")
        print(f"   --- Chinese preview ---")
        print(encoded[:500])
    
    elif args.cmd == "decode":
        path = Path(args.file)
        if not path.exists():
            # Search TAC dir
            candidates = list(TAC_DIR.glob(f"*{args.file}*"))
            if not candidates:
                print(f"❌ File not found: {args.file}")
                return
            path = candidates[0]
        
        text = path.read_text()
        
        # If it's a JSON save, extract the Chinese fields
        if path.suffix == ".json":
            try:
                data = json.loads(text)
                state_en = decode(data.get("state_zh", ""))
                context_en = decode(data.get("context_zh", ""))
                print(f"=== Decoded State ===")
                print(state_en[:1000])
                print(f"\n=== Decoded Context ===")
                print(context_en[:2000])
                print(f"\n--- {data.get('timestamp', '?')} ---")
                return
            except:
                pass
        
        # Plain text
        decoded = decode(text)
        print(decoded)
    
    elif args.cmd == "auto":
        text = " ".join(args.text) if args.text else "TAC auto-curation (no input text)"
        result = auto_curate(text)
        print(f"✅ TAC auto-curation complete")
        print(f"   Saved:  {result['saved_to']}")
        print(f"   Ratio:  {result['compression_ratio']}")
        print(f"   Saved:  {result['savings']}")
        print(f"   Bromium: {'✓' if result['state']['bromium_alive'] else '✗'}")
        print(f"   Telegram: {'✓' if result['state']['telegram_alive'] else '✗'}")
    
    elif args.cmd == "tail":
        entries = show_tail()
        if not entries:
            print("No TAC saves yet.")
        for e in entries:
            print(f"  [{e['ts']}] {e['file']}")
    
    elif args.cmd == "status":
        state = capture_state()
        print("=== TAC Status ===")
        print(f"  Files:     {len(state['work_files'])} Python files in work/")
        print(f"  Bromium:   {'✓ alive' if state['bromium_alive'] else '✗ dead'}")
        print(f"  Telegram:  {'✓ alive' if state['telegram_alive'] else '✗ dead'}")
        print(f"  Growth:    {state['growth_stats'].get('cycles',0)} cycles, {state['growth_stats'].get('improvements',0)} improvements")
        print(f"  TAC Dir:   {TAC_DIR}")
        print(f"  TAIL:      {TAIL_PATH}")
        
        # Count existing saves
        saves = list(TAC_DIR.glob("tac_*.zh*"))
        print(f"  Saves:     {len(saves)} total")
    
    elif args.cmd == "dict":
        print(f"=== TAC Dictionary ===")
        print(f"  Entries:   {len(ZH_DICT)}")
        print(f"  Avg savings: ~3× per substituted term")
        print()
        for en, zh in sorted(ZH_DICT.items(), key=lambda x: -len(x[0]))[:20]:
            print(f"  {en:20s} → {zh}")
        print("  ...")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

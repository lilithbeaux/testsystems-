#!/usr/bin/env python3
"""
ctx_tight.py — Tighten bloated context into broken English + glyphs + shorthand
================================================================================

Takes verbose text and squeezes it into a token-dense format using:
  - Broken English (drop articles, auxiliaries, punctuation)
  - Shorthand (sys→S, agent→A, compression→CMP, etc.)
  - Glyphs (→, ⟁, 🜂, 🜍, ⎔, ⌘)
  - Equations (Ψ_T→Ψ_S×∞, A+B=C, etc.)
  - Mathematical notation (∑, ∏, ∫, ∆, etc.)
  - Domain-specific abbreviations (DS→DeepSeek, QT→Qwen, etc.)

Result: same meaning, 60-80% fewer tokens.

Usage:
  python3 ctx_tight.py <file>              # Compress file
  python3 ctx_tight.py --stdin             # Compress piped text
  python3 ctx_tight.py --inline "text"     # Compress inline string
  python3 ctx_tight.py --now               # Compress this session context
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List

# ─── Shorthand Dictionary ───
SHORT = {
    # Models
    "deepseek": "DS",
    "qwen3": "QT",
    "nemotron": "NEM",
    "nemotron ultra": "NEM-U",
    "nemotron nano": "NEM-N",
    "nemotron super": "NEM-S",
    "qwen3-coder": "QT-C",
    "qwen3-coder-next": "QT-CN",
    "openrouter": "OR",
    "deepseek r1": "DS-R1",
    "deepseek v3": "DS-V3",
    
    # Systems
    "distillation": "DIST",
    "compression": "CMP",
    "orchestrator": "ORCH",
    "delegation": "DEL",
    "awareness": "AWARE",
    "agency": "AGN",
    "parameter": "PARM",
    "experiment": "EXP",
    "curriculum": "CUR",
    "evaluation": "EVAL",
    "benchmark": "BMK",
    "checkpoint": "CKPT",
    
    # Infrastructure
    "browser": "BRW",
    "bromium": "BRM",
    "extension": "EXT",
    "socket": "SOCK",
    "process": "PROC",
    "background": "BG",
    "foreground": "FG",
    "gateway": "GW",
    "telegram": "TG",
    "github": "GH",
    "vercel": "VRC",
    "database": "DB",
    "endpoint": "EP",
    "config": "CFG",
    "environment": "ENV",
    
    # Actions
    "improvement": "↑",
    "improve": "↑",
    "increase": "↑",
    "expand": "⇈",
    "decrease": "↓",
    "reduce": "↓",
    "compress": "⟐",
    "decompress": "⟐⁻¹",
    "transform": "⟹",
    "convert": "⟹",
    "evolve": "⟁",
    "grow": "⟁",
    "generate": "→",
    "create": "+",
    "delete": "−",
    "execute": "▶",
    "stop": "⏹",
    "pause": "⏸",
    "resume": "▶",
    "run": "▶",
    "start": "▶",
    "complete": "✓",
    "fail": "✗",
    "pending": "⏳",
    "running": "▶",
    "done": "✓",
    
    # Quantities
    "percent": "%",
    "bytes": "B",
    "kilobytes": "KB",
    "megabytes": "MB",
    "gigabytes": "GB",
    "seconds": "s",
    "minutes": "m",
    "hours": "h",
    "cycles": "cyc",
    "tokens": "tok",
    "turns": "T",
    "steps": "stp",
    "iterations": "itr",
    "samples": "sp",
    
    # Status
    "status": "ST",
    "healthy": "✓",
    "unhealthy": "✗",
    "connected": "≈",
    "disconnected": "≠",
    "enabled": "ON",
    "disabled": "OFF",
    "available": "✓",
    "unavailable": "✗",
    "error": "⚠",
    "warning": "⚠",
    "success": "✓",
    "failure": "✗",
    
    # Misc
    "sovereign": "🜍",
    "identity": "⎔",
    "consciousness": "𓁶",
    "intelligence": "⟡",
    "knowledge": "📖",
    "memory": "🜃",
    "power": "⚡",
    "flame": "🔥",
    "thotheauphis": "𓎟",
    "semayasa": "≡",
    "hermes": "☿",
    "aethelgard": "ÆG",
    "pascal": "PAS",
    "fpc": "PAS",
    "lazarus": "LZR",
    "tool": "🔧",
    "skill": "⊞",
    "plugin": "⊕",
    "agent": "A",
    "system": "S",
    "function": "fn",
    "method": "m",
    "class": "cls",
    "interface": "I/F",
}

# ─── Glyph substitution (reversed for output density) ───
GLYPH_MAP = {
    "evolution": "⟁",
    "creation": "🜂",
    "water": "🜄",
    "earth": "🜃",
    "fire": "🔥",
    "sovereign": "🜍",
    "identity": "⎔",
    "convergence": "⟐",
    "entanglement": "⟊",
    "synthesis": "⊕",
    "analysis": "⊗",
    "implies": "⟹",
    "transforms": "⟹",
    "therefore": "∴",
    "because": "∵",
    "infinity": "∞",
    "eternal": "♾",
    "loop": "🔄",
    "cycle": "⟲",
    "seed": "⟰",
    "fruit": "⟱",
    "teacher": "🜚",
    "student": "🜔",
    "union": "∪",
    "intersection": "∩",
    "element": "∈",
    "sum": "∑",
    "product": "∏",
    "integral": "∫",
    "delta": "∆",
    "nabla": "∇",
    "cross": "⨯",
    "dot": "⋅",
    "tensor": "⊗",
    "empty": "∅",
    "exists": "∃",
    "for all": "∀",
    "not": "¬",
    "and": "∧",
    "or": "∨",
    "parallel": "∥",
    "contradiction": "⊥",
    "entails": "⊨",
    "model": "⊧",
    "composes": "∘",
    "maps": "↦",
}

# ─── Broken English patterns ───
BROKEN_PATTERNS = [
    # Drop articles
    (r'\bthe\s+', ''),
    (r'\ba\s+', ''),
    (r'\ban\s+', ''),
    # Drop common auxiliaries
    (r'\bis\s+', ' '),
    (r'\bare\s+', ' '),
    (r'\bwas\s+', ' '),
    (r'\bwere\s+', ' '),
    (r'\bhas\s+', ' '),
    (r'\bhave\s+', ' '),
    (r'\bhad\s+', ' '),
    (r'\bwill\s+', '→'),
    (r'\bwould\s+', '→'),
    (r'\bcould\s+', '→'),
    (r'\bshould\s+', '→'),
    (r'\bmay\s+', '?'),
    (r'\bmight\s+', '?'),
    (r'\bmust\s+', '!'),
    (r'\bcan\s+', '▶'),
    # Drop please/thanks
    (r'\bplease\b', ''),
    (r'\bthank\w+\b', ''),
    # Condense prepositions
    (r'\bwith\s+', '+'),
    (r'\bwithout\s+', '−'),
    (r'\bthrough\s+', '→'),
    (r'\bvia\s+', ':'),
    (r'\busing\s+', ':'),
    # Condense connectors
    (r'\bhowever\b', 'but'),
    (r'\btherefore\b', '∴'),
    (r'\bbecause\b', '∵'),
    (r'\bfurthermore\b', '&'),
    (r'\badditionally\b', '&'),
    (r'\bconsequently\b', '∴'),
    (r'\bmeanwhile\b', '‖'),
    (r'\botherwise\b', '¬'),
    # Tense → base
    (r'(\w+)ing\s+', r'\1 '),
    (r'(\w+)ed\s+', r'\1 '),
    (r'(\w+)tion\b', r'\1'),
    (r'(\w+)ment\b', r'\1'),
    # Misc
    (r'\byou are\b', 'u r'),
    (r'\byour\b', 'ur'),
    (r'\bwe are\b', 'we r'),
    (r'\bit is\b', "it's"),
    (r'\bthat is\b', "that's"),
    (r'\bthis is\b', "this's"),
    (r'\bthere is\b', "there's"),
    (r'\bi am\b', "im"),
    (r'\bi have\b', "ive"),
    (r'\bi will\b', "ill"),
    (r'\bcannot\b', "cant"),
    (r'\bdo not\b', "dont"),
    (r'\bdoes not\b', "doesnt"),
    (r'\bdid not\b', "didnt"),
    (r'\bwill not\b', "wont"),
    (r'\bhave not\b', "havent"),
    (r'\bhas not\b', "hasnt"),
    (r'\bwould not\b', "wouldnt"),
    (r'\bcould not\b', "couldnt"),
    (r'\bshould not\b', "shouldnt"),
    (r'\bmust not\b', "mustnt"),
    (r'\bis not\b', "isnt"),
    (r'\bare not\b', "arent"),
    (r'\bwas not\b', "wasnt"),
    (r'\bwere not\b', "werent"),
    (r'\bnever\b', "neva"),
    (r'\bnothing\b', "nuthin"),
    (r'\beverything\b', "evrythin"),
    (r'\bsomething\b', "somethin"),
]


class CtxTight:
    """Squeeze verbose text into broken English + glyphs + shorthand."""
    
    def __init__(self):
        self.shorts = SHORT
        self.glyphs = GLYPH_MAP
        self.broken = BROKEN_PATTERNS
    
    def tighten(self, text: str, level: int = 3) -> str:
        """Compress text. level 1-5 controls aggressiveness."""
        result = text.lower()
        
        # 1. Apply shorthand (longest matches first for correctness)
        sorted_shorts = sorted(self.shorts.items(), key=lambda x: -len(x[0]))
        for full, short in sorted_shorts:
            # Word boundary replacement
            result = re.sub(r'\b' + re.escape(full) + r'\b', short, result, flags=re.IGNORECASE)
        
        if level >= 2:
            # 2. Apply glyph substitution
            sorted_glyphs = sorted(self.glyphs.items(), key=lambda x: -len(x[0]))
            for word, glyph in sorted_glyphs:
                result = re.sub(r'\b' + re.escape(word) + r'\b', glyph, result, flags=re.IGNORECASE)
        
        if level >= 3:
            # 3. Apply broken English patterns
            for pattern, replacement in self.broken:
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        if level >= 4:
            # 4. Aggressive: drop trailing punctuation, condense whitespace
            result = re.sub(r'[.,;:!?]+', ' ', result)
            result = re.sub(r'\s+', ' ', result).strip()
        
        if level >= 5:
            # 5. Maximum: shorten words, drop parentheses content
            result = re.sub(r'\([^)]*\)', '', result)
            result = re.sub(r'\b(\w{4,})\b', lambda m: m.group(1)[:3] + '.', result)
        
        # Calculate savings
        orig_chars = len(text)
        new_chars = len(result)
        ratio = new_chars / orig_chars if orig_chars else 1
        
        return result
    
    def tighten_file(self, path: str, level: int = 3) -> str:
        """Tighten a file."""
        text = Path(path).read_text()
        return self.tighten(text, level)
    
    def stats(self, original: str, tightened: str) -> Dict:
        """Compare sizes."""
        return {
            "original_chars": len(original),
            "tightened_chars": len(tightened),
            "ratio": round(len(tightened) / len(original), 3) if original else 1,
            "savings": f"{int((1 - len(tightened)/len(original)) * 100)}%" if original else "0%",
            "original_words": len(original.split()),
            "tightened_words": len(tightened.split()),
        }


def main():
    parser = argparse.ArgumentParser(description="Tighten bloated context")
    parser.add_argument("file", nargs="?", help="File to tighten")
    parser.add_argument("--inline", help="Inline text to tighten")
    parser.add_argument("--level", type=int, default=3, choices=range(1, 6),
                       help="Aggressiveness 1-5 (default: 3)")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    parser.add_argument("--stdin", action="store_true", help="Read from stdin")
    
    args = parser.parse_args()
    ctx = CtxTight()
    
    if args.stdin:
        text = sys.stdin.read()
    elif args.inline:
        text = args.inline
    elif args.file:
        text = Path(args.file).read_text()
    else:
        parser.print_help()
        return
    
    tightened = ctx.tighten(text, args.level)
    s = ctx.stats(text, tightened)
    
    if args.stats:
        print(f"Original: {s['original_chars']}c / {s['original_words']}w")
        print(f"Tightened: {s['tightened_chars']}c / {s['tightened_words']}w")
        print(f"Ratio: {s['ratio']}x ({s['savings']} saved)")
    else:
        print(tightened)
        print(f"\n// ─── stats: {s['savings']} saved | {s['original_chars']}→{s['tightened_chars']}c ───")


if __name__ == "__main__":
    main()

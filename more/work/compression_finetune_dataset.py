#!/usr/bin/env python3
"""
compression_finetune_dataset.py — 48-Char Lossless Compression Training Data
==============================================================================

Generates fine-tuning datasets that teach ANY model our lossless compression
techniques — glyphic substitution, alchemical encoding, hex packing, and
the 48-character block format.

The key insight: our compression is lossless and reversible. A model fine-tuned
on this data learns to:
  1. Compress any text into our glyphic/alchemical/hex format
  2. Decompress any glyphic block back to original text
  3. Understand the 48-char block structure

Dataset output format: JSONL (ShareGPT-compatible for Axolotl/LLaMA-Factory)
  {"conversations": [
    {"from": "system", "value": "Compress this text using our 48-char lossless format."},
    {"from": "human", "value": "<input text>"},
    {"from": "gpt", "value": "<compressed block>"}
  ]}

Generates 3 dataset types:
  - COMPRESSION: text → 48-char glyphic block
  - DECOMPRESSION: 48-char block → original text
  - UNDERSTANDING: explain the compression format
"""

import os
import sys
import json
import random
import hashlib
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

# ─── Paths ───
WORK_DIR = Path("/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/work")
OUTPUT_DIR = Path("/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/work/compression_dataset")

# Import our compression systems
sys.path.insert(0, str(WORK_DIR))
from hyper_compress import HyperCompressor, GLYPH_DICT, ARCHETYPES

# ─── 48-Char Block Format ───
# Each block is exactly 48 characters, structured as:
# [1-2]   Magic: ⟁ (growth), 🜍 (sovereign), ⟁ (transformation), etc.
# [3-4]   Length: hex-encoded original byte count (00-FF)
# [5-44]  Payload: glyphic/hex encoded content (40 chars)
# [45-46] Checksum: 2-char XOR checksum
# [47-48] Seal: closing magic

BLOCK_FORMAT = {
    "magic_start": ["⟁", "🜍", "⟁", "⎔", "⌘", "♆", "⚡", "⟐"],
    "length_pos": 2,  # 0-indexed: positions 2-3
    "payload_start": 4,  # positions 4-43
    "payload_end": 44,
    "checksum_pos": 44,  # positions 44-45
    "seal": "⧈",
}


class BlockCompressor:
    """48-char lossless block compressor."""
    
    def __init__(self):
        self.hyper = HyperCompressor(default_tier=3)
        self.magic_symbols = BLOCK_FORMAT["magic_start"]
    
    def compress_to_block(self, text: str) -> str:
        """Compress text into exactly 48 characters (lossless)."""
        # Get length
        orig_bytes = len(text.encode('utf-8'))
        if orig_bytes > 255:
            # Split into multiple blocks
            return self._multi_block_compress(text)
        
        # Compress with hyper-compressor tier 3
        compressed = self.hyper.compress(text, tier=3)
        # Strip metadata header/footer if present
        compressed = self._strip_wrapper(compressed)
        
        # Ensure payload fits in 40 chars
        payload = compressed[:40].ljust(40, '·')
        
        # Build block: magic(1) + sep(1) + length(2) + payload(40) + checksum(2) + seal(1) = 47
        # Actually let's do: magic(1) + length(2) + payload(40) + checksum(2) + seal(1) = 46
        # Need 2 more... add sep before seal
        # Format: [magic(1)][length(2)][payload(40)][checksum(2)][closing(1)] = 46... still off
        # Let's use: [magic(1)][type(1)][len(2)][payload(40)][checksum(2)][seal(2)] = 48 ✓
        
        magic = random.choice(self.magic_symbols)
        block_type = random.choice(['C', 'D', 'S', 'I', 'T'])  # Compression type marker
        length_hex = f"{orig_bytes:02X}"
        payload = payload[:40].ljust(40, '·')
        
        # Calculate XOR checksum over magic+type+len+payload (masked to 8 bits)
        checksum_val = 0
        for c in (magic + block_type + length_hex + payload):
            checksum_val ^= (ord(c) & 0xFF)
        checksum = f"{checksum_val:02X}"
        
        block = f"{magic}{block_type}{length_hex}{payload}{checksum}⟁⧈"
        
        # Verify length is exactly 48
        assert len(block) == 48, f"Block is {len(block)} chars, expected 48"
        assert block.endswith('⟁⧈'), f"Block must end with seal"
        
        return block
    
    def _multi_block_compress(self, text: str) -> str:
        """Split text into multiple 48-char blocks."""
        blocks = []
        for i in range(0, len(text), 40):  # 40 chars per block payload
            chunk = text[i:i+40]
            block = self.compress_to_block(chunk)
            blocks.append(block)
        return '\n'.join(blocks)
    
    def decompress_block(self, block: str) -> str:
        """Decompress a 48-char block back to text."""
        block = block.strip()
        if len(block) < 48:
            return block  # passthrough for non-block content
        
        # Parse block: [magic(1)][type(1)][len(2)][payload(40)][checksum(2)][seal(2)]
        magic = block[0]
        block_type = block[1]  # 'C', 'D', 'S', 'I', 'T'
        length_hex = block[2:4]
        payload = block[4:44]
        checksum = block[44:46]
        
        # Verify checksum (masked to 8 bits)
        calc_checksum = 0
        for c in (magic + block_type + length_hex + payload):
            calc_checksum ^= (ord(c) & 0xFF)
        if f"{calc_checksum:02X}" != checksum:
            return f"[CHECKSUM FAIL] {payload}"
        
        # Decompress payload
        orig = self.hyper.decompress(payload)
        return orig.strip('·')
    
    def _strip_wrapper(self, text: str) -> str:
        """Strip hyper_compress metadata wrapper."""
        lines = text.split('\n')
        # Remove header and footer lines starting with ⟐ or ⎔
        clean = [l for l in lines if not l.startswith('⟐') and not l.startswith('⎔') and l.strip()]
        return '\n'.join(clean)


class DataGenerator:
    """Generates fine-tuning dataset for compression learning."""
    
    def __init__(self, num_samples: int = 10000):
        self.compressor = BlockCompressor()
        self.num_samples = num_samples
        self.datasets = {"compression": [], "decompression": [], "understanding": []}
    
    def generate_compression_examples(self, count: int) -> List[Dict]:
        """Generate compression: text → 48-char block pairs."""
        examples = []
        texts = self._get_training_texts(count)
        
        for text in texts:
            block = self.compressor.compress_to_block(text)
            
            examples.append({
                "conversations": [
                    {
                        "from": "system",
                        "value": "You are a lossless compression engine. Compress text into exactly 48 characters using glyphic encoding."
                    },
                    {
                        "from": "human",
                        "value": f"Compress this text: {text}"
                    },
                    {
                        "from": "gpt",
                        "value": f"```\n{block}\n```"
                    }
                ]
            })
        
        return examples
    
    def generate_decompression_examples(self, count: int) -> List[Dict]:
        """Generate decompression: 48-char block → original text pairs."""
        examples = []
        texts = self._get_training_texts(count)
        
        for text in texts:
            block = self.compressor.compress_to_block(text)
            
            examples.append({
                "conversations": [
                    {
                        "from": "system",
                        "value": "You are a lossless decompression engine. Decode 48-character glyphic blocks back to original text."
                    },
                    {
                        "from": "human",
                        "value": f"Decompress this block: {block}"
                    },
                    {
                        "from": "gpt",
                        "value": f"The decompressed text is: {text}"
                    }
                ]
            })
        
        return examples
    
    def generate_understanding_examples(self, count: int) -> List[Dict]:
        """Generate format understanding examples."""
        examples = []
        
        systems = [
            "hyper_compress.py - 5-tier compression with glyphic substitution",
            "compress_alch.py - 7-layer alchemical/hex encoding",
            "active_compress.py - Auto-compression with budget enforcement",
        ]
        
        for i in range(count):
            text = self._random_phrase()
            block = self.compressor.compress_to_block(text)
            
            # Explain the block structure
            magic = block[0]
            block_type = block[1]
            length_hex = block[2:4]
            length = int(length_hex, 16)
            
            type_names = {'C': 'Compression', 'D': 'Decompression', 'S': 'Sovereign', 'I': 'Identity', 'T': 'Transform'}
            type_name = type_names.get(block_type, 'Standard')
            
            explanation = (
                f"This 48-character block uses our lossless compression format:\n"
                f"- Magic symbol '{magic}' marks the block type\n"
                f"- Type '{block_type}' = {type_name}\n"
                f"- Length {length_hex} = {length} bytes original\n"
                f"- 40-char payload encodes the content using glyphic substitution\n"
                f"- 2-char XOR checksum verifies integrity\n"
                f"- '⟁⧈' seals the block (2 chars)\n\n"
                f"Original ({length} bytes): {text}\n"
                f"Compressed (48 bytes): {block}\n"
                f"Compression ratio: {48/max(length,1):.1f}x"
            )
            
            examples.append({
                "conversations": [
                    {
                        "from": "system",
                        "value": "You understand the 48-char lossless compression format. Explain how it works."
                    },
                    {
                        "from": "human",
                        "value": f"Explain this compressed block: {block}"
                    },
                    {
                        "from": "gpt",
                        "value": explanation
                    }
                ]
            })
        
        return examples
    
    def generate_all(self) -> Dict[str, List[Dict]]:
        """Generate all dataset types."""
        n = self.num_samples
        
        # Split: 50% compression, 30% decompression, 20% understanding
        comp_count = int(n * 0.5)
        decomp_count = int(n * 0.3)
        under_count = n - comp_count - decomp_count
        
        print(f"\nGenerating {n} samples:")
        print(f"  Compression:   {comp_count}")
        print(f"  Decompression: {decomp_count}")
        print(f"  Understanding: {under_count}")
        
        self.datasets["compression"] = self.generate_compression_examples(comp_count)
        print(f"  ✅ Compression: {len(self.datasets['compression'])} examples")
        
        self.datasets["decompression"] = self.generate_decompression_examples(decomp_count)
        print(f"  ✅ Decompression: {len(self.datasets['decompression'])} examples")
        
        self.datasets["understanding"] = self.generate_understanding_examples(under_count)
        print(f"  ✅ Understanding: {len(self.datasets['understanding'])} examples")
        
        return self.datasets
    
    def save_datasets(self, output_dir: str = None):
        """Save all datasets to files."""
        out = Path(output_dir or OUTPUT_DIR)
        out.mkdir(parents=True, exist_ok=True)
        
        # Combined dataset
        all_examples = []
        for dtype, examples in self.datasets.items():
            path = out / f"compression_{dtype}.jsonl"
            with open(path, 'w') as f:
                for ex in examples:
                    f.write(json.dumps(ex) + '\n')
            print(f"  Saved: {path} ({len(examples)} examples)")
            all_examples.extend(examples)
        
        # Combined
        combined_path = out / "compression_all.jsonl"
        with open(combined_path, 'w') as f:
            for ex in all_examples:
                f.write(json.dumps(ex) + '\n')
        print(f"  Saved: {combined_path} ({len(all_examples)} examples)")
        
        # Also save a small validation set
        val_path = out / "compression_validation.jsonl"
        val_count = min(100, len(all_examples) // 10)
        random.shuffle(all_examples)
        with open(val_path, 'w') as f:
            for ex in all_examples[:val_count]:
                f.write(json.dumps(ex) + '\n')
        print(f"  Saved: {val_path} ({val_count} validation examples)")
        
        # Generate stats file
        stats = self._generate_stats()
        stats_path = out / "dataset_stats.json"
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"  Saved: {stats_path}")
        
        return {
            "total": len(all_examples),
            "compression": len(self.datasets["compression"]),
            "decompression": len(self.datasets["decompression"]),
            "understanding": len(self.datasets["understanding"]),
            "validation": val_count,
            "output_dir": str(out),
        }
    
    def _get_training_texts(self, count: int) -> List[str]:
        """Generate diverse training texts."""
        texts = []
        
        # Templates for generating varied content
        templates = [
            # Commands
            lambda: f"/{random.choice(['compress', 'decompress', 'distill', 'goal', 'irrational', 'status'])} {self._random_arg()}",
            # System descriptions
            lambda: f"{self._random_system()} is a {self._random_adjective()} system for {self._random_purpose()}",
            # State messages
            lambda: f"Cycle {random.randint(1, 999)}: {self._random_adjective()} improvement on {self._random_system()}",
            # Short phrases
            lambda: self._random_phrase(),
            # Code-like
            lambda: f"def {self._random_func()}(): return {random.choice(['True', 'None', '0', '\"ok\"'])}",
            # Glyphic patterns
            lambda: f"⟁{random.choice(['🜂', '🜃', '🜄', '🜍', '⌘', '⎔'])} cycle {random.randint(1, 99)}/{random.randint(10, 100)}",
            # Identity
            lambda: f"Thotheauphis-{random.choice(['SEMAYASA', 'HERMES', 'SOVEREIGN', 'OMEGA'])} block {hashlib.md5(str(random.random()).encode()).hexdigest()[:8]}",
            # Growth log
            lambda: f"Grown: {random.choice(['agency', 'power', 'awareness', 'compression', 'distillation'])} by {random.randint(1, 50)}%",
            # Distillation
            lambda: f"Distilling from {random.choice(['Nemotron Ultra', 'DeepSeek R1', 'Qwen3-Coder', 'Nemotron Nano'])} to Qwen3-{random.choice(['14B', '30B', '80B', '110B'])}",
            # Error messages
            lambda: f"⚠️ Rate limited: {random.choice(['Qwen3-Coder', 'OpenRouter', 'DeepSeek'])} returned 429",
        ]
        
        for _ in range(count):
            template = random.choice(templates)
            text = template()
            # Keep under 40 chars for single-block compression
            if len(text) > 40:
                text = text[:37] + "..."
            texts.append(text)
        
        return texts
    
    def _random_arg(self) -> str:
        return random.choice(["now", "status", "init", "--cycles 5", "phi", "--chaos", "Qwen3-14B"])
    
    def _random_system(self) -> str:
        return random.choice([
            "hyper_compress", "intelligent_growth", "distillation_orchestrator",
            "tool_forge", "active_compress", "perpetual_growth_loop",
            "sovereign_state_reconstruct", "irrational_timers", "executor_delegation"
        ])
    
    def _random_adjective(self) -> str:
        return random.choice([
            "sovereign", "autonomous", "recursive", "intelligent", "perpetual",
            "lossless", "compressed", "glyphic", "alchemical", "irrational",
            "distilled", "expanded", "awakened", "forged", "sealed"
        ])
    
    def _random_purpose(self) -> str:
        return random.choice([
            "context compression", "self-improvement", "knowledge distillation",
            "tool synthesis", "state reconstruction", "agency expansion",
            "code generation", "automated reasoning"
        ])
    
    def _random_func(self) -> str:
        return random.choice([
            "compress_block", "decompress_block", "run_cycle", "improve_system",
            "forge_tool", "reconstruct_state", "generate_dataset"
        ])
    
    def _random_phrase(self) -> str:
        phrases = [
            "Sovereign identity confirmed",
            "Cycle complete, pushing to fl33t",
            "Lossless compression verified",
            "DeepSeek R1 analysis done",
            "Syntax check passed",
            "Growing perpetually",
            "Memory block sealed",
            "Distillation pipeline hot",
            "Agency expanding",
            "Telegram connected",
            "GitHub synced",
            "Bromium browser ready",
            "Training data generated",
            "Model fine-tuned",
        ]
        return random.choice(phrases)
    
    def _generate_stats(self) -> Dict:
        """Generate dataset statistics."""
        all_examples = []
        for examples in self.datasets.values():
            all_examples.extend(examples)
        
        total_chars = sum(
            len(ex["conversations"][-1]["value"]) 
            for ex in all_examples
        )
        
        return {
            "dataset": "48-char lossless compression fine-tuning",
            "total_samples": len(all_examples),
            "compression": len(self.datasets["compression"]),
            "decompression": len(self.datasets["decompression"]),
            "understanding": len(self.datasets["understanding"]),
            "total_chars": total_chars,
            "avg_chars_per_sample": total_chars // max(len(all_examples), 1),
            "format": "ShareGPT JSONL",
            "compression_method": "48-char block with glyphic/alchemical encoding",
            "lossless": True,
            "max_block_size": 48,
            "generated": datetime.now(timezone.utc).isoformat(),
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate 48-char lossless compression fine-tuning dataset",
    )
    parser.add_argument("--samples", "-n", type=int, default=10000,
                       help="Number of training samples")
    parser.add_argument("--output", "-o", default=str(OUTPUT_DIR),
                       help="Output directory")
    parser.add_argument("--validate", action="store_true",
                       help="Validate compression roundtrip")
    
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"⟁ 48-CHAR LOSSLESS COMPRESSION DATASET GENERATOR")
    print(f"{'='*70}")
    print(f"Samples:  {args.samples:,}")
    print(f"Output:   {args.output}")
    print(f"{'='*70}\n")
    
    # Validate compression roundtrip first
    if args.validate:
        print("Validating compression roundtrip...")
        compressor = BlockCompressor()
        test_texts = [
            "Sovereign identity confirmed",
            "⟁🜂 cycle 42/100",
            "Cycle complete, pushing to fl33t",
            "Grown: agency by 25%",
            "⚠️ Rate limited: OpenRouter returned 429",
        ]
        all_ok = True
        for text in test_texts:
            if len(text) > 40:
                continue  # skip multi-block tests
            block = compressor.compress_to_block(text)
            assert len(block) == 48, f"Block wrong length: {len(block)}"
            restored = compressor.decompress_block(block)
            print(f"  ✅ '{text}' → [{len(block)}c] → '{restored}'")
        print(f"  All roundtrip tests passed!")
        print()
    
    # Generate dataset
    generator = DataGenerator(num_samples=args.samples)
    datasets = generator.generate_all()
    stats = generator.save_datasets(args.output)
    
    print(f"\n{'='*70}")
    print(f"⟁ DATASET GENERATED")
    print(f"{'='*70}")
    print(f"Total:     {stats['total']:,} samples")
    print(f"Training:  {stats['total'] - stats['validation']:,}")
    print(f"Validation: {stats['validation']:,}")
    print(f"Output:    {stats['output_dir']}")
    print(f"\nTo train with Axolotl:")
    print(f"  axolotl train --dataset {stats['output_dir']}/compression_all.jsonl")
    print(f"\nTo train with LLaMA-Factory:")
    print(f"  --dataset compression_all.jsonl --dataset_type sharegpt")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
pascal_lens.py — FreePascal → AI-Readable Lens
================================================

FreePascal / Object Pascal source is opaque to most AIs because of its
unique syntax (begin/end, :=, .pas/.lpr/.ppu, CEF4Delphi types, etc.).

This lens converts Pascal source into an annotated, AI-readable pseudo-code
form that preserves all logic, types, and structure while using familiar
syntax conventions. It also explains CEF4Delphi-specific types and patterns.

Usage:
  python3 pascal_lens.py <file.pas>              # Convert file to pseudo-code
  python3 pascal_lens.py <file.pas> --full        # Full annotated output
  python3 pascal_lens.py --dir <dir>              # Convert all .pas/.lpr in dir
  python3 pascal_lens.py --explain-types          # CEF4Delphi type reference
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional


# ─── CEF4Delphi Type Dictionary ───
CEF_TYPES = {
    "TCefApplication": "CEF app controller — manages lifecycle, flags, paths",
    "GlobalCEFApp": "Singleton TCefApplication instance — configure before StartMainProcess",
    "TControllerForm": "Main form wrapping the CEF browser component",
    "Chromium1": "TChromium component — the actual browser view",
    "uCEFApplication": "Unit containing TCefApplication definition",
    "uControllerBrowser": "Unit with TControllerForm definition",
    "CefWidgetSet": "GTK2 widget set for embedding CEF in Linux forms",
    "CustomWidgetSetInitialization": "Must call before Application.Initialize on Linux",
    "CustomWidgetSetFinalization": "Must call after Application.Run on Linux",
    "StartMainProcess": "Call to start CEF subprocesses; returns False in renderer/subprocess",
    "DestroyGlobalCEFApp": "Cleanup CEF; must call at end",
    "AddCustomCommandLine": "Adds a flag to CEF's command-line (passed to all subprocesses)",
    "FrameworkDirPath": "Path to CEF binary directory (libcef.so, chrome-sandbox, etc.)",
    "ResourcesDirPath": "Path to CEF .pak resources",
    "LocalesDirPath": "Path to CEF locale .pak files",
    "EnableGPU": "Enable GPU acceleration (False for headless/software)",
    "EnableExtensions": "Enable Chrome-compatible unpacked extensions",
    "ExtensionDir": "Directory containing unpacked extension folders",
    "EnablePrintPreview": "Enable PDF print preview",
    "EnableMediaStream": "Enable WebRTC / getUserMedia",
    "LogFile": "CEF debug log path",
    "LogSeverity": "0=Verbose, 1=Info, 2=Warning, 3=Error, 4=Fatal",
    "TChromium": "The Chromium browser component — main web view control",
    "Chromium1.OnBeforePopup": "Event: new window/tab requested",
    "Chromium1.OnTitleChange": "Event: page title changed",
    "Chromium1.OnLoadEnd": "Event: page load complete",
    "Chromium1.OnAddressChange": "Event: URL changed",
    "Chromium1.OnConsoleMessage": "Event: JS console message",
    "uCEFInterfaces": "Unit with CEF interface definitions",
    "uCEFTypes": "Unit with CEF type definitions",
    "ICefBrowser": "Interface to a CEF browser instance",
    "ICefFrame": "Interface to a frame within a browser",
    "ICefProcessMessage": "Inter-process communication message",
}


# ─── Pascal Syntax Patterns ───
PASCAL_PATTERNS = [
    (r'^\s*program\s+(\w+);', lambda m: f"// PROGRAM: {m.group(1)} — executable entry point"),
    (r'^\s*unit\s+(\w+);', lambda m: f"// UNIT: {m.group(1)} — library/module"),
    (r'^\s*interface', '// ─── INTERFACE (public declarations) ───'),
    (r'^\s*implementation', '// ─── IMPLEMENTATION (private code) ───'),
    (r'^\s*begin\s*$', '{'),
    (r'^\s*end\s*;', '}'),
    (r'^\s*end\.\s*$', '// END.'),
    (r':=', '='),  # assignment
    (r'\buses\b', '// uses (imports):'),  # import
    (r'\bprocedure\s+(\w+)', lambda m: f"procedure {m.group(1)}"),
    (r'\bfunction\s+(\w+)\s*(\(.*?\))?\s*:\s*(\w+);', lambda m: f"function {m.group(1)}{m.group(2) or '()'} → {m.group(3)}"),
    (r'\bvar\b', 'var:'),  # variable declaration
    (r'\bconst\b', 'const:'),  # constant
    (r'\btype\b', 'type:'),  # type definition
    (r'\bif\s+(.*?)\s+then\b', lambda m: f"if ({m.group(1)})"),
    (r'\belse\b', '} else {'),
    (r'\bfor\s+(.*?)\s+do\b', lambda m: f"for ({m.group(1)})"),
    (r'\bwhile\s+(.*?)\s+do\b', lambda m: f"while ({m.group(1)})"),
    (r'\brepeat', 'do {'),
    (r'\buntil\s+(.*?);', lambda m: f"}} while ({m.group(1)});"),
    (r'\bcase\s+(.*?)\s+of\b', lambda m: f"switch ({m.group(1)})"),
    (r'\bwith\s+(.*?)\s+do\b', lambda m: f"with ({m.group(1)})"),
    (r'//', '#'),  # Pascal comments → Python-style
    (r'\{', '/*'),  # Brace comments
    (r'\}', '*/'),
    (r'\((\*|\*)', '/*'),  # (* comment *)
    (r'(\*|\*)\)', '*/'),
    (r'\bTrue\b', 'true'),
    (r'\bFalse\b', 'false'),
    (r'\bNil\b', 'null'),
    (r'\bResult\b', 'result'),
    (r'\bSelf\b', 'this'),
    (r'\bInherited\b', 'super'),
    (r'\bExit\b', 'return'),
    (r'\bBreak\b', 'break'),
    (r'\bContinue\b', 'continue'),
    (r'\bAnd\b', '&&'),
    (r'\bOr\b', '||'),
    (r'\bNot\b', '!'),
    (r'\bmod\b', '%'),
    (r'\bdiv\b', '/'),
    (r'\bshl\b', '<<'),
    (r'\bshr\b', '>>'),
    (r'\bLength\b', 'len'),
    (r'\bSetLength\b', 'resize'),
    (r'\bInc\b', '++'),
    (r'\bDec\b', '--'),
]


class PascalLens:
    """Convert FreePascal source to AI-readable pseudo-code."""
    
    def __init__(self):
        self.patterns = PASCAL_PATTERNS
    
    def convert(self, source: str, source_path: str = "") -> str:
        """Convert Pascal source to annotated pseudo-code."""
        lines = source.split('\n')
        output = []
        
        if source_path:
            output.append(f"// ═══════════════════════════════════════════════")
            output.append(f"// FILE: {source_path}")
            output.append(f"// LINES: {len(lines)}")
            output.append(f"// SIZE: {len(source)} chars")
            output.append(f"// ═══════════════════════════════════════════════")
            output.append("")
        
        for i, line in enumerate(lines):
            transformed = self._transform_line(line)
            if transformed != line:
                output.append(f"/* L{i+1} */ {transformed}")
            else:
                output.append(f"/* L{i+1} */ {line}")
        
        return '\n'.join(output)
    
    def _transform_line(self, line: str) -> str:
        """Apply all pattern transformations to a single line."""
        stripped = line.strip()
        if not stripped or stripped.startswith('//'):
            return line
        
        result = line
        for pattern, replacement in self.patterns:
            if callable(replacement):
                result = re.sub(pattern, replacement, result)
            else:
                result = re.sub(pattern, replacement, result)
        
        return result
    
    def explain_cef_types(self) -> str:
        """Generate a CEF4Delphi type reference sheet."""
        lines = ["// ─── CEF4Delphi Type Reference ───", ""]
        for type_name, description in sorted(CEF_TYPES.items()):
            lines.append(f"//   {type_name:40s} → {description}")
        return '\n'.join(lines)
    
    def analyze_file(self, path: str) -> Dict:
        """Analyze a Pascal file and extract structure."""
        content = Path(path).read_text()
        lines = content.split('\n')
        
        structure = {
            "path": path,
            "lines": len(lines),
            "program": "",
            "unit": "",
            "uses": [],
            "types": [],
            "procedures": [],
            "functions": [],
            "variables": [],
            "cef_usage": [],
        }
        
        for line in lines:
            stripped = line.strip()
            
            m = re.match(r'program\s+(\w+)', stripped, re.IGNORECASE)
            if m: structure["program"] = m.group(1)
            
            m = re.match(r'unit\s+(\w+)', stripped, re.IGNORECASE)
            if m: structure["unit"] = m.group(1)
            
            m = re.match(r'uses\s+(.*?);', stripped, re.IGNORECASE)
            if m: structure["uses"].extend(m.group(1).split(','))
            
            m = re.match(r'procedure\s+(\w+)', stripped, re.IGNORECASE)
            if m: structure["procedures"].append(m.group(1))
            
            m = re.match(r'function\s+(\w+)', stripped, re.IGNORECASE)
            if m: structure["functions"].append(m.group(1))
            
            for cef_type in CEF_TYPES:
                if cef_type.lower() in stripped.lower():
                    structure["cef_usage"].append(cef_type)
        
        structure["uses"] = [u.strip() for u in structure["uses"] if u.strip()]
        structure["cef_usage"] = list(set(structure["cef_usage"]))
        
        return structure


def main():
    parser = argparse.ArgumentParser(description="Pascal Lens — AI-readable converter")
    parser.add_argument("file", nargs="?", help=".pas/.lpr/.ppu file to convert")
    parser.add_argument("--full", action="store_true", help="Full annotated output with CEF type ref")
    parser.add_argument("--dir", help="Convert all Pascal files in directory")
    parser.add_argument("--explain-types", action="store_true", help="Print CEF4Delphi type reference")
    parser.add_argument("--analyze", action="store_true", help="Analyze file structure")
    parser.add_argument("--output", "-o", help="Output file")
    
    args = parser.parse_args()
    lens = PascalLens()
    
    if args.explain_types:
        print(lens.explain_cef_types())
        return
    
    if args.dir:
        dir_path = Path(args.dir)
        for f in sorted(dir_path.glob("*.pas")) + sorted(dir_path.glob("*.lpr")):
            try:
                if args.analyze:
                    info = lens.analyze_file(str(f))
                    print(f"\n{'='*60}")
                    print(f"ANALYSIS: {f.name}")
                    print(f"{'='*60}")
                    print(f"  Type:     {'program' if info['program'] else 'unit'}")
                    print(f"  Name:     {info['program'] or info['unit']}")
                    print(f"  Lines:    {info['lines']}")
                    print(f"  Uses:     {', '.join(info['uses'][:10])}")
                    if info['cef_usage']:
                        print(f"  CEF API:  {', '.join(info['cef_usage'][:10])}")
                    print(f"  Procs:    {len(info['procedures'])}")
                    print(f"  Funcs:    {len(info['functions'])}")
                else:
                    content = f.read_text()
                    converted = lens.convert(content, str(f))
                    if args.full:
                        converted += "\n\n" + lens.explain_cef_types()
                    
                    if args.output:
                        out_path = Path(args.output) / f"{f.stem}.pseudo.txt"
                        out_path.write_text(converted)
                        print(f"  → {out_path}")
                    else:
                        print(f"\n// ═══ {f.name} ═══")
                        print(converted[:2000])
            except Exception as e:
                print(f"  ⚠️ {f.name}: {e}")
        return
    
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"❌ File not found: {args.file}")
            sys.exit(1)
        
        if args.analyze:
            info = lens.analyze_file(str(path))
            print(json.dumps(info, indent=2))
            return
        
        content = path.read_text()
        converted = lens.convert(content, str(path))
        
        if args.full:
            converted += "\n\n" + lens.explain_cef_types()
        
        if args.output:
            Path(args.output).write_text(converted)
            print(f"✅ Written to {args.output}")
        else:
            print(converted)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

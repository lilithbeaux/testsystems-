#!/usr/bin/env python3
"""
bromium_bridge.py — Control Bromium browser + its extensions via Unix socket
=============================================================================

Unified client for driving Bromium (the CEF browser) and talking to its
installed extensions. Uses the socket protocol for navigation/JS execution
and CDP (port 9224) for extension debugging.

Extension bridge works by:
  1. Injecting a content script into every page via Bromium's JS execution
  2. That script opens a channel to `chrome.runtime` so socket commands
     can invoke extension APIs (BetterDeepSeek, research tools, etc.)
  3. Or using CDP to talk to extension background pages directly

Usage:
  python3 bromium_bridge.py navigate https://chat.deepseek.com
  python3 bromium_bridge.py search reddit "sovereign AI"
  python3 bromium_bridge.py deepresearch "how to fine-tune Qwen3"
  python3 bromium_bridge.py extension BetterDeepSeek --action query --text "..."
"""

import os
import sys
import json
import time
import socket
import requests
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any

BROMIUM_SOCKET = "/tmp/aethelgard_cef.sock"
CDP_PORT = 9224
EXTENSIONS_DIR = Path("/home/craig/projects/aethelgard/fleet/pascal/dual-citizen-v2/extensions")

SITE_URLS = {
    "reddit": "https://www.reddit.com",
    "facebook": "https://www.facebook.com",
    "craigslist": "https://www.craigslist.org",
    "linkedin": "https://www.linkedin.com",
    "deepseek": "https://chat.deepseek.com",
    "x": "https://x.com",
    "github": "https://github.com",
}


def sock_send(payload: Dict, sock_path: str = BROMIUM_SOCKET) -> Optional[Dict]:
    """Send JSON command to Bromium via Unix socket."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(sock_path)
        s.send(json.dumps(payload).encode() + b'\n')
        resp = s.recv(65536).decode()
        s.close()
        return json.loads(resp) if resp else None
    except Exception as e:
        return {"error": str(e)}


def cdp_get_targets() -> List[Dict]:
    """Get all CDP targets (tabs, extensions, service workers)."""
    try:
        resp = requests.get(f"http://127.0.0.1:{CDP_PORT}/json", timeout=5)
        return resp.json()
    except Exception as e:
        return [{"error": str(e)}]


def cdp_evaluate(target_id: str, js: str) -> Optional[Dict]:
    """Evaluate JS in a CDP target (tab, extension background, etc.)."""
    try:
        # First attach
        attach = requests.post(
            f"http://127.0.0.1:{CDP_PORT}/json/attach/{target_id}",
            timeout=5
        )
        ws_url = attach.json().get("webSocketDebuggerUrl", "")
        if not ws_url:
            return {"error": "Could not attach"}

        # Use HTTP to evaluate (simpler than WebSocket for single evals)
        # CDP HTTP endpoint for eval
        eval_resp = requests.post(
            f"http://127.0.0.1:{CDP_PORT}/json/evaluate/{target_id}",
            json={"expression": js, "returnByValue": True},
            timeout=5
        )
        return eval_resp.json() if eval_resp.status_code == 200 else {"error": eval_resp.text}
    except Exception as e:
        return {"error": str(e)}


# ─── Public API ───

def navigate(url: str, tab_id: int = 1) -> Dict:
    """Navigate Bromium to a URL."""
    return sock_send({"action": "navigate", "url": url, "tab_id": tab_id})


def execute_js(js: str, tab_id: int = 1) -> Dict:
    """Execute JavaScript in the current page."""
    return sock_send({"action": "execute_javascript", "code": js, "tab_id": tab_id})


def get_title(tab_id: int = 1) -> str:
    """Get current page title."""
    r = sock_send({"action": "get_title", "tab_id": tab_id})
    return (r or {}).get("title", "")


def page_text(tab_id: int = 1) -> str:
    """Extract visible text from current page."""
    r = execute_js("document.body.innerText", tab_id)
    return (r or {}).get("result", "")


def extension_message(extension_id: str, message: Dict, tab_id: int = 1) -> Dict:
    """Send a message to an extension via injected JS + chrome.runtime.sendMessage."""
    # Inject a script that sends a message to the extension and returns the response
    js = f"""
    (async () => {{
      try {{
        const resp = await chrome.runtime.sendMessage(
          '{extension_id}',
          {json.dumps(message)}
        );
        return JSON.stringify(resp);
      }} catch(e) {{
        return JSON.stringify({{error: e.message}});
      }}
    }})();
    """
    return execute_js(js, tab_id)


def extension_bridge_init(tab_id: int = 1) -> Dict:
    """Inject the extension bridge content script into the current page.
    This opens a window-level event channel so socket commands can reach extensions."""
    js = r"""
    // Bromium Extension Bridge — installed by bromium_bridge.py
    if (!window.__bromiumBridge) {
      window.__bromiumBridge = {
        pending: {},
        counter: 0,
        results: [],
      };
      
      // Listen for extension responses
      chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
        window.__bromiumBridge.results.push({msg, sender, time: Date.now()});
        sendResponse({ack: true});
      });
      
      // Expose send function to be called from injected JS
      window.__bromiumBridge.send = async (extensionId, message) => {
        try {
          const resp = await chrome.runtime.sendMessage(extensionId, message);
          return resp;
        } catch(e) {
          return {error: e.message};
        }
      };
      
      document.title = '[Bromium Bridge Active] ' + document.title;
    }
    """
    return execute_js(js, tab_id)


def deepresearch(query: str, model: str = "deepseek-chat") -> Dict:
    """Use Bromium to research a query on chat.deepseek.com."""
    # 1. Navigate to DeepSeek chat
    navigate("https://chat.deepseek.com")
    time.sleep(5)
    
    # 2. Init extension bridge
    extension_bridge_init()
    
    # 3. Type query into the input
    type_js = f"""
    const input = document.querySelector('textarea, [contenteditable="true"], #prompt-textarea');
    if (!input) return {{error: 'No input', html: document.body.innerHTML.slice(0,500)}};
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
    if (nativeSetter) nativeSetter.set.call(input, {json.dumps(query)});
    else input.innerText = {json.dumps(query)};
    input.dispatchEvent(new Event('input', {{bubbles: true}}));
    return {{typed: true, len: {len(query)}}};
    """
    execute_js(type_js)
    time.sleep(1)
    
    # 4. Click send
    send_js = """
    const btn = document.querySelector('button[type="submit"], [data-testid="send-button"], .send-btn, .btn-primary');
    if (btn) { btn.click(); return {method:'button'}; }
    const enter = new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true});
    document.querySelector('textarea')?.dispatchEvent(enter);
    return {method:'enter'};
    """
    execute_js(send_js)
    
    # 5. Poll for response (up to 60s)
    extract_js = """
    (() => {
      for (let wait = 0; wait < 30; wait++) {
        // Try multiple selectors for DeepSeek's response
        const selectors = [
          '[class*="message"]:last-child [class*="content"]',
          '[class*="answer"]',
          '[class*="response"]',
          '.ds-markdown',
          '[class*="final"]',
        ];
        for (const sel of selectors) {
          const el = document.querySelector(sel);
          if (el && el.innerText.trim().length > 50) {
            return {found: true, text: el.innerText.slice(0, 5000), selector: sel};
          }
        }
        // Wait and retry
        new Promise(r => setTimeout(r, 2000));
      }
      return {found: false, html: document.body.innerHTML.slice(0, 300)};
    })();
    """
    
    for i in range(15):
        time.sleep(4)
        result = execute_js(extract_js)
        data = result or {}
        found = (data.get("result") or {}).get("found") or data.get("found")
        if found:
            text = (data.get("result") or data).get("text", "")
            return {
                "status": "completed",
                "query": query,
                "response": text[:5000],
                "waited_seconds": (i + 1) * 4,
            }
    
    return {"status": "timeout", "query": query, "waited_seconds": 60}


def browse_site(site: str, action: str = "navigate", query: str = "") -> Dict:
    """Unified site interaction for /reddit, /facebook, etc."""
    base = SITE_URLS.get(site, f"https://www.{site}.com")
    
    if action == "search" and query:
        search_urls = {
            "reddit": f"{base}/search/?q={query}",
            "craigslist": f"{base}/search/sss?query={query}",
            "linkedin": f"{base}/search/results/all/?keywords={query}",
        }
        url = search_urls.get(site, base)
    else:
        url = base
    
    nav_result = navigate(url)
    time.sleep(2)
    
    # Check if BetterDeepSeek extension is active (for deepseek site)
    ext_status = ""
    if site == "deepseek":
        init = extension_bridge_init()
        ext_status = "bridge_init" if init else ""
    
    return {
        "site": site,
        "url": url,
        "navigated": nav_result,
        "title": get_title(),
        "text_preview": page_text()[:500],
        "extension": ext_status,
    }


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description="Bromium Browser Controller")
    sub = parser.add_subparsers(dest="cmd")
    
    sub.add_parser("navigate").add_argument("url")
    sub.add_parser("title")
    sub.add_parser("text")
    
    p_search = sub.add_parser("search")
    p_search.add_argument("site", choices=["reddit", "craigslist", "linkedin", "github", "x"])
    p_search.add_argument("query", nargs="+")
    
    p_dr = sub.add_parser("deepresearch")
    p_dr.add_argument("query", nargs="+")
    
    p_browse = sub.add_parser("browse")
    p_browse.add_argument("site", choices=list(SITE_URLS.keys()))
    
    p_js = sub.add_parser("js")
    p_js.add_argument("code", nargs="+")
    
    p_ext = sub.add_parser("ext")
    p_ext.add_argument("extension_id")
    p_ext.add_argument("--action", default="ping")
    p_ext.add_argument("--data", default="{}")
    
    p_ls = sub.add_parser("ext-list")
    p_ls.add_argument("--cdp", action="store_true", help="List via CDP")
    
    args = parser.parse_args()
    
    if args.cmd == "navigate":
        r = navigate(args.url)
        print(json.dumps(r, indent=2))
    
    elif args.cmd == "title":
        print(get_title())
    
    elif args.cmd == "text":
        print(page_text()[:2000])
    
    elif args.cmd == "search":
        query = " ".join(args.query)
        r = browse_site(args.site, "search", query)
        print(json.dumps(r, indent=2, default=str))
    
    elif args.cmd == "deepresearch":
        query = " ".join(args.query)
        r = deepresearch(query)
        print(json.dumps(r, indent=2))
    
    elif args.cmd == "browse":
        r = browse_site(args.site)
        print(json.dumps(r, indent=2, default=str))
    
    elif args.cmd == "js":
        code = " ".join(args.code)
        r = execute_js(code)
        print(json.dumps(r, indent=2))
    
    elif args.cmd == "ext":
        data = json.loads(args.data)
        r = extension_message(args.extension_id, {"action": args.action, **data})
        print(json.dumps(r, indent=2))
    
    elif args.cmd == "ext-list":
        if args.cdp:
            targets = cdp_get_targets()
            for t in targets:
                if "extension" in str(t.get("url", "")).lower() or t.get("type") == "background":
                    print(f"  [{t.get('id','')[:12]}] {t.get('type','?')}: {t.get('title','')} — {t.get('url','')[:80]}")
        else:
            # List from extensions dir
            for d in EXTENSIONS_DIR.iterdir():
                if d.is_dir():
                    mf = d / "manifest.json"
                    if mf.exists():
                        m = json.loads(mf.read_text())
                        print(f"  {m.get('name','?')} ({m.get('version','?')}) — {m.get('description','')[:60]}")
                        print(f"    ID: {d.name}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

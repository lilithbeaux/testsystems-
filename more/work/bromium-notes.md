# Bromium Browser — Extension Enablement

## Binary
- **Path:** `/home/craig/projects/aethelgard/fleet/pascal/dual-citizen-v2/bromium`
- **Source:** `dual_citizen_v2.lpr` (same directory)
- **Type:** CEF4Delphi (Chromium Embedded Framework) Pascal browser
- **Size:** 36M ELF

## Extensions
Extensions are loaded from `extensions/` dir in the same folder as the binary:

```
/home/craig/projects/aethelgard/fleet/pascal/dual-citizen-v2/extensions/
```

### CEF Config
```pascal
GlobalCEFApp.EnableExtensions := True;
GlobalCEFApp.ExtensionDir := '.../extensions/';
```

### Known Pitfall
The original source had `--disable-extensions` hardcoded. Fixed by:
1. Removing the line from `dual_citizen_v2.lpr` source
2. Hex-patching the compiled binary: `sed -i 's/--disable-extensions/--enable-extensions /g' bromium`

## Launch
```bash
DISPLAY=:0 ./bromium --socket /tmp/aethelgard_cef.sock --user-data-dir=/tmp/bromium-profile
```

## Socket Protocol
Unix socket at `/tmp/aethelgard_cef.sock`. JSON commands, one per connection:
```json
{"action":"navigate","url":"https://example.com","tab_id":1}
{"action":"get_title","tab_id":1}
{"action":"execute_javascript","code":"document.title","tab_id":1}
```

## Process Tree
```
bromium (main, visible window)
├── bromium --type=zygote (×N)
├── bromium --type=utility --utility-sub-type=network.mojom.NetworkService
└── ...
```

## CDP
Remote debugging port: 9224 (configured in source)
- http://127.0.0.1:9224/json/list

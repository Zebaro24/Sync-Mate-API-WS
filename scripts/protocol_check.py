#!/usr/bin/env python3
"""protocol_check - cross-repo WS-protocol parity gate for CI.

Vendored, path-parameterized variant of the workspace `scripts/protocol_sync.py` so it can
run inside a GitHub Actions runner that has BOTH repos checked out (this repo + the extension).

The WebSocket message vocabulary is a CONTRACT shared by backend and frontend. Any change to a
message `type` on one side must be mirrored on the other, or room sync breaks silently. This
extracts every WS message `type` from each side and asserts the two sets are equal.

Paths (override via env in CI):
  API_DIR  backend repo root   (default ".")
  EXT_DIR  extension repo root (default "../Sync-Mate-Extension")

Exit 0 = in sync, 1 = drift, 2 = files not found.
Keep in sync with the workspace `scripts/protocol_sync.py` (this is a vendored copy).
"""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API_DIR = os.path.abspath(os.environ.get("API_DIR", "."))
EXT_DIR = os.path.abspath(os.environ.get("EXT_DIR", os.path.join("..", "Sync-Mate-Extension")))

FE_FILE = os.path.join(EXT_DIR, "src", "features", "room", "model", "messageTypes.ts")
BE_DIR = os.path.join(API_DIR, "app")
BE_HANDLER = os.path.join(BE_DIR, "modules", "room", "handler.py")
BE_WS_SCHEMAS = os.path.join(BE_DIR, "ws", "schemas.py")


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def py_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def frontend_types():
    text = read(FE_FILE)
    if text is None:
        return None
    m = re.search(r"enum\s+WSMessageTypes\s*\{(.*?)\}", text, re.S)
    if not m:
        return None
    return set(re.findall(r"""=\s*["']([^"']+)["']""", m.group(1)))


def backend_types():
    if not os.path.isdir(BE_DIR):
        return None
    h = read(BE_HANDLER) or ""
    m = re.search(r"_VALID_ACTIONS\s*=\s*frozenset\(\s*\{([^}]*)\}\s*\)", h)
    if not m:
        return None
    types = set(re.findall(r"""["']([^"']+)["']""", m.group(1)))
    types.update(re.findall(r"""Literal\[\s*["']([^"']+)["']\s*\]""", read(BE_WS_SCHEMAS) or ""))
    out_files = [BE_HANDLER, os.path.join(BE_DIR, "modules", "room", "models.py")]
    ws_dir = os.path.join(BE_DIR, "ws")
    if os.path.isdir(ws_dir):
        out_files += list(py_files(ws_dir))
    for path in out_files:
        text = read(path) or ""
        types.update(re.findall(r"""["']type["']\s*:\s*["']([^"']+)["']""", text))
        types.update(re.findall(r"""\[\s*["']type["']\s*\]\s*=\s*["']([^"']+)["']""", text))
    return types


def main():
    fe = frontend_types()
    be = backend_types()
    if fe is None:
        print(f"protocol: cannot read FE `enum WSMessageTypes` ({FE_FILE}) — renamed/missing?")
        return 2
    if be is None:
        print(f"protocol: cannot parse BE `_VALID_ACTIONS` in {BE_HANDLER} (or app/ missing) — aborting")
        return 2

    only_be = sorted(be - fe)
    only_fe = sorted(fe - be)
    shared = sorted(be & fe)

    if not only_be and not only_fe:
        print(f"protocol: OK — WS contract in sync ({len(shared)} types: {', '.join(shared)})")
        return 0

    print("protocol: DRIFT — the WS contract differs between backend and frontend.")
    if only_be:
        print("  ✗ in BACKEND but missing in FRONTEND (add to WSMessageTypes): " + ", ".join(only_be))
    if only_fe:
        print("  ✗ in FRONTEND but missing in BACKEND (add a handler / send_json): " + ", ".join(only_fe))
    return 1


if __name__ == "__main__":
    sys.exit(main())

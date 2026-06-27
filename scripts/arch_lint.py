#!/usr/bin/env python3
"""arch_lint_api - architecture guard for the FastAPI backend (Sync-Mate-API-WS).

Enforces the layering & invariants documented in Sync-Mate-API-WS/CLAUDE.md and
.claude/docs/architecture.md. Pure stdlib, regex/AST based, low false-positive.

Rules:
  1. Layer direction. Lower layers must not import higher ones:
       app/modules/**      must not import  app.api / app.ws / app.main
       app/modules/rezka/* must not import  app.modules.room   (and vice-versa)
  2. WS action/handler parity. Every action in `UserHandler._VALID_ACTIONS`
     must actually be handled in `handle()` — either inline (`action == "x"`)
     or via a `_handle_<action>` method. (Guards the historical "silently
     accepted action with no effect" bug.)
  3. No sync HTTP. The project is async-only: forbid `import requests` and the
     sync `httpx.Client(` anywhere under app/ (use httpx.AsyncClient).

Run:  python scripts/arch_lint_api.py [--root <repo dir>]
Exit 0 = clean, 1 = violations. Defaults to cwd (the gate runs it with cwd = repo dir).
"""
import argparse
import ast
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def py_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".venv", "venv"}]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\b|import\s+([\w.]+))", re.M)


def imported_modules(text):
    mods = set()
    for m in IMPORT_RE.finditer(text):
        mods.add(m.group(1) or m.group(2))
    return mods


def check_layers(app_dir, root, violations):
    for path in py_files(app_dir):
        r = rel(path, root)
        mods = imported_modules(read(path))
        if "/modules/" in "/" + r:
            for forbidden in ("app.api", "app.ws", "app.main"):
                if any(m == forbidden or m.startswith(forbidden + ".") for m in mods):
                    violations.append(f"{r}: layer violation — modules/ must not import `{forbidden}`")
            # sibling-module isolation
            if "/modules/rezka/" in "/" + r:
                if any(m.startswith("app.modules.room") for m in mods):
                    violations.append(f"{r}: cross-module coupling — rezka must not import `app.modules.room`")
            if "/modules/room/" in "/" + r:
                if any(m.startswith("app.modules.rezka") for m in mods):
                    violations.append(f"{r}: cross-module coupling — room must not import `app.modules.rezka`")


def check_action_parity(app_dir, root, violations):
    handler = os.path.join(app_dir, "modules", "room", "handler.py")
    if not os.path.isfile(handler):
        return  # nothing to check
    text = read(handler)
    m = re.search(r"_VALID_ACTIONS\s*=\s*frozenset\(\s*\{([^}]*)\}\s*\)", text)
    if not m:
        violations.append("modules/room/handler.py: could not find `_VALID_ACTIONS = frozenset({...})`")
        return
    actions = re.findall(r"""["']([^"']+)["']""", m.group(1))
    for action in actions:
        has_method = re.search(rf"\bdef\s+_handle_{re.escape(action)}\b", text) is not None
        has_inline = re.search(rf"""action\s*==\s*["']{re.escape(action)}["']""", text) is not None
        if not (has_method or has_inline):
            violations.append(
                f"modules/room/handler.py: action '{action}' is in _VALID_ACTIONS but has no "
                f"`_handle_{action}` method and no `action == \"{action}\"` branch — "
                f"it would be silently accepted with no effect."
            )


def check_no_sync_http(app_dir, root, violations):
    # AST-based (not regex on raw text) so a mention of `httpx.Client(` in a comment/docstring
    # does NOT false-trigger — only a real import/call counts.
    for path in py_files(app_dir):
        r = rel(path, root)
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(n.name == "requests" or n.name.startswith("requests.") for n in node.names):
                    violations.append(f"{r}: imports `requests` (sync). Use httpx.AsyncClient.")
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "requests" or node.module.startswith("requests.")):
                    violations.append(f"{r}: imports from `requests` (sync). Use httpx.AsyncClient.")
            elif isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Attribute) and f.attr == "Client"
                        and isinstance(f.value, ast.Name) and f.value.id == "httpx"):
                    violations.append(f"{r}: uses sync `httpx.Client(...)`. Use httpx.AsyncClient.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd(), help="repo dir (default: cwd)")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    app_dir = os.path.join(root, "app")
    if not os.path.isdir(app_dir):
        print(f"arch(api): no app/ dir under {root} — nothing to check")
        return 0

    violations: list[str] = []
    check_layers(app_dir, root, violations)
    check_action_parity(app_dir, root, violations)
    check_no_sync_http(app_dir, root, violations)

    if violations:
        print(f"arch(api): {len(violations)} violation(s):")
        for v in violations:
            print(f"  ✗ {v}")
        return 1
    print("arch(api): OK — layering, WS action/handler parity, async-HTTP all clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())

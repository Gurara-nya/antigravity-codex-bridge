#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-platform installer & updater for `antigravity-codex-bridge`.
Installs the plugin into `~/.gemini/config/plugins/codex-bridge/`, binds the verified Python 3.11+
interpreter into `mcp_config.json`, creates cross-platform `bin/codex-ctl` launchers, and runs `doctor`.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_DEST = pathlib.Path.home() / ".gemini" / "config" / "plugins" / "codex-bridge"

PLUGIN_ITEMS = [
    "plugin.json",
    "README.md",
    "README_EN.md",
    "LICENSE",
    "assets",
    "lib",
    "mcp",
    "scripts",
    "skills",
    "agents",
    "rules",
]


def copy_plugin_tree(src: pathlib.Path, dest: pathlib.Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in PLUGIN_ITEMS:
        s = src / name
        if not s.exists():
            continue
        d = dest / name
        if s.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        else:
            shutil.copy2(s, d)


def write_mcp_config(dest: pathlib.Path, python_exe: str) -> None:
    server_py = str((dest / "mcp" / "server.py").resolve())
    cfg = {
        "mcpServers": {
            "codex-bridge": {
                "command": python_exe,
                "args": ["-u", server_py],
                "env": {"PYTHONIOENCODING": "utf-8"},
            }
        }
    }
    (dest / "mcp_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_cli_launchers(dest: pathlib.Path, python_exe: str) -> dict[str, str]:
    bin_dir = dest / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    ctl_py = str((dest / "scripts" / "codex_ctl.py").resolve())

    cmd_path = bin_dir / "codex-ctl.cmd"
    cmd_path.write_text(f'@echo off\r\n"{python_exe}" "{ctl_py}" %*\r\n', encoding="utf-8")

    sh_path = bin_dir / "codex-ctl"
    sh_path.write_text(f'#!/usr/bin/env sh\nexec "{python_exe}" "{ctl_py}" "$@"\n', encoding="utf-8", newline="\n")
    try:
        sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    return {"windows": str(cmd_path), "posix": str(sh_path)}


def main() -> int:
    if sys.version_info < (3, 11):
        print(f"Error: Python 3.11+ is required (current: {sys.version}).", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Install or update `codex-bridge` in Antigravity.")
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help="Target plugin directory")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip running post-install doctor check")
    args = parser.parse_args()

    dest = pathlib.Path(args.dest).expanduser().resolve()
    python_exe = str(pathlib.Path(sys.executable).resolve())

    print(f"[1/4] Copying plugin bundle -> {dest}")
    copy_plugin_tree(REPO_ROOT, dest)

    print(f"[2/4] Binding MCP server interpreter -> {python_exe}")
    write_mcp_config(dest, python_exe)

    print("[3/4] Creating portable CLI launchers (`bin/codex-ctl` & `bin/codex-ctl.cmd`)")
    launchers = write_cli_launchers(dest, python_exe)

    if not args.skip_doctor:
        print("[4/4] Running environment diagnostics (`doctor`)...")
        proc = subprocess.run([python_exe, str(dest / "scripts" / "codex_ctl.py"), "doctor"], text=True)
        if proc.returncode != 0:
            print("Warning: doctor exited with non-zero status.", file=sys.stderr)

    print("\n✅ Codex Bridge v1.1.0 installed successfully!")
    print(f"   Plugin Path : {dest}")
    print(f"   CLI Launcher: {launchers['windows'] if os.name == 'nt' else launchers['posix']}")
    print("   Manage in Antigravity: customization://codex-bridge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-platform installer & readiness verifier for `antigravity-codex-bridge` (v1.2.1).
Strictly separates "Plugin Files Installed" from "Bridge Ready (`doctor` passed)" into
three unambiguous final outcomes:
  1. 安装完成，自检通过
  2. 文件已安装，自检未通过
  3. 文件已安装，跳过自检
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
    if src.resolve() == dest.resolve():
        return
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
        print(f"Error: Python 3.11+ is required (current: {sys.version.split()[0]}).", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Install or update `codex-bridge` in Antigravity.")
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help="Target plugin directory")
    parser.add_argument("--skip-doctor", action="store_true", help="Copy files and configure launchers without running doctor")
    parser.add_argument(
        "--strict-doctor",
        action="store_true",
        help="Exit with non-zero status (1) if post-install `doctor` self-check does not pass (recommended for CI)",
    )
    args = parser.parse_args()

    dest = pathlib.Path(args.dest).expanduser().resolve()
    python_exe = str(pathlib.Path(sys.executable).resolve())

    print(f"[1/3] Installing plugin files -> {dest}")
    copy_plugin_tree(REPO_ROOT, dest)

    print(f"[2/3] Binding MCP server Python 3.11+ interpreter -> {python_exe}")
    write_mcp_config(dest, python_exe)

    print("[3/3] Creating CLI launchers (`bin/codex-ctl` & `bin/codex-ctl.cmd`)")
    launchers = write_cli_launchers(dest, python_exe)
    launcher_cmd = launchers["windows"] if os.name == "nt" else launchers["posix"]
    rerun_doctor_hint = f'"{launcher_cmd}" doctor'

    # Outcome 3: Skipped self-check
    if args.skip_doctor:
        print("\n[状态 / Result] 文件已安装，跳过自检 (Files installed, self-check skipped)")
        print(f"  Plugin Path  : {dest}")
        print(f"  Re-run Doctor: {rerun_doctor_hint}")
        print("  Antigravity  : customization://codex-bridge")
        return 0

    print("\n[Doctor] Running post-install Bridge readiness check...")
    proc = subprocess.run(
        [python_exe, str(dest / "scripts" / "codex_ctl.py"), "doctor"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    doc: dict = {}
    if proc.stdout.strip():
        print(proc.stdout.strip())
        try:
            doc = json.loads(proc.stdout)
        except Exception:
            doc = {}
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    doctor_passed = proc.returncode == 0 and bool(doc.get("healthy"))

    # Outcome 1: Installed & self-check passed
    if doctor_passed:
        print("\n[状态 / Result] 安装完成，自检通过 (Installed, self-check passed)")
        warnings = doc.get("warnings") or []
        if warnings:
            print("  功能受限提示 (Optional Desktop Advisories):")
            for w in warnings:
                print(f"    - [{w.get('check')}] {w.get('detail')}")
                if w.get("nextStep"):
                    print(f"      提示: {w['nextStep']}")
        print(f"  Plugin Path  : {dest}")
        print(f"  Re-run Doctor: {rerun_doctor_hint}")
        print("  Antigravity  : customization://codex-bridge")
        return 0

    # Outcome 2: Files installed, self-check failed
    print("\n[状态 / Result] 文件已安装，自检未通过 (Files installed, self-check failed — Bridge currently unavailable)")
    failed_blockers = doc.get("failedBlockers") or []
    if failed_blockers:
        print("  未通过的核心检查项 (Failed Blockers):")
        for b in failed_blockers:
            print(f"    - [{b.get('check')}] {b.get('detail')}")
            if b.get("nextStep"):
                print(f"      下一步 (Next step): {b['nextStep']}")
    else:
        print("  下一步 (Next step): 请检查上方诊断输出，修复 Codex 安装或登录态后重跑自检。")

    print(f"  修复后单独重跑自检 (Re-run Doctor): {rerun_doctor_hint}")
    print(f"  Plugin Path  : {dest}")
    return 1 if args.strict_doctor else 0


if __name__ == "__main__":
    raise SystemExit(main())

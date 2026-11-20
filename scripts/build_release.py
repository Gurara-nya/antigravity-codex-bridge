#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Release packager & manifest/privacy validator for `antigravity-codex-bridge`.
Builds `dist/antigravity-codex-bridge-v<version>.zip` and its `.sha256` digest.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED_PLUGIN_KEYS = {
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "author",
    "homepage",
    "repository",
    "disabled",
}

EXCLUDE_DIRS = {".git", ".github", "dist", "data", "bin", "__pycache__", ".pytest_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".bak", ".log"}

FORBIDDEN_PATTERNS = [
    re.compile(r"C:[\\/]+Users[\\/]+(?!<|your|username)", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"gh[pousr]_[a-zA-Z0-9]{20,}"),
]


def validate_manifest() -> dict:
    manifest_p = REPO_ROOT / "plugin.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    unknown = set(manifest.keys()) - ALLOWED_PLUGIN_KEYS
    if unknown:
        raise ValueError(f"plugin.json contains unsupported top-level keys: {unknown}")
    for req in ("name", "description", "version"):
        if not manifest.get(req):
            raise ValueError(f"plugin.json missing required key: {req}")
    json.loads((REPO_ROOT / "mcp_config.json").read_text(encoding="utf-8"))
    return manifest


def iter_package_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for p in sorted(REPO_ROOT.rglob("*")):
        rel_parts = p.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIRS for part in rel_parts):
            continue
        if p.is_file() and p.suffix.lower() not in EXCLUDE_SUFFIXES:
            files.append(p)
    return files


def audit_privacy(files: list[pathlib.Path]) -> None:
    for f in files:
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".ico"}:
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for pat in FORBIDDEN_PATTERNS:
            m = pat.search(txt)
            if m:
                raise RuntimeError(f"Privacy/secret check failed in {f.relative_to(REPO_ROOT)}: matched '{m.group(0)}'")


def build_zip() -> pathlib.Path:
    manifest = validate_manifest()
    version = manifest["version"]
    files = iter_package_files()
    audit_privacy(files)

    dist_dir = REPO_ROOT / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"antigravity-codex-bridge-v{version}.zip"
    zip_path = dist_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arcname = f"codex-bridge/{f.relative_to(REPO_ROOT).as_posix()}"
            zf.write(f, arcname=arcname)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (dist_dir / f"{zip_name}.sha256").write_text(f"{digest}  {zip_name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(zip_path), "files": len(files), "bytes": zip_path.stat().st_size, "sha256": digest}, indent=2))
    return zip_path


if __name__ == "__main__":
    try:
        build_zip()
    except Exception as exc:
        print(f"Release build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

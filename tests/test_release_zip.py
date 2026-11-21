#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end verification against the ACTUAL built Release ZIP (`dist/antigravity-codex-bridge-v*.zip`).
Extracts the release archive into an isolated temporary folder and verifies:
  1. `安装完成，自检通过` (plus optional Desktop advisory warnings when SQLite/projects are absent) -> exit 0
  2. `文件已安装，自检未通过` on `app-server` handshake failure -> `codex-ctl doctor` exits 1, `--strict-doctor` exits 1, interactive install exits 0 with next steps
  3. `文件已安装，自检未通过` when `codex` binary is missing -> `doctor` exits 1, `--strict-doctor` exits 1
  4. `文件已安装，跳过自检` (`--skip-doctor`) -> exits 0
  5. (Windows) `install.ps1` skips an older Python (<3.11) earlier on `PATH` and selects a valid Python 3.11+ binary.
"""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _make_mock_codex(bin_dir: pathlib.Path, handshake_ok: bool) -> pathlib.Path:
    """Create a cross-platform mock `codex` executable driven by the current Python interpreter."""
    script = bin_dir / "mock_codex_impl.py"
    script.write_text(
        f"""#!/usr/bin/env python3
import json, sys

HANDSHAKE_OK = {handshake_ok!r}

if "--version" in sys.argv or "-V" in sys.argv:
    print("codex-cli 0.169.1-mock")
    raise SystemExit(0)

if len(sys.argv) >= 2 and sys.argv[1] == "app-server":
    if not HANDSHAKE_OK:
        sys.stderr.write("simulated app-server fatal handshake error\\n")
        sys.stderr.flush()
        raise SystemExit(2)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("method") == "initialize":
            resp = {{
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {{"userAgent": "mock-codex/0.169.1", "codexHome": ""}},
            }}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        elif msg.get("method") == "initialized":
            break
    raise SystemExit(0)

raise SystemExit(0)
""",
        encoding="utf-8",
    )

    if os.name == "nt":
        wrapper = bin_dir / "codex.cmd"
        wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return wrapper
    else:
        wrapper = bin_dir / "codex"
        wrapper.write_text(f'#!/usr/bin/env sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8", newline="\n")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return wrapper


class ReleaseZipInstallTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "build_release.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        info = json.loads(proc.stdout)
        cls.zip_path = pathlib.Path(info["zip"])
        assert cls.zip_path.is_file(), f"Built ZIP missing: {cls.zip_path}"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self._tmp.name)
        self.extract_dir = self.base / "unpacked"
        with zipfile.ZipFile(self.zip_path, "r") as zf:
            zf.extractall(self.extract_dir)
        self.pkg_root = self.extract_dir / "codex-bridge"
        self.assertTrue((self.pkg_root / "install.py").is_file())
        self.assertTrue((self.pkg_root / "plugin.json").is_file())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _base_env(self, codex_home: pathlib.Path, codex_cli: str) -> dict[str, str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        env["CODEX_BRIDGE_DATA_DIR"] = str(self.base / "bridge_data")
        env["CODEX_CLI_PATH"] = codex_cli
        env["CODEX_BRIDGE_NO_SYSTEM_SEARCH"] = "1"
        env.pop("OPENAI_API_KEY", None)
        return env

    def test_1_zip_install_doctor_pass_with_advisories(self) -> None:
        codex_home = self.base / "home_ok"
        codex_home.mkdir(parents=True)
        (codex_home / "auth.json").write_text('{"token":"mock"}', encoding="utf-8")
        bin_dir = self.base / "bin_ok"
        bin_dir.mkdir()
        mock_cli = _make_mock_codex(bin_dir, handshake_ok=True)
        dest = self.base / "installed_ok"

        env = self._base_env(codex_home, str(mock_cli))
        proc = subprocess.run(
            [sys.executable, str(self.pkg_root / "install.py"), "--dest", str(dest), "--strict-doctor"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertIn("安装完成，自检通过", proc.stdout)
        self.assertNotIn("文件已安装，自检未通过", proc.stdout)
        # Fresh CLI-only home without state_5.sqlite should surface advisory note without failing
        self.assertIn("功能受限提示", proc.stdout)

        launcher = dest / "bin" / ("codex-ctl.cmd" if os.name == "nt" else "codex-ctl")
        doc_proc = subprocess.run([str(launcher), "doctor"], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(doc_proc.returncode, 0)
        doc_json = json.loads(doc_proc.stdout)
        self.assertTrue(doc_json["healthy"])
        self.assertEqual(doc_json["status"], "ready_with_warnings")

    def test_2_zip_install_handshake_failure_and_exit_codes(self) -> None:
        codex_home = self.base / "home_bad_rpc"
        codex_home.mkdir(parents=True)
        (codex_home / "auth.json").write_text('{"token":"mock"}', encoding="utf-8")
        bin_dir = self.base / "bin_bad_rpc"
        bin_dir.mkdir()
        mock_cli = _make_mock_codex(bin_dir, handshake_ok=False)
        dest = self.base / "installed_bad_rpc"

        env = self._base_env(codex_home, str(mock_cli))

        # Default interactive install: copies files, prints failure + next step, exits 0
        proc_soft = subprocess.run(
            [sys.executable, str(self.pkg_root / "install.py"), "--dest", str(dest)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(proc_soft.returncode, 0)
        self.assertIn("文件已安装，自检未通过", proc_soft.stdout)
        self.assertNotIn("安装完成，自检通过", proc_soft.stdout)
        self.assertIn("app_server_rpc", proc_soft.stdout)
        self.assertIn("下一步", proc_soft.stdout)

        # Strict CI install (`--strict-doctor`): exits 1
        proc_strict = subprocess.run(
            [sys.executable, str(self.pkg_root / "install.py"), "--dest", str(dest), "--strict-doctor"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(proc_strict.returncode, 1)
        self.assertIn("文件已安装，自检未通过", proc_strict.stdout)

        # Standalone `codex-ctl doctor` CLI MUST also return exit code 1!
        launcher = dest / "bin" / ("codex-ctl.cmd" if os.name == "nt" else "codex-ctl")
        doc_proc = subprocess.run([str(launcher), "doctor"], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(doc_proc.returncode, 1)
        doc_json = json.loads(doc_proc.stdout)
        self.assertFalse(doc_json["healthy"])
        self.assertEqual(doc_json["status"], "unavailable")
        blocker_names = [b["check"] for b in doc_json["failedBlockers"]]
        self.assertIn("app_server_rpc", blocker_names)

    def test_3_zip_install_missing_codex_binary(self) -> None:
        codex_home = self.base / "home_missing"
        codex_home.mkdir(parents=True)
        dest = self.base / "installed_missing"
        env = self._base_env(codex_home, str(self.base / "nonexistent_codex_binary"))

        proc = subprocess.run(
            [sys.executable, str(self.pkg_root / "install.py"), "--dest", str(dest), "--strict-doctor"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("文件已安装，自检未通过", proc.stdout)
        self.assertIn("codex_binary", proc.stdout)

    def test_4_zip_install_skip_doctor(self) -> None:
        codex_home = self.base / "home_skip"
        codex_home.mkdir(parents=True)
        dest = self.base / "installed_skip"
        env = self._base_env(codex_home, str(self.base / "nonexistent_codex_binary"))

        proc = subprocess.run(
            [sys.executable, str(self.pkg_root / "install.py"), "--dest", str(dest), "--skip-doctor"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("文件已安装，跳过自检", proc.stdout)
        self.assertNotIn("安装完成，自检通过", proc.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell python probing test")
    def test_5_windows_install_ps1_skips_old_python_in_path(self) -> None:
        old_py_dir = self.base / "fake_python39"
        old_py_dir.mkdir(parents=True)
        # Fake `python.cmd` that always reports Python < 3.11 (exit code 1)
        (old_py_dir / "python.cmd").write_text("@echo off\r\nexit /b 1\r\n", encoding="utf-8")

        dest = self.base / "installed_ps1"
        env = os.environ.copy()
        env["PATH"] = str(old_py_dir) + os.pathsep + env.get("PATH", "")

        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.pkg_root / "install.ps1"),
                "--dest",
                str(dest),
                "--skip-doctor",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertIn("文件已安装，跳过自检", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated unit & integration test suite for `antigravity-codex-bridge` (v1.2.1).
Runs hermetically against an isolated temporary `CODEX_HOME`.
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import codex_engine as engine  # noqa: E402
import dashboard_ui as ui_gen  # noqa: E402
import web_console  # noqa: E402


class CodexBridgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self._tmp.name)
        self.codex_dir = self.base / ".codex"
        self.data_dir = self.base / "bridge_data"
        self.proj_dir = self.base / "workspace" / "demo-app"
        self.codex_dir.mkdir(parents=True)
        self.proj_dir.mkdir(parents=True)

        self._old_codex_home = os.environ.get("CODEX_HOME")
        self._old_data_dir = os.environ.get("CODEX_BRIDGE_DATA_DIR")
        os.environ["CODEX_HOME"] = str(self.codex_dir)
        os.environ["CODEX_BRIDGE_DATA_DIR"] = str(self.data_dir)

        sessions_dir = self.codex_dir / "sessions" / "2026" / "11" / "21"
        sessions_dir.mkdir(parents=True)
        self.ui_rollout = sessions_dir / "rollout-ui.jsonl"
        self.exec_rollout = sessions_dir / "rollout-exec.jsonl"

        self.ui_rollout.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "session_meta",
                            "payload": {
                                "id": "01900000-0000-7000-8000-000000000001",
                                "cwd": str(self.proj_dir),
                                "source": "vscode",
                                "originator": "Codex Desktop",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-11-21T00:00:01Z",
                            "type": "response_item",
                            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Audit demo-app"}]},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-11-21T00:00:02Z",
                            "type": "response_item",
                            "payload": {"type": "reasoning", "summary": [{"text": "Checking files in demo-app"}]},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-11-21T00:00:03Z",
                            "type": "response_item",
                            "payload": {"type": "function_call", "call_id": "call_1", "name": "shell", "arguments": '{"cmd":"pytest"}'},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-11-21T00:00:04Z",
                            "type": "response_item",
                            "payload": {"type": "function_call_output", "call_id": "call_1", "output": "5 passed in 0.12s"},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-11-21T00:00:05Z",
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "All 5 unit tests pass. Should I also enable strict linting?"}],
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        self.exec_rollout.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "01900000-0000-7000-8000-000000000002",
                        "cwd": str(self.proj_dir),
                        "source": "exec",
                        "originator": None,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        gs = {
            "local-projects": {
                "proj-demo-1": {
                    "id": "proj-demo-1",
                    "name": "Demo App",
                    "rootPaths": [str(self.proj_dir)],
                    "createdAt": 1790000000000,
                    "updatedAt": 1790000100000,
                }
            },
            "pinned-project-ids": ["proj-demo-1"],
            "thread-project-assignments": {
                "01900000-0000-7000-8000-000000000001": {"projectKind": "local", "projectId": "proj-demo-1"}
            },
        }
        (self.codex_dir / ".codex-global-state.json").write_text(json.dumps(gs), encoding="utf-8")

        con = sqlite3.connect(str(self.codex_dir / "state_5.sqlite"))
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY, rollout_path TEXT, cwd TEXT, title TEXT, name TEXT,
                preview TEXT, first_user_message TEXT, source TEXT, thread_source TEXT,
                originator TEXT, model TEXT, reasoning_effort TEXT, tokens_used INTEGER,
                sandbox_policy TEXT, created_at_ms INTEGER, updated_at_ms INTEGER, archived INTEGER,
                agent_nickname TEXT, agent_role TEXT
            )
            """
        )
        cur.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, updated_at_ms INTEGER)")
        cur.execute("CREATE TABLE project_roots (project_id TEXT, position INTEGER, path TEXT)")
        cur.execute("CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT, status TEXT)")
        cur.execute(
            """
            INSERT INTO threads VALUES (
                '01900000-0000-7000-8000-000000000001', ?, ?, 'Audit demo-app', '[AGY] Audit demo-app',
                'Audit demo-app', 'Audit demo-app', 'vscode', 'user', 'Codex Desktop',
                'gpt-6.2-sol', 'high', 125000, 'read-only', 1790000000000, 1790000200000, 0, NULL, NULL
            )
            """,
            (str(self.ui_rollout), str(self.proj_dir)),
        )
        cur.execute(
            """
            INSERT INTO threads VALUES (
                '01900000-0000-7000-8000-000000000002', ?, ?, 'Hidden CLI run', NULL,
                'Hidden CLI run', 'Hidden CLI run', 'exec', 'user', NULL,
                'gpt-6.1-sol', 'medium', 42000, 'read-only', 1790000050000, 1790000150000, 0, NULL, NULL
            )
            """,
            (str(self.exec_rollout), str(self.proj_dir)),
        )
        con.commit()
        con.close()

    def tearDown(self) -> None:
        if self._old_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self._old_codex_home
        if self._old_data_dir is None:
            os.environ.pop("CODEX_BRIDGE_DATA_DIR", None)
        else:
            os.environ["CODEX_BRIDGE_DATA_DIR"] = self._old_data_dir
        self._tmp.cleanup()

    def test_win_extended_path_normalization(self) -> None:
        self.assertEqual(engine.normalize_fs_path(r"\\?\G:\Workshop\Case\\"), r"G:\Workshop\Case")

    def test_projects_and_resolution(self) -> None:
        projs = engine.list_projects()
        self.assertEqual(len(projs), 1)
        self.assertEqual(projs[0]["name"], "Demo App")
        self.assertEqual(projs[0]["uiThreadCount"], 1)
        self.assertEqual(projs[0]["execThreadCount"], 1)
        self.assertEqual(projs[0]["totalTokens"], 167000)

        res = engine.resolve_project("demo")
        self.assertTrue(res["matched"])
        self.assertEqual(res["projectId"], "proj-demo-1")

    def test_read_export_and_digest_thread(self) -> None:
        detail = engine.read_thread("01900000-0000-7000-8000-000000000001")
        self.assertEqual(detail["totalMessages"], 2)
        self.assertEqual(detail["totalToolCalls"], 1)
        self.assertIn("5 passed", detail["recentToolCalls"][0]["outputPreview"])

        dig = engine.digest_thread_for_relay("01900000-0000-7000-8000-000000000001")
        self.assertTrue(dig["commanderRelay"]["mustRelayViaAntigravity"])
        self.assertEqual(dig["commanderRelay"]["outcome"], "needs_clarification")
        self.assertTrue(len(dig["commanderRelay"]["detectedQuestions"]) >= 1)

        exp = engine.export_thread_markdown("01900000-0000-7000-8000-000000000001")
        md_text = pathlib.Path(exp["outputPath"]).read_text(encoding="utf-8")
        self.assertIn("All 5 unit tests pass.", md_text)

    def test_commander_relay_inbox_lifecycle(self) -> None:
        relay = engine.build_commander_relay(
            thread_id="01900000-0000-7000-8000-000000000001",
            title="[AGY] Test",
            project_name="Demo App",
            cwd=str(self.proj_dir),
            turn_status="completed",
            turn_error=None,
            final_reply="Task done.",
            commands=[{"command": "pytest", "exitCode": 0, "status": "completed"}],
            file_changes=[{"path": "app.py", "kind": "update"}],
            elicited_questions=[],
            blocked_approvals=[],
        )
        self.assertEqual(relay["outcome"], "completed_clean")
        rid = engine.enqueue_relay_item(relay, "Task done.")

        inbox_before = engine.check_relay_inbox(detect_external_ui_turns=False)
        self.assertEqual(inbox_before["pendingCount"], 1)

        inbox_after = engine.check_relay_inbox(ack_ids=[rid], detect_external_ui_turns=False)
        self.assertEqual(inbox_after["pendingCount"], 0)

    def test_web_console_port_default_and_fallback(self) -> None:
        self.assertEqual(engine.DEFAULT_WEB_PORT, 18765)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupier:
            occupier.bind(("127.0.0.1", 0))
            busy_port = occupier.getsockname()[1]
            chosen = web_console.pick_available_port("127.0.0.1", busy_port, auto_port=True)
            self.assertNotEqual(chosen, busy_port)

    def test_promote_exec_threads(self) -> None:
        prom = engine.promote_exec_threads(force=True)
        self.assertEqual(prom["promotedCount"], 1)
        first_line = json.loads(self.exec_rollout.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(first_line["payload"]["source"], "vscode")

    def test_dashboard_html_generation(self) -> None:
        inline_html = ui_gen.build_inline_widget_html(include_live_quota=False)
        full_html = ui_gen.build_full_dashboard_html(include_live_quota=False)
        self.assertIn("tailwindcss.min.js", inline_html)
        self.assertIn("Demo App", full_html)

    def test_mcp_stdio_tools(self) -> None:
        srv = str(REPO_ROOT / "mcp" / "server.py")
        env = os.environ.copy()
        proc = subprocess.Popen(
            [sys.executable, "-u", srv],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            assert proc.stdin and proc.stdout
            init_req = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "unit", "version": "1.2"}},
                }
            ).encode("utf-8")
            proc.stdin.write(init_req + b"\n")
            proc.stdin.flush()
            init_resp = json.loads(proc.stdout.readline().decode("utf-8"))
            self.assertEqual(init_resp["result"]["serverInfo"]["version"], "1.2.1")

            tl_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode("utf-8")
            proc.stdin.write(tl_req + b"\n")
            proc.stdin.flush()
            tl_resp = json.loads(proc.stdout.readline().decode("utf-8"))
            self.assertEqual(len(tl_resp["result"]["tools"]), 13)
        finally:
            proc.terminate()
            proc.wait(timeout=3)
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe:
                    pipe.close()

    def test_doctor_blocker_vs_advisory_readiness(self) -> None:
        (self.codex_dir / "auth.json").write_text('{"token":"ok"}', encoding="utf-8")

        # 1. Handshake fails -> healthy MUST be False even if binary/version/auth pass
        with (
            mock.patch.object(engine, "find_codex_exe", return_value="/mock/codex"),
            mock.patch.object(engine, "get_codex_version", return_value="codex-cli 0.169.1"),
            mock.patch.object(engine, "_probe_app_server_handshake", return_value=(False, "RPC handshake failed")),
        ):
            doc_fail = engine.run_doctor()
            self.assertFalse(doc_fail["healthy"])
            self.assertFalse(doc_fail["bridgeReady"])
            self.assertEqual(doc_fail["status"], "unavailable")
            self.assertEqual([b["check"] for b in doc_fail["failedBlockers"]], ["app_server_rpc"])

        # 2. Handshake passes, but Desktop SQLite/projects missing -> healthy True with advisory warnings
        (self.codex_dir / "state_5.sqlite").unlink()
        (self.codex_dir / ".codex-global-state.json").unlink()
        with (
            mock.patch.object(engine, "find_codex_exe", return_value="/mock/codex"),
            mock.patch.object(engine, "get_codex_version", return_value="codex-cli 0.169.1"),
            mock.patch.object(engine, "_probe_app_server_handshake", return_value=(True, "JSON-RPC handshake OK (12ms)")),
        ):
            doc_warn = engine.run_doctor()
            self.assertTrue(doc_warn["healthy"])
            self.assertTrue(doc_warn["bridgeReady"])
            self.assertEqual(doc_warn["status"], "ready_with_warnings")
            warn_names = {w["check"] for w in doc_warn["warnings"]}
            self.assertIn("state_sqlite", warn_names)
            self.assertIn("desktop_projects", warn_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)

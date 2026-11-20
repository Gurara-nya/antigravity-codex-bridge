#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated unit & integration test suite for `antigravity-codex-bridge`.
Runs hermetically against an isolated temporary `CODEX_HOME` (zero OpenAI account or live DB needed).
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import codex_engine as engine  # noqa: E402
import dashboard_ui as ui_gen  # noqa: E402


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

        # Create mock rollout JSONL files (1 UI vscode session, 1 hidden exec session)
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
                            "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "All 5 unit tests pass."}]},
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

        # Create mock .codex-global-state.json
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

        # Create mock state_5.sqlite
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

    def test_read_and_export_thread(self) -> None:
        detail = engine.read_thread("01900000-0000-7000-8000-000000000001")
        self.assertEqual(detail["totalMessages"], 2)
        self.assertEqual(detail["totalToolCalls"], 1)
        self.assertIn("5 passed", detail["recentToolCalls"][0]["outputPreview"])

        exp = engine.export_thread_markdown("01900000-0000-7000-8000-000000000001")
        md_text = pathlib.Path(exp["outputPath"]).read_text(encoding="utf-8")
        self.assertIn("All 5 unit tests pass.", md_text)
        self.assertIn("pytest", md_text)

    def test_promote_exec_threads(self) -> None:
        prom = engine.promote_exec_threads(force=True)
        self.assertEqual(prom["promotedCount"], 1)
        first_line = json.loads(self.exec_rollout.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(first_line["payload"]["source"], "vscode")
        self.assertEqual(first_line["payload"]["originator"], "Codex Desktop")

        hidden_after = engine.list_threads(source_filter="exec")
        self.assertEqual(len(hidden_after), 0)
        ui_after = engine.list_threads(source_filter="ui")
        self.assertEqual(len(ui_after), 2)

    def test_dashboard_html_generation(self) -> None:
        inline_html = ui_gen.build_inline_widget_html(include_live_quota=False)
        full_html = ui_gen.build_full_dashboard_html(include_live_quota=False)
        self.assertIn("tailwindcss.min.js", inline_html)
        self.assertIn("Demo App", full_html)

    def test_mcp_stdio_newline_and_content_length(self) -> None:
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
            # 1. Newline-delimited JSON-RPC
            init_req = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "unit", "version": "1.0"}},
                }
            ).encode("utf-8")
            proc.stdin.write(init_req + b"\n")
            proc.stdin.flush()
            init_resp = json.loads(proc.stdout.readline().decode("utf-8"))
            self.assertEqual(init_resp["result"]["serverInfo"]["name"], "codex-bridge")

            # 2. Call overview tool
            call_req = json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "codex_bridge_overview", "arguments": {}}}
            ).encode("utf-8")
            proc.stdin.write(call_req + b"\n")
            proc.stdin.flush()
            call_resp = json.loads(proc.stdout.readline().decode("utf-8"))
            ov = json.loads(call_resp["result"]["content"][0]["text"])
            self.assertEqual(ov["projectCount"], 1)
            self.assertEqual(ov["threads"]["total"], 2)
        finally:
            proc.terminate()
            proc.wait(timeout=3)
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe:
                    pipe.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

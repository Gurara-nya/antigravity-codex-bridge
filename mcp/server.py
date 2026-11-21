#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-dependency Model Context Protocol (MCP) Stdio Server for `antigravity-codex-bridge` (v1.2.1).
Exposes 13 native tools including Commander Relay Inbox & Structured Thread Verification Digest.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import traceback
from typing import Any

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

import codex_engine as engine  # noqa: E402

if os.name == "nt":
    import msvcrt

    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


TOOLS: list[dict[str, Any]] = [
    {
        "name": "codex_bridge_overview",
        "description": (
            "Get comprehensive Codex installation health, project count, UI vs hidden exec session counts, "
            "pending Commander Relay inbox count, model token breakdown, daily activity, and optional live quota."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "includeLiveQuota": {
                    "type": "boolean",
                    "default": False,
                }
            },
        },
    },
    {
        "name": "codex_bridge_relay_inbox",
        "description": (
            "Inspect pending Codex task completions, questions, or external Codex Desktop UI updates that "
            "MUST be verified, interpreted, and relayed by Antigravity to the user. Pass `ackIds` or `ackAll=true` "
            "after relaying to mark items as handled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "includeRelayed": {
                    "type": "boolean",
                    "default": False,
                },
                "detectExternalUiTurns": {
                    "type": "boolean",
                    "default": True,
                    "description": "Also surface threads updated directly inside Codex Desktop UI since last check.",
                },
                "ackIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of `relayId` or `threadId` values to mark as relayed to the user.",
                },
                "ackAll": {
                    "type": "boolean",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "codex_bridge_digest_thread",
        "description": (
            "Produce a structured Commander Relay verification digest (`commanderRelay`) for any Codex thread, "
            "extracting latest prompt, verbatim reply, reasoning, failed commands, and follow-up questions so "
            "Antigravity can accurately translate and relay Codex's work to the user."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {
                    "type": "string",
                    "description": "Full UUID or unique prefix of the Codex thread.",
                }
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "codex_bridge_quota_and_models",
        "description": "Query live Codex account rate-limit windows (used/remaining %, reset time) and available model catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "includeModels": {
                    "type": "boolean",
                    "default": True,
                }
            },
        },
    },
    {
        "name": "codex_bridge_doctor",
        "description": "Run an 8-point diagnostic check on Python, Codex CLI/Desktop binary, auth, SQLite state, and app-server RPC.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "codex_bridge_list_projects",
        "description": "List Codex Desktop UI projects enriched with root paths, thread counts, token usage, and recent activity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "includeEmpty": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "default": 40},
            },
        },
    },
    {
        "name": "codex_bridge_list_threads",
        "description": "List Codex conversation threads filtered by project, visibility/source, or search keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "sourceFilter": {
                    "type": "string",
                    "enum": ["ui", "exec", "ui_and_exec", "subagent", "all"],
                    "default": "ui_and_exec",
                },
                "search": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "codex_bridge_read_thread",
        "description": "Read verbatim user prompts, reasoning summaries, executed shell commands/tool calls, outputs, and subagents from any Codex session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string"},
                "maxMessages": {"type": "integer", "default": 20},
                "maxCommands": {"type": "integer", "default": 25},
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "codex_bridge_export_report",
        "description": "Export any existing Codex conversation thread into a clean, shareable standalone Markdown report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string"},
                "outputPath": {"type": "string"},
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "codex_bridge_create_thread",
        "description": (
            "Create a brand-new native Codex Desktop UI conversation (`source='vscode'`, `originator='Codex Desktop'`) "
            "under a target Project or directory without manual user action."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "title": {"type": "string"},
                "sandbox": {
                    "type": "string",
                    "enum": ["read-only", "workspace-write", "danger-full-access"],
                    "default": "read-only",
                },
                "model": {"type": "string"},
            },
        },
    },
    {
        "name": "codex_bridge_fork_thread",
        "description": (
            "Fork/branch an existing Codex session (`thread/fork`) into a new independent UI-visible thread "
            "preserving prior context while keeping the original session untouched."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string"},
                "title": {"type": "string"},
                "project": {"type": "string"},
                "sandbox": {
                    "type": "string",
                    "enum": ["read-only", "workspace-write", "danger-full-access"],
                    "default": "read-only",
                },
                "model": {"type": "string"},
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "codex_bridge_promote_exec_threads",
        "description": "Promote hidden CLI `source='exec'` threads into UI-visible `source='vscode'` threads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadIds": {"type": "array", "items": {"type": "string"}},
                "project": {"type": "string"},
                "force": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "codex_bridge_open_ui",
        "description": "Launch Codex Desktop UI directly on a target Project or folder (`codex app <path>`).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
            },
        },
    },
]


def _handle_tool_call(name: str, args: dict[str, Any]) -> Any:
    if name == "codex_bridge_overview":
        return engine.get_overview_stats(include_live_quota=bool(args.get("includeLiveQuota", False)))
    if name == "codex_bridge_relay_inbox":
        return engine.check_relay_inbox(
            include_relayed=bool(args.get("includeRelayed", False)),
            detect_external_ui_turns=bool(args.get("detectExternalUiTurns", True)),
            ack_ids=args.get("ackIds"),
            ack_all=bool(args.get("ackAll", False)),
        )
    if name == "codex_bridge_digest_thread":
        return engine.digest_thread_for_relay(args["threadId"])
    if name == "codex_bridge_quota_and_models":
        return engine.get_quota_and_models(include_models=bool(args.get("includeModels", True)))
    if name == "codex_bridge_doctor":
        return engine.run_doctor()
    if name == "codex_bridge_list_projects":
        limit = int(args.get("limit") or 40)
        include_empty = bool(args.get("includeEmpty", True))
        return engine.list_projects(query=args.get("query"), include_empty=include_empty)[:limit]
    if name == "codex_bridge_list_threads":
        return engine.list_threads(
            project=args.get("project"),
            source_filter=args.get("sourceFilter") or "ui_and_exec",
            search=args.get("search"),
            limit=int(args.get("limit") or 20),
        )
    if name == "codex_bridge_read_thread":
        return engine.read_thread(
            thread_id=args["threadId"],
            max_messages=int(args.get("maxMessages") or 20),
            max_commands=int(args.get("maxCommands") or 25),
        )
    if name == "codex_bridge_export_report":
        return engine.export_thread_markdown(
            thread_id=args["threadId"],
            output_file=args.get("outputPath"),
        )
    if name == "codex_bridge_create_thread":
        return engine.create_ui_thread(
            project=args.get("project"),
            cwd=args.get("cwd"),
            title=args.get("title"),
            sandbox=args.get("sandbox") or "read-only",
            model=args.get("model"),
        )
    if name == "codex_bridge_fork_thread":
        return engine.fork_ui_thread(
            thread_id=args["threadId"],
            title=args.get("title"),
            project=args.get("project"),
            sandbox=args.get("sandbox") or "read-only",
            model=args.get("model"),
        )
    if name == "codex_bridge_promote_exec_threads":
        return engine.promote_exec_threads(
            thread_ids=args.get("threadIds"),
            project=args.get("project"),
            force=bool(args.get("force", False)),
        )
    if name == "codex_bridge_open_ui":
        return engine.open_in_desktop_ui(args.get("project"))
    raise ValueError(f"Unknown tool: {name}")


def _write_message(msg: dict[str, Any], use_content_length: bool) -> None:
    raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    if use_content_length:
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header + raw)
    else:
        sys.stdout.buffer.write(raw + b"\n")
    sys.stdout.buffer.flush()


def main() -> None:
    use_content_length = False
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.lower().startswith(b"content-length:"):
            use_content_length = True
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                hdr = sys.stdin.buffer.readline()
                if not hdr or hdr in (b"\r\n", b"\n"):
                    break
            body = sys.stdin.buffer.read(length)
            if not body:
                break
        else:
            body = stripped

        try:
            req = json.loads(body.decode("utf-8"))
        except Exception as e:
            sys.stderr.write(f"[codex-bridge mcp] JSON parse error: {e}\n")
            continue

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        if req_id is None:
            continue

        try:
            if method == "initialize":
                client_proto = params.get("protocolVersion") or "2024-11-05"
                supported = {"2024-11-05", "2025-03-26", "2025-06-18"}
                proto = client_proto if client_proto in supported else "2024-11-05"
                res = {
                    "protocolVersion": proto,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "codex-bridge", "version": "1.2.1"},
                }
                _write_message({"jsonrpc": "2.0", "id": req_id, "result": res}, use_content_length)
            elif method == "ping":
                _write_message({"jsonrpc": "2.0", "id": req_id, "result": {}}, use_content_length)
            elif method == "tools/list":
                _write_message({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}, use_content_length)
            elif method == "tools/call":
                tname = params.get("name", "")
                targs = params.get("arguments") or {}
                try:
                    out = _handle_tool_call(tname, targs)
                    _write_message(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                                "isError": False,
                            },
                        },
                        use_content_length,
                    )
                except Exception as tool_err:
                    _write_message(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": f"Error: {tool_err}"}],
                                "isError": True,
                            },
                        },
                        use_content_length,
                    )
            elif method == "resources/list":
                _write_message({"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}, use_content_length)
            elif method == "prompts/list":
                _write_message({"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}, use_content_length)
            else:
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    },
                    use_content_length,
                )
        except Exception as exc:
            sys.stderr.write(f"[codex-bridge mcp] Unhandled error: {traceback.format_exc()}\n")
            _write_message(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(exc)}},
                use_content_length,
            )


if __name__ == "__main__":
    main()

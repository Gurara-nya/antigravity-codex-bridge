#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core cross-platform orchestration, Commander Relay, & analytics engine for `antigravity-codex-bridge` (v1.2.0).
Zero third-party dependencies (Python 3.11+ standard library only).
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
import pathlib
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import tomllib
import uuid
from typing import Any, Callable, Optional

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_WEB_PORT = int(os.environ.get("CODEX_BRIDGE_WEB_PORT") or 18765)


def get_data_dir() -> pathlib.Path:
    override = os.environ.get("CODEX_BRIDGE_DATA_DIR")
    return pathlib.Path(override) if override else (PLUGIN_ROOT / "data")


def get_logs_dir() -> pathlib.Path:
    return get_data_dir() / "logs"


def get_history_file() -> pathlib.Path:
    return get_data_dir() / "dispatch_history.jsonl"


def get_relay_inbox_file() -> pathlib.Path:
    return get_data_dir() / "relay_inbox.jsonl"


def get_relay_cursor_file() -> pathlib.Path:
    return get_data_dir() / "relay_cursor.json"


def get_pending_assignments_file() -> pathlib.Path:
    return get_data_dir() / "pending_assignments.json"


def codex_home() -> pathlib.Path:
    env_home = os.environ.get("CODEX_HOME")
    return pathlib.Path(env_home) if env_home else (pathlib.Path.home() / ".codex")


def state_db_path() -> pathlib.Path:
    home = codex_home()
    if (home / "state_5.sqlite").is_file():
        return home / "state_5.sqlite"
    candidates = sorted(home.glob("state_*.sqlite"), reverse=True)
    return candidates[0] if candidates else (home / "state_5.sqlite")


def global_state_path() -> pathlib.Path:
    return codex_home() / ".codex-global-state.json"


def config_toml_path() -> pathlib.Path:
    return codex_home() / "config.toml"


def ensure_data_dirs() -> None:
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_logs_dir().mkdir(parents=True, exist_ok=True)


def normalize_fs_path(p: Optional[str]) -> str:
    """Normalize filesystem paths across Windows (stripping \\\\?\\ prefix) and POSIX."""
    if not p:
        return ""
    s = str(p).strip()
    if os.name == "nt" or s.startswith("\\\\?\\") or re.match(r"^[a-zA-Z]:[\\/]", s):
        if s.startswith("\\\\?\\UNC\\"):
            s = "\\\\" + s[8:]
        elif s.startswith("\\\\?\\"):
            s = s[4:]
        s = s.replace("/", "\\")
        if len(s) > 3 and s.endswith("\\"):
            s = s.rstrip("\\")
        return s
    if len(s) > 1 and s.endswith("/"):
        s = s.rstrip("/")
    return s


def norm_key(p: Optional[str]) -> str:
    s = normalize_fs_path(p)
    if os.name == "nt" or re.match(r"^[a-zA-Z]:\\", s):
        return s.lower()
    return s


def path_is_within(child_key: str, parent_key: str) -> bool:
    if not child_key or not parent_key:
        return False
    if child_key == parent_key:
        return True
    sep = "\\" if ("\\" in parent_key or os.name == "nt") else "/"
    return child_key.startswith(parent_key.rstrip(sep) + sep)


def find_codex_exe() -> Optional[str]:
    """Locate the newest runnable `codex` binary across Windows, macOS, and Linux."""
    env_p = os.environ.get("CODEX_CLI_PATH")
    if env_p:
        if pathlib.Path(env_p).is_file():
            return str(pathlib.Path(env_p))
        if os.environ.get("CODEX_BRIDGE_NO_SYSTEM_SEARCH") == "1":
            return None

    cfg_file = config_toml_path()
    if cfg_file.is_file():
        try:
            cfg = tomllib.loads(cfg_file.read_text(encoding="utf-8"))
            cfg_cli = (
                cfg.get("mcp_servers", {})
                .get("node_repl", {})
                .get("env", {})
                .get("CODEX_CLI_PATH")
            )
            if cfg_cli and pathlib.Path(cfg_cli).is_file():
                return str(pathlib.Path(cfg_cli))
        except Exception:
            pass

    if os.environ.get("CODEX_BRIDGE_NO_SYSTEM_SEARCH") == "1":
        return None

    which_p = shutil.which("codex") or shutil.which("codex.exe")
    if which_p:
        return which_p

    sys_name = platform.system()
    home = codex_home()

    if sys_name == "Windows":
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "(Get-AppxPackage OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1).InstallLocation",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            loc = proc.stdout.strip()
            if loc:
                candidate = pathlib.Path(loc) / "app" / "resources" / "codex.exe"
                if candidate.is_file():
                    return str(candidate)
        except Exception:
            pass
        sb_win = home / ".sandbox-bin" / "codex.exe"
        if sb_win.is_file():
            return str(sb_win)

    elif sys_name == "Darwin":
        for c in [
            pathlib.Path("/Applications/Codex.app/Contents/Resources/codex"),
            pathlib.Path.home() / "Applications/Codex.app/Contents/Resources/codex",
            pathlib.Path("/opt/homebrew/bin/codex"),
            pathlib.Path("/usr/local/bin/codex"),
            home / ".sandbox-bin" / "codex",
        ]:
            if c.is_file():
                return str(c)

    else:
        for c in [
            pathlib.Path.home() / ".local/bin/codex",
            pathlib.Path.home() / ".npm-global/bin/codex",
            pathlib.Path("/usr/local/bin/codex"),
            home / ".sandbox-bin" / "codex",
        ]:
            if c.is_file():
                return str(c)

    return None


def get_codex_version(codex_exe: Optional[str] = None) -> str:
    exe = codex_exe or find_codex_exe()
    if not exe:
        return "not-found"
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=5)
        return proc.stdout.strip() or proc.stderr.strip() or "unknown"
    except Exception as e:
        return f"error: {e}"


def is_desktop_running() -> bool:
    """Check whether Codex Desktop Electron UI is currently running."""
    sys_name = platform.system()
    try:
        if sys_name == "Windows":
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "[bool](Get-Process -Name Codex -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*\\app\\Codex.exe' })",
                ],
                capture_output=True,
                text=True,
                timeout=4,
            )
            return proc.stdout.strip().lower() == "true"
        elif sys_name == "Darwin":
            proc = subprocess.run(["pgrep", "-x", "Codex"], capture_output=True, text=True, timeout=3)
            return proc.returncode == 0
        else:
            proc = subprocess.run(["pgrep", "-f", "Codex.app|codex-desktop"], capture_output=True, text=True, timeout=3)
            return proc.returncode == 0
    except Exception:
        return False


def _load_global_state() -> dict[str, Any]:
    gs_file = global_state_path()
    if not gs_file.is_file():
        return {}
    try:
        return json.loads(gs_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_global_state_safely(gs: dict[str, Any]) -> bool:
    gs_file = global_state_path()
    if not gs_file.is_file():
        return False
    home = codex_home()
    bak = home / ".codex-global-state.codex-bridge.bak"
    tmp = home / f".codex-global-state.bridge-tmp-{os.getpid()}.json"
    try:
        shutil.copy2(gs_file, bak)
        tmp.write_text(json.dumps(gs, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, gs_file)
        return True
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        return False


def _queue_pending_assignment(thread_id: str, project_id: str) -> None:
    ensure_data_dirs()
    pf = get_pending_assignments_file()
    pending: dict[str, str] = {}
    if pf.is_file():
        try:
            pending = json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            pending = {}
    pending[thread_id] = project_id
    pf.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_pending_assignments() -> dict[str, Any]:
    pf = get_pending_assignments_file()
    if not pf.is_file():
        return {"synced": 0, "desktopRunning": is_desktop_running()}
    try:
        pending = json.loads(pf.read_text(encoding="utf-8"))
    except Exception:
        return {"synced": 0, "error": "invalid pending_assignments.json"}
    if not pending:
        return {"synced": 0, "desktopRunning": is_desktop_running()}
    if is_desktop_running():
        return {"synced": 0, "pending": len(pending), "desktopRunning": True}

    gs = _load_global_state()
    if not gs:
        return {"synced": 0, "error": "cannot load .codex-global-state.json"}
    tpa = gs.setdefault("thread-project-assignments", {})
    count = 0
    for tid, pid in list(pending.items()):
        tpa[tid] = {"projectKind": "local", "projectId": pid}
        count += 1
    if _save_global_state_safely(gs):
        pf.write_text("{}", encoding="utf-8")
        return {"synced": count, "desktopRunning": False}
    return {"synced": 0, "error": "failed to save global state"}


def assign_thread_to_project(thread_id: str, project_id: Optional[str]) -> dict[str, Any]:
    if not project_id:
        return {"assigned": False, "reason": "no_project_id"}
    if is_desktop_running():
        _queue_pending_assignment(thread_id, project_id)
        return {
            "assigned": False,
            "queued": True,
            "reason": "Codex Desktop is currently open; cwd is already matched and sidebar binding is queued for sync.",
        }
    gs = _load_global_state()
    if not gs:
        return {"assigned": False, "reason": "global_state_missing"}
    tpa = gs.setdefault("thread-project-assignments", {})
    tpa[thread_id] = {"projectKind": "local", "projectId": project_id}
    pf = get_pending_assignments_file()
    if pf.is_file():
        try:
            pending = json.loads(pf.read_text(encoding="utf-8"))
            for k, v in pending.items():
                tpa[k] = {"projectKind": "local", "projectId": v}
            pf.write_text("{}", encoding="utf-8")
        except Exception:
            pass
    ok = _save_global_state_safely(gs)
    return {"assigned": ok, "queued": False, "projectId": project_id}


def _open_ro_db() -> sqlite3.Connection:
    db = state_db_path()
    if not db.is_file():
        raise FileNotFoundError(f"Codex state DB not found: {db}")
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    return con


def classify_source(src: Optional[str]) -> str:
    if not src:
        return "unknown"
    if src in ("vscode", "cli", "appServer"):
        return "ui"
    if src == "exec":
        return "exec"
    if src.startswith("{"):
        return "subagent"
    return src


def fmt_ts(ms_or_sec: Optional[int | float]) -> Optional[str]:
    if not ms_or_sec:
        return None
    val = float(ms_or_sec)
    if val > 1e11:
        val /= 1000.0
    try:
        return dt.datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def fmt_tokens(n: Optional[int]) -> str:
    val = int(n or 0)
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return str(val)


# ---------------------------------------------------------------------------
# Commander Feedback Analyzer & Mandatory Relay Inbox
# ---------------------------------------------------------------------------

QUESTION_PATTERNS = [
    re.compile(r"(?:请问|请确认|需要你确认|请告诉我|你希望|是否需要|能否提供|请选择)[^\n。]{2,120}[？?]"),
    re.compile(r"(?:Could you|Would you like|Please confirm|Please clarify|Should I|Which option)[^\n.]{2,140}\?", re.IGNORECASE),
]


def detect_questions_in_text(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for pat in QUESTION_PATTERNS:
        for m in pat.findall(text):
            cleaned = m.strip()
            if cleaned not in found:
                found.append(cleaned)
    # Also check if the very last non-empty line ends with a question mark
    tail_lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if tail_lines and tail_lines[-1].endswith(("?", "？")) and len(tail_lines[-1]) <= 180:
        if tail_lines[-1] not in found:
            found.append(tail_lines[-1])
    return found[:5]


def build_commander_relay(
    *,
    thread_id: str,
    title: Optional[str],
    project_name: Optional[str],
    cwd: str,
    turn_status: str,
    turn_error: Any,
    final_reply: str,
    commands: list[dict[str, Any]],
    file_changes: list[dict[str, Any]],
    elicited_questions: list[dict[str, Any]],
    blocked_approvals: list[dict[str, Any]],
    raw_report_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    Constructs a structured `commanderRelay` packet so Antigravity ALWAYS verifies,
    translates, and relays Codex's completion or feedback to the user.
    """
    failed_cmds = [
        {"command": c.get("command"), "exitCode": c.get("exitCode")}
        for c in commands
        if c.get("exitCode") not in (None, 0) or c.get("status") in ("failed", "declined")
    ]
    text_questions = detect_questions_in_text(final_reply)

    if turn_error or turn_status in ("failed", "errored", "interrupted"):
        outcome = "turn_failed"
    elif elicited_questions:
        outcome = "needs_clarification"
    elif blocked_approvals:
        outcome = "blocked_by_sandbox"
    elif text_questions and not file_changes:
        outcome = "needs_clarification"
    elif failed_cmds:
        outcome = "completed_with_command_errors"
    else:
        outcome = "completed_clean"

    directives = {
        "completed_clean": (
            "MANDATORY RELAY: Cross-check `filesChanged` and `commands` against `finalReply`, then explain the result "
            "to the user in clear, plain language and attach the verbatim `rawReportPath` link."
        ),
        "completed_with_command_errors": (
            "MANDATORY RELAY: One or more commands exited non-zero (`failedCommands`). Inspect whether Codex recovered "
            "or left an unresolved error; fix/follow-up via `--thread` if trivial, then explain clearly to the user."
        ),
        "needs_clarification": (
            "MANDATORY RELAY: Codex raised follow-up questions (`elicitedQuestions` / `detectedQuestions`). "
            "If answerable from workspace files, answer Codex directly via `dispatch --thread`; otherwise translate "
            "the options into plain language for the user, collect their decision, and resume the thread."
        ),
        "blocked_by_sandbox": (
            "MANDATORY RELAY: Codex requested write/command permissions (`blockedApprovals`) while in `read-only` sandbox. "
            "Review the blocked action, explain what Codex wants to do in plain language, and ask the user whether to re-run with `workspace-write`."
        ),
        "turn_failed": (
            "MANDATORY RELAY: Codex encountered a turn error (`turnError`). Diagnose the cause (e.g., quota, path, or tool error) "
            "and explain clearly to the user with recommended next steps."
        ),
    }

    return {
        "mustRelayViaAntigravity": True,
        "outcome": outcome,
        "threadId": thread_id,
        "title": title,
        "projectName": project_name,
        "cwd": cwd,
        "filesChangedCount": len(file_changes),
        "filesChanged": file_changes[:25],
        "commandsExecutedCount": len(commands),
        "failedCommands": failed_cmds[:10],
        "elicitedQuestions": elicited_questions,
        "detectedQuestions": text_questions,
        "blockedApprovals": blocked_approvals,
        "rawReportPath": raw_report_path,
        "commanderDirective": directives[outcome],
    }


def enqueue_relay_item(relay: dict[str, Any], reply_preview: str) -> str:
    """Record a newly completed or paused Codex turn into the Commander Relay Inbox."""
    ensure_data_dirs()
    relay_id = f"rly_{uuid.uuid4().hex[:10]}"
    entry = {
        "relayId": relay_id,
        "createdAt": dt.datetime.now().isoformat(timespec="seconds"),
        "relayed": False,
        "threadId": relay["threadId"],
        "title": relay.get("title"),
        "projectName": relay.get("projectName"),
        "outcome": relay["outcome"],
        "filesChangedCount": relay.get("filesChangedCount", 0),
        "failedCommandCount": len(relay.get("failedCommands") or []),
        "questions": (relay.get("elicitedQuestions") or []) + (relay.get("detectedQuestions") or []),
        "blockedApprovals": relay.get("blockedApprovals") or [],
        "rawReportPath": relay.get("rawReportPath"),
        "replyPreview": reply_preview[:300],
        "commanderDirective": relay["commanderDirective"],
    }
    with get_relay_inbox_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return relay_id


def check_relay_inbox(
    include_relayed: bool = False,
    detect_external_ui_turns: bool = True,
    ack_ids: Optional[list[str]] = None,
    ack_all: bool = False,
) -> dict[str, Any]:
    """
    Inspect pending Codex completions/feedback awaiting Antigravity's relay to the user,
    optionally acknowledging already-relayed items and detecting new turns from Codex Desktop UI.
    """
    ensure_data_dirs()
    inbox_file = get_relay_inbox_file()
    entries: list[dict[str, Any]] = []
    if inbox_file.is_file():
        for line in inbox_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass

    ack_set = set(ack_ids or [])
    mutated = False
    for e in entries:
        if ack_all or e.get("relayId") in ack_set or e.get("threadId") in ack_set:
            if not e.get("relayed"):
                e["relayed"] = True
                e["relayedAt"] = dt.datetime.now().isoformat(timespec="seconds")
                mutated = True

    if mutated:
        inbox_file.write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in entries),
            encoding="utf-8",
        )

    external_updates: list[dict[str, Any]] = []
    if detect_external_ui_turns and state_db_path().is_file():
        cursor_file = get_relay_cursor_file()
        last_seen_ms = 0
        if cursor_file.is_file():
            try:
                last_seen_ms = int(json.loads(cursor_file.read_text(encoding="utf-8")).get("lastSeenUpdatedMs") or 0)
            except Exception:
                last_seen_ms = 0

        recent_ui = list_threads(source_filter="ui", limit=10)
        newest_ms = max((t["updatedAtMs"] for t in recent_ui), default=last_seen_ms)
        if last_seen_ms == 0:
            # Initialize watermark on first check
            cursor_file.write_text(json.dumps({"lastSeenUpdatedMs": newest_ms}), encoding="utf-8")
        else:
            known_tids = {e.get("threadId") for e in entries if not e.get("relayed")}
            for t in recent_ui:
                if t["updatedAtMs"] > last_seen_ms and t["id"] not in known_tids:
                    external_updates.append(
                        {
                            "threadId": t["id"],
                            "title": t["title"],
                            "projectName": t["projectName"],
                            "updatedAt": t["updatedAt"],
                            "note": "Updated externally in Codex Desktop UI; call `codex_bridge_digest_thread` to inspect and relay to the user.",
                        }
                    )
            if ack_all and newest_ms > last_seen_ms:
                cursor_file.write_text(json.dumps({"lastSeenUpdatedMs": newest_ms}), encoding="utf-8")

    filtered = entries if include_relayed else [e for e in entries if not e.get("relayed")]
    filtered.reverse()
    return {
        "pendingCount": sum(1 for e in entries if not e.get("relayed")),
        "externalUiUpdatesCount": len(external_updates),
        "items": filtered[:30],
        "externalUiUpdates": external_updates,
    }


def digest_thread_for_relay(thread_id: str) -> dict[str, Any]:
    """
    Generate a structured `commanderRelay` verification digest from any existing Codex session
    (ideal for relaying tasks executed in Codex Desktop UI or Web Console).
    """
    detail = read_thread(thread_id, max_messages=12, max_commands=30)
    msgs = detail.get("recentMessages") or []
    last_assistant = ""
    last_user = ""
    for m in reversed(msgs):
        if m["role"] == "assistant" and not last_assistant:
            last_assistant = m["text"]
        elif m["role"] == "user" and not last_user:
            last_user = m["text"]

    pseudo_cmds = []
    for tc in detail.get("recentToolCalls") or []:
        out_prev = tc.get("outputPreview") or ""
        failed = ("Exit code: 1" in out_prev) or ("Traceback" in out_prev) or ("error:" in out_prev.lower()[:200])
        pseudo_cmds.append(
            {
                "command": f"{tc.get('tool')}: {str(tc.get('input'))[:200]}",
                "exitCode": 1 if failed else 0,
                "status": "failed" if failed else "completed",
            }
        )

    relay = build_commander_relay(
        thread_id=detail["id"],
        title=detail["title"],
        project_name=None,
        cwd=detail["cwd"],
        turn_status="completed",
        turn_error=None,
        final_reply=last_assistant,
        commands=pseudo_cmds,
        file_changes=[],
        elicited_questions=[],
        blocked_approvals=[],
    )
    return {
        "thread": {
            "id": detail["id"],
            "title": detail["title"],
            "cwd": detail["cwd"],
            "model": detail["model"],
            "tokensFormatted": detail["tokensFormatted"],
            "updatedAt": detail["updatedAt"],
        },
        "lastUserPrompt": last_user,
        "lastAssistantReply": last_assistant,
        "recentReasoning": detail.get("recentReasoning") or [],
        "recentToolCalls": (detail.get("recentToolCalls") or [])[-10:],
        "subagents": detail.get("subagents") or [],
        "commanderRelay": relay,
    }


# ---------------------------------------------------------------------------
# Projects & Threads Queries
# ---------------------------------------------------------------------------


def list_projects(query: Optional[str] = None, include_empty: bool = True) -> list[dict[str, Any]]:
    """Return Codex Desktop UI projects enriched with live thread & token statistics."""
    sync_pending_assignments()
    gs = _load_global_state()
    local_projects: dict[str, Any] = gs.get("local-projects", {}) or {}
    tpa: dict[str, Any] = gs.get("thread-project-assignments", {}) or {}
    pinned_pids = set(gs.get("pinned-project-ids", []) or [])

    projects_by_id: dict[str, dict[str, Any]] = {}
    root_to_pid: dict[str, str] = {}

    for pid, pinfo in local_projects.items():
        if not isinstance(pinfo, dict):
            continue
        roots = [normalize_fs_path(r) for r in (pinfo.get("rootPaths") or []) if r]
        projects_by_id[pid] = {
            "id": pid,
            "name": pinfo.get("name") or (pathlib.Path(roots[0]).name if roots else pid),
            "rootPaths": roots,
            "primaryPath": roots[0] if roots else "",
            "pinned": pid in pinned_pids,
            "source": "desktop_ui",
            "uiThreadCount": 0,
            "execThreadCount": 0,
            "subagentCount": 0,
            "totalTokens": 0,
            "models": {},
            "lastActiveMs": int(pinfo.get("updatedAt") or pinfo.get("createdAt") or 0),
        }
        for r in roots:
            root_to_pid[norm_key(r)] = pid

    db = state_db_path()
    if db.is_file():
        con = _open_ro_db()
        try:
            cur = con.cursor()
            tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "projects" in tables and "project_roots" in tables:
                for row in cur.execute(
                    "SELECT p.id, p.name, p.updated_at_ms, r.path FROM projects p LEFT JOIN project_roots r ON p.id = r.project_id"
                ):
                    rpath = normalize_fs_path(row["path"])
                    rk = norm_key(rpath)
                    if rk and rk in root_to_pid:
                        continue
                    pid = row["id"]
                    if pid not in projects_by_id:
                        projects_by_id[pid] = {
                            "id": pid,
                            "name": row["name"] or (pathlib.Path(rpath).name if rpath else pid),
                            "rootPaths": [rpath] if rpath else [],
                            "primaryPath": rpath,
                            "pinned": pid in pinned_pids,
                            "source": "sqlite",
                            "uiThreadCount": 0,
                            "execThreadCount": 0,
                            "subagentCount": 0,
                            "totalTokens": 0,
                            "models": {},
                            "lastActiveMs": int(row["updated_at_ms"] or 0),
                        }
                        if rk:
                            root_to_pid[rk] = pid
                    elif rpath and rpath not in projects_by_id[pid]["rootPaths"]:
                        projects_by_id[pid]["rootPaths"].append(rpath)
                        root_to_pid[rk] = pid

            if "threads" in tables:
                for trow in cur.execute(
                    "SELECT id, cwd, source, tokens_used, model, updated_at_ms, archived FROM threads WHERE COALESCE(archived, 0) = 0"
                ):
                    tid = trow["id"]
                    cwd_norm = normalize_fs_path(trow["cwd"])
                    ck = norm_key(cwd_norm)

                    assigned = tpa.get(tid)
                    pid = assigned.get("projectId") if isinstance(assigned, dict) else None
                    if not pid or pid not in projects_by_id:
                        pid = root_to_pid.get(ck)
                    if not pid and ck:
                        for rk, candidate_pid in root_to_pid.items():
                            if path_is_within(ck, rk):
                                pid = candidate_pid
                                break
                    if not pid or pid not in projects_by_id:
                        continue

                    p = projects_by_id[pid]
                    kind = classify_source(trow["source"])
                    if kind == "ui":
                        p["uiThreadCount"] += 1
                    elif kind == "exec":
                        p["execThreadCount"] += 1
                    elif kind == "subagent":
                        p["subagentCount"] += 1
                    tok = int(trow["tokens_used"] or 0)
                    p["totalTokens"] += tok
                    mdl = trow["model"] or "unknown"
                    if kind != "subagent":
                        p["models"][mdl] = p["models"].get(mdl, 0) + 1
                    ums = int(trow["updated_at_ms"] or 0)
                    if ums > p["lastActiveMs"]:
                        p["lastActiveMs"] = ums
        finally:
            con.close()

    results = []
    q = (query or "").strip().lower()
    for p in projects_by_id.values():
        if not include_empty and (p["uiThreadCount"] + p["execThreadCount"]) == 0:
            continue
        if q:
            hay = " ".join([p["id"], p["name"], " ".join(p["rootPaths"])]).lower()
            if q not in hay:
                continue
        top_models = sorted(p["models"].items(), key=lambda kv: kv[1], reverse=True)
        results.append(
            {
                "id": p["id"],
                "name": p["name"],
                "primaryPath": p["primaryPath"],
                "rootPaths": p["rootPaths"],
                "pinned": p["pinned"],
                "source": p["source"],
                "uiThreadCount": p["uiThreadCount"],
                "execThreadCount": p["execThreadCount"],
                "subagentCount": p["subagentCount"],
                "totalTokens": p["totalTokens"],
                "totalTokensFormatted": fmt_tokens(p["totalTokens"]),
                "topModels": [m for m, _ in top_models[:3]],
                "lastActiveMs": p["lastActiveMs"],
                "lastActiveFormatted": fmt_ts(p["lastActiveMs"]),
            }
        )

    results.sort(key=lambda x: (1 if x["pinned"] else 0, x["lastActiveMs"], x["uiThreadCount"]), reverse=True)
    return results


def resolve_project(target: Optional[str]) -> dict[str, Any]:
    """Resolve a project name, project ID, or filesystem path to `{projectId, projectName, cwd, matched}`."""
    if not target:
        fallback = str(pathlib.Path.cwd())
        return {"projectId": None, "projectName": None, "cwd": fallback, "matched": False}

    raw = target.strip()
    all_projects = list_projects(include_empty=True)

    for p in all_projects:
        if p["id"].lower() == raw.lower() or p["name"].lower() == raw.lower():
            cwd = p["primaryPath"] or str(pathlib.Path.home())
            return {"projectId": p["id"], "projectName": p["name"], "cwd": cwd, "matched": True}

    rk = norm_key(raw)
    if ":" in raw or "\\" in raw or "/" in raw:
        best_match = None
        best_len = -1
        for p in all_projects:
            for root in p["rootPaths"]:
                root_k = norm_key(root)
                if path_is_within(rk, root_k) and len(root_k) > best_len:
                    best_len = len(root_k)
                    best_match = p
        norm_dir = normalize_fs_path(raw)
        if best_match:
            use_cwd = norm_dir if pathlib.Path(norm_dir).is_dir() else (best_match["primaryPath"] or norm_dir)
            return {
                "projectId": best_match["id"],
                "projectName": best_match["name"],
                "cwd": use_cwd,
                "matched": True,
            }
        if pathlib.Path(norm_dir).exists():
            return {
                "projectId": None,
                "projectName": pathlib.Path(norm_dir).name,
                "cwd": norm_dir,
                "matched": False,
            }

    candidates = [p for p in all_projects if raw.lower() in p["name"].lower()]
    if not candidates:
        candidates = [p for p in all_projects if any(raw.lower() in r.lower() for r in p["rootPaths"])]
    if candidates:
        chosen = candidates[0]
        return {
            "projectId": chosen["id"],
            "projectName": chosen["name"],
            "cwd": chosen["primaryPath"] or str(pathlib.Path.home()),
            "matched": True,
            "alternatives": [c["name"] for c in candidates[1:5]],
        }

    raise ValueError(
        f"Could not match project or existing directory for '{target}'. Call `codex_bridge_list_projects` to inspect available projects."
    )


def list_threads(
    project: Optional[str] = None,
    source_filter: str = "ui_and_exec",
    search: Optional[str] = None,
    limit: int = 25,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """List Codex threads with resolved Project names, token usage, and visibility status."""
    sync_pending_assignments()
    if not state_db_path().is_file():
        return []
    gs = _load_global_state()
    tpa = gs.get("thread-project-assignments", {}) or {}
    projects = list_projects(include_empty=True)
    proj_by_id = {p["id"]: p for p in projects}
    root_to_proj: dict[str, dict[str, Any]] = {}
    for p in projects:
        for r in p["rootPaths"]:
            root_to_proj[norm_key(r)] = p

    target_proj_id: Optional[str] = None
    target_cwd_key: Optional[str] = None
    if project:
        resolved = resolve_project(project)
        target_proj_id = resolved.get("projectId")
        target_cwd_key = norm_key(resolved.get("cwd"))

    con = _open_ro_db()
    try:
        cur = con.cursor()
        sql = """
            SELECT id, cwd, title, name, preview, first_user_message, source, thread_source,
                   originator, model, reasoning_effort, tokens_used, sandbox_policy,
                   created_at_ms, updated_at_ms, archived, rollout_path
            FROM threads
        """
        conds = []
        if not include_archived:
            conds.append("COALESCE(archived, 0) = 0")
        if source_filter == "ui":
            conds.append("source IN ('vscode', 'cli', 'appServer')")
        elif source_filter == "exec":
            conds.append("source = 'exec'")
        elif source_filter == "ui_and_exec":
            conds.append("source NOT LIKE '{%'")
        elif source_filter == "subagent":
            conds.append("source LIKE '{%'")

        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY updated_at_ms DESC"

        out: list[dict[str, Any]] = []
        q = (search or "").strip().lower()

        for row in cur.execute(sql):
            tid = row["id"]
            cwd_norm = normalize_fs_path(row["cwd"])
            ck = norm_key(cwd_norm)

            assigned = tpa.get(tid)
            pid = assigned.get("projectId") if isinstance(assigned, dict) else None
            pobj = proj_by_id.get(pid) if pid else root_to_proj.get(ck)
            if not pobj and ck:
                for rk, cand_p in root_to_proj.items():
                    if path_is_within(ck, rk):
                        pobj = cand_p
                        break

            if project:
                match_pid = pobj and target_proj_id and pobj["id"] == target_proj_id
                match_cwd = bool(target_cwd_key and path_is_within(ck, target_cwd_key))
                if not (match_pid or match_cwd):
                    continue

            display_title = (row["name"] or row["title"] or row["preview"] or row["first_user_message"] or "(Untitled)").strip()
            display_title = re.sub(r"\s+", " ", display_title)[:140]

            if q:
                hay = " ".join(
                    [
                        tid,
                        display_title,
                        cwd_norm,
                        pobj["name"] if pobj else "",
                        str(row["first_user_message"] or ""),
                        str(row["preview"] or ""),
                    ]
                ).lower()
                if q not in hay:
                    continue

            kind = classify_source(row["source"])
            out.append(
                {
                    "id": tid,
                    "title": display_title,
                    "customName": row["name"],
                    "projectId": pobj["id"] if pobj else None,
                    "projectName": pobj["name"] if pobj else (pathlib.Path(cwd_norm).name if cwd_norm else "Unassigned"),
                    "cwd": cwd_norm,
                    "source": row["source"],
                    "visibility": "visible_in_ui" if kind == "ui" else ("hidden_exec" if kind == "exec" else kind),
                    "originator": row["originator"],
                    "model": row["model"],
                    "reasoningEffort": row["reasoning_effort"],
                    "tokensUsed": int(row["tokens_used"] or 0),
                    "tokensFormatted": fmt_tokens(row["tokens_used"]),
                    "updatedAtMs": int(row["updated_at_ms"] or 0),
                    "updatedAt": fmt_ts(row["updated_at_ms"]),
                    "createdAt": fmt_ts(row["created_at_ms"]),
                    "rolloutPath": row["rollout_path"],
                }
            )
            if len(out) >= limit:
                break
        return out
    finally:
        con.close()


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text") or item.get("output_text") or item.get("input_text")
                if t:
                    parts.append(str(t))
                elif item.get("type") in ("input_image", "image"):
                    parts.append(f"[Image: {item.get('image_url') or item.get('path') or 'attached'}]")
        return "\n".join(parts)
    return ""


def read_thread(
    thread_id: str,
    max_messages: int = 20,
    max_commands: int = 30,
    max_chars_per_item: int = 4000,
) -> dict[str, Any]:
    """Read verbatim messages, reasoning summaries, tool/command executions, and subagents of any thread."""
    con = _open_ro_db()
    try:
        cur = con.cursor()
        q_tid = thread_id.strip()
        row = cur.execute("SELECT * FROM threads WHERE id = ?", (q_tid,)).fetchone()
        if not row:
            row = cur.execute(
                "SELECT * FROM threads WHERE id LIKE ? ORDER BY updated_at_ms DESC LIMIT 1",
                (q_tid + "%",),
            ).fetchone()
        if not row:
            raise ValueError(f"Thread '{thread_id}' not found in Codex database.")

        full_id = row["id"]
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        subagents = []
        if "thread_spawn_edges" in tables:
            subagents = [
                dict(r)
                for r in cur.execute(
                    """
                    SELECT e.child_thread_id, e.status, t.agent_nickname, t.agent_role, t.title, t.tokens_used
                    FROM thread_spawn_edges e
                    LEFT JOIN threads t ON t.id = e.child_thread_id
                    WHERE e.parent_thread_id = ?
                    """,
                    (full_id,),
                ).fetchall()
            ]
    finally:
        con.close()

    rollout_path = pathlib.Path(row["rollout_path"]) if row["rollout_path"] else None
    messages: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    reasoning_summaries: list[str] = []
    call_outputs: dict[str, str] = {}
    pending_calls: list[dict[str, Any]] = []

    if rollout_path and rollout_path.is_file():
        with rollout_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                etype = ev.get("type")
                payload = ev.get("payload")
                ts = ev.get("timestamp")
                if not isinstance(payload, dict):
                    continue

                if etype == "response_item":
                    ptype = payload.get("type")
                    if ptype == "message":
                        role = payload.get("role", "unknown")
                        if role in ("user", "assistant"):
                            txt = _extract_message_text(payload.get("content")).strip()
                            if txt and not (role == "user" and txt.startswith("<environment_context>") and len(txt) < 1500):
                                if len(txt) > max_chars_per_item:
                                    txt = txt[:max_chars_per_item] + f"\n... [truncated {len(txt) - max_chars_per_item} chars]"
                                messages.append({"role": role, "text": txt, "timestamp": ts})
                    elif ptype == "reasoning":
                        for s in payload.get("summary") or []:
                            if isinstance(s, dict) and s.get("text"):
                                reasoning_summaries.append(str(s["text"]).strip())
                    elif ptype in ("function_call", "custom_tool_call"):
                        cid = payload.get("call_id") or ""
                        name = payload.get("name") or ptype
                        raw_args = payload.get("arguments") or payload.get("input") or ""
                        if not isinstance(raw_args, str):
                            raw_args = json.dumps(raw_args, ensure_ascii=False)
                        pending_calls.append(
                            {
                                "callId": cid,
                                "tool": name,
                                "input": raw_args[:1200],
                                "timestamp": ts,
                            }
                        )
                    elif ptype in ("function_call_output", "custom_tool_call_output"):
                        cid = payload.get("call_id") or ""
                        out_body = payload.get("output")
                        if not isinstance(out_body, str):
                            out_body = _extract_message_text(out_body) or json.dumps(out_body, ensure_ascii=False)
                        call_outputs[cid] = out_body[:1500]

        for c in pending_calls:
            c["outputPreview"] = call_outputs.get(c["callId"], "")
            commands.append(c)

    cwd_norm = normalize_fs_path(row["cwd"])
    return {
        "id": full_id,
        "title": row["name"] or row["title"] or row["preview"] or "(Untitled)",
        "cwd": cwd_norm,
        "source": row["source"],
        "visibility": "visible_in_ui" if classify_source(row["source"]) == "ui" else classify_source(row["source"]),
        "originator": row["originator"],
        "model": row["model"],
        "reasoningEffort": row["reasoning_effort"],
        "tokensUsed": int(row["tokens_used"] or 0),
        "tokensFormatted": fmt_tokens(row["tokens_used"]),
        "createdAt": fmt_ts(row["created_at_ms"]),
        "updatedAt": fmt_ts(row["updated_at_ms"]),
        "rolloutPath": str(rollout_path) if rollout_path else None,
        "totalMessages": len(messages),
        "totalToolCalls": len(commands),
        "recentMessages": messages[-max_messages:],
        "recentReasoning": reasoning_summaries[-10:],
        "recentToolCalls": commands[-max_commands:],
        "subagents": subagents,
    }


def export_thread_markdown(thread_id: str, output_file: Optional[str] = None) -> dict[str, Any]:
    """Export any Codex thread into a standalone, human-readable Markdown report."""
    ensure_data_dirs()
    data = read_thread(thread_id, max_messages=100, max_commands=100, max_chars_per_item=12000)
    tid = data["id"]
    out_path = pathlib.Path(output_file) if output_file else (get_logs_dir() / f"export_{tid[:8]}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Codex Session Transcript — {data['title']}",
        "",
        f"- **Thread UUID**: `{tid}`",
        f"- **Workspace (`cwd`)**: `{data['cwd']}`",
        f"- **Model**: `{data['model']}` (effort: `{data['reasoningEffort'] or 'default'}`)",
        f"- **Tokens Used**: `{data['tokensFormatted']}` ({data['tokensUsed']:,})",
        f"- **Created / Updated**: `{data['createdAt']}` / `{data['updatedAt']}`",
        f"- **Messages / Tool Calls**: `{data['totalMessages']}` / `{data['totalToolCalls']}`",
        "",
        "---",
        "",
        "## Conversation Turns",
        "",
    ]
    for idx, m in enumerate(data["recentMessages"], 1):
        role_hdr = "User Prompt" if m["role"] == "user" else "Codex Assistant"
        lines.append(f"### {idx}. {role_hdr} ({m.get('timestamp') or ''})")
        lines.append("")
        lines.append(m["text"])
        lines.append("")

    if data["recentToolCalls"]:
        lines.extend(["---", "", "## Executed Commands & Tool Calls", ""])
        for idx, c in enumerate(data["recentToolCalls"], 1):
            lines.append(f"### Tool #{idx}: `{c['tool']}`")
            lines.append(f"```text\n{c['input']}\n```")
            if c.get("outputPreview"):
                lines.append(f"**Output Preview:**\n```text\n{c['outputPreview']}\n```")
            lines.append("")

    content = "\n".join(lines)
    out_path.write_text(content, encoding="utf-8")
    return {
        "threadId": tid,
        "title": data["title"],
        "outputPath": str(out_path),
        "bytes": len(content.encode("utf-8")),
    }


def get_dispatch_history(limit: int = 30) -> list[dict[str, Any]]:
    hf = get_history_file()
    if not hf.is_file():
        return []
    items: list[dict[str, Any]] = []
    try:
        for line in hf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                items.append(json.loads(line))
    except Exception:
        pass
    return list(reversed(items[-limit:]))


class AppServerClient:
    """
    JSON-RPC 2.0 client over `codex app-server --stdio` declaring `clientInfo.name = "Codex Desktop"`.
    Intercepts mid-turn `request_user_input` questions and sandbox approval escalations so every
    feedback item routes cleanly back through Antigravity Commander.
    """

    def __init__(self, codex_exe: Optional[str] = None, sandbox_mode: str = "read-only"):
        self.exe = codex_exe or find_codex_exe()
        if not self.exe:
            raise RuntimeError("codex executable not found on this machine.")
        self.sandbox_mode = sandbox_mode
        self.proc: Optional[subprocess.Popen[str]] = None
        self._next_id = 0
        self.notifications: list[dict[str, Any]] = []
        self.elicited_questions: list[dict[str, Any]] = []
        self.blocked_approvals: list[dict[str, Any]] = []
        self.approval_events: list[dict[str, Any]] = []

    def __enter__(self) -> "AppServerClient":
        self.proc = subprocess.Popen(
            [self.exe, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "Codex Desktop",
                    "title": "Codex Desktop",
                    "version": "1.2.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def handle_server_callback(self, msg: dict[str, Any]) -> None:
        """
        Handle server-to-client requests (`item/tool/requestUserInput`, approvals, etc.)
        so Codex feedback & permission boundaries always route back to Antigravity Commander.
        """
        req_id = msg["id"]
        method = msg.get("method", "")
        params = msg.get("params") or {}

        # 1. Codex calls `request_user_input` mid-turn -> capture structured questions for Antigravity to relay!
        if method == "item/tool/requestUserInput":
            questions = params.get("questions") or []
            answers_payload: dict[str, Any] = {}
            for q in questions:
                if isinstance(q, dict) and q.get("id"):
                    self.elicited_questions.append(
                        {
                            "id": q.get("id"),
                            "header": q.get("header"),
                            "question": q.get("question"),
                            "options": q.get("options") or [],
                        }
                    )
                    answers_payload[q["id"]] = {
                        "answers": [
                            "[Deferred to Antigravity Commander: conclude safe read-only analysis now and summarize the exact options/inputs needed so Antigravity can consult the user and resume this session.]"
                        ]
                    }
            self._send({"jsonrpc": "2.0", "id": req_id, "result": {"answers": answers_payload}})
            return

        # 2. Command / FileChange / Permissions approval callbacks -> enforce sandbox boundary!
        if method in (
            "item/commandExecution/requestApproval",
            "execCommandApproval",
            "item/fileChange/requestApproval",
            "applyPatchApproval",
            "item/permissions/requestApproval",
        ):
            is_readonly = self.sandbox_mode in ("read-only", "readOnly")
            detail = {
                "method": method,
                "command": params.get("command"),
                "reason": params.get("reason"),
                "grantRoot": params.get("grantRoot"),
            }
            if is_readonly:
                self.blocked_approvals.append(detail)
                if method == "item/permissions/requestApproval":
                    self._send({"jsonrpc": "2.0", "id": req_id, "result": {"permissions": {}, "scope": "turn"}})
                else:
                    self._send({"jsonrpc": "2.0", "id": req_id, "result": {"decision": "decline"}})
            else:
                self.approval_events.append(detail)
                if method == "item/permissions/requestApproval":
                    self._send(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {"permissions": params.get("permissions") or {}, "scope": "turn"},
                        }
                    )
                else:
                    self._send({"jsonrpc": "2.0", "id": req_id, "result": {"decision": "accept"}})
            return

        # 3. MCP form elicitation fallback
        if method == "mcpServer/elicitation/request":
            self.elicited_questions.append({"id": "mcp_elicitation", "question": str(params.get("message") or params)})
            self._send({"jsonrpc": "2.0", "id": req_id, "result": {"action": "cancel"}})
            return

        self._send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unsupported callback: {method}"}})

    def request(
        self,
        method: str,
        params: dict[str, Any],
        on_notification: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        assert self.proc and self.proc.stdout
        self._next_id += 1
        req_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

        while True:
            line = self.proc.stdout.readline()
            if not line:
                stderr_tail = ""
                if self.proc.stderr:
                    try:
                        stderr_tail = self.proc.stderr.read()[-800:]
                    except Exception:
                        pass
                raise RuntimeError(f"codex app-server closed unexpectedly while waiting for {method}. {stderr_tail}")
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("id") == req_id and ("result" in msg or "error" in msg):
                if "error" in msg:
                    raise RuntimeError(f"RPC {method} error: {json.dumps(msg['error'], ensure_ascii=False)}")
                return msg["result"]
            if "id" in msg and "method" in msg:
                self.handle_server_callback(msg)
                continue
            if "method" in msg:
                self.notifications.append(msg)
                if on_notification:
                    on_notification(msg["method"], msg.get("params") or {})

    def stream_until_turn_complete(
        self,
        thread_id: str,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        assert self.proc and self.proc.stdout
        agent_chunks: list[str] = []
        completed_messages: list[str] = []
        commands_ran: list[dict[str, Any]] = []
        file_changes: list[dict[str, Any]] = []
        mcp_calls: list[dict[str, Any]] = []
        plan_steps: list[dict[str, Any]] = []
        reasoning_chunks: list[str] = []
        token_usage: dict[str, Any] = {}
        turn_result: dict[str, Any] = {}

        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if "id" in msg and "method" in msg:
                self.handle_server_callback(msg)
                continue

            method = msg.get("method", "")
            params = msg.get("params") or {}

            if method == "item/agentMessage/delta":
                agent_chunks.append(params.get("delta") or "")
            elif method == "item/reasoning/summaryTextDelta":
                reasoning_chunks.append(params.get("delta") or "")
            elif method == "turn/plan/updated":
                plan_steps = params.get("plan") or plan_steps
            elif method == "item/started":
                item = params.get("item") or {}
                itype = item.get("type")
                if itype == "commandExecution" and on_progress:
                    on_progress(f"[Codex Command] {item.get('command', '')}")
                elif itype == "fileChange" and on_progress:
                    on_progress("[Codex FileEdit] Applying patch...")
                elif itype == "mcpToolCall" and on_progress:
                    on_progress(f"[Codex MCP] {item.get('server', '')}.{item.get('tool', '')}")
            elif method == "item/completed":
                item = params.get("item") or {}
                itype = item.get("type")
                if itype == "agentMessage":
                    txt = item.get("text") or ""
                    if txt:
                        completed_messages.append(txt)
                elif itype == "commandExecution":
                    commands_ran.append(
                        {
                            "command": item.get("command"),
                            "status": item.get("status"),
                            "exitCode": item.get("exitCode"),
                            "aggregatedOutput": (item.get("aggregatedOutput") or "")[:2000],
                        }
                    )
                elif itype == "fileChange":
                    for ch in item.get("changes") or []:
                        if isinstance(ch, dict):
                            file_changes.append(
                                {
                                    "path": ch.get("path"),
                                    "kind": ch.get("kind"),
                                    "status": item.get("status"),
                                }
                            )
                elif itype == "mcpToolCall":
                    mcp_calls.append(
                        {
                            "server": item.get("server"),
                            "tool": item.get("tool"),
                            "status": item.get("status"),
                        }
                    )
            elif method == "thread/tokenUsage/updated":
                token_usage = params.get("tokenUsage") or token_usage
            elif method == "error":
                err_msg = params.get("error", {}).get("message") if isinstance(params.get("error"), dict) else str(params)
                if on_progress:
                    on_progress(f"[Codex Warning/Error] {err_msg}")
            elif method == "turn/completed":
                if params.get("threadId") == thread_id or not params.get("threadId"):
                    turn_result = params.get("turn") or {}
                    break

        final_text = completed_messages[-1] if completed_messages else "".join(agent_chunks)
        return {
            "finalReply": final_text.strip(),
            "allMessages": completed_messages,
            "reasoningSummary": "".join(reasoning_chunks).strip(),
            "commands": commands_ran,
            "fileChanges": file_changes,
            "mcpCalls": mcp_calls,
            "planSteps": plan_steps,
            "elicitedQuestions": list(self.elicited_questions),
            "blockedApprovals": list(self.blocked_approvals),
            "tokenUsage": token_usage,
            "turnStatus": turn_result.get("status", "completed"),
            "turnError": turn_result.get("error"),
        }


def get_quota_and_models(include_models: bool = True) -> dict[str, Any]:
    """Query live rate-limit windows, remaining quota %, and available models via `codex app-server`."""
    exe = find_codex_exe()
    if not exe:
        return {"available": False, "error": "codex executable not found"}
    try:
        with AppServerClient(exe) as client:
            rl_raw = client.request("account/rateLimits/read", {})
            models_out: list[dict[str, Any]] = []
            if include_models:
                m_raw = client.request("model/list", {})
                for m in m_raw.get("data") or []:
                    if isinstance(m, dict):
                        models_out.append(
                            {
                                "id": m.get("id") or m.get("model"),
                                "displayName": m.get("displayName") or m.get("id"),
                                "description": m.get("description"),
                                "defaultReasoningEffort": m.get("defaultReasoningEffort"),
                                "supportedReasoningEfforts": [
                                    e.get("reasoningEffort") if isinstance(e, dict) else e
                                    for e in (m.get("supportedReasoningEfforts") or [])
                                ],
                            }
                        )

        rl = rl_raw.get("rateLimits") or {}
        primary = rl.get("primary") or {}
        secondary = rl.get("secondary") or {}
        used_pct = primary.get("usedPercent")
        resets_at = primary.get("resetsAt")
        resets_in_hours = round((float(resets_at) - time.time()) / 3600.0, 1) if resets_at else None

        return {
            "available": True,
            "ordinaryUsageAllowed": rl_raw.get("ordinaryUsageAllowed", True),
            "primaryWindow": {
                "usedPercent": used_pct,
                "remainingPercent": (100 - int(used_pct)) if used_pct is not None else None,
                "windowDurationMins": primary.get("windowDurationMins"),
                "resetsAt": fmt_ts(resets_at),
                "resetsInHours": resets_in_hours,
            }
            if primary
            else None,
            "secondaryWindow": {
                "usedPercent": secondary.get("usedPercent"),
                "windowDurationMins": secondary.get("windowDurationMins"),
                "resetsAt": fmt_ts(secondary.get("resetsAt")),
            }
            if secondary
            else None,
            "credits": rl.get("credits"),
            "models": models_out,
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def get_overview_stats(include_live_quota: bool = False) -> dict[str, Any]:
    """Compute comprehensive usage, project, model, timeline, inbox, and bridge dispatch statistics."""
    codex_exe = find_codex_exe()
    version = get_codex_version(codex_exe)
    desktop_open = is_desktop_running()
    projects = list_projects(include_empty=True)
    inbox_summary = check_relay_inbox(include_relayed=False, detect_external_ui_turns=False)

    stats: dict[str, Any] = {
        "codexExe": codex_exe,
        "codexVersion": version,
        "codexHome": str(codex_home()),
        "desktopRunning": desktop_open,
        "defaultWebPort": DEFAULT_WEB_PORT,
        "projectCount": len(projects),
        "activeProjectCount": sum(1 for p in projects if (p["uiThreadCount"] + p["execThreadCount"]) > 0),
        "threads": {"total": 0, "ui": 0, "exec": 0, "subagent": 0, "archived": 0},
        "tokens": {"total": 0, "totalFormatted": "0", "ui": 0, "subagent": 0},
        "byModel": [],
        "topProjects": projects[:12],
        "dailyActivity": [],
        "hiddenExecThreads": [],
        "recentUiThreads": [],
        "pendingRelayCount": inbox_summary["pendingCount"],
        "bridgeDispatches": {
            "total": 0,
            "completed": 0,
            "recent": [],
        },
        "liveQuota": None,
    }

    db = state_db_path()
    if db.is_file():
        con = _open_ro_db()
        try:
            cur = con.cursor()
            tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "threads" in tables:
                for row in cur.execute(
                    "SELECT source, archived, COUNT(*) AS cnt, SUM(COALESCE(tokens_used, 0)) AS tok FROM threads GROUP BY source, archived"
                ):
                    cnt = int(row["cnt"] or 0)
                    tok = int(row["tok"] or 0)
                    stats["threads"]["total"] += cnt
                    stats["tokens"]["total"] += tok
                    if row["archived"]:
                        stats["threads"]["archived"] += cnt
                    kind = classify_source(row["source"])
                    if kind == "ui":
                        stats["threads"]["ui"] += cnt
                        stats["tokens"]["ui"] += tok
                    elif kind == "exec":
                        stats["threads"]["exec"] += cnt
                    elif kind == "subagent":
                        stats["threads"]["subagent"] += cnt
                        stats["tokens"]["subagent"] += tok

                stats["tokens"]["totalFormatted"] = fmt_tokens(stats["tokens"]["total"])
                stats["tokens"]["uiFormatted"] = fmt_tokens(stats["tokens"]["ui"])
                stats["tokens"]["subagentFormatted"] = fmt_tokens(stats["tokens"]["subagent"])

                total_tok = max(stats["tokens"]["total"], 1)
                for mrow in cur.execute(
                    """
                    SELECT COALESCE(model, 'unknown') AS mdl,
                           COUNT(*) AS cnt,
                           SUM(CASE WHEN source NOT LIKE '{%' THEN 1 ELSE 0 END) AS main_cnt,
                           SUM(COALESCE(tokens_used, 0)) AS tok
                    FROM threads
                    GROUP BY COALESCE(model, 'unknown')
                    ORDER BY tok DESC
                    LIMIT 12
                    """
                ):
                    tok = int(mrow["tok"] or 0)
                    stats["byModel"].append(
                        {
                            "model": mrow["mdl"],
                            "totalThreads": int(mrow["cnt"] or 0),
                            "mainThreads": int(mrow["main_cnt"] or 0),
                            "tokens": tok,
                            "tokensFormatted": fmt_tokens(tok),
                            "sharePct": round(tok * 100.0 / total_tok, 1),
                        }
                    )

                for drow in cur.execute(
                    """
                    SELECT strftime('%Y-%m-%d', updated_at_ms / 1000, 'unixepoch', 'localtime') AS day,
                           SUM(CASE WHEN source NOT LIKE '{%' THEN 1 ELSE 0 END) AS sessions,
                           COUNT(*) AS all_threads,
                           SUM(COALESCE(tokens_used, 0)) AS tok
                    FROM threads
                    WHERE updated_at_ms IS NOT NULL
                    GROUP BY day
                    ORDER BY day DESC
                    LIMIT 21
                    """
                ):
                    if drow["day"]:
                        stats["dailyActivity"].append(
                            {
                                "date": drow["day"],
                                "sessions": int(drow["sessions"] or 0),
                                "allThreads": int(drow["all_threads"] or 0),
                                "tokens": int(drow["tok"] or 0),
                                "tokensFormatted": fmt_tokens(drow["tok"]),
                            }
                        )
                stats["dailyActivity"].reverse()
        finally:
            con.close()

        stats["hiddenExecThreads"] = list_threads(source_filter="exec", limit=20)
        stats["recentUiThreads"] = list_threads(source_filter="ui", limit=15)

    dispatches = get_dispatch_history(limit=50)
    stats["bridgeDispatches"] = {
        "total": len(dispatches),
        "completed": sum(1 for d in dispatches if d.get("status") == "completed"),
        "recent": dispatches[:10],
    }

    if include_live_quota:
        stats["liveQuota"] = get_quota_and_models(include_models=True)
    return stats


def _to_sandbox_policy(mode: str, cwd: str) -> dict[str, Any]:
    if mode in ("danger-full-access", "dangerFullAccess", "full"):
        return {"type": "dangerFullAccess"}
    if mode in ("workspace-write", "workspaceWrite", "write"):
        return {"type": "workspaceWrite", "writableRoots": [cwd], "networkAccess": True}
    return {"type": "readOnly", "networkAccess": True}


def _to_sandbox_mode_str(mode: str) -> str:
    if mode in ("danger-full-access", "dangerFullAccess", "full"):
        return "danger-full-access"
    if mode in ("workspace-write", "workspaceWrite", "write"):
        return "workspace-write"
    return "read-only"


def create_ui_thread(
    project: Optional[str] = None,
    cwd: Optional[str] = None,
    title: Optional[str] = None,
    sandbox: str = "read-only",
    model: Optional[str] = None,
    developer_instructions: Optional[str] = None,
) -> dict[str, Any]:
    """Create a brand-new native Codex Desktop UI thread (`source="vscode"`, `originator="Codex Desktop"`)."""
    resolved = resolve_project(project or cwd)
    use_cwd = normalize_fs_path(cwd) if cwd else resolved["cwd"]
    if not pathlib.Path(use_cwd).is_dir():
        raise ValueError(f"Working directory does not exist: {use_cwd}")

    sb_str = _to_sandbox_mode_str(sandbox)
    with AppServerClient(sandbox_mode=sb_str) as client:
        start_params: dict[str, Any] = {
            "cwd": use_cwd,
            "sandbox": sb_str,
            "approvalPolicy": "on-request" if sb_str == "read-only" else "never",
            "ephemeral": False,
        }
        if model:
            start_params["model"] = model
        if developer_instructions:
            start_params["developerInstructions"] = developer_instructions

        res = client.request("thread/start", start_params)
        thread_obj = res.get("thread") or {}
        tid = thread_obj.get("id")
        if not tid:
            raise RuntimeError(f"thread/start returned no thread ID: {res}")

        if title:
            client.request("thread/name/set", {"threadId": tid, "name": title.strip()})

    binding = assign_thread_to_project(tid, resolved.get("projectId"))
    return {
        "threadId": tid,
        "title": title,
        "projectId": resolved.get("projectId"),
        "projectName": resolved.get("projectName"),
        "cwd": use_cwd,
        "source": thread_obj.get("source", "vscode"),
        "originator": thread_obj.get("originator", "Codex Desktop"),
        "model": res.get("model") or thread_obj.get("model"),
        "rolloutPath": thread_obj.get("path"),
        "projectBinding": binding,
    }


def fork_ui_thread(
    thread_id: str,
    title: Optional[str] = None,
    project: Optional[str] = None,
    cwd: Optional[str] = None,
    sandbox: str = "read-only",
    model: Optional[str] = None,
) -> dict[str, Any]:
    """Fork an existing Codex thread into a new independent UI-visible branch (`thread/fork`)."""
    orig = read_thread(thread_id, max_messages=1, max_commands=0)
    resolved = resolve_project(project or cwd or orig["cwd"])
    use_cwd = normalize_fs_path(cwd) if cwd else (resolved.get("cwd") or orig["cwd"])
    sb_str = _to_sandbox_mode_str(sandbox)

    with AppServerClient(sandbox_mode=sb_str) as client:
        fork_params: dict[str, Any] = {
            "threadId": orig["id"],
            "cwd": use_cwd,
            "sandbox": sb_str,
            "approvalPolicy": "on-request" if sb_str == "read-only" else "never",
            "ephemeral": False,
        }
        if model:
            fork_params["model"] = model
        res = client.request("thread/fork", fork_params)
        thread_obj = res.get("thread") or {}
        new_tid = thread_obj.get("id")
        if not new_tid:
            raise RuntimeError(f"thread/fork returned no thread ID: {res}")
        new_title = (title or f"[Fork] {orig['title'][:45]}").strip()
        client.request("thread/name/set", {"threadId": new_tid, "name": new_title})

    binding = assign_thread_to_project(new_tid, resolved.get("projectId"))
    return {
        "parentThreadId": orig["id"],
        "threadId": new_tid,
        "title": new_title,
        "projectId": resolved.get("projectId"),
        "projectName": resolved.get("projectName"),
        "cwd": use_cwd,
        "source": thread_obj.get("source", "vscode"),
        "projectBinding": binding,
    }


def dispatch_task(
    prompt: str,
    project: Optional[str] = None,
    cwd: Optional[str] = None,
    thread_id: Optional[str] = None,
    fork_from: Optional[str] = None,
    title: Optional[str] = None,
    sandbox: str = "read-only",
    model: Optional[str] = None,
    effort: Optional[str] = None,
    images: Optional[list[str]] = None,
    output_schema: Optional[dict[str, Any]] = None,
    output_file: Optional[str] = None,
    auto_ack_relay: bool = False,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """
    Full native orchestration turn with mandatory Commander Relay packaging:
    1. Creates, forks, or resumes a native Codex Desktop UI-visible thread.
    2. Runs the prompt via `codex app-server` (`turn/start`), intercepting mid-turn questions & escalations.
    3. Builds a structured `commanderRelay` verification digest, logs to Relay Inbox, and writes the verbatim `.md` report.
    """
    ensure_data_dirs()
    started_ts = time.time()
    sb_str = _to_sandbox_mode_str(sandbox)
    approval_policy = "on-request" if sb_str == "read-only" else "never"

    resolved = (
        resolve_project(project or cwd)
        if (project or cwd or (not thread_id and not fork_from))
        else {"projectId": None, "projectName": None, "cwd": ""}
    )
    use_cwd = normalize_fs_path(cwd) if cwd else (resolved.get("cwd") or "")

    with AppServerClient(sandbox_mode=sb_str) as client:
        created_new = False
        if fork_from:
            orig = read_thread(fork_from, max_messages=1, max_commands=0)
            if not use_cwd:
                use_cwd = orig["cwd"]
            res = client.request(
                "thread/fork",
                {"threadId": orig["id"], "cwd": use_cwd, "sandbox": sb_str, "approvalPolicy": approval_policy, "ephemeral": False},
            )
            thread_obj = res.get("thread") or {}
            tid = thread_obj.get("id")
            auto_title = (title or f"[AGY Fork] {prompt.strip().splitlines()[0][:42]}").strip()
            client.request("thread/name/set", {"threadId": tid, "name": auto_title})
            title = auto_title
            created_new = True
        elif thread_id:
            res = client.request("thread/resume", {"threadId": thread_id.strip()})
            thread_obj = res.get("thread") or {}
            tid = thread_obj.get("id") or thread_id.strip()
            if not use_cwd:
                use_cwd = normalize_fs_path(thread_obj.get("cwd")) or str(pathlib.Path.cwd())
            if title:
                client.request("thread/name/set", {"threadId": tid, "name": title.strip()})
        else:
            created_new = True
            if not use_cwd or not pathlib.Path(use_cwd).is_dir():
                raise ValueError(f"Valid working directory required to start a new thread (got: '{use_cwd}').")
            start_params: dict[str, Any] = {
                "cwd": use_cwd,
                "sandbox": sb_str,
                "approvalPolicy": approval_policy,
                "ephemeral": False,
            }
            if model:
                start_params["model"] = model
            res = client.request("thread/start", start_params)
            thread_obj = res.get("thread") or {}
            tid = thread_obj.get("id")
            auto_title = (title or f"[AGY] {prompt.strip().splitlines()[0][:48]}").strip()
            client.request("thread/name/set", {"threadId": tid, "name": auto_title})
            title = auto_title

        if on_progress:
            on_progress(f"[Codex Session] thread={tid} cwd={use_cwd} sandbox={sb_str}")

        user_inputs: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images or []:
            img_p = str(pathlib.Path(img).resolve())
            user_inputs.append({"type": "localImage", "path": img_p})

        turn_params: dict[str, Any] = {
            "threadId": tid,
            "input": user_inputs,
            "approvalPolicy": approval_policy,
            "sandboxPolicy": _to_sandbox_policy(sandbox, use_cwd),
        }
        if use_cwd:
            turn_params["cwd"] = use_cwd
        if model:
            turn_params["model"] = model
        if effort:
            turn_params["effort"] = effort
        if output_schema:
            turn_params["outputSchema"] = output_schema

        client.request("turn/start", turn_params)
        turn_out = client.stream_until_turn_complete(tid, on_progress=on_progress)

    binding = assign_thread_to_project(tid, resolved.get("projectId"))
    elapsed_sec = round(time.time() - started_ts, 1)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_md_path = pathlib.Path(output_file) if output_file else (get_logs_dir() / f"{stamp}_{tid[:8]}.md")
    raw_md_path.parent.mkdir(parents=True, exist_ok=True)

    relay = build_commander_relay(
        thread_id=tid,
        title=title,
        project_name=resolved.get("projectName"),
        cwd=use_cwd,
        turn_status=turn_out["turnStatus"],
        turn_error=turn_out["turnError"],
        final_reply=turn_out["finalReply"],
        commands=turn_out["commands"],
        file_changes=turn_out["fileChanges"],
        elicited_questions=turn_out["elicitedQuestions"],
        blocked_approvals=turn_out["blockedApprovals"],
        raw_report_path=str(raw_md_path),
    )

    cmd_lines = []
    for i, c in enumerate(turn_out["commands"], 1):
        cmd_lines.append(f"### {i}. `{c.get('command')}` (exit={c.get('exitCode')}, status={c.get('status')})")
        if c.get("aggregatedOutput"):
            cmd_lines.append(f"```text\n{c['aggregatedOutput'].strip()}\n```")

    fchange_lines = [f"- `{fc.get('kind')}`: `{fc.get('path')}`" for fc in turn_out["fileChanges"]]

    md_report = "\n".join(
        [
            f"# Codex Raw Execution Report (`{tid}`)",
            "",
            f"- **Title**: {title or '(continued session)'}",
            f"- **Project**: {resolved.get('projectName') or 'Auto/Directory'} (`{use_cwd}`)",
            f"- **Thread UUID**: `{tid}` (Native Codex Desktop UI visible: `source=vscode`)",
            f"- **Model**: `{res.get('model') or model or 'default'}` | **Sandbox**: `{sb_str}` | **Duration**: `{elapsed_sec}s`",
            f"- **Turn Status**: `{turn_out['turnStatus']}` | **Relay Outcome**: `{relay['outcome']}`",
            "",
            "## 1. Instruction Sent by Antigravity",
            "```text",
            prompt.strip(),
            "```",
            "",
            "## 2. Reasoning Summary",
            turn_out["reasoningSummary"] or "_No public reasoning summary emitted._",
            "",
            f"## 3. Files Modified ({len(fchange_lines)})",
            "\n".join(fchange_lines) if fchange_lines else "_No workspace files modified._",
            "",
            f"## 4. Commands Executed ({len(turn_out['commands'])})",
            "\n\n".join(cmd_lines) if cmd_lines else "_No shell commands executed in this turn._",
            "",
            "## 5. Verbatim Codex Reply",
            turn_out["finalReply"] or "_Empty reply._",
            "",
        ]
    )
    raw_md_path.write_text(md_report, encoding="utf-8")

    relay_id = enqueue_relay_item(relay, turn_out["finalReply"] or "")
    if auto_ack_relay:
        check_relay_inbox(ack_ids=[relay_id], detect_external_ui_turns=False)
    relay["relayId"] = relay_id

    record = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "relayId": relay_id,
        "threadId": tid,
        "createdNew": created_new,
        "title": title,
        "projectName": resolved.get("projectName"),
        "projectId": resolved.get("projectId"),
        "cwd": use_cwd,
        "sandbox": sb_str,
        "model": res.get("model") or model,
        "status": turn_out["turnStatus"],
        "outcome": relay["outcome"],
        "durationSec": elapsed_sec,
        "commandCount": len(turn_out["commands"]),
        "filesChangedCount": len(turn_out["fileChanges"]),
        "rawReportPath": str(raw_md_path),
        "promptPreview": prompt.strip()[:160],
        "replyPreview": (turn_out["finalReply"] or "")[:240],
    }
    with get_history_file().open("a", encoding="utf-8") as hf:
        hf.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        **record,
        "finalReply": turn_out["finalReply"],
        "reasoningSummary": turn_out["reasoningSummary"],
        "commands": turn_out["commands"],
        "fileChanges": turn_out["fileChanges"],
        "turnError": turn_out["turnError"],
        "projectBinding": binding,
        "commanderRelay": relay,
    }


def run_code_review(
    project: Optional[str] = None,
    cwd: Optional[str] = None,
    focus: Optional[str] = None,
    base_branch: Optional[str] = None,
    commit_sha: Optional[str] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """Run an independent UI-synced adversarial Code Review in Codex."""
    target_desc = (
        f"commit `{commit_sha}`"
        if commit_sha
        else (f"diff against base branch `{base_branch}`" if base_branch else "current uncommitted working-tree & staged Git changes (and recent commit context)")
    )
    review_prompt = "\n".join(
        [
            f"Perform an independent, rigorous Code Review on {target_desc}.",
            f"Extra review focus: {focus}" if focus else "Focus on correctness bugs, edge cases, race conditions, security/safety risks, and regressions.",
            "",
            "Instructions:",
            "1. Inspect `git status`, `git diff`, or the relevant git commit/files directly in read-only mode.",
            "2. Cite exact file paths and line numbers for every finding.",
            "3. Classify findings into `[Critical]`, `[Major]`, `[Minor]`, or `[Nit]`, and state clearly if no defects are found.",
        ]
    )
    short_focus = (focus or base_branch or commit_sha or "Git Changes")[:34]
    return dispatch_task(
        prompt=review_prompt,
        project=project,
        cwd=cwd,
        title=f"[AGY Review] {short_focus}",
        sandbox="read-only",
        model=model,
    )


def batch_dispatch(tasks: list[dict[str, Any]], max_workers: int = 3) -> dict[str, Any]:
    """Execute multiple UI-synced Codex tasks in parallel and collect their `commanderRelay` digests."""
    started = time.time()
    results: list[dict[str, Any]] = [{}] * len(tasks)

    def _run_one(idx: int, spec: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            r = dispatch_task(
                prompt=spec["prompt"],
                project=spec.get("project"),
                cwd=spec.get("cwd"),
                thread_id=spec.get("threadId"),
                fork_from=spec.get("forkFrom"),
                title=spec.get("title") or f"[AGY Batch #{idx + 1}] {spec['prompt'][:36]}",
                sandbox=spec.get("sandbox") or "read-only",
                model=spec.get("model"),
                effort=spec.get("effort"),
            )
            return idx, {"ok": True, **r}
        except Exception as e:
            return idx, {"ok": False, "error": str(e), "title": spec.get("title")}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, 6))) as pool:
        futs = [pool.submit(_run_one, i, t) for i, t in enumerate(tasks)]
        for fut in concurrent.futures.as_completed(futs):
            i, res = fut.result()
            results[i] = res

    return {
        "mustRelayViaAntigravity": True,
        "commanderDirective": "Synthesize all parallel Codex branch results, compare trade-offs, and present a unified recommendation to the user.",
        "totalTasks": len(tasks),
        "succeeded": sum(1 for r in results if r.get("ok")),
        "elapsedSec": round(time.time() - started, 1),
        "results": results,
    }


def promote_exec_threads(
    thread_ids: Optional[list[str]] = None,
    project: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Promote hidden `source='exec'` threads into UI-visible `source='vscode'` threads."""
    if is_desktop_running() and not force:
        return {
            "promoted": [],
            "error": "Codex Desktop UI is currently open. Close Codex Desktop first (or pass force=True) so SQLite and sidebar state are not overwritten.",
        }

    db = state_db_path()
    if not db.is_file():
        return {"promotedCount": 0, "promoted": []}

    explicit_proj = resolve_project(project) if project else None
    all_projects = list_projects(include_empty=True)
    root_to_pid = {norm_key(r): p["id"] for p in all_projects for r in p["rootPaths"]}

    con = sqlite3.connect(str(db), timeout=10.0)
    con.row_factory = sqlite3.Row
    promoted: list[dict[str, Any]] = []
    try:
        cur = con.cursor()
        if thread_ids:
            placeholders = ",".join("?" for _ in thread_ids)
            rows = cur.execute(
                f"SELECT id, rollout_path, cwd, title, source FROM threads WHERE id IN ({placeholders})",
                thread_ids,
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT id, rollout_path, cwd, title, source FROM threads WHERE source = 'exec'"
            ).fetchall()

        gs = _load_global_state()
        tpa = gs.setdefault("thread-project-assignments", {}) if gs else {}

        for row in rows:
            tid = row["id"]
            rpath = pathlib.Path(row["rollout_path"]) if row["rollout_path"] else None
            if rpath and rpath.is_file():
                lines = rpath.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                if lines:
                    first = json.loads(lines[0])
                    if first.get("type") == "session_meta" and isinstance(first.get("payload"), dict):
                        first["payload"]["source"] = "vscode"
                        first["payload"]["originator"] = "Codex Desktop"
                        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
                        rpath.write_text("".join(lines), encoding="utf-8")

            cur.execute(
                "UPDATE threads SET source = 'vscode', originator = 'Codex Desktop' WHERE id = ?",
                (tid,),
            )

            cwd_norm = normalize_fs_path(row["cwd"])
            ck = norm_key(cwd_norm)
            pid = explicit_proj["projectId"] if explicit_proj else root_to_pid.get(ck)
            if not pid and ck:
                for rk, cand_pid in root_to_pid.items():
                    if path_is_within(ck, rk):
                        pid = cand_pid
                        break
            if pid and gs:
                tpa[tid] = {"projectKind": "local", "projectId": pid}

            promoted.append({"threadId": tid, "title": row["title"], "cwd": cwd_norm, "projectId": pid})

        con.commit()
        if promoted and gs and not is_desktop_running():
            _save_global_state_safely(gs)
    finally:
        con.close()

    return {"promotedCount": len(promoted), "promoted": promoted}


def open_in_desktop_ui(project_or_path: Optional[str] = None) -> dict[str, Any]:
    exe = find_codex_exe()
    if not exe:
        raise RuntimeError("codex executable not found.")
    resolved = resolve_project(project_or_path) if project_or_path else {"cwd": str(pathlib.Path.cwd()), "projectName": None}
    cwd = resolved.get("cwd") or str(pathlib.Path.cwd())
    kwargs: dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([exe, "app", cwd], **kwargs)
    return {"launched": True, "cwd": cwd, "projectName": resolved.get("projectName")}


def _probe_app_server_handshake(exe: str, timeout_sec: float = 10.0) -> tuple[bool, str]:
    """Run an isolated `codex app-server --stdio` initialize handshake with a strict timeout."""
    t0 = time.time()
    proc: Optional[subprocess.Popen[str]] = None
    try:
        proc = subprocess.Popen(
            [exe, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        def _handshake() -> dict[str, Any]:
            assert proc and proc.stdin and proc.stdout
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "Codex Desktop", "title": "Codex Desktop", "version": "1.2.1"},
                    "capabilities": {"experimentalApi": True},
                },
            }
            proc.stdin.write(json.dumps(init_msg) + "\n")
            proc.stdin.flush()
            while True:
                line = proc.stdout.readline()
                if not line:
                    err_tail = proc.stderr.read()[-400:].strip() if proc.stderr else ""
                    raise RuntimeError(f"app-server closed before initialize response. {err_tail}".strip())
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("id") == 1:
                    if "error" in msg:
                        raise RuntimeError(f"RPC error: {json.dumps(msg['error'], ensure_ascii=False)}")
                    return msg.get("result") or {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_handshake)
            fut.result(timeout=timeout_sec)

        ms = round((time.time() - t0) * 1000)
        return True, f"JSON-RPC handshake OK ({ms}ms)"
    except concurrent.futures.TimeoutError:
        return False, f"app-server handshake timed out after {timeout_sec}s"
    except Exception as exc:
        return False, str(exc)
    finally:
        if proc:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            finally:
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    if pipe:
                        try:
                            pipe.close()
                        except Exception:
                            pass


def run_doctor() -> dict[str, Any]:
    """
    Run an 8-point diagnostic check separating core Bridge readiness (`severity='blocker'`)
    from optional Desktop UI metadata availability (`severity='advisory'`).
    `healthy` / `bridgeReady` is True iff ALL blocker checks pass (including `app_server_rpc`).
    """
    checks: list[dict[str, Any]] = []

    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)
    checks.append(
        {
            "check": "python_version",
            "severity": "blocker",
            "ok": py_ok,
            "detail": py_ver,
            "nextStep": None if py_ok else "安装 Python 3.11+ (https://www.python.org/downloads/) 后重新运行安装脚本。",
        }
    )

    exe = find_codex_exe()
    exe_ok = bool(exe)
    checks.append(
        {
            "check": "codex_binary",
            "severity": "blocker",
            "ok": exe_ok,
            "detail": exe or "Not found",
            "nextStep": None
            if exe_ok
            else "安装 OpenAI Codex Desktop 桌面端或 Codex CLI（或设置环境变量 CODEX_CLI_PATH 指向 codex 可执行文件），再重跑 doctor。",
        }
    )

    ver = get_codex_version(exe) if exe else "unavailable"
    ver_ok = bool(exe and not ver.startswith("error") and ver not in ("not-found", "unavailable"))
    checks.append(
        {
            "check": "codex_version",
            "severity": "blocker",
            "ok": ver_ok,
            "detail": ver,
            "nextStep": None if ver_ok else "确认检测到的 codex 可执行文件未损坏且有执行权限（运行 `codex --version` 验证）。",
        }
    )

    home = codex_home()
    has_auth_file = (home / "auth.json").is_file()
    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
    auth_ok = has_auth_file or has_api_key
    auth_detail = str(home / "auth.json") if has_auth_file else ("OPENAI_API_KEY env set" if has_api_key else f"Missing {home / 'auth.json'}")
    checks.append(
        {
            "check": "codex_auth",
            "severity": "blocker",
            "ok": auth_ok,
            "detail": auth_detail,
            "nextStep": None if auth_ok else "打开 Codex Desktop 完成登录，或在终端执行 `codex login`（或配置 OPENAI_API_KEY），然后重跑 doctor。",
        }
    )

    rpc_ok = False
    rpc_detail = "skipped (codex_binary missing)"
    if exe and ver_ok:
        rpc_ok, rpc_detail = _probe_app_server_handshake(exe)
    elif exe:
        rpc_detail = "skipped (codex_version failed)"
    checks.append(
        {
            "check": "app_server_rpc",
            "severity": "blocker",
            "ok": rpc_ok,
            "detail": rpc_detail,
            "nextStep": None
            if rpc_ok
            else "确认已安装的 Codex 版本支持 `codex app-server --stdio`（建议升级至最新 Codex Desktop / CLI）并已完成登录，随后重跑 doctor。",
        }
    )

    db = state_db_path()
    db_ok = db.is_file()
    checks.append(
        {
            "check": "state_sqlite",
            "severity": "advisory",
            "ok": db_ok,
            "detail": str(db) if db_ok else f"Not initialized yet ({db.name})",
            "nextStep": None
            if db_ok
            else "本地历史库尚未生成（历史统计与旧会话转正功能暂受限）；打开一次 Codex Desktop 或执行首条派发任务后会自动初始化。",
        }
    )

    projs = list_projects(include_empty=True) if (db_ok or global_state_path().is_file()) else []
    proj_ok = len(projs) > 0
    checks.append(
        {
            "check": "desktop_projects",
            "severity": "advisory",
            "ok": proj_ok,
            "detail": f"{len(projs)} projects discovered",
            "nextStep": None
            if proj_ok
            else "未检测到 Codex Desktop 项目列表（按项目名归类功能暂受限）；派发任务时可直接传 `--cwd <目录路径>`，或在 Codex Desktop 中添加项目。",
        }
    )

    hidden_cnt = len(list_threads(source_filter="exec", limit=100)) if db_ok else 0
    sync_ok = hidden_cnt == 0
    checks.append(
        {
            "check": "ui_sync_health",
            "severity": "advisory",
            "ok": sync_ok,
            "detail": f"{hidden_cnt} hidden exec threads",
            "nextStep": None
            if sync_ok
            else f"存在 {hidden_cnt} 条旧版隐藏 exec 会话；如需在桌面端侧边栏查看，可关闭 Codex Desktop 后运行 `codex-ctl promote`。",
        }
    )

    failed_blockers = [
        {"check": c["check"], "detail": c["detail"], "nextStep": c["nextStep"]}
        for c in checks
        if c["severity"] == "blocker" and not c["ok"]
    ]
    warnings = [
        {"check": c["check"], "detail": c["detail"], "nextStep": c["nextStep"]}
        for c in checks
        if c["severity"] == "advisory" and not c["ok"]
    ]
    healthy = len(failed_blockers) == 0
    status = "unavailable" if not healthy else ("ready_with_warnings" if warnings else "ready")
    next_steps = [b["nextStep"] for b in failed_blockers if b.get("nextStep")] or [
        w["nextStep"] for w in warnings if w.get("nextStep")
    ]

    return {
        "healthy": healthy,
        "bridgeReady": healthy,
        "status": status,
        "desktopRunning": is_desktop_running(),
        "defaultWebPort": DEFAULT_WEB_PORT,
        "failedBlockers": failed_blockers,
        "warnings": warnings,
        "nextSteps": next_steps,
        "checks": checks,
    }

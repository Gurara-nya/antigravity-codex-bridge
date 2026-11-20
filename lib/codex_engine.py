#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core cross-platform orchestration & analytics engine for `antigravity-codex-bridge` (v1.1.0).
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
from typing import Any, Callable, Optional

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent


def get_data_dir() -> pathlib.Path:
    override = os.environ.get("CODEX_BRIDGE_DATA_DIR")
    return pathlib.Path(override) if override else (PLUGIN_ROOT / "data")


def get_logs_dir() -> pathlib.Path:
    return get_data_dir() / "logs"


def get_history_file() -> pathlib.Path:
    return get_data_dir() / "dispatch_history.jsonl"


def get_pending_assignments_file() -> pathlib.Path:
    return get_data_dir() / "pending_assignments.json"


def codex_home() -> pathlib.Path:
    env_home = os.environ.get("CODEX_HOME")
    return pathlib.Path(env_home) if env_home else (pathlib.Path.home() / ".codex")


def state_db_path() -> pathlib.Path:
    home = codex_home()
    if (home / "state_5.sqlite").is_file():
        return home / "state_5.sqlite"
    # Fallback to highest-numbered state_*.sqlite if future schema bumps
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
    # 1. Explicit environment override
    env_p = os.environ.get("CODEX_CLI_PATH")
    if env_p and pathlib.Path(env_p).is_file():
        return str(pathlib.Path(env_p))

    # 2. ~/.codex/config.toml [mcp_servers.node_repl.env].CODEX_CLI_PATH (auto-maintained by Codex Desktop)
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

    # 3. System PATH
    which_p = shutil.which("codex") or shutil.which("codex.exe")
    if which_p:
        return which_p

    sys_name = platform.system()
    home = codex_home()

    # 4. Platform-specific Desktop App / package locations
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
        mac_candidates = [
            pathlib.Path("/Applications/Codex.app/Contents/Resources/codex"),
            pathlib.Path.home() / "Applications/Codex.app/Contents/Resources/codex",
            pathlib.Path("/opt/homebrew/bin/codex"),
            pathlib.Path("/usr/local/bin/codex"),
            home / ".sandbox-bin" / "codex",
        ]
        for c in mac_candidates:
            if c.is_file():
                return str(c)

    else:
        linux_candidates = [
            pathlib.Path.home() / ".local/bin/codex",
            pathlib.Path.home() / ".npm-global/bin/codex",
            pathlib.Path("/usr/local/bin/codex"),
            home / ".sandbox-bin" / "codex",
        ]
        for c in linux_candidates:
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
    JSON-RPC 2.0 client over `codex app-server --stdio` declaring `clientInfo.name = "Codex Desktop"`
    so newly created or forked sessions are 100% native Codex Desktop UI threads.
    """

    def __init__(self, codex_exe: Optional[str] = None):
        self.exe = codex_exe or find_codex_exe()
        if not self.exe:
            raise RuntimeError("codex executable not found on this machine.")
        self.proc: Optional[subprocess.Popen[str]] = None
        self._next_id = 0
        self.notifications: list[dict[str, Any]] = []

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
                    "version": "1.1.0",
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
                self._auto_respond_server_request(msg)
                continue
            if "method" in msg:
                self.notifications.append(msg)
                if on_notification:
                    on_notification(msg["method"], msg.get("params") or {})

    def _auto_respond_server_request(self, msg: dict[str, Any]) -> None:
        req_id = msg["id"]
        m = msg.get("method", "")
        if "Approval" in m or "approval" in m:
            self._send({"jsonrpc": "2.0", "id": req_id, "result": {"decision": "accept"}})
        else:
            self._send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unsupported client callback: {m}"}})

    def stream_until_turn_complete(
        self,
        thread_id: str,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        assert self.proc and self.proc.stdout
        agent_chunks: list[str] = []
        completed_messages: list[str] = []
        commands_ran: list[dict[str, Any]] = []
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
                self._auto_respond_server_request(msg)
                continue

            method = msg.get("method", "")
            params = msg.get("params") or {}

            if method == "item/agentMessage/delta":
                agent_chunks.append(params.get("delta") or "")
            elif method == "item/reasoning/summaryTextDelta":
                reasoning_chunks.append(params.get("delta") or "")
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
    """Compute comprehensive usage, project, model, timeline, and bridge dispatch statistics."""
    codex_exe = find_codex_exe()
    version = get_codex_version(codex_exe)
    desktop_open = is_desktop_running()
    projects = list_projects(include_empty=True)

    stats: dict[str, Any] = {
        "codexExe": codex_exe,
        "codexVersion": version,
        "codexHome": str(codex_home()),
        "desktopRunning": desktop_open,
        "projectCount": len(projects),
        "activeProjectCount": sum(1 for p in projects if (p["uiThreadCount"] + p["execThreadCount"]) > 0),
        "threads": {"total": 0, "ui": 0, "exec": 0, "subagent": 0, "archived": 0},
        "tokens": {"total": 0, "totalFormatted": "0", "ui": 0, "subagent": 0},
        "byModel": [],
        "topProjects": projects[:12],
        "dailyActivity": [],
        "hiddenExecThreads": [],
        "recentUiThreads": [],
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
    with AppServerClient() as client:
        start_params: dict[str, Any] = {
            "cwd": use_cwd,
            "sandbox": sb_str,
            "approvalPolicy": "never",
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

    with AppServerClient() as client:
        fork_params: dict[str, Any] = {
            "threadId": orig["id"],
            "cwd": use_cwd,
            "sandbox": sb_str,
            "approvalPolicy": "never",
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
    output_file: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """
    Full native orchestration turn:
    1. Creates a new Codex Desktop UI-visible thread, forks `fork_from`, OR resumes `thread_id`.
    2. Runs the prompt via `codex app-server` (`turn/start`) with real-time progress.
    3. Saves a complete raw report `.md` file and logs dispatch metrics.
    """
    ensure_data_dirs()
    started_ts = time.time()
    sb_str = _to_sandbox_mode_str(sandbox)

    resolved = (
        resolve_project(project or cwd)
        if (project or cwd or (not thread_id and not fork_from))
        else {"projectId": None, "projectName": None, "cwd": ""}
    )
    use_cwd = normalize_fs_path(cwd) if cwd else (resolved.get("cwd") or "")

    with AppServerClient() as client:
        created_new = False
        if fork_from:
            orig = read_thread(fork_from, max_messages=1, max_commands=0)
            if not use_cwd:
                use_cwd = orig["cwd"]
            res = client.request(
                "thread/fork",
                {"threadId": orig["id"], "cwd": use_cwd, "sandbox": sb_str, "approvalPolicy": "never", "ephemeral": False},
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
                "approvalPolicy": "never",
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
            "approvalPolicy": "never",
            "sandboxPolicy": _to_sandbox_policy(sandbox, use_cwd),
        }
        if use_cwd:
            turn_params["cwd"] = use_cwd
        if model:
            turn_params["model"] = model
        if effort:
            turn_params["effort"] = effort

        client.request("turn/start", turn_params)
        turn_out = client.stream_until_turn_complete(tid, on_progress=on_progress)

    binding = assign_thread_to_project(tid, resolved.get("projectId"))
    elapsed_sec = round(time.time() - started_ts, 1)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_md_path = pathlib.Path(output_file) if output_file else (get_logs_dir() / f"{stamp}_{tid[:8]}.md")
    raw_md_path.parent.mkdir(parents=True, exist_ok=True)

    cmd_lines = []
    for i, c in enumerate(turn_out["commands"], 1):
        cmd_lines.append(f"### {i}. `{c.get('command')}` (exit={c.get('exitCode')}, status={c.get('status')})")
        if c.get("aggregatedOutput"):
            cmd_lines.append(f"```text\n{c['aggregatedOutput'].strip()}\n```")

    md_report = "\n".join(
        [
            f"# Codex Raw Execution Report (`{tid}`)",
            "",
            f"- **Title**: {title or '(continued session)'}",
            f"- **Project**: {resolved.get('projectName') or 'Auto/Directory'} (`{use_cwd}`)",
            f"- **Thread UUID**: `{tid}` (Native Codex Desktop UI visible: `source=vscode`)",
            f"- **Model**: `{res.get('model') or model or 'default'}` | **Sandbox**: `{sb_str}` | **Duration**: `{elapsed_sec}s`",
            f"- **Turn Status**: `{turn_out['turnStatus']}`",
            "",
            "## 1. Instruction Sent by Antigravity",
            "```text",
            prompt.strip(),
            "```",
            "",
            "## 2. Reasoning Summary",
            turn_out["reasoningSummary"] or "_No public reasoning summary emitted._",
            "",
            f"## 3. Commands Executed ({len(turn_out['commands'])})",
            "\n\n".join(cmd_lines) if cmd_lines else "_No shell commands executed in this turn._",
            "",
            "## 4. Verbatim Codex Reply",
            turn_out["finalReply"] or "_Empty reply._",
            "",
        ]
    )
    raw_md_path.write_text(md_report, encoding="utf-8")

    record = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "threadId": tid,
        "createdNew": created_new,
        "title": title,
        "projectName": resolved.get("projectName"),
        "projectId": resolved.get("projectId"),
        "cwd": use_cwd,
        "sandbox": sb_str,
        "model": res.get("model") or model,
        "status": turn_out["turnStatus"],
        "durationSec": elapsed_sec,
        "commandCount": len(turn_out["commands"]),
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
        "turnError": turn_out["turnError"],
        "projectBinding": binding,
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
    target_desc = f"commit `{commit_sha}`" if commit_sha else (f"diff against base branch `{base_branch}`" if base_branch else "current uncommitted working-tree & staged Git changes (and recent commit context)")
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
    """
    Execute multiple UI-synced Codex tasks in parallel (e.g., multi-angle audits or parameter sweeps).
    Each item in `tasks` accepts `{prompt, project, cwd, title, sandbox, model, effort, forkFrom}`.
    """
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


def run_doctor() -> dict[str, Any]:
    """Run an 8-point diagnostic check on the local Codex + Codex Bridge environment."""
    checks: list[dict[str, Any]] = []
    py_ver = sys.version.split()[0]
    checks.append({"check": "python_version", "ok": sys.version_info >= (3, 11), "detail": py_ver})

    exe = find_codex_exe()
    checks.append({"check": "codex_binary", "ok": bool(exe), "detail": exe or "Not found"})

    ver = get_codex_version(exe) if exe else "unavailable"
    checks.append({"check": "codex_version", "ok": bool(exe and not ver.startswith("error")), "detail": ver})

    home = codex_home()
    auth_ok = (home / "auth.json").is_file()
    checks.append({"check": "codex_auth", "ok": auth_ok, "detail": str(home / "auth.json") if auth_ok else "auth.json missing"})

    db = state_db_path()
    db_ok = db.is_file()
    checks.append({"check": "state_sqlite", "ok": db_ok, "detail": str(db) if db_ok else "state_*.sqlite missing"})

    projs = list_projects(include_empty=True) if db_ok or global_state_path().is_file() else []
    checks.append({"check": "desktop_projects", "ok": True, "detail": f"{len(projs)} projects discovered"})

    rpc_ok = False
    rpc_detail = "skipped"
    if exe:
        t0 = time.time()
        try:
            with AppServerClient(exe):
                rpc_ok = True
                rpc_detail = f"JSON-RPC handshake OK ({round((time.time() - t0) * 1000)}ms)"
        except Exception as e:
            rpc_detail = str(e)
    checks.append({"check": "app_server_rpc", "ok": rpc_ok, "detail": rpc_detail})

    hidden_cnt = len(list_threads(source_filter="exec", limit=100)) if db_ok else 0
    checks.append({"check": "ui_sync_health", "ok": True, "detail": f"{hidden_cnt} hidden exec threads"})

    return {
        "healthy": all(c["ok"] for c in checks[:5]),
        "desktopRunning": is_desktop_running(),
        "checks": checks,
    }

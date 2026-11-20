#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`codex_ctl.py` — Command-line orchestration, diagnostics, & UI export tool for `antigravity-codex-bridge` (v1.1.0).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

import codex_engine as engine  # noqa: E402
import dashboard_ui as ui_gen  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity <-> Codex Bridge CLI Controller (v1.1.0)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # doctor
    sub.add_parser("doctor", help="Run 8-point environment & RPC diagnostic check")

    # quota
    p_quota = sub.add_parser("quota", help="Query live Codex account rate limits and model catalog")
    p_quota.add_argument("--no-models", action="store_true", help="Skip listing full model catalog")

    # overview
    p_ov = sub.add_parser("overview", help="Print comprehensive Codex usage, project, and model statistics as JSON")
    p_ov.add_argument("--live-quota", action="store_true", help="Include live rate-limit & model catalog")

    # projects
    p_proj = sub.add_parser("projects", help="List Codex Desktop UI projects")
    p_proj.add_argument("--query", "-q", default=None, help="Filter by name, ID, or path")
    p_proj.add_argument("--non-empty", action="store_true", help="Only list projects with threads")
    p_proj.add_argument("--limit", type=int, default=50)

    # threads
    p_thr = sub.add_parser("threads", help="List Codex threads")
    p_thr.add_argument("--project", "-p", default=None, help="Project name, ID, or path")
    p_thr.add_argument("--source", choices=["ui", "exec", "ui_and_exec", "subagent", "all"], default="ui_and_exec")
    p_thr.add_argument("--search", "-s", default=None)
    p_thr.add_argument("--limit", type=int, default=25)

    # read
    p_read = sub.add_parser("read", help="Read raw conversation turns and tool calls of a thread")
    p_read.add_argument("thread_id", help="Thread UUID or prefix")
    p_read.add_argument("--max-messages", type=int, default=20)
    p_read.add_argument("--max-commands", type=int, default=30)

    # export-report
    p_exp_rep = sub.add_parser("export-report", help="Export any thread into a standalone Markdown report")
    p_exp_rep.add_argument("thread_id", help="Thread UUID or prefix")
    p_exp_rep.add_argument("--out", "-o", default=None, help="Custom output Markdown file path")

    # create
    p_create = sub.add_parser("create", help="Create a native Codex Desktop UI thread without running a turn yet")
    p_create.add_argument("--project", "-p", default=None, help="Target Project name, ID, or directory")
    p_create.add_argument("--cwd", default=None, help="Explicit working directory override")
    p_create.add_argument("--title", "-t", default=None, help="Display title in Codex Desktop UI")
    p_create.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write", "danger-full-access"])
    p_create.add_argument("--model", "-m", default=None)

    # fork
    p_fork = sub.add_parser("fork", help="Fork an existing Codex session into a new UI-visible branch")
    p_fork.add_argument("thread_id", help="Source thread UUID or prefix")
    p_fork.add_argument("--title", "-t", default=None, help="Title for the forked session")
    p_fork.add_argument("--project", "-p", default=None, help="Optional target Project override")
    p_fork.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write", "danger-full-access"])
    p_fork.add_argument("--model", "-m", default=None)

    # dispatch
    p_disp = sub.add_parser("dispatch", help="Create, fork, or resume a UI-visible Codex thread and run a full turn")
    p_disp.add_argument("--project", "-p", default=None, help="Target Project name, ID, or directory")
    p_disp.add_argument("--cwd", default=None, help="Explicit working directory override")
    p_disp.add_argument("--thread", default=None, help="Existing thread UUID to resume")
    p_disp.add_argument("--fork-from", default=None, help="Existing thread UUID to fork before running this turn")
    p_disp.add_argument("--title", "-t", default=None, help="Thread title in Codex Desktop UI")
    p_disp.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write", "danger-full-access"])
    p_disp.add_argument("--model", "-m", default=None, help="Optional model override")
    p_disp.add_argument("--effort", default=None, help="Optional reasoning effort (low/medium/high)")
    p_disp.add_argument("--image", action="append", default=[], help="Attach local image path (repeatable)")
    p_disp.add_argument("--out", "-o", default=None, help="Optional path for the raw execution Markdown report")
    p_disp.add_argument("--prompt", default=None, help="Instruction text (or pass `--prompt-file`, or pipe via stdin)")
    p_disp.add_argument("--prompt-file", default=None, help="UTF-8 file containing the instruction prompt")

    # review
    p_rev = sub.add_parser("review", help="Run an independent UI-synced adversarial Code Review in Codex")
    p_rev.add_argument("--project", "-p", default=None)
    p_rev.add_argument("--cwd", default=None)
    p_rev.add_argument("--focus", default=None, help="Specific review focus or concerns")
    p_rev.add_argument("--base", default=None, help="Base branch to diff against")
    p_rev.add_argument("--commit", default=None, help="Specific commit SHA to review")
    p_rev.add_argument("--model", "-m", default=None)

    # batch
    p_batch = sub.add_parser("batch", help="Run multiple UI-synced Codex tasks concurrently from a JSON file")
    p_batch.add_argument("--spec-file", required=True, help="Path to UTF-8 JSON file containing a list of task objects")
    p_batch.add_argument("--workers", type=int, default=3, help="Max concurrent Codex workers (1-6)")

    # promote
    p_prom = sub.add_parser("promote", help="Promote hidden `exec` threads into Codex Desktop UI")
    p_prom.add_argument("--thread", action="append", default=[], help="Specific thread UUID (repeatable; omit for all)")
    p_prom.add_argument("--project", "-p", default=None, help="Optional target Project name or ID")
    p_prom.add_argument("--force", action="store_true", help="Force update even if Codex Desktop is open")

    # open-ui
    p_open = sub.add_parser("open-ui", help="Open Codex Desktop UI on a project or directory")
    p_open.add_argument("--project", "-p", default=None)

    # export-ui
    p_exp = sub.add_parser("export-ui", help="Generate Antigravity Generative UI HTML dashboard")
    p_exp.add_argument("--mode", choices=["inline", "full"], default="full")
    p_exp.add_argument("--no-live-quota", action="store_true", help="Skip live quota RPC lookup for faster offline export")
    p_exp.add_argument("--out", "-o", required=True, help="Output HTML file path")

    # serve-web
    p_web = sub.add_parser("serve-web", help="Launch live local interactive Web Console (default http://127.0.0.1:8765)")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()

    if args.cmd == "doctor":
        _print_json(engine.run_doctor())
        return 0

    if args.cmd == "quota":
        _print_json(engine.get_quota_and_models(include_models=not args.no_models))
        return 0

    if args.cmd == "overview":
        _print_json(engine.get_overview_stats(include_live_quota=args.live_quota))
        return 0

    if args.cmd == "projects":
        items = engine.list_projects(query=args.query, include_empty=not args.non_empty)[: args.limit]
        _print_json(items)
        return 0

    if args.cmd == "threads":
        items = engine.list_threads(
            project=args.project,
            source_filter=args.source,
            search=args.search,
            limit=args.limit,
        )
        _print_json(items)
        return 0

    if args.cmd == "read":
        _print_json(
            engine.read_thread(
                args.thread_id,
                max_messages=args.max_messages,
                max_commands=args.max_commands,
            )
        )
        return 0

    if args.cmd == "export-report":
        _print_json(engine.export_thread_markdown(args.thread_id, output_file=args.out))
        return 0

    if args.cmd == "create":
        _print_json(
            engine.create_ui_thread(
                project=args.project,
                cwd=args.cwd,
                title=args.title,
                sandbox=args.sandbox,
                model=args.model,
            )
        )
        return 0

    if args.cmd == "fork":
        _print_json(
            engine.fork_ui_thread(
                thread_id=args.thread_id,
                title=args.title,
                project=args.project,
                sandbox=args.sandbox,
                model=args.model,
            )
        )
        return 0

    if args.cmd == "dispatch":
        prompt_text = args.prompt
        if args.prompt_file:
            prompt_text = pathlib.Path(args.prompt_file).read_text(encoding="utf-8")
        elif not prompt_text and not sys.stdin.isatty():
            prompt_text = sys.stdin.read()
        if not prompt_text or not prompt_text.strip():
            raise SystemExit("Error: --prompt, --prompt-file, or stdin is required for `dispatch`.")

        def progress(line: str) -> None:
            print(line, file=sys.stderr, flush=True)

        res = engine.dispatch_task(
            prompt=prompt_text,
            project=args.project,
            cwd=args.cwd,
            thread_id=args.thread,
            fork_from=args.fork_from,
            title=args.title,
            sandbox=args.sandbox,
            model=args.model,
            effort=args.effort,
            images=args.image,
            output_file=args.out,
            on_progress=progress,
        )
        _print_json(res)
        return 0

    if args.cmd == "review":
        _print_json(
            engine.run_code_review(
                project=args.project,
                cwd=args.cwd,
                focus=args.focus,
                base_branch=args.base,
                commit_sha=args.commit,
                model=args.model,
            )
        )
        return 0

    if args.cmd == "batch":
        spec = json.loads(pathlib.Path(args.spec_file).read_text(encoding="utf-8"))
        if not isinstance(spec, list):
            raise SystemExit("Error: --spec-file must contain a JSON array of task objects.")
        _print_json(engine.batch_dispatch(spec, max_workers=args.workers))
        return 0

    if args.cmd == "promote":
        _print_json(
            engine.promote_exec_threads(
                thread_ids=args.thread or None,
                project=args.project,
                force=args.force,
            )
        )
        return 0

    if args.cmd == "open-ui":
        _print_json(engine.open_in_desktop_ui(args.project))
        return 0

    if args.cmd == "export-ui":
        use_quota = not args.no_live_quota
        html_str = (
            ui_gen.build_inline_widget_html(include_live_quota=use_quota)
            if args.mode == "inline"
            else ui_gen.build_full_dashboard_html(include_live_quota=use_quota)
        )
        out_p = pathlib.Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(html_str, encoding="utf-8")
        _print_json({"written": str(out_p), "mode": args.mode, "bytes": len(html_str.encode("utf-8"))})
        return 0

    if args.cmd == "serve-web":
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
        from web_console import run_server  # type: ignore

        run_server(host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

# Codex Bridge Guidelines

When the user asks to interact with **Codex** (dispatching tasks, commanding Codex across projects, running independent code reviews, forking/branching Codex sessions, inspecting raw logs/outputs, promoting hidden `exec` threads into Codex Desktop UI, checking Codex quota/models, or viewing Codex analytics dashboards):

1. **Load the `codex-commander` skill** before orchestrating multi-step workflows, parallel batches, or Generative UI dashboards.
2. **Use fast MCP tools (`codex-bridge`) for instant structured operations**:
   - `codex_bridge_overview`: Usage analytics, project/thread totals, model token breakdown, and dispatch stats.
   - `codex_bridge_quota_and_models`: Real-time Codex account rate-limit usage (`usedPercent` / `remainingPercent` / reset countdown) and available model catalog.
   - `codex_bridge_doctor`: 8-point environment & `app-server` JSON-RPC health check.
   - `codex_bridge_list_projects`: Resolve Codex Desktop UI projects, IDs, root paths, and activity metrics.
   - `codex_bridge_list_threads`: Browse or search sessions by project, keyword, or visibility (`ui` vs hidden `exec`).
   - `codex_bridge_read_thread`: Inspect verbatim user prompts, reasoning summaries, executed shell commands, and raw assistant replies.
   - `codex_bridge_export_report`: Export any Codex thread into a standalone Markdown report.
   - `codex_bridge_create_thread`: Natively create a UI-visible Codex session (`source="vscode"`, `originator="Codex Desktop"`) with a clear title under any project without manual user action.
   - `codex_bridge_fork_thread`: Branch an existing Codex session (`thread/fork`) into a new UI-visible thread to test alternative hypotheses safely.
   - `codex_bridge_promote_exec_threads`: Promote hidden `source="exec"` sessions into Codex Desktop UI.
   - `codex_bridge_open_ui`: Open a project workspace directly in Codex Desktop UI (`codex app`).
3. **Use `codex_ctl.py` via `run_command` for long-running task execution**:
   - Never run multi-minute coding, review, batch, or simulation turns inside synchronous MCP calls where they may time out. Run the plugin's CLI wrapper (`~/.gemini/config/plugins/codex-bridge/bin/codex-ctl.cmd` on Windows, `~/.gemini/config/plugins/codex-bridge/bin/codex-ctl` on macOS/Linux, or `python ~/.gemini/config/plugins/codex-bridge/scripts/codex_ctl.py`) with `dispatch`, `review`, or `batch`.
4. **Act as Commander, Translator & Verifier**:
   - Translate high-level user requests into structured, unambiguous prompts for Codex.
   - Always link the saved verbatim Markdown report (`file:///...`) alongside a clear, plain-language explanation of what Codex did, any errors encountered, and recommended next steps.

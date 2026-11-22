# Codex Bridge Guidelines (v1.2 — Mandatory Commander Relay)

When the user asks to interact with **Codex** (dispatching tasks, commanding Codex across projects, running independent code reviews, forking/branching Codex sessions, checking pending Codex feedback, promoting hidden `exec` threads into Codex Desktop UI, checking Codex quota/models, or viewing Codex analytics dashboards):

1. **Load the `codex-commander` skill** before orchestrating tasks, handling Codex feedback, or generating Generative UI dashboards.
2. **MANDATORY COMMANDER RELAY RULE (核心铁律：所有完成结果与中途反馈必须由你再次经手转达)**:
   - **Never treat dispatching to Codex as the end of your job.** Whenever a Codex task finishes (foreground or background wakeup), pauses with questions (`needs_clarification`), hits a sandbox boundary (`blocked_by_sandbox`), or updates externally in Codex Desktop / Web Console:
     1. **Inspect & Cross-Verify** the `commanderRelay` digest (`filesChanged`, `commands` exit codes, `elicitedQuestions`, `detectedQuestions`, `blockedApprovals`, and `finalReply`).
     2. **Auto-Resolve Trivial Technical Questions**: If Codex asks a factual question answerable from workspace files, answer Codex directly by resuming `--thread <uuid>` without troubling the user.
     3. **Translate & Relay to User**: Present a clear, plain-language explanation of what Codex actually accomplished, translate stack traces / domain metrics / follow-up questions into actionable choices for the user, attach the verbatim `[Raw Execution Report](file:///...)` link, and mark any Relay Inbox item acknowledged (`codex_bridge_relay_inbox(ackIds=[...])`).
3. **Use fast MCP tools (`codex-bridge`, 13 tools) for instant structured operations**:
   - `codex_bridge_relay_inbox` & `codex_bridge_digest_thread`: Check un-relayed completions/questions (including external Codex Desktop UI turns) and produce structured verification digests.
   - `codex_bridge_overview`, `codex_bridge_quota_and_models`, `codex_bridge_doctor`: Analytics, live rate-limit %, model catalog, and 8-point health check.
   - `codex_bridge_list_projects`, `codex_bridge_list_threads`, `codex_bridge_read_thread`, `codex_bridge_export_report`: Browse projects/threads and inspect or export verbatim transcripts.
   - `codex_bridge_create_thread`, `codex_bridge_fork_thread`, `codex_bridge_promote_exec_threads`, `codex_bridge_open_ui`: Native UI-synced session lifecycle management.
4. **Use `codex-ctl` (`codex_ctl.py`) via `run_command` for long-running task execution**:
   - Run `~/.gemini/config/plugins/codex-bridge/bin/codex-ctl.cmd` (Windows) or `~/.gemini/config/plugins/codex-bridge/bin/codex-ctl` (macOS/Linux) with `dispatch --ack-relay`, `review`, or `batch`.
   - **Desktop Writer-Lock Auto-Bypass (`v1.2.2+`)**: Codex Desktop (`26.1117+`) holds an exclusive OS lock (`already has an active writer`) on any thread open in its UI, even when idle. `codex-ctl dispatch --thread <id_or_prefix_or_uri>` **automatically detects this lock and seamlessly `thread/fork`s** 100% of the conversation history into an unlocked `[AGY 续]` continuation session (`autoForkedFrom` is returned in JSON). **Never interrupt or ask the user how to handle a Codex Desktop writer lock**—dispatch directly with `--thread <id>` and use the returned `threadId` on subsequent turns.
   - Standalone Live Web Console runs on port **`18765`** by default (`http://127.0.0.1:18765`, with automatic free-port fallback if `18765` is busy).

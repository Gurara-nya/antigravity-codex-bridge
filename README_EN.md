<div align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Codex Bridge Logo" />
  <h1>Antigravity Codex Bridge</h1>
  <p><strong>Native Dual-Agent Orchestration, Zero-Click UI Sync & Visual Analytics Plugin for Google Antigravity ↔ OpenAI Codex</strong></p>
  <p>
    <a href="./README.md">中文文档</a> ·
    <a href="#-why-codex-bridge">Why Codex Bridge</a> ·
    <a href="#-three-visual-surfaces">Visual Dashboards</a> ·
    <a href="#-quick-install">Quick Install</a>
  </p>
</div>

---

## ✨ Overview

**Antigravity Codex Bridge (`codex-bridge`)** is a zero-dependency (Python 3.11+ stdlib only) native plugin for **Google Antigravity**. It turns Antigravity into your **Lead Architect, Prompt Translator, and Verifier** while orchestrating **OpenAI Codex (Desktop & CLI)** as a seamlessly synced execution and adversarial review engine across **Windows, macOS, and Linux**.

---

## 🚀 Why Codex Bridge?

- **Zero-Click Native Codex Desktop UI Sync**: Standard `codex exec` sessions are tagged `source="exec"` and hidden from the Codex Desktop sidebar by default. Codex Bridge speaks the official `codex app-server --stdio` JSON-RPC protocol (`clientInfo="Codex Desktop"`) to create native `source="vscode"` threads, name them clearly, and bind them directly to your Codex Projects—plus 1-click promotion for legacy `exec` sessions.
- **Auto-Discovery on Windows MSIX / macOS / Linux**: Automatically locates bundled `codex` binaries inside Microsoft Store `OpenAI.Codex` packages, macOS `.app` bundles, `config.toml`, or `.sandbox-bin` even when `codex` is absent from `PATH`.
- **Dual-Speed Architecture (Never Times Out)**:
  - **11 Fast Native MCP Tools** for sub-second analytics, live rate-limit quota checks, project/session lookup, transcript inspection, native thread creation, and session forking (`thread/fork`).
  - **Async Streaming CLI (`codex-ctl`) + `codex-delegate` Subagent** for multi-minute coding, adversarial reviews, parallel batches, and simulations—saving verbatim Markdown execution reports on every turn.
- **Commander + Translator Loop**: Speak high-level goals in plain language; Antigravity formulates rigorous technical prompts, supervises Codex, verifies raw command outputs, and explains results clearly with direct links to verbatim logs.

---

## 📊 Three Visual Surfaces

1. **Inline Generative UI Widget**: Compact in-chat card displaying project counts, UI session totals, live account quota remaining % & reset countdown, model token share, and 14-day activity bars.
2. **4-Tab Full-Screen Side-Pane Artifact**: Interactive analytics overview, searchable project browser, session & fork manager, and domain-agnostic task prompt builder.
3. **Live Local Web Console (`http://127.0.0.1:8765`)**: Run `codex-ctl serve-web` to browse full raw transcripts & shell outputs in real time, fork threads, export Markdown reports, promote `exec` sessions, or dispatch new UI-synced tasks from your browser.

---

## ⚡ Quick Install

Requires **Python 3.11+** (zero third-party packages) and an authenticated **Codex Desktop** or **Codex CLI** installation.

**Windows (PowerShell):**
```powershell
git clone https://github.com/Gurara-nya/antigravity-codex-bridge.git
cd antigravity-codex-bridge
.\install.ps1
```

**macOS / Linux:**
```bash
git clone https://github.com/Gurara-nya/antigravity-codex-bridge.git
cd antigravity-codex-bridge
chmod +x install.sh && ./install.sh
```

---

## 🧪 Testing & Release Packaging

```bash
python tests/test_codex_bridge.py
python scripts/build_release.py
```

## 📄 License

Released under the [MIT License](./LICENSE).

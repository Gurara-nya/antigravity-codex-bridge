<div align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Codex Bridge Logo" />
  <h1>Antigravity Codex Bridge</h1>
  <p><strong>Native Dual-Agent Orchestration, Mandatory Commander Feedback Relay, Zero-Click UI Sync & Visual Analytics Plugin for Google Antigravity ↔ OpenAI Codex</strong></p>
  <p>
    <a href="./README.md">中文文档</a> ·
    <a href="#-quick-start-recommended-official-release-zip">Quick Start (Release ZIP)</a> ·
    <a href="#-why-codex-bridge">Why Codex Bridge</a> ·
    <a href="#-testing--release-zip-verification">Verification</a>
  </p>
</div>

---

## ⚡ Quick Start (Recommended: Official Release ZIP)

### 1. Prerequisites
- **Python 3.11+** (stdlib only — **zero `pip install` dependencies**; on Windows, `install.ps1` automatically probes all installed Python binaries and skips versions older than 3.11).
- **Google Antigravity** (IDE, Desktop 2.0, or CLI).
- **OpenAI Codex** (authenticated **Codex Desktop** or **Codex CLI**).

### 2. Download & Extract the Official Release ZIP
Download `antigravity-codex-bridge-v1.2.1.zip` from [**GitHub Releases (Latest)**](https://github.com/Gurara-nya/antigravity-codex-bridge/releases/latest) (or [v1.2.1 Expanded Assets](https://github.com/Gurara-nya/antigravity-codex-bridge/releases/expanded_assets/v1.2.1)) and extract it. Extracting creates a `codex-bridge/` folder.

### 3. Run the Installer Script
Open a terminal inside the extracted `codex-bridge/` folder:

**Windows (PowerShell):**
```powershell
cd .\codex-bridge
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**macOS / Linux:**
```bash
cd ./codex-bridge
chmod +x install.sh && ./install.sh
```

The installer strictly separates **file installation** from **Bridge readiness** and prints **one of three explicit final outcomes**:
1. **`安装完成，自检通过 (Installed, self-check passed)`**: Python 3.11+, Codex binary, credentials, and live `codex app-server --stdio` JSON-RPC handshake all succeeded (optional Desktop project library advisories are noted separately if applicable).
2. **`文件已安装，自检未通过 (Files installed, self-check failed)`**: Plugin files are installed, but Codex is missing, unauthenticated, or failed the `app-server` handshake. Actionable next steps are printed immediately. Pass `--strict-doctor` in CI/automation to exit with code `1` when self-check fails.
3. **`文件已安装，跳过自检 (Files installed, self-check skipped)`**: Printed when `--skip-doctor` is used.

### 4. Re-running `doctor` Standalone Anytime
After signing in to Codex or updating your binary, re-verify readiness directly without reinstalling (`0` = Bridge ready, `1` = unavailable):

- **Windows (PowerShell):**
  ```powershell
  & "$HOME\.gemini\config\plugins\codex-bridge\bin\codex-ctl.cmd" doctor
  ```
- **macOS / Linux:**
  ```bash
  "$HOME/.gemini/config/plugins/codex-bridge/bin/codex-ctl" doctor
  ```

### 5. Confirming the Plugin Works Inside Antigravity (First Run)
1. Open `customization://codex-bridge` inside Antigravity and confirm **Codex Bridge** is **Enabled** with its `codex-bridge` MCP server and `codex-commander` skill listed.
2. In your next chat turn, send:
   > `Run codex_bridge_doctor and codex_bridge_overview to verify Codex Bridge connectivity, discovered projects, and remaining quota.`
   Seeing `"healthy": true` confirms end-to-end connectivity!

---

## 🛠️ Developer Install (From Source via Git)

```bash
git clone https://github.com/Gurara-nya/antigravity-codex-bridge.git
cd antigravity-codex-bridge
# Windows PowerShell: .\install.ps1
# macOS / Linux:      ./install.sh
```

---

## 🚀 Why Codex Bridge?

- **Mandatory Commander Relay Loop (`commanderRelay` + Relay Inbox)**: Captures every Codex completion, mid-turn `request_user_input` question, non-zero command exit, and `read-only` sandbox escalation into a structured digest so Antigravity always verifies and translates outcomes for you.
- **Strict Layered Readiness Diagnostics (`doctor`)**: Distinguishes core blockers (including live `app-server` JSON-RPC handshake) from optional Desktop DB advisories, returning accurate exit codes (`0` vs `1`).
- **Zero-Click Native Codex Desktop UI Sync**: Creates `source="vscode"` (`originator="Codex Desktop"`) sessions directly via `codex app-server --stdio` and assigns them to your Projects—plus 1-click promotion for legacy `exec` threads.
- **13 Native MCP Tools + Async `codex-ctl` Engine + 3 Visual Surfaces**: Inline Generative UI Widget, 4-tab Side-Pane Control Center, and standalone Live Web Console on port **`18765`** (`18765..18799` auto-fallback).

---

## 🧪 Testing & Release ZIP Verification

```bash
python tests/test_codex_bridge.py
python scripts/build_release.py
python tests/test_release_zip.py
```

## 📄 License

Released under the [MIT License](./LICENSE).

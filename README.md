<div align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Codex Bridge Logo" />
  <h1>Antigravity Codex Bridge</h1>
  <p><strong>原生级 Google Antigravity ↔ OpenAI Codex 双引擎协同编排、强制总工转达闭环、UI 无感同步与可视化统计插件</strong></p>
  <p>
    <a href="./README_EN.md">English Documentation</a> ·
    <a href="#-快速开始推荐下载正式发布包安装">快速开始 (ZIP 安装)</a> ·
    <a href="#-核心优势解决什么痛点">核心优势</a> ·
    <a href="#-三层可视化与统计交互体验">可视化面板</a> ·
    <a href="#-功能清单">功能参考</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/version-1.2.2-3B82F6" alt="Version 1.2.2" />
    <img src="https://img.shields.io/badge/python-3.11%2B%20(zero%20deps)-10B981" alt="Python 3.11+ Zero Dependencies" />
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-6366F1" alt="Cross Platform" />
    <img src="https://img.shields.io/badge/license-MIT-slate" alt="MIT License" />
  </p>
</div>

---

## ⚡ 快速开始（推荐：下载正式发布包安装）

### 1. 环境准备
- **Python 3.11 或更高版本**（仅使用标准库，**无需 `pip install` 任何第三方依赖**；Windows 安装脚本会自动跳过旧版 Python 并寻找本机已安装的 Python 3.11+）。
- **Google Antigravity**（IDE / Desktop 2.0 / CLI 任一形态）。
- **OpenAI Codex**（已安装并完成账号登录的 **Codex Desktop 桌面端** 或 **Codex CLI**）。

### 2. 下载并解压正式发布 ZIP
前往 [**GitHub Releases 最新版本页面**](https://github.com/Gurara-nya/antigravity-codex-bridge/releases/latest)（或直接查看 [v1.2.2 发布资产列表](https://github.com/Gurara-nya/antigravity-codex-bridge/releases/expanded_assets/v1.2.2)），下载 `antigravity-codex-bridge-v1.2.2.zip` 并解压。解压后会得到 `codex-bridge` 文件夹。

### 3. 运行安装脚本
进入解压后的 `codex-bridge` 目录，运行对应系统的安装脚本：

**Windows (PowerShell)：**
```powershell
cd .\codex-bridge
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**macOS / Linux：**
```bash
cd ./codex-bridge
chmod +x install.sh && ./install.sh
```

安装器会严格区分 **“插件文件落盘”** 与 **“Bridge 连通就绪”**，并在末尾明确打印以下 **三种结果之一**：
1. **`安装完成，自检通过`**：Python 3.11+、Codex 可执行文件、登录凭证与 `codex app-server --stdio` JSON-RPC 握手全部通过，插件立即可用（若尚未打开过 Codex Desktop 项目库，会单独列出非阻塞的**功能受限提示**）。
2. **`文件已安装，自检未通过`**：插件文件已就位，但找不到 Codex、未登录或 `app-server` 握手失败；终端会直接给出对应的**下一步修复动作**（自动化/CI 场景可加 `--strict-doctor` 让自检未通过时返回退出码 `1`）。
3. **`文件已安装，跳过自检`**：传入 `--skip-doctor` 时仅安装文件并跳过连通性检查。

### 4. 如何单独重跑 `doctor` 自检
修复 Codex 登录或升级客户端后，无需重新解压安装，随时可单独重跑 `doctor`（全部核心项通过返回退出码 `0`，否则返回 `1`）：

- **Windows (PowerShell)**：
  ```powershell
  & "$HOME\.gemini\config\plugins\codex-bridge\bin\codex-ctl.cmd" doctor
  ```
- **macOS / Linux**：
  ```bash
  "$HOME/.gemini/config/plugins/codex-bridge/bin/codex-ctl" doctor
  ```

### 5. 首次在 Antigravity 中确认插件真的可用
1. **查看插件管理页**：在 Antigravity 聊天框或地址栏打开 `customization://codex-bridge`，确认 **Codex Bridge** 处于启用（Enabled）状态，且列出了 `codex-bridge` MCP 服务与 `codex-commander` 技能。
2. **发起首条只读连通验证**：新开一轮对话（或在当前对话下一轮）发送：
   > `请调用 codex_bridge_doctor 检查 Codex Bridge 状态，并调用 codex_bridge_overview 告诉我当前发现了多少个 Codex 项目与实时剩余配额。`
   当 Antigravity 返回 `"healthy": true` 及你的本机项目数/配额百分比时，即代表 **Antigravity ↔ Codex Bridge ↔ Codex** 全链路已打通！

---

## 🛠️ 开发与源码安装（Git Clone）

如果你需要二次开发、参与贡献或通过 Git 跟踪更新：

```bash
git clone https://github.com/Gurara-nya/antigravity-codex-bridge.git
cd antigravity-codex-bridge
# Windows PowerShell 运行: .\install.ps1
# macOS / Linux 运行:      ./install.sh
```

后续升级只需执行 `git pull` 后再次运行安装脚本即可。

---

## ✨ 项目简介

**Antigravity Codex Bridge (`codex-bridge`)** 将 **Google Antigravity** 打造成你的 **“总工程师 + 需求翻译官 + 强制验收转达中枢”**，把本机已安装的 **OpenAI Codex（Desktop 桌面端 / CLI）** 变成随时待命的 **“二号执行与独立审查引擎”**。

无论是 **全栈软件开发、独立交叉 Code Review、系统脚本与电脑自动化、学术论文与数据处理、还是 CAE/CFD 科学工程仿真**，你只需用大白话描述目标，插件即可完成：
**澄清与翻译需求 → 原生创建 Codex Desktop UI 可见会话 → 异步流式执行与中途追问拦截 → 生成结构化核验摘要（`commanderRelay`） → 由 Antigravity 二次把关并用通俗中文向你转达结论**。

---

## 🚀 核心优势（解决什么痛点？）

| 传统双工具割裂痛点 | Codex Bridge v1.2.2 原生解决方案 |
| :--- | :--- |
| **执行后没人兜底解读**：普通 CLI 跑完吐出一堆晦涩日志，或者 Codex 中途追问参数、权限受阻时无人接应 | **强制总工转达闭环（Commander Relay）**：拦截 `request_user_input` 中途提问与只读越权请求，自动归类 5 种状态并写入 **Relay Inbox**，强制经由 Antigravity 核验翻译后再转达给你 |
| **安装成功却连不上**：传统脚本复制完文件就报成功，真正调用时才发现旧版 Python、缺登录态或握手失败 | **严格分层首装自检（`doctor`）**：区分核心阻断项（含 `app-server` 实时握手）与桌面端可选提示，按真实可用性返回退出码并给出下一步修复命令 |
| **命令行新建会话在 UI 消失**：直接跑 `codex exec` 会被打上 `source="exec"` 标签，被 Codex 桌面端侧边栏默认过滤隐藏 | **零手动原生 UI 同步**：对接官方 `codex app-server --stdio`（`clientInfo="Codex Desktop"`），原生创建 `source="vscode"` 对话、自动命名并归入目标 Project；支持历史 `exec` 会话一键转正 |
| **Windows 桌面版找不到 CLI**：安装 Microsoft Store 版 Codex Desktop 后系统 `PATH` 无 `codex` 命令 | **全平台动态寻址**：自动从配置、MSIX 包目录、macOS App Bundle 或 `.sandbox-bin` 定位最新 `codex` 可执行文件 |
| **MCP 同步调用长任务必超时**：复杂重构、测试或仿真运行数分钟至数十分钟，纯 MCP 工具极易断连 | **快慢分离双通道架构**：毫秒级查询/收件箱/建会话走 **13 个原生 MCP 工具**；长耗时任务走 **`codex-ctl` 异步流式引擎 + `codex-delegate` 子代理** |
| **配额黑盒 & 端口冲突**：不清楚周配额剩余多少；常见端口易冲突 | **实时配额监控 + 智能防冲突端口**：实时展示剩余配额百分比与重置倒计时；本地 Web 控制台默认使用 **`18765`** 端口并支持 `18765..18799` 自动顺延 |

---

## 🧠 架构与总工转达闭环 (Commander Relay)

```mermaid
flowchart LR
    U["👤 用户 (大白话提目标 / 做决策)"] -->|"1. 口述目标"| AGY["🧭 Antigravity (总工翻译与把关)"]
    AGY -->|"2. 严谨技术指令 + 原生 UI 会话"| ENG["📦 Codex Bridge Engine (v1.2.2)"]
    ENG <-->|"JSON-RPC 2.0 (拦截提问/权限/补丁)"| APP["🔌 codex app-server --stdio"]
    APP --> UI["🖥️ Codex Desktop UI (对应 Project 实时同步)"]
    ENG -->|"3. commanderRelay 核验包 + Relay Inbox"| AGY
    AGY -->|"4. 核对退出码/Diff · 通俗中文转达 + 原文链接"| U
```

---

## 📊 三层可视化与统计交互体验

1. **Antigravity 对话内联卡片（Inline Generative UI Widget）**：展示纳管项目数、UI 可见会话数、账户实时剩余配额 % 与重置倒计时、模型 Token 占比条与近期趋势图。
2. **Antigravity 侧边栏全屏控制台（4-Tab Standalone Artifact）**：包含数据与实时配额、项目库检索、会话与分支（Fork）管理、泛用交互式派单器。
3. **独立本地实时 Web 控制台（默认 `http://127.0.0.1:18765`，空闲端口自动顺延）**：运行 `codex-ctl serve-web` 打开，支持在线阅读完整原始问答与底层命令输出、一键点击 **「📨 交由 Antigravity 解读转达」**、一键 Fork 分支或导出 Markdown 报告。

---

## 🧰 功能清单

### 1. 13 个原生 MCP 工具（`codex-bridge`）
| MCP 工具名 | 用途说明 |
| :--- | :--- |
| `codex_bridge_relay_inbox` | 检查待转达的任务完成结果、中途提问及 Codex 桌面端外部新动态，支持已读确认（`ack`） |
| `codex_bridge_digest_thread` | 为任意会话生成结构化 `commanderRelay` 核验摘要供总工转达 |
| `codex_bridge_doctor` | 8 项分层环境自检（区分核心阻断项与桌面可选提示，验证 `app-server` 实时握手） |
| `codex_bridge_overview` | 全局项目、会话分类计数、待转达数、模型 Token 分布与每日活跃趋势 |
| `codex_bridge_quota_and_models` | 实时查询 Codex 账户配额已用/剩余百分比、重置时间及可用模型目录 |
| `codex_bridge_list_projects` | 检索全部 Codex Desktop 项目（含根路径、会话数、累计 Token 与最近活跃时间） |
| `codex_bridge_list_threads` | 按项目、关键词或可见性（`ui` / `exec` / `subagent`）检索会话 |
| `codex_bridge_read_thread` | 读取任意会话的原始用户指令、推理摘要、执行的底层命令及原始回复 |
| `codex_bridge_export_report` | 将任意历史会话一键导出为结构清晰的独立 Markdown 报告 |
| `codex_bridge_create_thread` | 在目标项目下原生创建带自定义标题的 Codex Desktop UI 会话 |
| `codex_bridge_fork_thread` | 基于已有会话无损派生（Fork）独立新分支 |
| `codex_bridge_promote_exec_threads` | 将旧版命令行 `source="exec"` 隐藏会话批量转正显示到 Codex Desktop UI |
| `codex_bridge_open_ui` | 直接拉起 Codex Desktop 桌面窗口并定位到目标项目工作区 |

### 2. 命令行控制器（`codex-ctl` / `scripts/codex_ctl.py`）
支持 `doctor`、`quota`、`inbox`、`digest`、`overview`、`projects`、`threads`、`read`、`export-report`、`create`、`fork`、`dispatch`、`review`、`batch`、`promote`、`open-ui`、`export-ui`、`serve-web` 共 **18 个子命令**。

---

## 🧪 自动化验证与真实发行包测试

```bash
# 1. 隔离单元与 MCP 协议集成测试
python tests/test_codex_bridge.py

# 2. 清单校验、隐私扫描并构建正式发行包 (dist/*.zip + .sha256)
python scripts/build_release.py

# 3. 从构建出的真实 ZIP 解压到临时目录，回归测试自检通过 / 握手失败 / 跳过自检三条路径与退出码
python tests/test_release_zip.py
```

## 📄 开源协议

本项目基于 [MIT License](./LICENSE) 开源。

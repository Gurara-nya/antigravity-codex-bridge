#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Interactive Local Web Control Center for `antigravity-codex-bridge` (v1.1.0).
Provides real-time browsing of projects & raw thread transcripts, live quota & model picker,
1-click session forking, Markdown report export, `exec` promotion, and direct UI-synced dispatch.
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

import codex_engine as engine  # noqa: E402

ACTIVE_JOBS: dict[str, dict[str, Any]] = {}

WEB_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Codex Bridge v1.1 Live Console</title>
  <style>
    :root {
      --bg: #0b0f19; --card: #131a2a; --border: #232f46; --fg: #e5ecff; --muted: #8ea0c0;
      --primary: #4f7cff; --success: #10b981; --warn: #f59e0b; --code: #090d16;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--fg); font-size: 13px; }
    header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; padding: 14px 24px; border-bottom: 1px solid var(--border); background: rgba(19,26,42,0.88); position: sticky; top: 0; z-index: 10; backdrop-filter: blur(8px); }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 16px; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--success); display: inline-block; }
    .badge { font-family: ui-monospace, Consolas, monospace; font-size: 11px; padding: 3px 8px; border-radius: 999px; background: var(--code); border: 1px solid var(--border); color: var(--muted); }
    .container { max-width: 1320px; margin: 0 auto; padding: 20px 24px; display: grid; grid-template-columns: 330px 1fr; gap: 18px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }
    .kpis { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .kpi-val { font-size: 22px; font-weight: 700; font-family: ui-monospace, Consolas, monospace; margin-top: 4px; }
    .muted { color: var(--muted); font-size: 12px; }
    input, select, textarea { width: 100%; background: var(--code); color: var(--fg); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px; outline: none; }
    button { background: var(--primary); color: #fff; border: none; border-radius: 8px; padding: 7px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
    button.ghost { background: transparent; border: 1px solid var(--border); color: var(--fg); }
    button:hover { opacity: 0.92; }
    .list { max-height: 560px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
    .item { padding: 9px 10px; border-radius: 8px; border: 1px solid transparent; cursor: pointer; background: rgba(255,255,255,0.02); }
    .item:hover, .item.active { border-color: var(--primary); background: rgba(79,124,255,0.1); }
    .msg { padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 8px; white-space: pre-wrap; line-height: 1.5; }
    .msg.user { border-left: 3px solid var(--primary); }
    .msg.assistant { border-left: 3px solid var(--success); background: rgba(16,185,129,0.04); }
    pre { background: var(--code); padding: 10px; border-radius: 8px; overflow-x: auto; border: 1px solid var(--border); font-size: 11.5px; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="dot"></span>
      <span>Codex Bridge v1.1 · 实时交互控制台</span>
      <span id="ver" class="badge">加载中...</span>
      <span id="quota-badge" class="badge" style="display:none;"></span>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="ghost" onclick="promoteExec()">一键转正隐藏 Exec</button>
      <button onclick="openNewModal()">+ 新建 UI 同步任务</button>
      <button class="ghost" onclick="loadAll()">刷新</button>
    </div>
  </header>

  <div class="container">
    <div class="kpis">
      <div class="card"><div class="muted">纳管项目</div><div id="k-proj" class="kpi-val">-</div></div>
      <div class="card"><div class="muted">UI 可见主会话</div><div id="k-ui" class="kpi-val">-</div></div>
      <div class="card"><div class="muted">实时剩余配额</div><div id="k-quota" class="kpi-val">-</div></div>
      <div class="card"><div class="muted">累计 Token 消耗</div><div id="k-tok" class="kpi-val">-</div></div>
    </div>

    <div class="card">
      <div style="font-weight:600; margin-bottom:8px;">1. 选择项目过滤</div>
      <select id="proj-sel" onchange="loadThreads()"><option value="">全部项目</option></select>
      <div style="display:flex; gap:6px; margin-top:8px;">
        <button class="ghost" style="flex:1" onclick="openDesktop()">在 Codex 桌面端打开项目</button>
      </div>
      <hr style="border:none; border-top:1px solid var(--border); margin:12px 0;" />
      <div style="font-weight:600; margin-bottom:8px;">2. 会话列表 (点击查看原始执行过程)</div>
      <input id="thr-q" placeholder="搜索会话标题或 UUID..." oninput="loadThreads()" />
      <div id="thr-list" class="list"></div>
    </div>

    <div class="card" id="detail-pane">
      <div id="empty-hint" class="muted" style="padding:40px 20px; text-align:center;">
        点击左侧任意会话即可实时读取它的原始对话、思维摘要与执行的每一条底层命令；支持一键派生新分支（Fork）或导出 Markdown 报告。
      </div>
      <div id="thr-detail" style="display:none;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; border-bottom:1px solid var(--border); padding-bottom:10px; margin-bottom:12px;">
          <div>
            <div id="d-title" style="font-size:15px; font-weight:700;"></div>
            <div id="d-meta" class="muted" style="margin-top:4px; font-family:monospace;"></div>
          </div>
          <div style="display:flex; gap:6px; shrink:0;">
            <button class="ghost" onclick="forkCurrent()">派生分支 (Fork)</button>
            <button class="ghost" onclick="exportCurrent()">导出 MD</button>
            <button onclick="openFollowup()">追加指令</button>
          </div>
        </div>
        <div id="d-followup" style="display:none; margin-bottom:14px; padding:12px; border:1px solid var(--primary); border-radius:10px;">
          <textarea id="fu-prompt" rows="3" placeholder="输入要发给此会话的指令..."></textarea>
          <div style="display:flex; gap:8px; margin-top:8px; justify-content:flex-end;">
            <select id="fu-sb" style="width:180px;"><option value="read-only">只读 (read-only)</option><option value="workspace-write">读写 (workspace-write)</option></select>
            <button onclick="submitDispatch(window.__curTid)">立即发送执行</button>
          </div>
        </div>
        <div id="d-body" style="max-height:600px; overflow-y:auto;"></div>
      </div>

      <div id="new-modal" style="display:none;">
        <h3 style="margin-top:0;">新建原生 Codex Desktop UI 会话并派发任务</h3>
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:10px;">
          <div><label class="muted">目标项目</label><select id="nm-proj"></select></div>
          <div><label class="muted">模型 (可选)</label><select id="nm-model"><option value="">默认模型</option></select></div>
          <div><label class="muted">权限沙盒</label><select id="nm-sb"><option value="read-only">只读分析 (read-only)</option><option value="workspace-write">允许改写项目文件 (workspace-write)</option></select></div>
        </div>
        <div style="margin-bottom:10px;"><label class="muted">会话标题 (直接显示在 Codex UI 左侧栏)</label><input id="nm-title" placeholder="例如：[AGY] 模块重构与边界检查" /></div>
        <div style="margin-bottom:10px;"><label class="muted">执行指令</label><textarea id="nm-prompt" rows="5" placeholder="输入详细任务指令..."></textarea></div>
        <button onclick="submitDispatch(null)">创建 UI 会话并后台启动</button>
        <div id="nm-status" class="muted" style="margin-top:10px;"></div>
      </div>
    </div>
  </div>

  <script>
    async function api(path, opts) {
      const r = await fetch(path, opts);
      return await r.json();
    }
    async function loadAll() {
      const ov = await api('/api/overview');
      document.getElementById('ver').textContent = ov.codexVersion + (ov.desktopRunning ? ' · 桌面端运行中' : ' · 桌面端待命');
      document.getElementById('k-proj').textContent = ov.projectCount;
      document.getElementById('k-ui').textContent = ov.threads.ui;
      document.getElementById('k-tok').textContent = ov.tokens.totalFormatted;

      const qt = await api('/api/quota');
      if (qt && qt.available && qt.primaryWindow && qt.primaryWindow.remainingPercent != null) {
        document.getElementById('k-quota').textContent = qt.primaryWindow.remainingPercent + '%';
        const qb = document.getElementById('quota-badge');
        qb.style.display = 'inline-block';
        qb.textContent = `已用 ${qt.primaryWindow.usedPercent}% · ${qt.primaryWindow.resetsInHours || '?'}h 后重置`;
        const mSel = document.getElementById('nm-model');
        mSel.innerHTML = '<option value="">默认模型</option>';
        (qt.models || []).forEach(m => {
          mSel.innerHTML += `<option value="${m.id}">${m.id}</option>`;
        });
      } else {
        document.getElementById('k-quota').textContent = ov.threads.subagent + ' sub';
      }

      const projs = await api('/api/projects');
      const sel = document.getElementById('proj-sel');
      const nmSel = document.getElementById('nm-proj');
      const cur = sel.value;
      sel.innerHTML = '<option value="">全部项目 (' + projs.length + ')</option>';
      nmSel.innerHTML = '';
      projs.forEach(p => {
        sel.innerHTML += `<option value="${p.name}">${p.name} (${p.uiThreadCount})</option>`;
        nmSel.innerHTML += `<option value="${p.name}">${p.name} — ${p.primaryPath}</option>`;
      });
      sel.value = cur;
      await loadThreads();
    }
    async function loadThreads() {
      const proj = document.getElementById('proj-sel').value;
      const q = document.getElementById('thr-q').value;
      const list = await api(`/api/threads?project=${encodeURIComponent(proj)}&search=${encodeURIComponent(q)}`);
      const el = document.getElementById('thr-list');
      el.innerHTML = '';
      list.forEach(t => {
        const div = document.createElement('div');
        div.className = 'item' + (window.__curTid === t.id ? ' active' : '');
        const tag = t.visibility === 'hidden_exec' ? '<span style="color:#f59e0b">[exec隐藏]</span> ' : '';
        div.innerHTML = `<div style="font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${tag}${escapeHtml(t.title)}</div>
          <div class="muted" style="margin-top:3px;">${escapeHtml(t.projectName)} · ${t.tokensFormatted} · ${(t.updatedAt||'').slice(5,16)}</div>`;
        div.onclick = () => inspectThread(t.id);
        el.appendChild(div);
      });
    }
    async function inspectThread(tid) {
      window.__curTid = tid;
      document.getElementById('empty-hint').style.display = 'none';
      document.getElementById('new-modal').style.display = 'none';
      document.getElementById('thr-detail').style.display = 'block';
      document.getElementById('d-body').innerHTML = '<div class="muted">正在读取原始日志...</div>';
      const d = await api(`/api/thread?id=${encodeURIComponent(tid)}`);
      document.getElementById('d-title').textContent = d.title;
      document.getElementById('d-meta').textContent = `UUID: ${d.id} | 目录: ${d.cwd} | 模型: ${d.model} | 来源: ${d.source} | Token: ${d.tokensFormatted}`;
      let html = '';
      (d.recentMessages || []).forEach(m => {
        const cls = m.role === 'user' ? 'user' : 'assistant';
        const who = m.role === 'user' ? '👤 输入指令 (User)' : '🤖 Codex 原始回复 (Assistant)';
        html += `<div class="msg ${cls}"><div class="muted" style="margin-bottom:4px;font-weight:600;">${who} · ${m.timestamp || ''}</div>${escapeHtml(m.text)}</div>`;
      });
      if ((d.recentToolCalls || []).length) {
        html += `<h4 style="margin:14px 0 6px;">最近执行的底层命令 / 工具调用 (${d.totalToolCalls})</h4>`;
        d.recentToolCalls.slice(-12).forEach(c => {
          html += `<pre><b>[${escapeHtml(c.tool)}]</b> ${escapeHtml(c.input)}\n${c.outputPreview ? '--- 输出 ---\n' + escapeHtml(c.outputPreview) : ''}</pre>`;
        });
      }
      document.getElementById('d-body').innerHTML = html || '<div class="muted">该会话暂无消息内容。</div>';
      loadThreads();
    }
    function escapeHtml(s) {
      return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function openNewModal() {
      document.getElementById('empty-hint').style.display = 'none';
      document.getElementById('thr-detail').style.display = 'none';
      document.getElementById('new-modal').style.display = 'block';
    }
    function openFollowup() {
      const el = document.getElementById('d-followup');
      el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }
    async function forkCurrent() {
      if (!window.__curTid) return;
      const title = prompt('请输入派生分支的新标题（可留空自动生成）：', '');
      if (title === null) return;
      const res = await api('/api/fork', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({threadId: window.__curTid, title: title || undefined})});
      if (res.error) return alert(res.error);
      await loadAll();
      inspectThread(res.threadId);
    }
    async function exportCurrent() {
      if (!window.__curTid) return;
      const res = await api('/api/export-report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({threadId: window.__curTid})});
      alert(res.error ? res.error : `已导出完整 Markdown 报告至：\n${res.outputPath}`);
    }
    async function promoteExec() {
      const res = await api('/api/promote', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      alert(res.error ? res.error : `成功将 ${res.promotedCount} 条隐藏 exec 会话转正至 Codex UI！`);
      loadAll();
    }
    async function openDesktop() {
      const proj = document.getElementById('proj-sel').value;
      await api('/api/open-ui', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({project:proj})});
    }
    async function submitDispatch(tid) {
      const payload = tid ? {
        threadId: tid,
        sandbox: document.getElementById('fu-sb').value,
        prompt: document.getElementById('fu-prompt').value
      } : {
        project: document.getElementById('nm-proj').value,
        model: document.getElementById('nm-model').value || undefined,
        sandbox: document.getElementById('nm-sb').value,
        title: document.getElementById('nm-title').value,
        prompt: document.getElementById('nm-prompt').value
      };
      if (!payload.prompt || !payload.prompt.trim()) return alert('请输入指令内容');
      const st = document.getElementById('nm-status');
      if (st) st.textContent = '已提交后台执行，正在运行...';
      const res = await api('/api/dispatch', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      if (res.jobId) pollJob(res.jobId);
    }
    async function pollJob(jid) {
      const st = document.getElementById('nm-status');
      const iv = setInterval(async () => {
        const j = await api(`/api/job?id=${jid}`);
        if (st) st.textContent = `状态: ${j.status} ${j.lastLog || ''}`;
        if (j.status === 'done' || j.status === 'error') {
          clearInterval(iv);
          await loadAll();
          if (j.result && j.result.threadId) inspectThread(j.result.threadId);
          else if (j.error) alert('执行出错: ' + j.error);
        }
      }, 1500);
    }
    loadAll();
  </script>
</body>
</html>
"""


class BridgeRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _send_json(self, obj: Any, code: int = 200) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path in ("/", "/index.html"):
                raw = WEB_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if parsed.path == "/api/overview":
                return self._send_json(engine.get_overview_stats(include_live_quota=False))
            if parsed.path == "/api/quota":
                return self._send_json(engine.get_quota_and_models(include_models=True))
            if parsed.path == "/api/projects":
                return self._send_json(engine.list_projects(include_empty=True))
            if parsed.path == "/api/threads":
                proj = (qs.get("project") or [""])[0] or None
                search = (qs.get("search") or [""])[0] or None
                return self._send_json(engine.list_threads(project=proj, search=search, limit=50))
            if parsed.path == "/api/thread":
                tid = (qs.get("id") or [""])[0]
                return self._send_json(engine.read_thread(tid, max_messages=30, max_commands=30))
            if parsed.path == "/api/job":
                jid = (qs.get("id") or [""])[0]
                return self._send_json(ACTIVE_JOBS.get(jid, {"status": "unknown"}))
            self._send_json({"error": "not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
        try:
            if self.path == "/api/promote":
                return self._send_json(engine.promote_exec_threads(force=bool(body.get("force", False))))
            if self.path == "/api/open-ui":
                return self._send_json(engine.open_in_desktop_ui(body.get("project")))
            if self.path == "/api/fork":
                return self._send_json(engine.fork_ui_thread(thread_id=body["threadId"], title=body.get("title")))
            if self.path == "/api/export-report":
                return self._send_json(engine.export_thread_markdown(thread_id=body["threadId"]))
            if self.path == "/api/dispatch":
                import uuid

                jid = uuid.uuid4().hex[:10]
                ACTIVE_JOBS[jid] = {"status": "running", "lastLog": "initializing..."}

                def worker() -> None:
                    try:
                        res = engine.dispatch_task(
                            prompt=body["prompt"],
                            project=body.get("project"),
                            thread_id=body.get("threadId"),
                            title=body.get("title"),
                            model=body.get("model"),
                            sandbox=body.get("sandbox") or "read-only",
                            on_progress=lambda msg: ACTIVE_JOBS[jid].update({"lastLog": msg}),
                        )
                        ACTIVE_JOBS[jid] = {"status": "done", "result": res}
                    except Exception as ex:
                        ACTIVE_JOBS[jid] = {"status": "error", "error": str(ex)}

                threading.Thread(target=worker, daemon=True).start()
                return self._send_json({"jobId": jid, "status": "started"})
            self._send_json({"error": "not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    srv = ThreadingHTTPServer((host, port), BridgeRequestHandler)
    print(f"Codex Bridge Live Console listening on http://{host}:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    run_server()

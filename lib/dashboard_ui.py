#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generates Antigravity-native Generative UI HTML dashboards (inline widget & full-page artifact)
with live Rate-Limit Quota indicators, Model Catalog, Project Explorer, and Task Prompt Builder.
"""

from __future__ import annotations

import json
from typing import Any

from codex_engine import get_overview_stats, list_projects, list_threads


def build_inline_widget_html(stats: dict[str, Any] | None = None, include_live_quota: bool = True) -> str:
    data = stats or get_overview_stats(include_live_quota=include_live_quota)
    payload_json = json.dumps(
        {
            "version": data.get("codexVersion", ""),
            "desktopRunning": data.get("desktopRunning", False),
            "projectCount": data.get("projectCount", 0),
            "activeProjectCount": data.get("activeProjectCount", 0),
            "threads": data.get("threads", {}),
            "tokens": data.get("tokens", {}),
            "byModel": (data.get("byModel") or [])[:5],
            "daily": (data.get("dailyActivity") or [])[-14:],
            "dispatches": data.get("bridgeDispatches", {}).get("total", 0),
            "quota": (data.get("liveQuota") or {}).get("primaryWindow"),
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-0 m-0">
  <div class="py-2 space-y-3 select-none">
    <div class="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[var(--card-border)] text-xs">
      <div class="flex items-center gap-2">
        <span class="inline-block w-2 h-2 rounded-full" style="background: var(--success)"></span>
        <span class="font-semibold text-[var(--foreground)]">Codex Bridge v1.1</span>
        <span id="ver" class="font-mono text-[var(--muted-foreground)]"></span>
      </div>
      <div class="flex items-center gap-2">
        <span id="quota-pill" class="hidden px-2 py-0.5 rounded bg-[var(--card)] border border-[var(--card-border)] font-mono"></span>
        <button data-tab="models" class="tab-btn px-2 py-0.5 rounded bg-[var(--primary)] text-[var(--primary-foreground)] font-medium transition">模型与算力</button>
        <button data-tab="trend" class="tab-btn px-2 py-0.5 rounded text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition">近期趋势</button>
      </div>
    </div>

    <div class="grid grid-cols-4 gap-2 text-xs">
      <div class="p-2.5 rounded-lg bg-[var(--card)] border border-[var(--card-border)]">
        <div class="text-[var(--muted-foreground)]">纳管项目</div>
        <div id="kpi-proj" class="text-base font-bold font-mono tabular-nums mt-0.5"></div>
        <div id="kpi-proj-sub" class="text-xs text-[var(--muted-foreground)] mt-0.5"></div>
      </div>
      <div class="p-2.5 rounded-lg bg-[var(--card)] border border-[var(--card-border)]">
        <div class="text-[var(--muted-foreground)]">UI 可见会话</div>
        <div id="kpi-ui" class="text-base font-bold font-mono tabular-nums mt-0.5"></div>
        <div id="kpi-exec" class="text-xs text-[var(--muted-foreground)] mt-0.5"></div>
      </div>
      <div class="p-2.5 rounded-lg bg-[var(--card)] border border-[var(--card-border)]">
        <div class="text-[var(--muted-foreground)]">实时剩余配额</div>
        <div id="kpi-quota" class="text-base font-bold font-mono tabular-nums mt-0.5"></div>
        <div id="kpi-quota-sub" class="text-xs text-[var(--muted-foreground)] mt-0.5 truncate"></div>
      </div>
      <div class="p-2.5 rounded-lg bg-[var(--card)] border border-[var(--card-border)]">
        <div class="text-[var(--muted-foreground)]">累计 Token</div>
        <div id="kpi-tok" class="text-base font-bold font-mono tabular-nums mt-0.5"></div>
        <div id="kpi-agy" class="text-xs text-[var(--muted-foreground)] mt-0.5"></div>
      </div>
    </div>

    <div id="panel-models" class="space-y-1.5 pt-1"></div>
    <div id="panel-trend" class="hidden pt-1">
      <div id="bars" class="flex items-end gap-1.5 h-28 pt-2 px-1"></div>
      <div id="bar-labels" class="flex justify-between text-xs text-[var(--muted-foreground)] font-mono mt-1 px-1"></div>
    </div>
  </div>

  <script>
    const D = {payload_json};
    document.getElementById('ver').textContent = D.version + (D.desktopRunning ? ' · UI 运行中' : ' · UI 待命');
    document.getElementById('kpi-proj').textContent = D.projectCount;
    document.getElementById('kpi-proj-sub').textContent = D.activeProjectCount + ' 个活跃项目';
    document.getElementById('kpi-ui').textContent = D.threads.ui || 0;
    document.getElementById('kpi-exec').textContent = (D.threads.exec || 0) > 0 ? ('含 ' + D.threads.exec + ' 条可转正 exec') : '全部已同步 UI';
    if (D.quota && D.quota.remainingPercent != null) {{
      document.getElementById('kpi-quota').textContent = D.quota.remainingPercent + '%';
      document.getElementById('kpi-quota-sub').textContent = D.quota.resetsInHours != null ? (D.quota.resetsInHours + 'h 后重置') : '周配额正常';
    }} else {{
      document.getElementById('kpi-quota').textContent = D.threads.subagent || 0;
      document.getElementById('kpi-quota-sub').textContent = '内部子代理数';
    }}
    document.getElementById('kpi-tok').textContent = D.tokens.totalFormatted || '0';
    document.getElementById('kpi-agy').textContent = 'Bridge 已派发 ' + D.dispatches + ' 次';

    const pm = document.getElementById('panel-models');
    const colors = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)'];
    (D.byModel || []).forEach((m, idx) => {{
      const row = document.createElement('div');
      row.className = 'text-xs space-y-1';
      row.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="font-mono font-medium">${{m.model}}</span>
          <span class="font-mono text-[var(--muted-foreground)]">${{m.mainThreads}} 主会话 / ${{m.totalThreads}} 总 · ${{m.tokensFormatted}} (${{m.sharePct}}%)</span>
        </div>
        <div class="w-full h-1.5 rounded-full bg-[var(--secondary)] overflow-hidden">
          <div class="h-full rounded-full" style="width:${{Math.max(m.sharePct, 2)}}%; background:${{colors[idx % colors.length]}}"></div>
        </div>
      `;
      pm.appendChild(row);
    }});

    const barsEl = document.getElementById('bars');
    const lblEl = document.getElementById('bar-labels');
    const maxTok = Math.max(...(D.daily || []).map(x => x.tokens || 0), 1);
    (D.daily || []).forEach(d => {{
      const pct = Math.max(Math.round((d.tokens / maxTok) * 100), 6);
      const wrap = document.createElement('div');
      wrap.className = 'flex-1 flex flex-col items-center justify-end h-full';
      wrap.title = `${{d.date}}: ${{d.sessions}} 会话, ${{d.tokensFormatted}} tokens`;
      wrap.innerHTML = `<div class="w-full rounded-t transition-all opacity-85 hover:opacity-100" style="height:${{pct}}%; background: var(--primary)"></div>`;
      barsEl.appendChild(wrap);
    }});
    if (D.daily && D.daily.length) {{
      lblEl.innerHTML = `<span>${{D.daily[0].date}}</span><span>近 ${{D.daily.length}} 个活跃日 Token 消耗</span><span>${{D.daily[D.daily.length - 1].date}}</span>`;
    }}

    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const target = btn.dataset.tab;
        document.querySelectorAll('.tab-btn').forEach(b => {{
          const on = b.dataset.tab === target;
          b.className = on
            ? 'tab-btn px-2 py-0.5 rounded bg-[var(--primary)] text-[var(--primary-foreground)] font-medium transition'
            : 'tab-btn px-2 py-0.5 rounded text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition';
        }});
        document.getElementById('panel-models').classList.toggle('hidden', target !== 'models');
        document.getElementById('panel-trend').classList.toggle('hidden', target !== 'trend');
      }});
    }});
  </script>
</body>
</html>
"""


def build_full_dashboard_html(include_live_quota: bool = True) -> str:
    stats = get_overview_stats(include_live_quota=include_live_quota)
    raw_projects = list_projects(include_empty=True)[:75]
    raw_threads = list_threads(source_filter="ui_and_exec", limit=45)

    projects = [
        {
            "id": p["id"],
            "name": p["name"],
            "primaryPath": p["primaryPath"],
            "rootPaths": (p["rootPaths"] or [])[:2],
            "pinned": p["pinned"],
            "uiThreadCount": p["uiThreadCount"],
            "execThreadCount": p["execThreadCount"],
            "totalTokens": p["totalTokens"],
            "totalTokensFormatted": p["totalTokensFormatted"],
            "lastActiveFormatted": (p["lastActiveFormatted"] or "")[:16],
        }
        for p in raw_projects
    ]
    threads = [
        {
            "id": t["id"],
            "title": (t["title"] or "")[:90],
            "projectName": t["projectName"],
            "cwd": t["cwd"],
            "visibility": t["visibility"],
            "model": t["model"],
            "tokensFormatted": t["tokensFormatted"],
            "updatedAt": (t["updatedAt"] or "")[:16],
        }
        for t in raw_threads
    ]
    slim_stats = {
        "codexVersion": stats["codexVersion"],
        "desktopRunning": stats["desktopRunning"],
        "projectCount": stats["projectCount"],
        "activeProjectCount": stats["activeProjectCount"],
        "threads": stats["threads"],
        "tokens": stats["tokens"],
        "byModel": stats["byModel"][:8],
        "dailyActivity": stats["dailyActivity"],
        "hiddenExecThreads": [
            {"id": x["id"], "title": (x["title"] or "")[:80]} for x in (stats.get("hiddenExecThreads") or [])[:5]
        ],
        "bridgeDispatches": stats["bridgeDispatches"],
        "liveQuota": stats.get("liveQuota"),
    }

    bundle = {"stats": slim_stats, "projects": projects, "threads": threads}
    json_str = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Codex Bridge 控制台与统计中心</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-[var(--background)] text-[var(--foreground)] antialiased p-5 m-0">
  <div class="max-w-6xl mx-auto space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-[var(--border)]">
      <div>
        <div class="flex items-center gap-2.5">
          <span class="inline-block w-2.5 h-2.5 rounded-full" style="background: var(--success)"></span>
          <h1 class="text-lg font-bold tracking-tight">Codex Bridge v1.1 · 全局控制与统计中心</h1>
          <span id="hdr-ver" class="text-xs font-mono px-2 py-0.5 rounded bg-[var(--card)] border border-[var(--border)] text-[var(--muted-foreground)]"></span>
        </div>
        <p class="text-xs text-[var(--muted-foreground)] mt-1">
          泛用型双 Agent 协同引擎：支持软件开发、交叉审查、脚本运维、数据分析与科学仿真，会话原生同步至 Codex Desktop UI
        </p>
      </div>
      <div class="flex items-center gap-1.5 bg-[var(--card)] p-1 rounded-lg border border-[var(--border)] text-xs">
        <button data-view="overview" class="nav-btn px-3 py-1.5 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] font-medium">数据与配额</button>
        <button data-view="projects" class="nav-btn px-3 py-1.5 rounded-md text-[var(--muted-foreground)] hover:text-[var(--foreground)]">项目库 (<span id="cnt-proj">0</span>)</button>
        <button data-view="sessions" class="nav-btn px-3 py-1.5 rounded-md text-[var(--muted-foreground)] hover:text-[var(--foreground)]">会话与分支 (<span id="cnt-sess">0</span>)</button>
        <button data-view="builder" class="nav-btn px-3 py-1.5 rounded-md text-[var(--muted-foreground)] hover:text-[var(--foreground)]">交互式派单器</button>
      </div>
    </div>

    <div id="toast" class="hidden fixed bottom-4 right-4 z-50 px-3.5 py-2 rounded-lg bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-medium shadow-lg"></div>

    <section id="view-overview" class="space-y-5">
      <!-- Live Quota Banner -->
      <div id="quota-banner" class="hidden p-4 rounded-xl bg-[var(--card)] border border-[var(--border)] space-y-2 text-xs"></div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)]">
          <div class="text-xs text-[var(--muted-foreground)]">Codex 纳管项目总数</div>
          <div id="ov-proj" class="text-2xl font-bold font-mono mt-1"></div>
          <div id="ov-proj-sub" class="text-xs text-[var(--muted-foreground)] mt-1"></div>
        </div>
        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)]">
          <div class="text-xs text-[var(--muted-foreground)]">主对话数 (UI 原生可见)</div>
          <div id="ov-ui" class="text-2xl font-bold font-mono mt-1"></div>
          <div id="ov-exec" class="text-xs text-[var(--muted-foreground)] mt-1"></div>
        </div>
        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)]">
          <div class="text-xs text-[var(--muted-foreground)]">总线程数 (含内部子代理)</div>
          <div id="ov-total" class="text-2xl font-bold font-mono mt-1"></div>
          <div id="ov-sub" class="text-xs text-[var(--muted-foreground)] mt-1"></div>
        </div>
        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)]">
          <div class="text-xs text-[var(--muted-foreground)]">累计消耗 Token</div>
          <div id="ov-tok" class="text-2xl font-bold font-mono mt-1"></div>
          <div id="ov-agy" class="text-xs text-[var(--muted-foreground)] mt-1"></div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)] space-y-3">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold">各模型调用与 Token 占比</h2>
            <span class="text-xs text-[var(--muted-foreground)]">按累计 Token 排序</span>
          </div>
          <div id="ov-models" class="space-y-2.5"></div>
        </div>

        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)] flex flex-col justify-between space-y-3">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold">最近活跃日算力趋势</h2>
            <span class="text-xs text-[var(--muted-foreground)]">悬停查看每日明细</span>
          </div>
          <div id="ov-chart" class="flex items-end gap-1.5 h-44 pt-4 px-1"></div>
          <div id="ov-chart-lbl" class="flex justify-between text-xs font-mono text-[var(--muted-foreground)]"></div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)] space-y-3">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold">最活跃项目 Top 8</h2>
            <span class="text-xs text-[var(--muted-foreground)]">点击一键准备派发话术</span>
          </div>
          <div id="ov-top-projects" class="divide-y divide-[var(--border)]"></div>
        </div>

        <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)] space-y-3">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold">UI 同步体检 & 最近指派记录</h2>
            <span class="text-xs text-[var(--muted-foreground)]">支持一键转正与分支派生</span>
          </div>
          <div id="ov-sync-box" class="space-y-2 text-xs"></div>
        </div>
      </div>
    </section>

    <section id="view-projects" class="hidden space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <input id="proj-search" type="text" placeholder="搜索项目名称或文件夹路径..."
          class="flex-1 min-w-[260px] px-3 py-2 rounded-lg bg-[var(--card)] border border-[var(--border)] text-xs focus:outline-none" />
        <label class="text-xs text-[var(--muted-foreground)] flex items-center gap-1.5 cursor-pointer">
          <input id="proj-nonempty" type="checkbox" class="accent-[var(--primary)]" />
          仅显示有历史对话的项目
        </label>
      </div>
      <div id="proj-grid" class="grid grid-cols-1 md:grid-cols-2 gap-3"></div>
    </section>

    <section id="view-sessions" class="hidden space-y-3">
      <div class="flex flex-wrap items-center gap-3">
        <input id="sess-search" type="text" placeholder="按标题、项目名、UUID 或路径过滤会话..."
          class="flex-1 min-w-[240px] px-3 py-2 rounded-lg bg-[var(--card)] border border-[var(--border)] text-xs focus:outline-none" />
        <select id="sess-vis" class="px-3 py-2 rounded-lg bg-[var(--card)] border border-[var(--border)] text-xs">
          <option value="all">全部主会话 (UI + Exec)</option>
          <option value="visible_in_ui">仅 Codex UI 可见</option>
          <option value="hidden_exec">仅隐藏的 Exec 会话</option>
        </select>
      </div>
      <div id="sess-list" class="rounded-xl bg-[var(--card)] border border-[var(--border)] divide-y divide-[var(--border)]"></div>
    </section>

    <section id="view-builder" class="hidden space-y-4">
      <div class="p-4 rounded-xl bg-[var(--card)] border border-[var(--border)] space-y-4">
        <div>
          <h2 class="text-sm font-semibold">交互式任务指令生成器（支持单任务指派 / 独立审查 / 多路并行对比）</h2>
          <p class="text-xs text-[var(--muted-foreground)] mt-0.5">
            选好目标项目、模型与模式，自动生成可直接发给 Antigravity 的对话指令，新会话 100% 原生同步至 Codex Desktop UI。
          </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          <div class="space-y-1">
            <label class="text-[var(--muted-foreground)] font-medium">1. 目标项目</label>
            <select id="bld-proj" class="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]"></select>
          </div>
          <div class="space-y-1">
            <label class="text-[var(--muted-foreground)] font-medium">2. 指定模型 (可选)</label>
            <select id="bld-model" class="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
              <option value="">跟随 Codex 默认模型</option>
            </select>
          </div>
          <div class="space-y-1">
            <label class="text-[var(--muted-foreground)] font-medium">3. 权限与执行模式</label>
            <select id="bld-mode" class="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
              <option value="read-only">只读诊断 / 咨询 (read-only)</option>
              <option value="workspace-write">自动改代码 / 跑脚本 (workspace-write)</option>
              <option value="review">独立交叉 Code Review</option>
              <option value="batch">多角度并行会诊 (Batch 并发)</option>
            </select>
          </div>
          <div class="space-y-1">
            <label class="text-[var(--muted-foreground)] font-medium">4. 泛用场景模板</label>
            <select id="bld-tpl" class="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
              <option value="general">通用：口述目标 -> 拆解并指挥执行</option>
              <option value="code">研发：功能实现 / 修 Bug / 补单测</option>
              <option value="review">审查：排查漏洞、边界与性能隐患</option>
              <option value="ops">自动化：本机脚本 / 环境部署验证</option>
              <option value="sim">仿真计算：核查参数 / UDF / 残差解读</option>
              <option value="doc">数据与写作：核对口径并输出通俗摘要</option>
            </select>
          </div>
        </div>

        <div class="space-y-1 text-xs">
          <label class="text-[var(--muted-foreground)] font-medium">5. 你的大白话需求</label>
          <textarea id="bld-goal" rows="3" placeholder="用自然语言描述你想达成的效果，Antigravity 会自动翻译为严谨指令并替你验收..."
            class="w-full p-3 rounded-lg bg-[var(--background)] border border-[var(--border)] text-xs focus:outline-none"></textarea>
        </div>

        <div class="space-y-2 pt-2 border-t border-[var(--border)] text-xs">
          <div class="flex items-center justify-between">
            <span class="font-semibold">生成的 Antigravity 对话指令：</span>
            <button id="btn-copy-chat" class="px-3 py-1.5 rounded-lg bg-[var(--primary)] text-[var(--primary-foreground)] font-medium">一键复制发给 Antigravity</button>
          </div>
          <pre id="bld-out-chat" class="p-3 rounded-lg bg-[var(--background)] border border-[var(--border)] whitespace-pre-wrap font-mono text-xs"></pre>
        </div>
      </div>
    </section>
  </div>

  <script>
    const B = {json_str};
    const S = B.stats;
    const colors = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)'];

    function toast(msg) {{
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.remove('hidden');
      clearTimeout(window.__toastTimer);
      window.__toastTimer = setTimeout(() => t.classList.add('hidden'), 2200);
    }}
    function copyText(txt, tip) {{
      navigator.clipboard.writeText(txt).then(() => toast(tip || '已复制到剪贴板'));
    }}
    function esc(s) {{
      return String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}

    document.getElementById('hdr-ver').textContent = S.codexVersion + (S.desktopRunning ? ' · UI 运行中' : ' · UI 待命');
    document.getElementById('cnt-proj').textContent = B.projects.length;
    document.getElementById('cnt-sess').textContent = B.threads.length;
    document.getElementById('ov-proj').textContent = S.projectCount;
    document.getElementById('ov-proj-sub').textContent = S.activeProjectCount + ' 个项目有会话记录';
    document.getElementById('ov-ui').textContent = S.threads.ui;
    document.getElementById('ov-exec').textContent = S.threads.exec > 0 ? (S.threads.exec + ' 条隐藏 exec 会话可一键转正') : '0 条隐藏会话（全部 UI 可见）';
    document.getElementById('ov-total').textContent = S.threads.total;
    document.getElementById('ov-sub').textContent = '含 ' + S.threads.subagent + ' 个内部并行子代理';
    document.getElementById('ov-tok').textContent = S.tokens.totalFormatted;
    document.getElementById('ov-agy').textContent = 'Antigravity 已累计指派 ' + (S.bridgeDispatches.total || 0) + ' 次';

    // Live Quota Banner & Model Dropdown
    const lq = S.liveQuota;
    if (lq && lq.available && lq.primaryWindow && lq.primaryWindow.usedPercent != null) {{
      const pw = lq.primaryWindow;
      const qb = document.getElementById('quota-banner');
      qb.classList.remove('hidden');
      const modelBadges = (lq.models || []).slice(0, 6).map(m => `<span class="px-2 py-0.5 rounded bg-[var(--background)] border border-[var(--border)] font-mono">${{esc(m.id)}}</span>`).join(' ');
      qb.innerHTML = `
        <div class="flex flex-wrap items-center justify-between gap-2">
          <span class="font-semibold">Codex 账户实时配额监控：已用 ${{pw.usedPercent}}% · 剩余 ${{pw.remainingPercent}}%</span>
          <span class="font-mono text-[var(--muted-foreground)]">重置时间：${{esc(pw.resetsAt || '—')}} (${{pw.resetsInHours != null ? pw.resetsInHours + ' 小时后' : ''}})</span>
        </div>
        <div class="w-full h-2 rounded-full bg-[var(--secondary)] overflow-hidden">
          <div class="h-full rounded-full" style="width:${{Math.min(pw.usedPercent, 100)}}%; background: ${{pw.usedPercent > 85 ? 'var(--warning)' : 'var(--success)'}}"></div>
        </div>
        <div class="flex flex-wrap items-center gap-1.5 pt-1 text-[var(--muted-foreground)]">
          <span>当前可用模型：</span> ${{modelBadges}}
        </div>`;
      const mSel = document.getElementById('bld-model');
      (lq.models || []).forEach(m => {{
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.id;
        mSel.appendChild(opt);
      }});
    }}

    const ovModels = document.getElementById('ov-models');
    (S.byModel || []).slice(0, 7).forEach((m, i) => {{
      const d = document.createElement('div');
      d.className = 'text-xs space-y-1';
      d.innerHTML = `
        <div class="flex justify-between">
          <span class="font-mono font-medium">${{esc(m.model)}}</span>
          <span class="font-mono text-[var(--muted-foreground)]">${{m.mainThreads}} 会话 (${{m.totalThreads}} 总) · ${{esc(m.tokensFormatted)}} · ${{m.sharePct}}%</span>
        </div>
        <div class="w-full h-2 rounded-full bg-[var(--secondary)] overflow-hidden">
          <div class="h-full rounded-full" style="width:${{Math.max(m.sharePct, 1.5)}}%; background:${{colors[i % colors.length]}}"></div>
        </div>`;
      ovModels.appendChild(d);
    }});

    const chartEl = document.getElementById('ov-chart');
    const chartLbl = document.getElementById('ov-chart-lbl');
    const daily = S.dailyActivity || [];
    const maxTok = Math.max(...daily.map(x => x.tokens || 0), 1);
    daily.forEach(d => {{
      const h = Math.max(Math.round((d.tokens / maxTok) * 100), 5);
      const col = document.createElement('div');
      col.className = 'flex-1 h-full flex flex-col justify-end items-center';
      col.title = `${{d.date}} · ${{d.sessions}} 主会话 / ${{d.allThreads}} 总线程 · ${{d.tokensFormatted}} tokens`;
      col.innerHTML = `<div class="w-full rounded-t opacity-85 hover:opacity-100 transition" style="height:${{h}}%; background: var(--primary)"></div>`;
      chartEl.appendChild(col);
    }});
    if (daily.length) {{
      chartLbl.innerHTML = `<span>${{esc(daily[0].date)}}</span><span>近 ${{daily.length}} 个活跃日</span><span>${{esc(daily[daily.length - 1].date)}}</span>`;
    }}

    const topProjEl = document.getElementById('ov-top-projects');
    B.projects.filter(p => p.totalTokens > 0 || p.uiThreadCount > 0).sort((a,b) => b.totalTokens - a.totalTokens).slice(0, 8).forEach(p => {{
      const row = document.createElement('div');
      row.className = 'py-2 flex items-center justify-between gap-2 text-xs';
      row.innerHTML = `
        <div class="min-w-0">
          <div class="font-medium truncate">${{esc(p.name)}}</div>
          <div class="font-mono text-[var(--muted-foreground)] truncate">${{esc(p.primaryPath)}}</div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span class="font-mono text-[var(--muted-foreground)]">${{p.uiThreadCount}} 会话 · ${{esc(p.totalTokensFormatted)}}</span>
          <button class="px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--secondary)]">派活</button>
        </div>`;
      row.querySelector('button').onclick = () => {{
        switchView('builder');
        document.getElementById('bld-proj').value = p.name;
        updateBuilder();
      }};
      topProjEl.appendChild(row);
    }});

    const syncBox = document.getElementById('ov-sync-box');
    const hiddenExecs = S.hiddenExecThreads || [];
    if (hiddenExecs.length) {{
      const alertDiv = document.createElement('div');
      alertDiv.className = 'p-3 rounded-lg border border-[var(--border)] bg-[var(--background)] space-y-2';
      alertDiv.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="font-medium">检测到 ${{hiddenExecs.length}} 条旧版 exec 会话未显示在 UI 侧边栏</span>
          <button id="btn-promote" class="px-2.5 py-1 rounded bg-[var(--primary)] text-[var(--primary-foreground)]">复制一键转正指令</button>
        </div>
        <div class="text-[var(--muted-foreground)] font-mono truncate">示例：${{esc(hiddenExecs[0].title)}} (${{esc(hiddenExecs[0].id.slice(0,8))}})</div>`;
      syncBox.appendChild(alertDiv);
      setTimeout(() => {{
        const bp = document.getElementById('btn-promote');
        if (bp) bp.onclick = () => copyText('请调用 codex_bridge_promote_exec_threads 把我历史上的 exec 隐藏会话转正显示到 Codex UI 里。', '已复制转正指令');
      }}, 0);
    }} else {{
      syncBox.innerHTML += `<div class="p-3 rounded-lg border border-[var(--border)] bg-[var(--background)]">当前所有主会话均处于 Codex Desktop UI 可见状态。</div>`;
    }}

    const recentDisp = (S.bridgeDispatches && S.bridgeDispatches.recent) || [];
    if (recentDisp.length) {{
      recentDisp.slice(0, 4).forEach(d => {{
        const item = document.createElement('div');
        item.className = 'p-2.5 rounded-lg border border-[var(--border)] flex items-center justify-between gap-2';
        item.innerHTML = `
          <div class="min-w-0">
            <div class="font-medium truncate">${{esc(d.title || d.promptPreview)}}</div>
            <div class="font-mono text-[var(--muted-foreground)] truncate">${{esc(d.projectName || d.cwd)}} · ${{d.durationSec}}s · ${{esc(d.status)}}</div>
          </div>
          <span class="font-mono text-[var(--muted-foreground)] shrink-0">${{esc((d.threadId || '').slice(0,8))}}</span>`;
        syncBox.appendChild(item);
      }});
    }} else {{
      syncBox.innerHTML += `<div class="p-3 rounded-lg border border-[var(--border)] text-[var(--muted-foreground)]">暂无派发记录。切到「交互式派单器」即可开始。</div>`;
    }}

    function renderProjects() {{
      const q = document.getElementById('proj-search').value.trim().toLowerCase();
      const nonEmpty = document.getElementById('proj-nonempty').checked;
      const grid = document.getElementById('proj-grid');
      grid.innerHTML = '';
      B.projects.filter(p => {{
        if (nonEmpty && (p.uiThreadCount + p.execThreadCount) === 0) return false;
        if (!q) return true;
        return (p.name + ' ' + p.rootPaths.join(' ')).toLowerCase().includes(q);
      }}).forEach(p => {{
        const card = document.createElement('div');
        card.className = 'p-3.5 rounded-xl bg-[var(--card)] border border-[var(--border)] flex flex-col justify-between gap-2 text-xs';
        card.innerHTML = `
          <div>
            <div class="flex items-center justify-between gap-2">
              <span class="font-semibold text-sm truncate">${{p.pinned ? '📌 ' : ''}}${{esc(p.name)}}</span>
              <span class="font-mono text-[var(--muted-foreground)] shrink-0">${{p.uiThreadCount}} 会话 · ${{esc(p.totalTokensFormatted)}}</span>
            </div>
            <div class="font-mono text-[var(--muted-foreground)] truncate mt-1">${{esc(p.primaryPath || '未绑定目录')}}</div>
          </div>
          <div class="flex items-center justify-between pt-2 border-t border-[var(--border)]">
            <span class="text-[var(--muted-foreground)]">最近活跃: ${{esc(p.lastActiveFormatted || '—')}}</span>
            <div class="flex gap-1.5">
              <button class="btn-open px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--secondary)]">在 Codex 打开</button>
              <button class="btn-send px-2.5 py-1 rounded bg-[var(--primary)] text-[var(--primary-foreground)]">在此项目派活</button>
            </div>
          </div>`;
        card.querySelector('.btn-open').onclick = () => copyText(`请调用 codex_bridge_open_ui 在 Codex 桌面端打开「${{p.name}}」项目。`, '已复制打开 UI 指令');
        card.querySelector('.btn-send').onclick = () => {{
          switchView('builder');
          document.getElementById('bld-proj').value = p.name;
          updateBuilder();
        }};
        grid.appendChild(card);
      }});
    }}
    document.getElementById('proj-search').oninput = renderProjects;
    document.getElementById('proj-nonempty').onchange = renderProjects;
    renderProjects();

    function renderSessions() {{
      const q = document.getElementById('sess-search').value.trim().toLowerCase();
      const vis = document.getElementById('sess-vis').value;
      const listEl = document.getElementById('sess-list');
      listEl.innerHTML = '';
      B.threads.filter(t => {{
        if (vis !== 'all' && t.visibility !== vis) return false;
        if (!q) return true;
        return (t.title + ' ' + t.projectName + ' ' + t.id + ' ' + t.cwd).toLowerCase().includes(q);
      }}).forEach(t => {{
        const row = document.createElement('div');
        row.className = 'p-3 flex flex-wrap items-center justify-between gap-3 text-xs';
        const badge = t.visibility === 'visible_in_ui'
          ? `<span class="px-1.5 py-0.5 rounded border border-[var(--border)]">UI 可见</span>`
          : `<span class="px-1.5 py-0.5 rounded border border-[var(--border)]" style="color: var(--warning)">隐藏 exec</span>`;
        row.innerHTML = `
          <div class="min-w-0 flex-1 space-y-0.5">
            <div class="flex items-center gap-2">
              ${{badge}}
              <span class="font-semibold truncate">${{esc(t.title)}}</span>
            </div>
            <div class="font-mono text-[var(--muted-foreground)] truncate">
              项目: ${{esc(t.projectName)}} · 模型: ${{esc(t.model || '—')}} · Token: ${{esc(t.tokensFormatted)}} · ${{esc(t.updatedAt || '')}} · ID: ${{esc(t.id.slice(0,8))}}
            </div>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            <button class="btn-read px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--secondary)]">解读原始过程</button>
            <button class="btn-fork px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--secondary)]">派生新分支</button>
            <button class="btn-cont px-2.5 py-1 rounded bg-[var(--primary)] text-[var(--primary-foreground)]">接续指挥</button>
          </div>`;
        row.querySelector('.btn-read').onclick = () => copyText(`请调用 codex_bridge_read_thread 读取会话 ${{t.id}} 的原始执行过程与回复，并用通俗中文帮我解读。`, '已复制解读指令');
        row.querySelector('.btn-fork').onclick = () => copyText(`请基于 Codex 会话 ${{t.id}}（项目：${{t.projectName}}）调用 codex_bridge_fork_thread 派生一个新分支会话，用来尝试以下新方案：`, '已复制分支派生指令前缀');
        row.querySelector('.btn-cont').onclick = () => copyText(`请接续 Codex 会话 ${{t.id}}（项目：${{t.projectName}}），帮我继续指挥它完成：`, '已复制续聊指令前缀');
        listEl.appendChild(row);
      }});
    }}
    document.getElementById('sess-search').oninput = renderSessions;
    document.getElementById('sess-vis').onchange = renderSessions;
    renderSessions();

    const projSel = document.getElementById('bld-proj');
    B.projects.forEach(p => {{
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = `${{p.name}} (${{p.primaryPath || p.id}})`;
      projSel.appendChild(opt);
    }});

    const tplHints = {{
      general: '先帮我理清需要给 Codex 的关键输入约束，在对应项目下自动新建 Codex UI 可见会话派发给它，完成后读取原始结果并用通俗中文向我汇报。',
      code: '请先阅读相关上下文，转化成清晰的编码与验证指令，在对应项目下新建 Codex UI 会话让它实现并自测，最后帮我核对代码改动并通俗总结。',
      review: '请在该项目下发起独立交叉 Code Review，重点找边界漏洞、并发安全与逻辑隐患，然后汇总评估哪些值得修。',
      ops: '请帮我把需求转化成安全的脚本/自动化步骤，指挥 Codex 执行验证，并把每一步跑了什么命令和最终状态清楚地解释给我。',
      sim: '请帮我把仿真意图翻译为准确的软件/UDF/脚本检查与执行指令发给 Codex（自动同步到 Codex UI），跑完后帮我解读残差、报错或物理量结果。',
      doc: '请指挥 Codex 在该项目下核对数据/脚本/文档内容，并把它的专业输出整理成清晰易懂的要点总结附上原文链接。'
    }};

    function updateBuilder() {{
      const proj = projSel.value || '当前项目';
      const mdl = document.getElementById('bld-model').value;
      const mode = document.getElementById('bld-mode').value;
      const tpl = document.getElementById('bld-tpl').value;
      const goal = document.getElementById('bld-goal').value.trim() || '<在这里填写你的具体目标>';
      const modeMap = {{
        'read-only': '只读安全模式 (read-only)',
        'workspace-write': '工作区读写模式 (workspace-write)',
        'review': '独立交叉代码审查模式 (review)',
        'batch': '多角度并行并发会诊模式 (batch)'
      }};
      const mdlNote = mdl ? `，指定模型 ${{mdl}}` : '';
      const msg = [
        `请在 Codex 的「${{proj}}」项目下（使用 ${{modeMap[mode]}}${{mdlNote}}）帮我指挥 Codex 完成以下目标：`,
        `目标：${{goal}}`,
        `要求：${{tplHints[tpl] || tplHints.general}}`
      ].join('\\n');
      document.getElementById('bld-out-chat').textContent = msg;
    }}
    ['bld-proj', 'bld-model', 'bld-mode', 'bld-tpl', 'bld-goal'].forEach(id => {{
      document.getElementById(id).addEventListener('input', updateBuilder);
      document.getElementById(id).addEventListener('change', updateBuilder);
    }});
    document.getElementById('btn-copy-chat').onclick = () => copyText(document.getElementById('bld-out-chat').textContent, '已复制！直接粘贴到聊天框发送即可');
    updateBuilder();

    function switchView(view) {{
      ['overview', 'projects', 'sessions', 'builder'].forEach(v => {{
        document.getElementById('view-' + v).classList.toggle('hidden', v !== view);
      }});
      document.querySelectorAll('.nav-btn').forEach(btn => {{
        const on = btn.dataset.view === view;
        btn.className = on
          ? 'nav-btn px-3 py-1.5 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] font-medium'
          : 'nav-btn px-3 py-1.5 rounded-md text-[var(--muted-foreground)] hover:text-[var(--foreground)]';
      }});
    }}
    document.querySelectorAll('.nav-btn').forEach(btn => {{
      btn.onclick = () => switchView(btn.dataset.view);
    }});
  </script>
</body>
</html>
"""

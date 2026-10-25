/* Presentation only: fixed samples, navigation, filters and dialogs. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const tasks = window.PreviewTasks;
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const number = value => Number(value || 0).toLocaleString("zh-CN");
  const size = value => value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1048576).toFixed(1)} MB`;
  const labels = { queued: "排队中", running: "处理中", succeeded: "已完成", failed: "失败" };
  const tag = task => `<span class="tag ${task.status}"><span class="small-dot"></span>${labels[task.status]}</span>`;
  const pending = text => `<button class="button small" disabled title="待接入后端">${text} · 待接入</button>`;
  let filter = "all", page = 1;
  const pageSize = 8;

  function filtered() {
    const query = $("search-input").value.trim().toLowerCase();
    return tasks.filter(t => (filter === "all" || filter === "active" && ["queued", "running"].includes(t.status) || t.status === filter) && `${t.name} ${t.id} ${t.owner}`.toLowerCase().includes(query));
  }
  function progress(task) {
    const phase = { queued: "等待分配", running: "处理记录", succeeded: "处理完成", failed: "执行中断" }[task.status];
    return `<div class="progress-cell"><div class="progress-caption"><span>${phase}</span><span>${task.progress}%</span></div><div class="progress-track" role="progressbar" aria-label="${esc(task.name)}的示例进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${task.progress}"><div class="progress-fill ${task.status}" style="width:${task.progress}%"></div></div></div>`;
  }
  function dateCell(t) { return `<div class="date-cell">${esc(t.createdAt.slice(0, 10))}<span>${esc(t.createdAt.slice(11))}</span></div>`; }
  function fileCell(t) { return `<div class="file-cell"><span class="file-symbol">${icon("file")}</span><div><span class="file-name" title="${esc(t.name)}">${esc(t.name)}</span><span class="task-id">${esc(t.id)}</span></div></div>`; }
  function renderStats() {
    const active = tasks.filter(t => ["running", "queued"].includes(t.status)).length;
    const done = tasks.filter(t => t.status === "succeeded").length;
    const failed = tasks.filter(t => t.status === "failed").length;
    $("stats").innerHTML = [["导入任务", tasks.length, "", "静态示例"], ["进行中", active, "", "状态展示"], ["已完成", done, "success", "结果展示"], ["执行失败", failed, "danger", "失败展示"]].map(([title, count, kind, note]) => `<div class="stat"><div class="stat-label">${title}</div><div class="stat-value ${kind}">${count}<small>${note}</small></div></div>`).join("");
    $("nav-count").textContent = tasks.length;
    $("all-count").textContent = tasks.length;
    $("active-count").textContent = active;
  }
  function renderTasks() {
    const list = filtered(), pages = Math.max(1, Math.ceil(list.length / pageSize));
    page = Math.min(page, pages);
    $("task-table-body").innerHTML = list.length ? list.slice((page - 1) * pageSize, page * pageSize).map(t => {
      const done = t.status === "succeeded";
      const counts = done ? `<span class="good-count">${number(t.validCount)}</span><span class="count-divider">/</span><span class="${t.invalidCount ? "bad-count" : "good-count"}">${number(t.invalidCount)}</span>` : "—";
      const extra = t.status === "failed" ? '<button class="text-button" disabled title="待接入后端">重试</button>' : done ? `<button class="text-button" data-detail="${esc(t.id)}">预览报告</button>` : "";
      return `<tr><td>${fileCell(t)}</td><td><span class="person"><span class="mini-avatar">${esc(t.owner[0])}</span>${esc(t.owner)}</span></td><td>${tag(t)}</td><td>${progress(t)}</td><td class="numeric">${counts}</td><td>${dateCell(t)}</td><td><div class="row-actions"><button class="text-button" data-detail="${esc(t.id)}">详情</button>${extra}</div></td></tr>`;
    }).join("") : `<tr><td colspan="7" class="empty-state">${icon("search")}<strong>没有匹配的示例任务</strong><p>调整搜索或状态筛选条件。</p></td></tr>`;
    $("result-count").textContent = list.length ? `共 ${list.length} 条示例 · 当前显示 ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, list.length)} 条` : "共 0 条示例";
    $("page-label").textContent = `${page} / ${pages}`;
    $("prev-page").disabled = page <= 1; $("next-page").disabled = page >= pages;
  }
  function renderFiles() {
    $("file-table-body").innerHTML = tasks.map(t => `<tr><td>${fileCell(t)}</td><td>${size(t.size)}</td><td><span class="tag neutral">静态示例</span></td><td><code class="task-id">${esc(t.id)}</code></td><td>${dateCell(t)}</td><td><button class="text-button" data-detail="${esc(t.id)}">查看任务</button></td></tr>`).join("");
  }
  function resultPreview(t) {
    if (t.status !== "succeeded") return "";
    const errors = t.errors.length ? `<section class="detail-section"><h3>错误明细 · 布局预览</h3><table class="tiny-table"><thead><tr><th>行号</th><th>字段</th><th>原因</th></tr></thead><tbody>${t.errors.map(e => `<tr><td>${e.line}</td><td>${esc(e.field)}</td><td>${esc(e.reason)}</td></tr>`).join("")}</tbody></table><p class="small-note">以下均为预置示例，尚未执行数据校验。</p></section>` : "";
    return `<section class="detail-section"><h3>处理结果 · 布局预览</h3><div class="result-grid"><div class="result-item"><span>总行数</span><strong>${number(t.total)}</strong></div><div class="result-item"><span>有效行</span><strong>${number(t.validCount)}</strong></div><div class="result-item"><span>错误行</span><strong>${number(t.invalidCount)}</strong></div></div><div class="detail-actions">${pending("下载报告")}${pending("下载错误明细")}</div></section>${errors}`;
  }
  function openDetail(id) {
    const t = tasks.find(t => t.id === id); if (!t) return;
    $("detail-content").innerHTML = `<div class="detail-main"><h2 id="detail-title">${esc(t.name)}</h2><div class="detail-meta"><code>${esc(t.id)}</code>${tag(t)}</div>${progress(t)}<p class="small-note">静态界面示例。进度和结果仅用于确认布局，不会执行任务。</p><div class="detail-grid"><div><label>提交人</label><span>${esc(t.owner)}</span></div><div><label>文件大小</label><span>${size(t.size)}</span></div><div><label>提交时间</label><span>${esc(t.createdAt)}</span></div><div><label>耗时示例</label><span>${t.duration ? `${t.duration} 秒` : "—"}</span></div>${t.note ? `<div style="grid-column:1/-1"><label>备注示例</label><span>${esc(t.note)}</span></div>` : ""}</div>${t.status === "failed" ? `<div class="error-message">${esc(t.failure)}</div><div class="detail-actions">${pending("重试任务")}</div>` : ""}${resultPreview(t)}<section class="detail-section"><h3>执行记录</h3><p class="small-note">此处预留任务事件列表，后续由后端返回真实记录。</p></section></div>`;
    $("detail-dialog").showModal();
  }
  function switchView(view) {
    const info = { tasks: ["导入任务", "管理文件导入，跟踪处理进度，查看数据质量。"], files: ["数据文件", "查看源文件信息，追溯对应的导入任务。"], rules: ["处理规则", "预览规则展示方式，具体规则将在后端逐步实现。"] };
    $("page-title").textContent = info[view][0]; $("breadcrumb-current").textContent = info[view][0]; $("page-description").textContent = info[view][1];
    for (const name of ["task", "file", "rule"]) $(`${name}-view`).hidden = `${name}s` !== view;
    $("stats").hidden = view !== "tasks";
    document.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === view));
    history.replaceState(null, "", `#${view}`);
  }
  function showFileName(file) {
    $("drop-title").textContent = file ? file.name : "点击选择，或将文件拖到这里";
    $("drop-subtitle").textContent = file ? `${size(file.size)} · 仅预览文件名称，尚未上传` : "CSV 格式 · 文件上传待接入";
  }
  document.addEventListener("click", event => { const b = event.target.closest("[data-detail]"); if (b) openDetail(b.dataset.detail); });
  document.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", () => $(b.dataset.close).close()));
  document.querySelectorAll("dialog").forEach(d => d.addEventListener("click", event => { if (event.target !== d) return; const r = d.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) d.close(); }));
  document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => switchView(b.dataset.view)));
  document.querySelector(".brand").addEventListener("click", event => { event.preventDefault(); switchView("tasks"); });
  document.querySelectorAll("[data-filter]").forEach(b => b.addEventListener("click", () => { filter = b.dataset.filter; page = 1; document.querySelectorAll("[data-filter]").forEach(item => { item.classList.toggle("active", item === b); item.setAttribute("aria-selected", String(item === b)); }); renderTasks(); }));
  $("search-input").addEventListener("input", () => { page = 1; renderTasks(); });
  $("prev-page").addEventListener("click", () => { page--; renderTasks(); }); $("next-page").addEventListener("click", () => { page++; renderTasks(); });
  $("help-button").addEventListener("click", () => $("help-dialog").showModal());
  $("new-task-button").addEventListener("click", () => { $("upload-form").reset(); showFileName(null); $("upload-dialog").showModal(); });
  $("upload-form").addEventListener("submit", event => event.preventDefault());
  $("file-input").addEventListener("change", event => showFileName(event.target.files[0]));
  $("dropzone").addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("file-input").click(); } });
  ["dragenter", "dragover"].forEach(name => $("dropzone").addEventListener(name, event => { event.preventDefault(); $("dropzone").classList.add("dragging"); }));
  ["dragleave", "drop"].forEach(name => $("dropzone").addEventListener(name, event => { event.preventDefault(); $("dropzone").classList.remove("dragging"); }));
  $("dropzone").addEventListener("drop", event => showFileName(event.dataTransfer.files[0]));
  $("rule-list").innerHTML = [["订单号", "拟定规则：订单号必填并检查重复。具体实现待后端开发。", "order_id"], ["商品名称", "拟定规则：商品名称用于分组统计。", "product"], ["订单金额", "拟定规则：检查金额格式，具体业务限制后续确定。", "amount"], ["订单日期", "拟定规则：使用 YYYY-MM-DD，并检查日期有效性。", "order_date"]].map(([title, text, field], i) => `<div class="rule-row"><span class="rule-index">0${i + 1}</span><div><strong>${title}</strong><p>${text}</p></div><code>${field}</code></div>`).join("");
  renderStats(); renderTasks(); renderFiles();
  switchView(["tasks", "files", "rules"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "tasks");
})();

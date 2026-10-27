/* Authenticated CSV upload, persistence and preview. No task creation or automatic upload retry. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const session = window.AuthSession;
  const previewOnly = new URLSearchParams(window.location.search).get("preview") === "1";
  const form = $("upload-form"), dialog = $("upload-dialog"), input = $("file-input");
  let selectedFile = null, busy = false, requestVersion = 0, activeController = null;

  class UploadError extends Error {
    constructor(message, needsLogin = false) { super(message); this.needsLogin = needsLogin; }
  }

  const formatSize = bytes => bytes < 1024 ? `${bytes} B`
    : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / 1048576).toFixed(1)} MiB`;

  function setStatus(message) {
    $("upload-status").textContent = message;
    $("upload-status").hidden = !message;
  }

  function showError(message = "", needsLogin = false) {
    $("upload-error").textContent = message;
    $("upload-error").hidden = !message;
    $("upload-login").hidden = !needsLogin;
  }

  function setBusy(value) {
    busy = value;
    form.setAttribute("aria-busy", String(value));
    input.disabled = value;
    $("dropzone").setAttribute("aria-disabled", String(value));
    $("submit-upload").disabled = value || !selectedFile || previewOnly;
    $("submit-upload").textContent = value ? "上传并检查中…" : "上传并预览";
  }

  function clearResult() {
    $("upload-result").hidden = true;
    $("upload-preview-head").replaceChildren();
    $("upload-preview-body").replaceChildren();
  }

  function selectFiles(files) {
    if (busy) return;
    clearResult(); showError(); setStatus("");
    selectedFile = files.length === 1 ? files[0] : null;
    $("drop-title").textContent = selectedFile ? selectedFile.name : "点击选择，或将文件拖到这里";
    $("drop-subtitle").textContent = selectedFile ? `${formatSize(selectedFile.size)} · 尚未提交`
      : "每次一个 CSV · UTF-8 编码 · 默认上限 50 MiB";
    if (files.length > 1) { input.value = ""; showError("每次只能上传一个文件，请重新选择。"); }
    if (previewOnly) showError("当前为静态演示模式，请登录后上传文件。", true);
    setBusy(false);
  }

  function validResult(data) {
    return data?.persisted === true
      && typeof data.file_id === "string" && /^[0-9a-f]{32}$/.test(data.file_id)
      && typeof data.created_at === "string" && Number.isFinite(Date.parse(data.created_at))
      && Number.isInteger(data.owner_id) && data.owner_id > 0
      && (data.filename === null || typeof data.filename === "string")
      && Number.isInteger(data.size_bytes) && data.size_bytes >= 0
      && typeof data.preview_truncated === "boolean" && Array.isArray(data.preview_rows)
      && data.preview_rows.length <= 5 && data.preview_rows.every(row => Array.isArray(row)
        && row.length <= 50 && row.every(cell => typeof cell === "string" && Array.from(cell).length <= 200));
  }

  function renderResult(data) {
    const rows = data.preview_rows;
    const columns = Math.max(0, ...rows.map(row => row.length));
    $("upload-result-meta").textContent = `${data.filename || selectedFile.name} · ${formatSize(data.size_bytes)} · ${rows.length} 条预览记录 · 文件编号 ${data.file_id}`;
    $("upload-preview-head").replaceChildren();
    $("upload-preview-body").replaceChildren();
    $("upload-preview-scroll").hidden = columns === 0;
    $("upload-empty-preview").hidden = columns !== 0;
    $("upload-empty-preview").textContent = rows.length
      ? "预览中只有空记录，没有可展示的字段；是否存在有效数据需后续确认。"
      : "文件中没有可预览的 CSV 记录；检查通过不代表存在有效数据。";
    $("upload-truncated").hidden = !data.preview_truncated;
    if (columns) {
      const heading = document.createElement("tr");
      for (let column = 0; column <= columns; column++) {
        const cell = document.createElement("th");
        cell.scope = "col";
        cell.textContent = column === 0 ? "记录" : `第${column}列`;
        heading.appendChild(cell);
      }
      $("upload-preview-head").appendChild(heading);
      rows.forEach((row, index) => {
        const record = document.createElement("tr");
        const number = document.createElement("th");
        number.scope = "row"; number.textContent = String(index + 1); record.appendChild(number);
        for (let column = 0; column < columns; column++) {
          const cell = document.createElement("td");
          // All uploaded content is rendered as text, including HTML-looking values.
          cell.textContent = row[column] ?? "";
          record.appendChild(cell);
        }
        $("upload-preview-body").appendChild(record);
      });
    }
    $("upload-result").hidden = false;
  }

  function cancelPending() {
    requestVersion++;
    if (activeController) activeController.abort();
    activeController = null;
    setBusy(false); setStatus("");
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy) return;
    if (previewOnly) { showError("当前为静态演示模式，请登录后上传文件。", true); return; }
    if (!selectedFile) { showError("请先选择一个 CSV 文件。"); return; }
    const version = ++requestVersion;
    const controller = new AbortController();
    activeController = controller;
    let timeout = null, timedOut = false;
    clearResult(); showError(); setBusy(true); setStatus("正在确认登录状态…");
    try {
      // Reuse existing refresh/recovery before this write; never replay the upload automatically.
      const user = await session.currentUser();
      if (version !== requestVersion) return;
      const token = session.getToken();
      if (!token) throw new UploadError("请先登录后再上传文件。", true);
      const body = new FormData();
      body.append("file", selectedFile);
      setStatus("正在上传并检查文件…");
      timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 120000);
      const response = await fetch(`${session.apiBaseUrl}/api/files`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body,
        credentials: "omit", cache: "no-store", signal: controller.signal,
      });
      if (version !== requestVersion) return;
      if (response.status === 401) throw new UploadError("登录状态已失效，请重新登录后再上传。", true);
      let data;
      try { data = await response.json(); }
      catch { throw new UploadError("暂时无法确认上传结果，请稍后手动重试。"); }
      if (version !== requestVersion) return;
      if (!response.ok) {
        const detail = typeof data?.detail === "string" ? data.detail
          : Array.isArray(data?.detail) ? data.detail.map(item => item.msg).filter(Boolean).join("；") : "";
        throw new UploadError(response.status >= 500 ? "暂时无法确认文件保存结果，请稍后核对；重复上传会生成新记录。"
          : detail || `文件未通过检查（${response.status}），请检查后重试。`);
      }
      if (!session.getToken()) throw new UploadError("登录状态已变化，请重新登录后再上传。", true);
      if (!validResult(data) || data.owner_id !== user.id) {
        throw new UploadError("暂时无法确认上传结果，请确认登录账号后手动重试。");
      }
      renderResult(data);
      setStatus("文件及信息已保存，尚未创建处理任务。");
    } catch (error) {
      if (version !== requestVersion) return;
      setStatus("");
      if (timedOut) showError("请求超时，暂时无法确认保存结果；已保留所选文件，重复上传会生成新记录。");
      else if (error instanceof UploadError) showError(error.message, error.needsLogin);
      else if (error instanceof session.SessionExpiredError || error instanceof session.SessionChangedError) {
        showError("登录状态已变化，请重新登录后再上传。", true);
      } else if (error instanceof session.ConnectionError) {
        showError("暂时无法确认登录状态，已保留所选文件，请稍后重试。");
      } else showError("连接失败，暂时无法确认保存结果；已保留所选文件，请检查网络或后端服务。");
    } finally {
      if (timeout !== null) window.clearTimeout(timeout);
      if (version === requestVersion) { activeController = null; setBusy(false); }
    }
  });

  $("new-task-button").addEventListener("click", () => dialog.showModal());
  input.addEventListener("change", () => selectFiles(Array.from(input.files || [])));
  $("dropzone").addEventListener("keydown", event => {
    if (!busy && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); input.click(); }
  });
  ["dragenter", "dragover"].forEach(name => $("dropzone").addEventListener(name, event => {
    event.preventDefault(); if (!busy) $("dropzone").classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach(name => $("dropzone").addEventListener(name, event => {
    event.preventDefault(); $("dropzone").classList.remove("dragging");
  }));
  $("dropzone").addEventListener("drop", event => {
    event.preventDefault();
    if (!busy) { input.value = ""; selectFiles(Array.from(event.dataTransfer?.files || [])); }
  });
  dialog.addEventListener("close", cancelPending);
  window.addEventListener("pagehide", cancelPending);
  selectFiles([]);
})();

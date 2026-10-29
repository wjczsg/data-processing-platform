/* Authenticated CSV upload, header confirmation and task creation. Writes are never replayed automatically. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const session = window.AuthSession;
  const previewOnly = new URLSearchParams(window.location.search).get("preview") === "1";
  const form = $("upload-form"), dialog = $("upload-dialog"), input = $("file-input");
  let selectedFile = null, busy = false, requestVersion = 0, activeController = null;
  let uploadedResult = null, confirmedHasHeader = null, confirmedColumns = null;
  let savingHeader = false, headerSaveUncertain = false;
  let creatingTask = false, createdTask = null, taskCreateUncertain = false;
  const headerOptions = $("upload-header-options"), headerYes = $("upload-header-yes");
  const headerNo = $("upload-header-no"), confirmHeader = $("confirm-upload-header");
  const createTaskButton = $("create-upload-task"), taskSection = $("upload-task");

  class UploadError extends Error {
    constructor(message, needsLogin = false) { super(message); this.needsLogin = needsLogin; }
  }

  const formatSize = bytes => bytes < 1024 ? `${bytes} B`
    : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / 1048576).toFixed(1)} MiB`;

  function previewCell(value) {
    let text = "", count = 0;
    for (const character of value) {
      if (count++ === 200) break;
      text += character;
    }
    return text;
  }

  function setStatus(message) {
    $("upload-status").textContent = message;
    $("upload-status").hidden = !message;
  }

  function showError(message = "", needsLogin = false) {
    $("upload-error").textContent = message;
    $("upload-error").hidden = !message;
    $("upload-login").hidden = !needsLogin;
  }

  function revealOutcome(section = headerOptions) {
    const target = $("upload-error").hidden ? section : $("upload-error");
    const top = dialog.scrollTop + target.getBoundingClientRect().top - dialog.getBoundingClientRect().top - 16;
    dialog.scrollTo({ top: Math.max(0, top), behavior: "auto" });
  }

  function setBusy(value, operation = "upload") {
    busy = value;
    savingHeader = value && operation === "header";
    creatingTask = value && operation === "task";
    form.setAttribute("aria-busy", String(value));
    input.disabled = value;
    $("dropzone").setAttribute("aria-disabled", String(value));
    $("submit-upload").disabled = value || !selectedFile || previewOnly;
    $("submit-upload").textContent = value && operation === "upload" ? "上传并检查中…" : "上传并预览";
    headerOptions.disabled = value || !uploadedResult?.preview_rows.length || Boolean(createdTask);
    updateHeaderChoice();
  }

  function clearResult() {
    uploadedResult = null;
    confirmedHasHeader = null;
    confirmedColumns = null;
    headerSaveUncertain = false;
    createdTask = null;
    taskCreateUncertain = false;
    headerYes.checked = false;
    headerNo.checked = false;
    headerOptions.disabled = true;
    confirmHeader.disabled = true;
    $("upload-header-status").textContent = "请选择是否包含表头。";
    $("upload-result").hidden = true;
    $("upload-preview-head").replaceChildren();
    $("upload-preview-body").replaceChildren();
    updateTaskChoice();
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
    // Always derive the view from the original response; changing the choice must never lose a row.
    const hasHeader = confirmedHasHeader === true;
    const rows = hasHeader ? data.preview_rows.slice(1) : data.preview_rows;
    const columns = Math.min(50, Math.max(confirmedColumns?.length || 0, ...data.preview_rows.map(row => row.length)));
    $("upload-result-meta").textContent = `${data.filename || selectedFile.name} · ${formatSize(data.size_bytes)} · ${rows.length} 条预览记录 · 文件编号 ${data.file_id}`;
    $("upload-preview-note").textContent = confirmedHasHeader === null
      ? "以下为原始记录，表头设置尚未保存。"
      : hasHeader ? "首条记录用于列名，下方展示其余预览记录。"
        : "文件按无表头预览，首条记录保留为数据，使用第1列、第2列等展示标题。";
    $("upload-preview-head").replaceChildren();
    $("upload-preview-body").replaceChildren();
    $("upload-preview-scroll").hidden = columns === 0;
    $("upload-empty-preview").hidden = columns !== 0 && rows.length !== 0;
    $("upload-empty-preview").textContent = hasHeader && rows.length === 0
      ? "当前预览中只有表头，没有可展示的数据记录。"
      : rows.length
      ? "预览中只有空记录，没有可展示的字段；是否存在有效数据需后续确认。"
      : "文件中没有可预览的 CSV 记录；检查通过不代表存在有效数据。";
    $("upload-truncated").hidden = !(data.preview_truncated || confirmedColumns?.length > 50
      || confirmedColumns?.slice(0, 50).some(column => previewCell(column.name) !== column.name));
    if (columns) {
      const heading = document.createElement("tr");
      for (let column = 0; column <= columns; column++) {
        const cell = document.createElement("th");
        cell.scope = "col";
        const name = confirmedColumns?.[column - 1]?.name;
        cell.textContent = column === 0 ? "记录"
          : confirmedColumns && name === undefined ? `（第${column}列未在确认列中）`
            : !hasHeader ? `第${column}列` : previewCell(name);
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

  function updateHeaderChoice() {
    const choice = headerYes.checked && !headerYes.disabled ? true : headerNo.checked ? false : null;
    confirmHeader.disabled = busy || !uploadedResult || headerOptions.disabled || choice === null
      || (choice === confirmedHasHeader && !headerSaveUncertain);
    confirmHeader.textContent = savingHeader ? "保存中…" : "确认选择";
    $("upload-header-status").textContent = savingHeader ? "正在保存表头设置…"
      : headerSaveUncertain ? "保存结果未确认，请重试确认所选设置。"
      : !uploadedResult || !uploadedResult.preview_rows.length
      ? "没有可预览的记录，暂时无法选择表头。"
      : choice === null ? (headerYes.disabled ? "首条记录没有字段，可选择按无表头预览。" : "请选择是否包含表头。")
        : choice === confirmedHasHeader ? `表头设置已保存：${choice ? "第一条记录作为列名" : "全部记录作为数据"}。`
          : "已选择，请点击确认保存设置。";
    updateTaskChoice();
  }

  function updateTaskChoice() {
    const choice = headerYes.checked && !headerYes.disabled ? true : headerNo.checked ? false : null;
    const ready = uploadedResult && confirmedHasHeader !== null && !headerSaveUncertain
      && choice === confirmedHasHeader;
    createTaskButton.disabled = busy || previewOnly || !ready || Boolean(createdTask);
    createTaskButton.textContent = creatingTask ? "创建中…" : createdTask ? "任务已创建"
      : taskCreateUncertain ? "重新创建任务" : "创建任务";
    $("upload-task-status").textContent = creatingTask ? "正在创建任务…"
      : createdTask ? "任务已创建，等待处理。"
      : taskCreateUncertain ? "创建结果未确认，请先核对记录；再次创建可能产生重复任务。"
      : ready ? "表头已保存，可以创建任务。" : "请先确认并保存当前的表头选择。";
    $("upload-task-result").hidden = !createdTask;
    $("upload-task-result").textContent = createdTask
      ? `任务编号：${createdTask.task_id} · 状态：等待处理（${createdTask.status}）` : "";
  }

  headerYes.addEventListener("change", updateHeaderChoice);
  headerNo.addEventListener("change", updateHeaderChoice);
  confirmHeader.addEventListener("click", async () => {
    if (busy || previewOnly || confirmHeader.disabled || !uploadedResult) return;
    const record = uploadedResult, choice = headerYes.checked, previousUncertainty = headerSaveUncertain;
    const version = ++requestVersion, controller = new AbortController();
    activeController = controller;
    let timeout = null, timedOut = false;
    showError(); setBusy(true, "header"); setStatus("正在确认并保存表头设置…");
    try {
      const user = await session.currentUser();
      if (version !== requestVersion) return;
      if (user.id !== record.owner_id) throw new UploadError("当前账号与上传账号不一致，请重新登录。", true);
      const token = session.getToken();
      if (!token) throw new UploadError("请先登录后再确认表头。", true);
      timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
      // Once sent, losing the response does not establish whether the server committed.
      headerSaveUncertain = true;
      const response = await fetch(`${session.apiBaseUrl}/api/files/${record.file_id}/header`, {
        method: "PUT", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ has_header: choice }), credentials: "omit", cache: "no-store", signal: controller.signal,
      });
      if (version !== requestVersion) return;
      if (response.status === 401) {
        headerSaveUncertain = previousUncertainty;
        throw new UploadError("登录状态已失效，请重新登录后再确认。", true);
      }
      const data = await response.json();
      if (version !== requestVersion) return;
      if (!response.ok) {
        // These responses mean this attempt did not update the configuration.
        if (response.status < 500 || response.status === 503) headerSaveUncertain = previousUncertainty;
        const detail = typeof data?.detail === "string" ? data.detail
          : Array.isArray(data?.detail) ? data.detail.map(item => item.msg).filter(Boolean).join("；") : "";
        throw new UploadError(response.status >= 500 && response.status !== 503
          ? "暂时无法确认保存结果，请稍后重试确认。" : detail || "表头设置未通过检查，请修改后重试。");
      }
      if (!session.getToken()) throw new UploadError("登录状态已变化，请重新登录后再确认。", true);
      if (data?.file_id !== record.file_id || data.has_header !== choice || !Array.isArray(data.columns)
        || !data.columns.length || !data.columns.every((column, index) => column?.index === index
          && typeof column.name === "string" && column.name.length > 0)) {
        throw new UploadError("暂时无法确认保存结果，请重试确认。");
      }
      confirmedHasHeader = data.has_header;
      confirmedColumns = data.columns;
      headerSaveUncertain = false;
      renderResult(record);
      setStatus("文件及表头设置已保存，尚未创建处理任务。");
    } catch (error) {
      if (version !== requestVersion) return;
      setStatus(headerSaveUncertain ? "文件已保存，表头设置的保存结果待确认。" : "文件已保存，本次表头确认未完成。");
      if (timedOut) showError("保存请求超时，暂时无法确认结果，请重试确认。");
      else if (error instanceof UploadError) showError(error.message, error.needsLogin);
      else if (error instanceof session.SessionExpiredError || error instanceof session.SessionChangedError) {
        showError("登录状态已变化，请重新登录后再确认。", true);
      } else if (error instanceof session.ConnectionError) {
        showError("暂时无法确认登录状态，请稍后重试。");
      } else showError("暂时无法确认保存结果，当前文件和预览已保留，请重试确认。");
    } finally {
      if (timeout !== null) window.clearTimeout(timeout);
      if (version === requestVersion) { activeController = null; setBusy(false); revealOutcome(); }
    }
  });

  createTaskButton.addEventListener("click", async () => {
    if (busy || previewOnly || createTaskButton.disabled || !uploadedResult) return;
    const record = uploadedResult, previousUncertainty = taskCreateUncertain;
    const version = ++requestVersion, controller = new AbortController();
    activeController = controller;
    let timeout = null, timedOut = false;
    showError(); setBusy(true, "task"); setStatus("正在确认登录状态并创建任务…");
    try {
      const user = await session.currentUser();
      if (version !== requestVersion) return;
      if (user.id !== record.owner_id) throw new UploadError("当前账号与上传账号不一致，请重新登录。", true);
      const token = session.getToken();
      if (!token) throw new UploadError("请先登录后再创建任务。", true);
      timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
      // POST is not idempotent yet: a lost response may still mean a committed task.
      taskCreateUncertain = true;
      const response = await fetch(`${session.apiBaseUrl}/api/tasks`, {
        method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: record.file_id }), credentials: "omit", cache: "no-store", signal: controller.signal,
      });
      if (version !== requestVersion) return;
      if (response.status >= 400 && response.status < 500) taskCreateUncertain = previousUncertainty;
      if (response.status === 401) throw new UploadError("登录状态已失效，请重新登录后再创建任务。", true);
      const data = await response.json().catch(() => null);
      if (version !== requestVersion) return;
      if (!response.ok) {
        const detail = typeof data?.detail === "string" ? data.detail
          : Array.isArray(data?.detail) ? data.detail.map(item => item.msg).filter(Boolean).join("；") : "";
        throw new UploadError(response.status >= 500
          ? "暂时无法确认任务创建结果，请先核对记录；重复创建可能生成新任务。"
          : detail || "任务创建失败，请检查后重试。");
      }
      if (!session.getToken()) throw new UploadError("登录状态已变化，请重新登录后核对创建结果。", true);
      if (response.status !== 201 || typeof data?.task_id !== "string" || !/^[0-9a-f]{32}$/.test(data.task_id)
        || data.file_id !== record.file_id || data.status !== "pending") {
        throw new UploadError("暂时无法确认任务创建结果，请先核对记录；重复创建可能生成新任务。");
      }
      createdTask = { task_id: data.task_id, file_id: data.file_id, status: data.status };
      taskCreateUncertain = false;
      setStatus("任务已创建，状态为等待处理。");
    } catch (error) {
      if (version !== requestVersion) return;
      setStatus(taskCreateUncertain ? "文件及表头已保存，任务创建结果待确认。" : "文件及表头已保存，本次任务未创建。");
      if (timedOut) showError("创建请求超时，结果未确认；请先核对记录，重复创建可能生成新任务。");
      else if (error instanceof UploadError) showError(error.message, error.needsLogin);
      else if (error instanceof session.SessionExpiredError || error instanceof session.SessionChangedError) {
        showError("登录状态已变化，请重新登录后再创建任务。", true);
      } else if (error instanceof session.ConnectionError && !taskCreateUncertain) {
        showError("暂时无法确认登录状态，请稍后重试。");
      } else showError("暂时无法确认任务创建结果；文件和预览已保留，重复创建可能生成新任务。");
    } finally {
      if (timeout !== null) window.clearTimeout(timeout);
      if (version === requestVersion) { activeController = null; setBusy(false); revealOutcome(taskSection); }
    }
  });

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
      uploadedResult = data;
      headerOptions.disabled = data.preview_rows.length === 0;
      headerYes.disabled = !data.preview_rows[0]?.length;
      renderResult(data);
      updateHeaderChoice();
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
      if (version === requestVersion) { activeController = null; setBusy(false); revealOutcome(); }
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

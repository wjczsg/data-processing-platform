/* Register through the backend API. Login is pending; credentials are not stored. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const tabs = [...document.querySelectorAll("[data-mode]")];
  const PASSWORD_MIN_LENGTH = 8;
  const PASSWORD_MAX_LENGTH = 128;
  const API_BASE_URL = document.querySelector('meta[name="api-base-url"]').content.replace(/\/+$/, "");
  let mode = "login";
  let submitting = false;

  function showStatus(message, state = "error") {
    $("auth-feedback").textContent = message;
    $("auth-feedback").dataset.state = state;
    $("auth-feedback").hidden = !message;
  }

  function setSubmitting(value) {
    submitting = value;
    $("auth-form").setAttribute("aria-busy", String(value));
    $("auth-submit").disabled = value || mode !== "register";
    $("auth-submit").textContent = value ? "正在注册…" : mode === "register" ? "注册账号" : "登录 · 暂未开放";
    $("account").disabled = value;
    $("password").disabled = value;
    $("confirm-password").disabled = value || mode !== "register";
    tabs.forEach(tab => { tab.disabled = value; });
    $("switch-mode").disabled = value;
    document.querySelectorAll("[data-password]").forEach(button => { button.disabled = value; });
  }

  function showFieldError(inputId, messageId, message) {
    $(inputId).setCustomValidity(message);
    $(inputId).setAttribute("aria-invalid", String(Boolean(message)));
    $(messageId).textContent = message;
    $(messageId).hidden = !message;
  }

  function updatePasswordFeedback() {
    const password = $("password").value;
    const confirmation = $("confirm-password").value;
    // 按 Unicode 码点计数，与后端 len 保持一致，不截断或清理密码。
    const length = Array.from(password).length;
    const invalidLength = password && (length < PASSWORD_MIN_LENGTH || length > PASSWORD_MAX_LENGTH);
    showFieldError("password", "password-feedback", mode === "register" && invalidLength
      ? `密码长度必须为 ${PASSWORD_MIN_LENGTH}～${PASSWORD_MAX_LENGTH} 个字符` : "");
    showFieldError("confirm-password", "confirmation-feedback", mode === "register" && confirmation && password !== confirmation
      ? "两次输入的密码不一致" : "");
  }

  function resetPasswordVisibility() {
    document.querySelectorAll("[data-password]").forEach(button => {
      $(button.dataset.password).type = "password";
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", button.dataset.password === "password" ? "显示密码" : "显示确认密码");
    });
  }

  function setMode(next, moveFocus = false) {
    if (submitting) return;
    mode = next;
    showStatus("");
    showFieldError("account", "account-feedback", "");
    const register = mode === "register";
    tabs.forEach(tab => {
      const active = tab.dataset.mode === mode;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    $("auth-panel").setAttribute("aria-labelledby", `${mode}-tab`);
    $("auth-title").textContent = register ? "创建账号" : "欢迎回来";
    $("auth-description").textContent = register ? "创建账号，使用你的数据处理工作区。" : "登录后，管理你的数据文件与处理任务。";
    $("confirm-field").hidden = !register;
    $("password-hint").hidden = !register;
    $("confirm-password").disabled = !register;
    $("password").autocomplete = register ? "new-password" : "current-password";
    $("password").placeholder = register ? "请设置密码" : "请输入密码";
    $("password").value = "";
    $("confirm-password").value = "";
    updatePasswordFeedback();
    setSubmitting(false);
    $("switch-description").textContent = register ? "已有账号？" : "还没有账号？";
    $("switch-mode").textContent = register ? "返回登录" : "注册账号";
    document.title = register ? "注册 · 行序" : "登录 · 行序";
    resetPasswordVisibility();
    if (moveFocus) $(`${mode}-tab`).focus();
  }

  function validateRegistration() {
    const username = $("account").value.trim();
    showFieldError("account", "account-feedback", !username ? "请输入账号"
      : /^[A-Za-z0-9_]{3,32}$/.test(username) ? "" : "账号必须为 3～32 位字母、数字或下划线");
    updatePasswordFeedback();
    if (!$("password").value) showFieldError("password", "password-feedback", "请输入密码");
    if (!$("confirm-password").value) showFieldError("confirm-password", "confirmation-feedback", "请再次输入密码");
    const invalid = [$("account"), $("password"), $("confirm-password")].find(input => input.validationMessage);
    if (invalid) invalid.focus();
    return !invalid;
  }

  function registrationError(response, data) {
    if (response.status === 409) return "用户名已存在，请更换账号。";
    if (response.status === 422) {
      if (typeof data?.detail === "string") return data.detail;
      if (Array.isArray(data?.detail)) {
        const labels = { username: "账号", password: "密码", password_confirmation: "确认密码" };
        return data.detail.map(error => {
          const label = labels[error.loc?.[1]];
          return `${label ? label + "：" : ""}${error.msg || "输入不符合要求"}`;
        }).join("；") || "请检查账号和密码是否符合要求。";
      }
      return "请检查账号和密码是否符合要求。";
    }
    return "注册服务暂时不可用，请稍后重试。";
  }

  async function submitRegistration(event) {
    event.preventDefault();
    if (mode !== "register" || submitting) return;
    showStatus("");
    if (!validateRegistration()) return;

    const payload = {
      username: $("account").value.trim(),
      password: $("password").value,
      password_confirmation: $("confirm-password").value,
    };
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    let registeredUsername = null;
    setSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "omit",
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => null);
      if (response.status !== 201) throw new Error(registrationError(response, data));
      if (typeof data?.username !== "string" || !Number.isInteger(data.id) || data.id <= 0) {
        throw new Error("注册结果暂时无法确认，请稍后重试。");
      }
      registeredUsername = data.username;
    } catch (error) {
      showStatus(controller.signal.aborted ? "请求超时，注册结果尚未确认，请稍后再试。"
        : error instanceof TypeError ? "注册请求未完成，请确认后端服务可访问后再试。"
        : error.message || "注册请求未完成，请稍后重试。");
    } finally {
      window.clearTimeout(timeout);
      setSubmitting(false);
    }
    if (registeredUsername !== null) {
      setMode("login");
      $("account").value = registeredUsername;
      showStatus("注册成功，账号已创建。登录功能暂未开放。", "success");
      $("password").focus();
    }
  }

  tabs.forEach(tab => {
    tab.addEventListener("click", () => { if (tab.dataset.mode !== mode) setMode(tab.dataset.mode); });
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? "login" : event.key === "End" ? "register" : mode === "login" ? "register" : "login";
      setMode(next, true);
    });
  });
  $("switch-mode").addEventListener("click", () => setMode(mode === "login" ? "register" : "login", true));
  document.querySelectorAll("[data-password]").forEach(button => button.addEventListener("click", () => {
    const input = $(button.dataset.password);
    const visible = input.type === "password";
    input.type = visible ? "text" : "password";
    button.setAttribute("aria-pressed", String(visible));
    button.setAttribute("aria-label", `${visible ? "隐藏" : "显示"}${button.dataset.password === "password" ? "密码" : "确认密码"}`);
  }));
  $("auth-form").addEventListener("submit", submitRegistration);
  $("account").addEventListener("input", () => {
    showFieldError("account", "account-feedback", "");
    showStatus("");
  });
  [$("password"), $("confirm-password")].forEach(input => input.addEventListener("input", () => {
    updatePasswordFeedback();
    showStatus("");
  }));
  setMode("login");
})();

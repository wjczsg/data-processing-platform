/* Form display only. No authentication, network requests or credential storage. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const tabs = [...document.querySelectorAll("[data-mode]")];
  let mode = "login";

  function resetPasswordVisibility() {
    document.querySelectorAll("[data-password]").forEach(button => {
      $(button.dataset.password).type = "password";
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", button.dataset.password === "password" ? "显示密码" : "显示确认密码");
    });
  }

  function setMode(next, moveFocus = false) {
    mode = next;
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
    $("confirm-password").disabled = !register;
    $("password").autocomplete = register ? "new-password" : "current-password";
    $("password").placeholder = register ? "请设置密码" : "请输入密码";
    $("password").value = "";
    $("confirm-password").value = "";
    $("auth-submit").textContent = register ? "注册 · 待接入后端" : "登录 · 待接入后端";
    $("switch-description").textContent = register ? "已有账号？" : "还没有账号？";
    $("switch-mode").textContent = register ? "返回登录" : "注册账号";
    document.title = register ? "注册 · 行序" : "登录 · 行序";
    resetPasswordVisibility();
    if (moveFocus) $(`${mode}-tab`).focus();
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
  $("auth-form").addEventListener("submit", event => event.preventDefault());
  setMode("login");
})();

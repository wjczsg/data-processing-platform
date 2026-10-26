/* Authenticate the workbench; explicit preview mode contains static examples only. */
(async function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const session = window.AuthSession;
  const preview = new URLSearchParams(window.location.search).get("preview") === "1";
  function reveal() {
    $("auth-loading").hidden = true;
    document.body.dataset.authState = "ready";
  }

  $("auth-retry").addEventListener("click", () => window.location.reload());
  $("logout-button").addEventListener("click", () => {
    session.clear();
    window.location.replace("auth.html");
  });

  if (preview) {
    reveal();
    return;
  }
  if (!session.getToken()) {
    window.location.replace("auth.html");
    return;
  }

  try {
    const user = await session.currentUser();
    $("current-username").textContent = user.username;
    $("current-avatar").textContent = user.username.slice(0, 1).toUpperCase();
    $("current-role").textContent = user.role === "admin" ? "管理员" : "普通用户";
    $("auth-entry").hidden = true;
    $("logout-button").hidden = false;
    $("identity-badge").textContent = "已登录 · 示例数据";
    reveal();
  } catch (error) {
    if (error instanceof session.SessionExpiredError) {
      window.location.replace("auth.html?reason=expired");
      return;
    }
    $("auth-loading-text").textContent = "暂时无法确认登录状态，请检查后端服务后重试。";
    $("auth-retry").hidden = false;
  }
})();

/* Authenticate the workbench; explicit preview mode contains static examples only. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const session = window.AuthSession;
  const preview = new URLSearchParams(window.location.search).get("preview") === "1";
  const retryDelays = [2000, 5000, 10000, 30000];
  let checking = false;
  let stopped = false;
  let verified = false;
  let failures = 0;
  let retryTimer = null;
  let refreshingStarted = false;
  function reveal() {
    $("auth-loading").hidden = true;
    document.body.dataset.authState = "ready";
  }

  function clearRetry() {
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    retryTimer = null;
  }

  function showFailure(message, expired = false) {
    if (verified) {
      $("session-notice").hidden = false;
      $("session-notice-text").textContent = message;
      $("session-retry").hidden = expired;
      $("session-relogin").hidden = !expired;
      if (expired) $("identity-badge").textContent = "登录已失效";
    } else {
      $("auth-loading-text").textContent = message;
      $("auth-retry").hidden = expired;
    }
  }

  function updateIdentity(user) {
    $("current-username").textContent = user.username;
    $("current-avatar").textContent = user.username.slice(0, 1).toUpperCase();
    $("current-role").textContent = user.role === "admin" ? "管理员" : "普通用户";
    $("auth-entry").hidden = true;
    $("logout-button").hidden = false;
    $("identity-badge").textContent = "已登录 · 示例数据";
    $("session-notice").hidden = true;
  }

  function sessionExpired() {
    stopped = true;
    clearRetry();
    session.stopAutoRefresh();
    showFailure("登录已失效，请重新登录。页面内容已保留。", true);
  }

  function startRefresh() {
    if (refreshingStarted) return;
    refreshingStarted = true;
    session.startAutoRefresh({
      onUpdated(user) { if (!stopped) updateIdentity(user); },
      onConnectionError() { if (!stopped) showFailure("续期暂时不可用，页面已保留，将自动重试。"); },
      onExpired: sessionExpired,
    });
  }

  function scheduleRetry() {
    clearRetry();
    // 离线时等待浏览器 online 事件；其他临时失败逐步退避，最多每 30 秒一次。
    if (window.navigator?.onLine === false) return;
    const delay = retryDelays[Math.min(failures++, retryDelays.length - 1)];
    retryTimer = window.setTimeout(() => { retryTimer = null; void verifyIdentity(); }, delay);
  }

  async function verifyIdentity() {
    if (stopped || checking) return;
    clearRetry();
    checking = true;
    $("auth-retry").disabled = true;
    $("session-retry").disabled = true;
    try {
      if (window.navigator?.onLine === false) throw new session.ConnectionError();
      const user = await session.currentUser();
      if (stopped) return;
      updateIdentity(user);
      failures = 0;
      verified = true;
      reveal();
      startRefresh();
    } catch (error) {
      if (stopped || error instanceof session.SessionChangedError) return;
      if (error instanceof session.SessionExpiredError) {
        sessionExpired();
      } else if (error instanceof session.ConnectionError) {
        showFailure("连接暂时不可用，页面已保留，将自动重试。");
        scheduleRetry();
      } else {
        showFailure("暂时无法确认登录状态，请点击重试。");
      }
    } finally {
      checking = false;
      $("auth-retry").disabled = false;
      $("session-retry").disabled = false;
    }
  }

  $("auth-retry").addEventListener("click", () => { void verifyIdentity(); });
  $("session-retry").addEventListener("click", () => { void verifyIdentity(); });
  $("logout-button").addEventListener("click", async () => {
    stopped = true;
    clearRetry();
    $("logout-button").disabled = true;
    try {
      await session.logout();
      window.location.replace("auth.html");
    } catch {
      window.location.replace("auth.html?reason=logout_pending");
    }
  });

  if (preview) {
    reveal();
    return;
  }
  if (!session.getToken()) {
    window.location.replace("auth.html");
    return;
  }

  window.addEventListener("online", () => { void verifyIdentity(); });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void verifyIdentity();
  });
  window.addEventListener("pagehide", () => { clearRetry(); });
  window.addEventListener("pageshow", () => { if (!verified || failures) void verifyIdentity(); });
  void verifyIdentity();
})();

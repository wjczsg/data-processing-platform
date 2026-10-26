/* Tab-scoped credentials, recoverable refresh rotation and expiry-based scheduling. */
(function () {
  "use strict";
  const SESSION_KEY = "xingxu.auth_session";
  const LEGACY_KEY = "xingxu.access_token";
  const apiBaseUrl = document.querySelector('meta[name="api-base-url"]').content.replace(/\/+$/, "");
  class SessionExpiredError extends Error {}
  class ConnectionError extends Error {}
  class SessionChangedError extends Error {}
  let sessionVersion = 0;
  let refreshInFlight = null;
  let refreshController = null;
  let stopScheduler = null;

  function read() {
    try {
      const raw = window.sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        const value = JSON.parse(raw);
        if (typeof value.accessToken === "string" && typeof value.refreshToken === "string") return value;
      }
      const legacy = window.sessionStorage.getItem(LEGACY_KEY);
      return legacy ? { accessToken: legacy, refreshToken: null } : null;
    } catch { return null; }
  }

  function write(value) {
    try {
      window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
      window.sessionStorage.removeItem(LEGACY_KEY);
    } catch { throw new Error("浏览器无法保存登录状态，请允许本站使用会话存储后重试。"); }
  }

  function validResponse(data) {
    return typeof data?.access_token === "string" && !!data.access_token
      && typeof data.refresh_token === "string" && !!data.refresh_token && data.token_type === "bearer"
      && Number.isFinite(data.expires_in) && data.expires_in > 0
      && Number.isFinite(data.refresh_expires_in) && data.refresh_expires_in > 0
      && Number.isInteger(data.user?.id) && data.user.id > 0 && typeof data.user.username === "string";
  }

  function setSession(data, requestedAt = Date.now()) {
    if (!validResponse(data)) throw new ConnectionError("暂时无法确认登录结果，请重试。");
    // 从发起请求时保守计时，避免响应延迟或浏览器休眠后高估剩余有效期。
    const now = requestedAt;
    write({ accessToken: data.access_token, refreshToken: data.refresh_token,
      expiresAt: now + data.expires_in * 1000, refreshExpiresAt: now + data.refresh_expires_in * 1000,
      accessLifetimeMs: data.expires_in * 1000, refreshLifetimeMs: data.refresh_expires_in * 1000,
      pendingRequestId: null });
    sessionVersion++;
  }

  function erase() {
    sessionVersion++;
    try {
      window.sessionStorage.removeItem(SESSION_KEY);
      window.sessionStorage.removeItem(LEGACY_KEY);
    } catch { /* No browser credential is available when storage is blocked. */ }
  }

  function stopAutoRefresh() {
    if (stopScheduler) stopScheduler();
  }

  function clear() {
    stopAutoRefresh();
    erase();
    if (refreshController) refreshController.abort();
    refreshInFlight = null;
  }

  function getToken() { return read()?.accessToken || null; }

  function dueAt(value) {
    if (value.pendingRequestId) return 0;
    const buffer = Math.min(300000, value.accessLifetimeMs / 6, value.refreshLifetimeMs / 6);
    return Math.min(value.expiresAt, value.refreshExpiresAt) - buffer;
  }

  async function send(path, options = {}, version = sessionVersion, controller = new AbortController()) {
    const startedAt = Date.now();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        ...options, credentials: "omit", cache: "no-store", signal: controller.signal,
      });
      if (version !== sessionVersion) throw new SessionChangedError();
      if (response.status === 401) return { status: 401, data: null };
      if (!response.ok) throw new ConnectionError("账号服务暂时不可用，请稍后重试。");
      const data = response.status === 204 ? null : await response.json();
      if (version !== sessionVersion) throw new SessionChangedError();
      return { status: response.status, data, startedAt };
    } catch (error) {
      if (version !== sessionVersion || error instanceof SessionChangedError) throw new SessionChangedError();
      if (error instanceof TypeError || error instanceof SyntaxError || controller.signal.aborted) {
        throw new ConnectionError("连接暂时不可用，请稍后重试。");
      }
      throw error;
    } finally { window.clearTimeout(timeout); }
  }

  function refresh() {
    if (refreshInFlight) return refreshInFlight;
    const value = read();
    if (!value?.refreshToken) return Promise.reject(new SessionExpiredError("请重新登录以启用自动续期。"));
    const version = sessionVersion;
    const controller = new AbortController();
    refreshController = controller;
    const task = (async () => {
      // 先保存请求编号，响应丢失或页面刷新后仍重试同一次轮换。
      const requestId = value.pendingRequestId || window.crypto.randomUUID();
      if (!value.pendingRequestId) write({ ...value, pendingRequestId: requestId });
      const result = await send("/api/auth/refresh", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: value.refreshToken, request_id: requestId }),
      }, version, controller);
      if (result.status === 401) {
        erase();
        throw new SessionExpiredError("登录已失效，请重新登录。");
      }
      if (!validResponse(result.data)) throw new ConnectionError("暂时无法确认续期结果，请重试。");
      setSession(result.data, result.startedAt);
      return result.data;
    })();
    const tracked = task.finally(() => {
      if (refreshInFlight === tracked) refreshInFlight = null;
      if (refreshController === controller) refreshController = null;
    });
    refreshInFlight = tracked;
    return tracked;
  }

  async function currentUser() {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        let value = read();
        if (!value?.accessToken) throw new SessionExpiredError("请先登录。");
        if (value.refreshToken && (value.pendingRequestId || Date.now() >= dueAt(value))) await refresh();
        value = read();
        if (!value?.accessToken) throw new SessionExpiredError("请先登录。");
        const result = await send("/api/auth/me", { headers: { Authorization: `Bearer ${value.accessToken}` } });
        if (result.status === 401) {
          if (attempt === 0 && value.refreshToken) { await refresh(); continue; }
          erase();
          throw new SessionExpiredError("登录已失效，请重新登录。");
        }
        const user = result.data;
        if (!user || !Number.isInteger(user.id) || user.id <= 0 || typeof user.username !== "string") {
          throw new ConnectionError("暂时无法确认登录状态，请重试。");
        }
        return user;
      } catch (error) {
        if (error instanceof SessionChangedError && attempt === 0 && getToken()) continue;
        throw error;
      }
    }
  }

  function startAutoRefresh({ onUpdated, onConnectionError, onExpired }) {
    stopAutoRefresh();
    let stopped = false, running = false, timer = null, failures = 0;
    const delays = [2000, 5000, 10000, 30000];
    function cancelTimer() { if (timer !== null) window.clearTimeout(timer); timer = null; }
    function schedule(delay) {
      cancelTimer();
      if (!stopped) timer = window.setTimeout(() => { timer = null; void run(); }, Math.max(0, delay));
    }
    function scheduleDeadline() {
      const value = read();
      if (!value?.refreshToken) return;
      schedule(Math.max(0, dueAt(value) - Date.now()));
    }
    async function run() {
      if (stopped || running) return;
      const value = read();
      if (!value?.refreshToken) { stop(); onExpired(); return; }
      if (!failures && Date.now() < dueAt(value)) { scheduleDeadline(); return; }
      cancelTimer(); running = true;
      try {
        if (window.navigator?.onLine === false) throw new ConnectionError("网络暂时不可用。");
        const result = await refresh();
        if (stopped) return;
        failures = 0;
        onUpdated(result.user);
        scheduleDeadline();
      } catch (error) {
        if (stopped) return;
        if (error instanceof SessionChangedError) { scheduleDeadline(); return; }
        if (error instanceof SessionExpiredError) { stop(); onExpired(); return; }
        onConnectionError(error);
        const delay = delays[Math.min(failures++, delays.length - 1)];
        if (window.navigator?.onLine !== false) schedule(delay);
      } finally { running = false; }
    }
    function visible() { if (document.visibilityState === "visible") void run(); }
    function wake() { void run(); }
    function stop() {
      stopped = true; cancelTimer();
      window.removeEventListener("online", wake);
      window.removeEventListener("pageshow", wake);
      document.removeEventListener("visibilitychange", visible);
      if (stopScheduler === stop) stopScheduler = null;
    }
    stopScheduler = stop;
    window.addEventListener("online", wake);
    window.addEventListener("pageshow", wake);
    document.addEventListener("visibilitychange", visible);
    scheduleDeadline();
    return stop;
  }

  async function logout() {
    const value = read();
    clear();
    if (value?.refreshToken) {
      await send("/api/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: value.refreshToken }) });
    }
  }

  window.AuthSession = { apiBaseUrl, getToken, setSession, clear, currentUser, refresh,
    startAutoRefresh, stopAutoRefresh, logout, SessionExpiredError, ConnectionError, SessionChangedError };
})();

/* Keep only the access token in this tab; the backend confirms the user's identity. */
(function () {
  "use strict";
  const TOKEN_KEY = "xingxu.access_token";
  const apiBaseUrl = document.querySelector('meta[name="api-base-url"]').content.replace(/\/+$/, "");

  class SessionExpiredError extends Error {}
  class ConnectionError extends Error {}
  class SessionChangedError extends Error {}
  let sessionVersion = 0;

  function getToken() {
    try { return window.sessionStorage.getItem(TOKEN_KEY); }
    catch { return null; }
  }

  function setToken(token) {
    try { window.sessionStorage.setItem(TOKEN_KEY, token); sessionVersion++; }
    catch { throw new Error("浏览器无法保存登录状态，请允许本站使用会话存储后重试。"); }
  }

  function clear() {
    sessionVersion++;
    try { window.sessionStorage.removeItem(TOKEN_KEY); }
    catch { /* Nothing is retained when session storage is unavailable. */ }
  }

  async function currentUser() {
    const token = getToken();
    const version = sessionVersion;
    if (!token) throw new SessionExpiredError("请先登录");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${apiBaseUrl}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "omit", cache: "no-store", signal: controller.signal,
      });
      if (version !== sessionVersion || token !== getToken()) throw new SessionChangedError();
      if (response.status === 401) {
        clear();
        throw new SessionExpiredError("登录已失效，请重新登录");
      }
      if (response.status >= 500 || response.status === 408) {
        throw new ConnectionError("账号服务暂时不可用，请稍后重试。");
      }
      if (!response.ok) throw new Error("暂时无法确认登录状态，请稍后重试。");
      const user = await response.json();
      if (version !== sessionVersion || token !== getToken()) throw new SessionChangedError();
      if (!user || !Number.isInteger(user.id) || user.id <= 0 || typeof user.username !== "string") {
        throw new Error("暂时无法确认登录状态，请稍后重试。");
      }
      return user;
    } catch (error) {
      if (error instanceof SessionExpiredError || error instanceof SessionChangedError) throw error;
      if (error instanceof TypeError || controller.signal.aborted) {
        throw new ConnectionError("连接暂时不可用，请稍后重试。");
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  window.AuthSession = {
    apiBaseUrl, getToken, setToken, clear, currentUser,
    SessionExpiredError, ConnectionError, SessionChangedError,
  };
})();

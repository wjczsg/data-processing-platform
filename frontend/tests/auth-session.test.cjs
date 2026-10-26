// Clock and transport simulations run only under node --test, never on the page.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '..', 'auth-session.js'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
const user = { id: 1, username: 'student_01', role: 'user' };
const credentials = (number, overrides = {}) => ({ access_token: `access-${number}`,
  refresh_token: `refresh-${number}`, token_type: 'bearer', expires_in: 1800,
  refresh_expires_in: 43200, user, ...overrides });
const response = (status, data) => ({ status, ok: status >= 200 && status < 300, json: async () => data });

function browser(fetcher, storage = new Map(), initialTime = 1000000000) {
  let now = initialTime, sequence = 0;
  const timers = new Map();
  const listeners = new Map();
  const eventTarget = prefix => ({
    addEventListener(name, fn) { const key = prefix + name; if (!listeners.has(key)) listeners.set(key, new Set()); listeners.get(key).add(fn); },
    removeEventListener(name, fn) { listeners.get(prefix + name)?.delete(fn); },
  });
  const window = {
    ...eventTarget('window:'), navigator: { onLine: true }, crypto,
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    setTimeout(fn, delay) { timers.set(++sequence, { fn, at: now + delay }); return sequence; },
    clearTimeout(id) { timers.delete(id); },
  };
  const document = { ...eventTarget('document:'), visibilityState: 'visible',
    querySelector: () => ({ content: 'http://127.0.0.1:8000' }) };
  class ClockDate extends Date { static now() { return now; } }
  vm.runInNewContext(source, { window, document, fetch: fetcher, AbortController,
    Date: ClockDate, TypeError, SyntaxError, Error, Promise });
  return {
    api: window.AuthSession, window, storage, time: () => now, jump: ms => { now += ms; },
    emit(name) { for (const fn of listeners.get('window:' + name) || []) fn(); },
    async advance(ms) {
      const end = now + ms;
      while (true) {
        const entry = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!entry) break;
        timers.delete(entry[0]); now = entry[1].at; entry[1].fn(); await settle();
      }
      now = end; await settle();
    },
  };
}

function callbacks() {
  const state = { updated: 0, errors: 0, expired: 0 };
  return { state, options: {
    onUpdated() { state.updated++; }, onConnectionError() { state.errors++; }, onExpired() { state.expired++; },
  } };
}

test('30-minute access token renews at minute 25 and reschedules', async () => {
  let requests = 0;
  const page = browser(async url => { assert(url.endsWith('/api/auth/refresh')); return response(200, credentials(++requests + 1)); });
  page.api.setSession(credentials(1));
  const observer = callbacks(); page.api.startAutoRefresh(observer.options);
  await page.advance(25 * 60000 - 1); assert.equal(requests, 0);
  await page.advance(1); assert.equal(requests, 1); assert.equal(page.api.getToken(), 'access-2');
  await page.advance(25 * 60000); assert.equal(requests, 2); assert.equal(observer.state.updated, 2);
});

test('failed refresh retains request ID across retry and page reload', async () => {
  const requests = [];
  const storage = new Map();
  const first = browser(async (url, options) => { requests.push(JSON.parse(options.body)); throw new TypeError('response lost'); }, storage);
  first.api.setSession(credentials(1));
  const observer = callbacks(); const stop = first.api.startAutoRefresh(observer.options);
  await first.advance(25 * 60000); assert.equal(observer.state.errors, 1);
  assert.equal(first.api.getToken(), 'access-1'); stop();
  const restored = browser(async (url, options) => { requests.push(JSON.parse(options.body)); return response(200, credentials(2)); }, storage, first.time());
  restored.api.startAutoRefresh(callbacks().options); await restored.advance(0);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].request_id, requests[1].request_id);
  assert.equal(requests[0].refresh_token, requests[1].refresh_token);
  assert.equal(restored.api.getToken(), 'access-2');
});

test('simultaneous renewals use one request and logout cannot be undone by a late response', async () => {
  let resolve, requests = 0;
  const page = browser(() => { requests++; return new Promise(done => { resolve = done; }); });
  page.api.setSession(credentials(1));
  const first = page.api.refresh(); const second = page.api.refresh();
  assert.equal(first, second); assert.equal(requests, 1);
  page.api.clear(); resolve(response(200, credentials(2)));
  await assert.rejects(first, page.api.SessionChangedError);
  assert.equal(page.api.getToken(), null); assert.equal(page.storage.size, 0);
});

test('offline does not erase session; coming online recovers immediately', async () => {
  let requests = 0;
  const page = browser(async () => { requests++; return response(200, credentials(2)); });
  page.api.setSession(credentials(1)); page.window.navigator.onLine = false;
  const observer = callbacks(); page.api.startAutoRefresh(observer.options);
  await page.advance(30 * 60000); assert.equal(requests, 0); assert.equal(page.api.getToken(), 'access-1');
  page.window.navigator.onLine = true; page.emit('online'); await settle();
  assert.equal(requests, 1); assert.equal(page.api.getToken(), 'access-2');
});

test('confirmed refresh rejection stops scheduling and requests re-login', async () => {
  let requests = 0;
  const page = browser(async () => { requests++; return response(401, {}); });
  page.api.setSession(credentials(1)); const observer = callbacks(); page.api.startAutoRefresh(observer.options);
  await page.advance(25 * 60000); assert.equal(observer.state.expired, 1); assert.equal(page.api.getToken(), null);
  await page.advance(60 * 60000); assert.equal(requests, 1);
});

test('expired access recovers with refresh; short recovery deadline is respected', async () => {
  const routes = [];
  const page = browser(async url => { routes.push(url); return response(200, url.endsWith('/refresh') ? credentials(2) : user); });
  page.api.setSession(credentials(1)); await page.advance(35 * 60000);
  assert.equal((await page.api.currentUser()).id, 1);
  assert(routes[0].endsWith('/refresh')); assert(routes[1].endsWith('/me'));
  let renewals = 0;
  const short = browser(async () => { renewals++; return response(200, credentials(2)); });
  short.api.setSession(credentials(1, { refresh_expires_in: 180 })); short.api.startAutoRefresh(callbacks().options);
  await short.advance(150000); assert.equal(renewals, 1);
});

test('delayed response does not move the advertised expiry forward', async () => {
  let resolve;
  const page = browser(() => new Promise(done => { resolve = done; }));
  page.api.setSession(credentials(1)); const started = page.time();
  const pending = page.api.refresh();
  page.jump(60000); // Simulate a suspended event loop, without firing its queued timers.
  resolve(response(200, credentials(2))); await pending;
  const stored = JSON.parse(page.storage.get('xingxu.auth_session'));
  assert.equal(stored.expiresAt, started + 1800000);
});

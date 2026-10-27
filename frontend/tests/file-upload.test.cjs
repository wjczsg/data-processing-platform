// Exercise the actual upload script with native FormData and a small DOM fixture.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'file-upload.js'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
const response = (status, data) => ({ status, ok: status >= 200 && status < 300, json: async () => data });
const result = (overrides = {}) => ({ filename: 'students.csv', size_bytes: 20, owner_id: 1,
  persisted: false, preview_rows: [['学号', '姓名'], ['001', '张三']], preview_truncated: false, ...overrides });

class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.listeners = new Map(); this.attributes = new Map();
    this.hidden = false; this.disabled = false; this.files = []; this.value = ''; this.text = '';
    const classes = new Set();
    this.classList = { add: name => classes.add(name), remove: name => classes.delete(name) };
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  set innerHTML(_) { throw new Error('Uploaded content must not be rendered as HTML'); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.text = ''; this.children = children; }
  setAttribute(name, value) { this.attributes.set(name, value); }
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(callback);
  }
  async emit(name, values = {}) {
    const event = { preventDefault() {}, target: this, ...values };
    for (const callback of this.listeners.get(name) || []) await callback(event);
  }
  showModal() { this.open = true; }
  click() { return this.emit('click'); }
}

function page(fetcher, { previewOnly = false, currentUser } = {}) {
  const ids = ['upload-form', 'upload-dialog', 'file-input', 'upload-status', 'upload-error', 'upload-login',
    'dropzone', 'submit-upload', 'upload-result', 'upload-preview-head', 'upload-preview-body', 'drop-title',
    'drop-subtitle', 'upload-result-meta', 'upload-preview-scroll', 'upload-empty-preview', 'upload-truncated',
    'new-task-button'];
  const elements = new Map(ids.map(id => [id, new Element()]));
  for (const id of ['upload-result', 'upload-status', 'upload-error', 'upload-login']) elements.get(id).hidden = true;
  const timers = new Map(); let sequence = 0, token = 'access-after-refresh', identityChecks = 0;
  class SessionExpiredError extends Error {}
  class SessionChangedError extends Error {}
  class ConnectionError extends Error {}
  const session = { apiBaseUrl: 'http://127.0.0.1:8000', getToken: () => token,
    async currentUser() { identityChecks++; return currentUser ? currentUser(session) : { id: 1 }; },
    SessionExpiredError, SessionChangedError, ConnectionError };
  const window = { AuthSession: session, location: { search: previewOnly ? '?preview=1' : '' },
    addEventListener() {}, setTimeout(fn) { timers.set(++sequence, fn); return sequence; },
    clearTimeout(id) { timers.delete(id); } };
  vm.runInNewContext(source, { window, document: { getElementById: id => elements.get(id),
    createElement: tag => new Element(tag) }, URLSearchParams, FormData, AbortController, fetch: fetcher,
    Error, TypeError, Array });
  return { get: id => elements.get(id), timers, session, identityChecks: () => identityChecks,
    clearToken: () => { token = null; },
    async select(...files) { elements.get('file-input').files = files; await elements.get('file-input').emit('change'); },
    submit: () => elements.get('upload-form').emit('submit'),
    drop: files => elements.get('dropzone').emit('drop', { dataTransfer: { files } }),
    close: () => elements.get('upload-dialog').emit('close'),
    expire: () => { for (const fn of [...timers.values()]) fn(); } };
}
const csv = (name = 'students.csv') => new File(['学号,姓名\n001,张三\n'], name, { type: 'text/csv' });

test('picker submits native FormData with current Bearer token and renders generic columns as text', async () => {
  let sent;
  const malicious = '<img src=x onerror=alert(1)>';
  const ui = page(async (url, options) => { sent = { url, options };
    return response(200, result({ filename: malicious + '.csv', preview_rows: [['学号', '姓名'], ['001', malicious]] })); });
  await ui.select(csv()); await ui.submit();
  assert.equal(sent.url, 'http://127.0.0.1:8000/api/files');
  assert.equal(sent.options.headers.Authorization, 'Bearer access-after-refresh');
  assert.equal(sent.options.headers['Content-Type'], undefined);
  assert.equal(sent.options.body.get('file').name, 'students.csv');
  assert.equal(sent.options.credentials, 'omit');
  assert.equal(ui.identityChecks(), 1);
  assert.equal(ui.get('upload-result').hidden, false);
  assert.equal(ui.get('upload-preview-head').children[0].children[1].textContent, '第1列');
  assert.equal(ui.get('upload-preview-body').children[0].children[1].textContent, '学号');
  assert.equal(ui.get('upload-preview-body').children[1].children[1].textContent, '001');
  assert.equal(ui.get('upload-preview-body').children[1].children[2].textContent, malicious);
  assert(ui.get('upload-result-meta').textContent.includes(malicious));
  assert(ui.get('upload-status').textContent.includes('尚未正式保存'));
});

test('dragged file is submitted and multiple dropped files are rejected without choosing the first', async () => {
  const files = [];
  const ui = page(async (_, options) => { files.push(options.body.get('file').name); return response(200, result()); });
  await ui.select(csv('old.csv')); await ui.drop([csv('one.csv'), csv('two.csv')]);
  assert.equal(ui.get('submit-upload').disabled, true);
  assert(ui.get('upload-error').textContent.includes('每次只能上传一个文件'));
  await ui.submit(); assert.equal(files.length, 0);
  await ui.drop([csv('dragged.csv')]); await ui.submit();
  assert.deepEqual(files, ['dragged.csv']);
});

test('backend validation failures preserve the selection and allow an explicit retry', async () => {
  for (const [status, detail] of [[422, '不能上传空文件'], [413, '文件大小不能超过 50 MiB']]) {
    let calls = 0;
    const ui = page(async () => ++calls === 1 ? response(status, { detail }) : response(200, result()));
    await ui.select(csv()); await ui.submit();
    assert.equal(ui.get('upload-error').textContent, detail);
    assert.equal(ui.get('upload-result').hidden, true);
    assert.equal(ui.get('submit-upload').disabled, false);
    assert.equal(calls, 1);
    await ui.submit(); assert.equal(calls, 2); assert.equal(ui.get('upload-result').hidden, false);
  }
});

test('pending upload disables file changes and ignores duplicate submissions', async () => {
  let resolve, calls = 0;
  const ui = page(() => { calls++; return new Promise(done => { resolve = done; }); });
  await ui.select(csv()); const first = ui.submit(); await settle();
  assert.equal(ui.get('file-input').disabled, true);
  assert.equal(ui.get('submit-upload').disabled, true);
  await ui.submit(); assert.equal(calls, 1);
  resolve(response(200, result())); await first;
  assert.equal(ui.get('file-input').disabled, false);
});

test('network failures do not clear the selected file or automatically replay uploads', async () => {
  let calls = 0;
  const ui = page(async () => { calls++; throw new TypeError('offline'); });
  await ui.select(csv()); await ui.submit(); await settle();
  assert.equal(calls, 1); assert.equal(ui.timers.size, 0);
  assert.equal(ui.get('submit-upload').disabled, false);
  assert.equal(ui.get('drop-title').textContent, 'students.csv');
  assert(ui.get('upload-error').textContent.includes('已保留所选文件'));
});

test('closing a pending upload aborts its request and discards late results', async () => {
  let resolve, signal;
  const ui = page((_, options) => { signal = options.signal; return new Promise(done => { resolve = done; }); });
  await ui.select(csv()); const pending = ui.submit(); await settle();
  await ui.close(); assert.equal(signal.aborted, true);
  resolve(response(200, result())); await pending;
  assert.equal(ui.get('upload-result').hidden, true); assert.equal(ui.timers.size, 0);
});

test('request timeout preserves the file and requires a manual retry', async () => {
  const ui = page((_, options) => new Promise((_, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted')));
  }));
  await ui.select(csv()); const pending = ui.submit(); await settle(); ui.expire(); await pending;
  assert(ui.get('upload-error').textContent.includes('请求超时'));
  assert.equal(ui.get('submit-upload').disabled, false);
});

test('expired login and static demo mode cannot submit files', async () => {
  let calls = 0;
  const fetcher = async () => { calls++; return response(200, result()); };
  const expired = page(fetcher, { currentUser: session => { throw new session.SessionExpiredError(); } });
  await expired.select(csv()); await expired.submit();
  assert.equal(expired.get('upload-login').hidden, false);
  const demo = page(fetcher, { previewOnly: true });
  await demo.select(csv()); await demo.submit();
  assert.equal(demo.get('submit-upload').disabled, true);
  assert.equal(demo.identityChecks(), 0); assert.equal(calls, 0);
});

test('401 and mismatched or malformed responses never display a preview', async () => {
  for (const reply of [response(401, {}), response(200, result({ owner_id: 2 })), response(200, {})]) {
    const ui = page(async () => reply);
    await ui.select(csv()); await ui.submit();
    assert.equal(ui.get('upload-result').hidden, true);
    assert.equal(ui.get('upload-error').hidden, false);
  }
});

test('truncation and an empty preview are shown without claiming valid headers or saved files', async () => {
  const ui = page(async () => response(200, result({ preview_truncated: true })));
  await ui.select(csv()); await ui.submit();
  assert.equal(ui.get('upload-truncated').hidden, false);
  const empty = page(async () => response(200, result({ preview_rows: [] })));
  await empty.select(csv()); await empty.submit();
  assert.equal(empty.get('upload-preview-scroll').hidden, true);
  assert.equal(empty.get('upload-empty-preview').hidden, false);
  assert.equal(empty.get('upload-result').hidden, false);
});

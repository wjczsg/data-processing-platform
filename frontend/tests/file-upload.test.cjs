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
  persisted: true, file_id: "a".repeat(32), created_at: "2026-10-27T00:00:00Z", preview_rows: [['学号', '姓名'], ['001', '张三']], preview_truncated: false, ...overrides });
const headerResult = (hasHeader = true, overrides = {}) => ({ file_id: 'a'.repeat(32), has_header: hasHeader,
  columns: (hasHeader ? ['学号', '姓名'] : ['column_1', 'column_2']).map((name, index) => ({ index, name })),
  message: '表头设置已保存', ...overrides });
const uploadAndHeader = (data = result()) => async (_, options) => options.method === 'PUT'
  ? response(200, headerResult(JSON.parse(options.body).has_header)) : response(201, data);

class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.listeners = new Map(); this.attributes = new Map();
    this.hidden = false; this.disabled = false; this.checked = false; this.files = []; this.value = ''; this.text = '';
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
  getBoundingClientRect() { return { top: 0 }; }
  get scrollTop() { return this.scrollPosition || 0; }
  set scrollTop(value) { this.scrollPosition = value; }
  scrollTo({ top }) { this.scrollTop = top; }
  click() { return this.emit('click'); }
}

function page(fetcher, { previewOnly = false, currentUser } = {}) {
  const ids = ['upload-form', 'upload-dialog', 'file-input', 'upload-status', 'upload-error', 'upload-login',
    'dropzone', 'submit-upload', 'upload-result', 'upload-preview-head', 'upload-preview-body', 'drop-title',
    'drop-subtitle', 'upload-result-meta', 'upload-preview-scroll', 'upload-empty-preview', 'upload-truncated',
    'new-task-button', 'upload-header-options', 'upload-header-yes', 'upload-header-no',
    'confirm-upload-header', 'upload-header-status', 'upload-preview-note'];
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
    async chooseHeader(hasHeader) {
      elements.get('upload-header-yes').checked = hasHeader;
      elements.get('upload-header-no').checked = !hasHeader;
      await elements.get(hasHeader ? 'upload-header-yes' : 'upload-header-no').emit('change');
    },
    confirmHeader: () => elements.get('confirm-upload-header').emit('click'),
    drop: files => elements.get('dropzone').emit('drop', { dataTransfer: { files } }),
    close: () => elements.get('upload-dialog').emit('close'),
    expire: () => { for (const fn of [...timers.values()]) fn(); } };
}
const csv = (name = 'students.csv') => new File(['学号,姓名\n001,张三\n'], name, { type: 'text/csv' });

test('picker submits native FormData with current Bearer token and renders generic columns as text', async () => {
  let sent;
  const malicious = '<img src=x onerror=alert(1)>';
  const ui = page(async (url, options) => { sent = { url, options };
    return response(201, result({ filename: malicious + '.csv', preview_rows: [['学号', '姓名'], ['001', malicious]] })); });
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
  assert(ui.get('upload-status').textContent.includes('已保存'));
});

test('dragged file is submitted and multiple dropped files are rejected without choosing the first', async () => {
  const files = [];
  const ui = page(async (_, options) => { files.push(options.body.get('file').name); return response(201, result()); });
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
    const ui = page(async () => ++calls === 1 ? response(status, { detail }) : response(201, result()));
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
  resolve(response(201, result())); await first;
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
  resolve(response(201, result())); await pending;
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
  const fetcher = async () => { calls++; return response(201, result()); };
  const expired = page(fetcher, { currentUser: session => { throw new session.SessionExpiredError(); } });
  await expired.select(csv()); await expired.submit();
  assert.equal(expired.get('upload-login').hidden, false);
  const demo = page(fetcher, { previewOnly: true });
  await demo.select(csv()); await demo.submit();
  assert.equal(demo.get('submit-upload').disabled, true);
  assert.equal(demo.identityChecks(), 0); assert.equal(calls, 0);
});

test('401 and mismatched or malformed responses never display a preview', async () => {
  for (const reply of [response(401, {}), response(201, result({ owner_id: 2 })), response(200, {}), response(201, result({ persisted: false }))]) {
    const ui = page(async () => reply);
    await ui.select(csv()); await ui.submit();
    assert.equal(ui.get('upload-result').hidden, true);
    assert.equal(ui.get('upload-error').hidden, false);
  }
});

test('truncation and an empty preview are shown without claiming valid headers or processing tasks', async () => {
  const ui = page(async () => response(201, result({ preview_truncated: true })));
  await ui.select(csv()); await ui.submit();
  assert.equal(ui.get('upload-truncated').hidden, false);
  const empty = page(async () => response(201, result({ preview_rows: [] })));
  await empty.select(csv()); await empty.submit();
  assert.equal(empty.get('upload-preview-scroll').hidden, true);
  assert.equal(empty.get('upload-empty-preview').hidden, false);
  assert.equal(empty.get('upload-result').hidden, false);
});

test('header choice uses authenticated PUT and applies the response only after saving', async () => {
  const calls = [];
  const data = result();
  const originalRows = JSON.stringify(data.preview_rows);
  const ui = page(async (url, options) => { calls.push({ url, options });
    return uploadAndHeader(data)(url, options); });
  await ui.select(csv()); await ui.submit();
  assert.equal(ui.get('upload-header-options').disabled, false);
  assert.equal(ui.get('upload-header-yes').checked, false);
  assert.equal(ui.get('upload-header-no').checked, false);
  assert.equal(ui.get('confirm-upload-header').disabled, true);
  await ui.confirmHeader();
  assert.equal(ui.get('upload-preview-body').children.length, 2);
  await ui.chooseHeader(true);
  assert.equal(ui.get('confirm-upload-header').disabled, false);
  assert.equal(ui.get('upload-preview-head').children[0].children[1].textContent, '第1列');
  await ui.confirmHeader();
  assert.equal(ui.get('upload-preview-head').children[0].children[1].textContent, '学号');
  assert.equal(ui.get('upload-preview-body').children.length, 1);
  assert.equal(ui.get('upload-preview-body').children[0].children[1].textContent, '001');
  assert.equal(ui.get('confirm-upload-header').disabled, true);
  assert(ui.get('upload-header-status').textContent.includes('表头设置已保存'));
  assert.equal(calls[1].url, 'http://127.0.0.1:8000/api/files/' + data.file_id + '/header');
  assert.equal(calls[1].options.headers.Authorization, 'Bearer access-after-refresh');
  assert.equal(calls[1].options.headers['Content-Type'], 'application/json');
  assert.equal(calls[1].options.body, JSON.stringify({ has_header: true }));
  await ui.chooseHeader(false);
  assert.equal(ui.get('upload-preview-body').children.length, 1);
  await ui.confirmHeader();
  assert.equal(ui.get('upload-preview-head').children[0].children[1].textContent, '第1列');
  assert.equal(ui.get('upload-preview-body').children.length, 2);
  assert.equal(ui.get('upload-preview-body').children[0].children[1].textContent, '学号');
  assert.equal(JSON.stringify(data.preview_rows), originalRows);
  assert.deepEqual(calls.map(call => call.options.method), ['POST', 'PUT', 'PUT']);
  assert.equal(JSON.parse(calls[2].options.body).has_header, false);
});

test('a new file or a new upload clears the previous header confirmation', async () => {
  const ui = page(uploadAndHeader());
  await ui.select(csv()); await ui.submit();
  await ui.chooseHeader(true); await ui.confirmHeader();
  await ui.select(csv('other.csv'));
  assert.equal(ui.get('upload-result').hidden, true);
  assert.equal(ui.get('upload-header-yes').checked, false);
  assert.equal(ui.get('upload-header-no').checked, false);
  assert.equal(ui.get('confirm-upload-header').disabled, true);
  await ui.submit();
  assert.equal(ui.get('upload-preview-body').children.length, 2);
  await ui.chooseHeader(true); await ui.confirmHeader();
  await ui.submit();
  assert.equal(ui.get('upload-header-yes').checked, false);
  assert.equal(ui.get('upload-preview-head').children[0].children[1].textContent, '第1列');
  assert.equal(ui.get('upload-preview-body').children.length, 2);
});

test('empty previews cannot confirm headers and a header-only preview shows the empty-data message', async () => {
  const empty = page(async () => response(201, result({ preview_rows: [] })));
  await empty.select(csv()); await empty.submit();
  assert.equal(empty.get('upload-header-options').disabled, true);
  assert.equal(empty.get('confirm-upload-header').disabled, true);
  await empty.confirmHeader();
  assert(empty.get('upload-header-status').textContent.includes('没有可预览'));
  const headerOnly = page(uploadAndHeader(result({ preview_rows: [['学号', '姓名']] })));
  await headerOnly.select(csv()); await headerOnly.submit();
  await headerOnly.chooseHeader(true); await headerOnly.confirmHeader();
  assert.equal(headerOnly.get('upload-preview-body').children.length, 0);
  assert.equal(headerOnly.get('upload-empty-preview').hidden, false);
  assert(headerOnly.get('upload-empty-preview').textContent.includes('只有表头'));
});

test('server header names are rendered as bounded plain text rather than copied from the preview', async () => {
  const malicious = '<img src=x onerror=alert(1)>';
  const name = '完整列名' + '🙂'.repeat(220);
  const ui = page(async (_, options) => options.method === 'PUT'
    ? response(200, headerResult(true, { columns: [{ index: 0, name: malicious }, { index: 1, name }] }))
    : response(201, result({ preview_rows: [[malicious, '预览截断列名'], ['001', 'Alice', 'extra']] })));
  await ui.select(csv()); await ui.submit();
  await ui.chooseHeader(true); await ui.confirmHeader();
  const headings = ui.get('upload-preview-head').children[0].children;
  assert.equal(headings[1].textContent, malicious);
  assert(headings[2].textContent.startsWith('完整列名'));
  assert.equal(Array.from(headings[2].textContent).length, 200);
  assert(headings[3].textContent.includes('第3列未在确认列中'));
  assert.equal(ui.get('upload-truncated').hidden, false);
});

test('a blank first record supports data preview without inventing a header', async () => {
  const ui = page(uploadAndHeader(result({ preview_rows: [[], ['001', 'Alice']] })));
  await ui.select(csv()); await ui.submit();
  assert.equal(ui.get('upload-header-yes').disabled, true);
  assert.equal(ui.get('upload-header-options').disabled, false);
  await ui.chooseHeader(false); await ui.confirmHeader();
  assert.equal(ui.get('upload-preview-body').children.length, 2);
  assert.equal(ui.get('upload-preview-head').children[0].children[1].textContent, '第1列');
});

test('saving disables duplicate requests and file changes until the server acknowledges the result', async () => {
  let resolve, puts = 0;
  const ui = page(async (_, options) => options.method === 'PUT'
    ? (++puts, new Promise(done => { resolve = done; })) : response(201, result()));
  await ui.select(csv()); await ui.submit(); await ui.chooseHeader(true);
  const saving = ui.confirmHeader(); await settle();
  assert.equal(ui.get('file-input').disabled, true);
  assert.equal(ui.get('submit-upload').disabled, true);
  assert.equal(ui.get('upload-header-options').disabled, true);
  assert.equal(ui.get('confirm-upload-header').disabled, true);
  assert.equal(ui.get('upload-preview-body').children.length, 2);
  assert(ui.get('upload-header-status').textContent.includes('正在保存'));
  await ui.confirmHeader(); assert.equal(puts, 1);
  resolve(response(200, headerResult())); await saving;
  assert.equal(ui.get('file-input').disabled, false);
  assert.equal(ui.get('upload-preview-body').children.length, 1);
  assert(ui.get('upload-header-status').textContent.includes('表头设置已保存'));
});

test('header validation failure preserves the preview and allows saving a corrected choice', async () => {
  let puts = 0;
  const ui = page(async (_, options) => options.method === 'PUT'
    ? (++puts === 1 ? response(422, { detail: '第 2 列的列名不能为空' }) : response(200, headerResult(false)))
    : response(201, result({ preview_rows: [['学号', ''], ['001', '张三']] })));
  await ui.select(csv()); await ui.submit(); await ui.chooseHeader(true); await ui.confirmHeader();
  assert.equal(ui.get('upload-error').textContent, '第 2 列的列名不能为空');
  assert.equal(ui.get('upload-preview-head').children[0].children[1].textContent, '第1列');
  assert.equal(ui.get('upload-preview-body').children.length, 2);
  assert.equal(ui.get('confirm-upload-header').disabled, false);
  assert(!ui.get('upload-header-status').textContent.includes('已保存'));
  await ui.chooseHeader(false); await ui.confirmHeader();
  assert.equal(puts, 2);
  assert(ui.get('upload-header-status').textContent.includes('表头设置已保存'));
});

test('a lost save response preserves the last acknowledged preview and permits reconfirming it', async () => {
  let puts = 0, uploads = 0;
  const ui = page(async (_, options) => {
    if (options.method !== 'PUT') { uploads++; return response(201, result()); }
    if (++puts === 2) throw new TypeError('response lost');
    return response(200, headerResult(true));
  });
  await ui.select(csv()); await ui.submit(); await ui.chooseHeader(true); await ui.confirmHeader();
  await ui.chooseHeader(false); await ui.confirmHeader(); await settle();
  assert.equal(puts, 2);
  assert.equal(ui.get('upload-preview-body').children.length, 1);
  assert(ui.get('upload-header-status').textContent.includes('保存结果未确认'));
  assert(ui.get('upload-status').textContent.includes('保存结果待确认'));
  await ui.chooseHeader(true);
  assert.equal(ui.get('confirm-upload-header').disabled, false);
  await ui.confirmHeader();
  assert.equal(puts, 3); assert.equal(uploads, 1);
  assert(ui.get('upload-header-status').textContent.includes('表头设置已保存'));
});

test('closing during a save aborts waiting and never applies a late success response', async () => {
  let resolve, signal;
  const ui = page(async (_, options) => options.method === 'PUT'
    ? (signal = options.signal, new Promise(done => { resolve = done; })) : response(201, result()));
  await ui.select(csv()); await ui.submit(); await ui.chooseHeader(true);
  const saving = ui.confirmHeader(); await settle(); await ui.close();
  assert.equal(signal.aborted, true);
  resolve(response(200, headerResult())); await saving;
  assert.equal(ui.get('upload-preview-body').children.length, 2);
  assert(!ui.get('upload-header-status').textContent.includes('已保存'));
  assert(ui.get('upload-header-status').textContent.includes('未确认'));
  assert.equal(ui.get('confirm-upload-header').disabled, false);
});

test('a timed-out header save retains the selection and requires an explicit retry', async () => {
  const ui = page(async (_, options) => options.method === 'PUT'
    ? new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted'))))
    : response(201, result()));
  await ui.select(csv()); await ui.submit(); await ui.chooseHeader(true);
  const saving = ui.confirmHeader(); await settle(); ui.expire(); await saving;
  assert(ui.get('upload-error').textContent.includes('保存请求超时'));
  assert.equal(ui.get('upload-header-yes').checked, true);
  assert.equal(ui.get('confirm-upload-header').disabled, false);
  assert.equal(ui.timers.size, 0);
});

test('an account change before saving prevents the PUT request', async () => {
  let checks = 0, puts = 0;
  const ui = page(async (_, options) => { if (options.method === 'PUT') puts++; return response(201, result()); },
    { currentUser: () => ({ id: ++checks === 1 ? 1 : 2 }) });
  await ui.select(csv()); await ui.submit(); await ui.chooseHeader(true); await ui.confirmHeader();
  assert.equal(puts, 0);
  assert.equal(ui.get('upload-login').hidden, false);
  assert.equal(ui.get('upload-preview-body').children.length, 2);
});

test('rejected or malformed header responses never claim a successful save', async () => {
  const replies = [response(401, {}), response(503, { detail: '原文件暂时无法读取，请稍后重试' }),
    response(500, { detail: 'Internal Server Error' }), response(200, headerResult(true, { file_id: 'b'.repeat(32) })),
    response(200, headerResult(false)), response(200, { columns: [] })];
  for (const reply of replies) {
    const ui = page(async (_, options) => options.method === 'PUT' ? reply : response(201, result()));
    await ui.select(csv()); await ui.submit(); await ui.chooseHeader(true); await ui.confirmHeader();
    assert.equal(ui.get('upload-preview-body').children.length, 2);
    assert.equal(ui.get('upload-error').hidden, false);
    assert(!ui.get('upload-header-status').textContent.includes('已保存'));
  }
});

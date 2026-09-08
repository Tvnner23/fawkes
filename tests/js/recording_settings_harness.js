const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

class Element {
  constructor(tagName = 'div') {
    this.tagName = tagName; this.children = []; this.listeners = {}; this.value = '';
    this.textContent = ''; this.className = ''; this.dataset = {}; this.style = {};
    this.disabled = false;
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: name => { if (!this.classList.contains(name)) this.className += ' ' + name; },
      remove: name => { this.className = this.className.split(/\s+/).filter(item => item !== name).join(' '); },
      toggle: (name, force) => { if (force === undefined) force = !this.classList.contains(name);
        if (force) this.classList.add(name); else this.classList.remove(name); },
    };
  }
  append(...items) { for (let item of items) { if (typeof item === 'string') item = Object.assign(new Element('#text'), { textContent: item }); item.parent = this; this.children.push(item); } }
  appendChild(item) { this.append(item); return item; }
  removeChild(item) { this.children.splice(this.children.indexOf(item), 1); item.parent = null; }
  remove() { if (this.parent) this.parent.removeChild(this); }
  get firstChild() { return this.children[0] || null; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this[name] = String(value); }
  matches(selector) { return selector.startsWith('.') ? this.classList.contains(selector.slice(1)) : this.tagName === selector; }
  querySelector(selector) { return descendants(this).find(node => node.matches(selector)) || null; }
  querySelectorAll(selector) { return descendants(this).filter(node => node.matches(selector)); }
  closest() { return null; }
  focus() {}
}
function descendants(node) { return node.children.flatMap(child => [child, ...descendants(child)]); }
function textOf(node) { return [node.textContent, ...node.children.map(textOf)].join(' '); }
const nodes = {};
const getNode = selector => nodes[selector] || (nodes[selector] = new Element());
const timers = new Map(); let timerId = 0;
global.window = {
  location: { origin: 'http://recording.invalid', search: '' },
  setTimeout(callback, delay) { timers.set(++timerId, { callback, delay }); return timerId; },
  clearTimeout(id) { timers.delete(id); },
  setInterval() { return 1; }, clearInterval() {},
};
Object.defineProperty(window, 'localStorage', { get() { throw new Error('Private client attempted browser storage'); } });
Object.defineProperty(window, 'sessionStorage', { get() { throw new Error('Private client attempted browser storage'); } });
global.document = {
  querySelector(selector) { return selector === '#developer-build' ? null : getNode(selector); },
  querySelectorAll() { return []; },
  createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag),
  createTextNode: text => Object.assign(new Element('#text'), { textContent: text }),
};
global.Event = class { constructor(type) { this.type = type; } };
const names = ['archive_recording', 'memory_learning', 'personal_diagnostics', 'research_records', 'library_retention', 'social_archive'];
let policy = { schema_version: 1, instance_id: 'fixture', revision: 0, mode: 'retained',
  categories: Object.fromEntries([...names.map(name => [name, true]), ['sensor_retention', false]]) };
function effective(requested = null) {
  const mode = policy.mode === 'private' || !policy.categories.archive_recording || requested === 'private' ? 'private' : 'retained';
  return { policy_revision: policy.revision, configured_mode: policy.mode, mode,
    categories: Object.fromEntries(Object.entries(policy.categories).map(([key, value]) => [key, mode === 'private' ? false : value])) };
}
const requests = []; let settingFailure = null; let badRead = false; let pauseChat = false; let releaseChat;
function response(status, value) { return { status, ok: status >= 200 && status < 300, async json() { return JSON.parse(JSON.stringify(value)); } }; }
global.fetch = async (url, options) => {
  const payload = options.body ? JSON.parse(options.body) : null;
  requests.push({ url, payload, options });
  if (url === '/api/chat') return response(200, { phoenix: { name: 'Fawkes' }, conversation: { conversation_id: 'retained-start' }, messages: [], recording: effective() });
  if (url === '/api/preferences/recording' && !payload) return response(200, badRead ? { mode: 'retained' } : policy);
  if (url === '/api/preferences/recording') {
    assert.strictEqual(options.headers['X-Fawkes-CSRF-Token'], 'fixture-csrf');
    if (settingFailure === 'conflict') {
      policy = { ...policy, revision: policy.revision + 1, mode: 'private' }; settingFailure = null;
      return response(409, { error: { code: 'recording_policy_conflict', message: 'Changed elsewhere.' } });
    }
    assert.strictEqual(payload.expected_revision, policy.revision);
    policy = { ...policy, ...payload.changes, categories: { ...policy.categories, ...(payload.changes.categories || {}) }, revision: policy.revision + 1 };
    if (settingFailure === 'durability') {
      settingFailure = null;
      return response(503, { error: { code: 'recording_policy_commit_unconfirmed', message: 'Durability was not confirmed.' } });
    }
    return response(200, policy);
  }
  if (url === '/api/chat/messages') {
    const recording = effective(payload.recording_mode);
    const value = { recording, conversation_id: recording.mode === 'private' ? 'private-fixture' : 'retained-next',
      message: { message_id: 'reply-' + requests.length, role: 'assistant', content: 'Synthetic response.' }, events: [] };
    if (pauseChat) { pauseChat = false; return new Promise(resolve => { releaseChat = () => resolve(response(201, value)); }); }
    return response(201, value);
  }
  if (url === '/api/preferences/sounds') return response(200, { preferences: { master_enabled: false, events: {}, volume: 0 }, events: [] });
  throw new Error('Unexpected endpoint ' + url);
};
const tick = () => new Promise(resolve => setImmediate(resolve));
const posts = () => requests.filter(item => item.url === '/api/preferences/recording' && item.payload).length;
const reads = () => requests.filter(item => item.url === '/api/preferences/recording' && !item.payload).length;
const chatRequests = () => requests.filter(item => item.url === '/api/chat/messages');
(async () => {
  const source = fs.readFileSync('src/app/static/app.js', 'utf8');
  vm.runInThisContext(source, { filename: 'actual-app.js' });
  await tick();
  vm.runInThisContext("csrfToken = 'fixture-csrf'");
  await loadRecordingSettings();
  const settings = getNode('#recording-settings');
  const toggles = descendants(settings).filter(node => node.tagName === 'input');
  assert.strictEqual(toggles.filter(node => !node.disabled).length, 6);
  assert.strictEqual(toggles.filter(node => node.disabled && !node.checked).length, 1);
  assert(textOf(settings).includes('do not delete existing history'));
  assert(textOf(settings).includes('Metadata-only authority and provider receipts'));
  await saveRecordingSetting({ mode: 'private' });
  assert(getNode('#recording-status').textContent.includes('Next interaction: private'));
  assert(getNode('#recording-status').textContent.includes('Last confirmed interaction: retained'));

  pauseChat = true;
  const privateRequest = submitChatTurn('PRIVATE TURN MARKER');
  await tick();
  const slow = [...timers.values()].find(timer => timer.delay === 12000);
  assert(slow); slow.callback();
  assert(!getNode('#status').textContent.includes('preserved'));
  assert(getNode('#status').textContent.includes('not yet been confirmed'));
  releaseChat(); await privateRequest;
  assert.strictEqual(chatRequests().at(-1).payload.recording_mode, 'private');
  assert(getNode('#recording-status').textContent.includes('Last confirmed interaction: private'));

  getNode('#message').value = 'PRIVATE DRAFT MARKER';
  getNode('#message').listeners.input();
  await saveRecordingSetting({ mode: 'retained' });
  assert(getNode('#recording-status').textContent.includes('This draft stays private'));
  await getNode('#composer').listeners.submit({ preventDefault() {} });
  assert.strictEqual(chatRequests().at(-1).payload.recording_mode, 'private');

  getNode('#message').value = 'New retained request';
  getNode('#message').listeners.input();
  await getNode('#composer').listeners.submit({ preventDefault() {} });
  const retained = chatRequests().at(-1).payload;
  assert.strictEqual(retained.recording_mode, 'retained');
  assert.strictEqual(retained.conversation_id, null);
  assert(!JSON.stringify(retained).includes('PRIVATE'));
  assert(!('history' in retained));
  assert(!textOf(getNode('#messages')).includes('PRIVATE'));
  assert(getNode('#recording-status').textContent.includes('Last confirmed interaction: retained'));

  const privateClarification = new Element('article');
  renderRetrievalClarification(privateClarification, {
    clarification_required: true, decision_id: 'private-decision', resulting_retrieval_plan_identity: 'private-plan',
    ambiguity_sets: [{ clarification_required: true, ambiguity_set_id: 'private-set', choices: [
      { choice_id: 'first', label: 'First conversation' }, { choice_id: 'second', label: 'Second conversation' },
    ] }],
  }, { originatingResponseMessageId: 'private-response', originalQuery: 'PRIVATE ORIGINAL QUERY', recordingMode: 'private' });
  await privateClarification.querySelector('.clarification-choice').listeners.click();
  const privateFollowup = chatRequests().at(-1).payload;
  assert.strictEqual(policy.mode, 'retained');
  assert.strictEqual(privateFollowup.recording_mode, 'private');
  assert.strictEqual(privateFollowup.retrieval_clarification.original_query, 'PRIVATE ORIGINAL QUERY');
  assert(getNode('#recording-status').textContent.includes('Last confirmed interaction: private'));

  let beforePosts = posts(); let beforeReads = reads();
  settingFailure = 'conflict';
  await saveRecordingSetting({ mode: 'retained' });
  assert.strictEqual(posts(), beforePosts + 1);
  assert.strictEqual(reads(), beforeReads + 1);
  assert(textOf(settings).includes('changed elsewhere'));
  assert.strictEqual(settings.querySelector('select').value, policy.mode);

  beforePosts = posts(); beforeReads = reads(); settingFailure = 'durability';
  await saveRecordingSetting({ categories: { memory_learning: false } });
  assert.strictEqual(posts(), beforePosts + 1);
  assert.strictEqual(reads(), beforeReads + 1);
  assert(textOf(settings).includes('Saving was not confirmed'));
  assert(textOf(settings).includes('no write was retried'));
  assert.strictEqual(policy.categories.archive_recording, true);
  assert.strictEqual(policy.categories.memory_learning, false);

  badRead = true;
  await loadRecordingSettings();
  assert(!settings.querySelector('select'));
  assert(textOf(settings).includes('No mode was assumed'));
  beforePosts = posts();
  await saveRecordingSetting({ mode: 'retained' });
  assert.strictEqual(posts(), beforePosts);
  assert(!source.includes('localStorage') && !source.includes('sessionStorage'));
  console.log('recording-settings-client-ok: six categories, CSRF/CAS, private draft/transition/follow-up, delay and ambiguous-save handling');
})().catch(error => { console.error(error); process.exitCode = 1; });

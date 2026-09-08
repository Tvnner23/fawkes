// Execute the actual normal-app script with synthetic DOM + transport only.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
class Element {
  constructor(tagName = 'div') {
    this.tagName = tagName; this.children = []; this.listeners = {}; this.value = '';
    this.textContent = ''; this.className = ''; this.dataset = {}; this.style = {}; this.disabled = false;
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: name => { if (!this.classList.contains(name)) this.className += ' ' + name; },
      remove: name => { this.className = this.className.split(/\s+/).filter(item => item !== name).join(' '); },
      toggle: (name, force) => { if (force === undefined) force = !this.classList.contains(name);
        if (force) this.classList.add(name); else this.classList.remove(name); },
    };
  }
  append(...items) { for (let item of items) {
    if (typeof item === 'string') item = Object.assign(new Element('#text'), { textContent: item });
    item.parent = this; this.children.push(item);
    if (this.tagName === 'select' && this.children.length === 1) this.value = item.value;
  } }
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
global.window = { location: { origin: 'http://workshop.invalid', search: '' },
  setTimeout() { return 1; }, clearTimeout() {}, setInterval() { return 1; }, clearInterval() {} };
for (const key of ['localStorage', 'sessionStorage']) Object.defineProperty(window, key, {
  get() { throw new Error('Workshop attempted browser persistence'); } });
global.document = {
  querySelector(selector) { return selector === '#developer-build' ? null : getNode(selector); },
  querySelectorAll() { return []; }, createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag),
  createTextNode: text => Object.assign(new Element('#text'), { textContent: text }),
};
global.Event = class { constructor(type) { this.type = type; } };
const categories = { archive_recording: true, memory_learning: true, personal_diagnostics: true,
  research_records: true, library_retention: true, social_archive: true, sensor_retention: false };
let configured = { schema_version: 1, instance_id: 'fixture', revision: 0, mode: 'retained', categories };
const records = []; const history = []; const requests = []; let failure = null;
const copy = value => JSON.parse(JSON.stringify(value));
function envelope(record = null) {
  return { schema_version: 'fawkes.workshop.http.v1', instance_id: 'fixture', creates_authority: false,
    execution_allowed: false, recording_policy: configured, ...(record ? { proposal: record,
      history: history.filter(item => item.proposal_id === record.proposal_id) } : { proposals: records }) };
}
function response(status, data) { return { status, ok: status >= 200 && status < 300, async json() { return copy(data); } }; }
global.fetch = async (url, options = {}) => {
  const payload = options.body ? JSON.parse(options.body) : null;
  requests.push({ url, payload, options });
  if (url === '/api/chat') return response(200, { phoenix: { name: 'Fixture' }, conversation: { conversation_id: 'test' }, messages: [] });
  if (url === '/api/preferences/sounds') return response(200, { preferences: { master_enabled: false, events: {}, volume: 0 }, events: [] });
  if (url === '/api/preferences/recording') return response(200, configured);
  assert(url.startsWith('/api/development/workshop'), 'Unexpected non-Workshop operation: ' + url);
  if (url.startsWith('/api/development/workshop/development-source/')) return response(200, {
    ...envelope(), development_source: { source_proposal_id: 'existing-source', instance_id: 'fixture',
      expected_source_sha256: 'd'.repeat(64), observation: 'Existing source observation', origin: 'development_experience',
      producer_identity: 'not_recorded_by_legacy_owner', source_record: { proposal_id: 'existing-source', observation: 'Original source' } } });
  if (payload) {
    assert.strictEqual(options.headers['X-Fawkes-CSRF-Token'], 'fixture-csrf');
    if (failure) {
      const status = failure; failure = null;
      records[0] = { ...records[0], revision: records[0].revision + 1 };
      return response(status, { error: { code: status === 409 ? 'workshop_revision_conflict' : 'workshop_unavailable', message: 'Synthetic uncertain or stale write.' } });
    }
    if (url === '/api/development/workshop/intake-development') {
      assert.deepStrictEqual(Object.keys(payload).sort(), ['classification', 'expected_source_sha256', 'source_proposal_id']);
      assert.strictEqual(payload.source_proposal_id, 'existing-source');
      assert.strictEqual(payload.expected_source_sha256, 'd'.repeat(64));
      const record = { ...copy(records[0]), proposal_id: 'workshop-' + 'e'.repeat(32), revision: 1,
        observation: 'Existing source observation', status: 'investigating', investigations: [], evaluations: [], reviews: [], verdict: 'inconclusive' };
      records.push(record); history.push(copy(record)); return response(201, envelope(record));
    }
    if (url === '/api/development/workshop') {
      const record = { ...payload, proposal_id: 'workshop-' + 'a'.repeat(32), instance_id: 'fixture', revision: 1,
        record_sha256: 'b'.repeat(64), status: 'investigating', applied_revision: null, outcome: 'not_applied',
        investigations: [], acceptance_contracts: [], evaluations: [], assurance: [], reviews: [], design: null, verdict: 'inconclusive' };
      records.push(record); history.push(copy(record)); return response(201, envelope(record));
    }
    const record = records[0]; assert.strictEqual(payload.expected_revision, record.revision);
    assert(!('instance_id' in payload) && !('actor' in payload) && !('authority' in payload));
    record.revision += 1;
    if (payload.action === 'investigate') record.investigations.push(payload.payload);
    if (payload.action === 'submit') record.status = 'submitted';
    if (url.endsWith('/review')) { record.status = 'approved_for_future_action'; record.reviews.push({ decision: payload.decision }); }
    history.push(copy(record)); return response(200, envelope(record));
  }
  if (url === '/api/development/workshop') return response(200, envelope());
  const revision = new URL(url, window.location.origin).searchParams.get('revision');
  const id = new URL(url, window.location.origin).pathname.split('/')[4];
  return response(200, envelope(revision ? history.find(item => item.revision === Number(revision) && item.proposal_id === id)
    : records.find(item => item.proposal_id === id)));
};
const tick = () => new Promise(resolve => setImmediate(resolve));
const posts = () => requests.filter(item => item.payload);
const formWith = (host, name) => descendants(host).filter(node => node.tagName === 'form')
  .find(form => descendants(form).some(node => node.name === name));
function fill(form, values) { for (const [key, value] of Object.entries(values)) {
  const control = descendants(form).find(node => node.name === key); assert(control, key); control.value = value;
} }
async function submit(form) { await form.listeners.submit({ preventDefault() {} }); await tick(); }
(async () => {
  vm.runInThisContext(fs.readFileSync('src/app/static/app.js', 'utf8'), { filename: 'actual-app.js' });
  await tick(); vm.runInThisContext("csrfToken = 'fixture-csrf'; developerSection = 'workshop'");
  await loadWorkshop();
  const content = getNode('#developer-content'); const detail = getNode('#detail-content');
  assert(textOf(content).includes('Nothing here runs a provider'));
  assert(textOf(content).includes('rider input—not a Phoenix-generated experiment'));
  const create = formWith(content, 'observation');
  fill(create, { classification: 'ui_defect', observation: '<img src=x onerror=alert(1)> synthetic failure',
    interpretation: 'Unverified hypothesis', uncertainty: 'No real rider evidence', evidence: '' });
  await submit(create);
  assert.strictEqual(posts().length, 1);
  assert.strictEqual(posts()[0].payload.evidence.length, 0);
  assert(textOf(detail).includes('<img src=x onerror=alert(1)>'));
  assert(!descendants(detail).some(node => node.tagName === 'img' || node.tagName === 'script'));
  assert(textOf(detail).includes('No isolated evaluation imported'));
  let investigation = formWith(detail, 'investigation');
  fill(investigation, { investigation: 'Read fixture source', knowledge: 'Label mismatch', hypothesis: 'Wrong key', evidence: '', cost: 'unknown' });
  await submit(investigation);
  assert.strictEqual(posts().at(-1).payload.expected_revision, 1);
  assert.strictEqual(posts().at(-1).payload.action, 'investigate');
  assert.deepStrictEqual(posts().at(-1).payload.payload.cost, { description: 'unknown', basis: 'rider_reported' });
  const importForm = formWith(detail, 'reference');
  fill(importForm, { reference: 'worker-report-fixture | ' + 'c'.repeat(64) });
  await submit(importForm);
  assert.strictEqual(posts().at(-1).payload.action, 'record_evaluation');
  assert.deepStrictEqual(Object.keys(posts().at(-1).payload.payload), ['report_reference']);
  assert.strictEqual(posts().at(-1).payload.payload.report_reference.instance_id, 'fixture');
  for (const failureStatus of [409, 503]) {
    investigation = formWith(detail, 'investigation');
    fill(investigation, { investigation: 'Read source', knowledge: 'Observed', hypothesis: 'Uncertain', evidence: '', cost: '{}' });
    failure = failureStatus; const count = posts().length;
    await submit(investigation);
    assert.strictEqual(posts().length, count + 1);
    assert(textOf(investigation).includes('No request was retried'));
    assert(investigation.querySelector('button').disabled);
    await submit(investigation); assert.strictEqual(posts().length, count + 1);
    await openWorkshop(records[0].proposal_id);
  }
  await openWorkshop(records[0].proposal_id, 1);
  assert(!descendants(detail).some(node => node.tagName === 'form'));
  assert(textOf(detail).includes('read-only'));
  configured = { ...configured, revision: 1, categories: { ...categories, personal_diagnostics: false } };
  await loadWorkshop(); await openWorkshop(records[0].proposal_id);
  assert(formWith(content, 'observation').querySelector('button').disabled);
  assert(!descendants(detail).some(node => node.tagName === 'form'));
  configured = { ...configured, revision: 2, categories };
  records[0].status = 'submitted'; await loadWorkshop(); await openWorkshop(records[0].proposal_id);
  const review = formWith(detail, 'decision'); assert(review);
  fill(review, { decision: 'approve', note: 'Future proposal only, not an execution grant.' });
  await submit(review);
  assert(posts().at(-1).url.endsWith('/review'));
  assert.strictEqual(posts().at(-1).payload.decision, 'approve');
  assert.strictEqual(records[0].outcome, 'not_applied');
  assert(!descendants(detail).some(node => node.tagName === 'form'));
  await openWorkshopIntake('existing-source');
  assert(textOf(detail).includes('not recorded by legacy owner'));
  assert(textOf(detail).includes('does not claim investigation, acceptance or evaluation was completed'));
  const intake = formWith(detail, 'classification'); assert(intake);
  fill(intake, { classification: 'development_observation' }); await submit(intake);
  assert(posts().at(-1).url.endsWith('/intake-development'));
  assert.strictEqual(records[1].investigations.length, 0);
  assert.strictEqual(records[1].verdict, 'inconclusive');
  assert(posts().every(item => !/\/(run|apply|export|campaign|provider)(\/|$)/.test(item.url)));
  // Real rendering must not reuse candidate A's advice for B or a new contract.
  const candidate = { candidate_id: 'candidate-a', revision: 'rev-a', sha256: 'a'.repeat(64), instance_id: 'fixture', reality_scope: 'isolated' };
  const contract = { contract_version: 1, contract_sha256: 'c'.repeat(64), rider_expectation: 'Synthetic current expectation' };
  const reportReference = { report_id: 'worker-report-eval-a', record_sha256: 'd'.repeat(64), instance_id: 'fixture' };
  const evaluation = { ...contract, candidate, report_reference: reportReference, results: [], limitations: [] };
  const advice = { ...contract, candidate, evaluation_report: reportReference,
    authority_check: 'CURRENT AUTHORITY SENTINEL', rider_impact: 'CURRENT IMPACT SENTINEL',
    recommendation: 'CURRENT ADVICE SENTINEL', disagreements: ['CURRENT DISAGREEMENT SENTINEL'] };
  Object.assign(records[0], { acceptance_contracts: [contract], evaluations: [evaluation], assurance: [advice] });
  const visibleText = () => detail.children.filter(node => node.tagName !== 'details').map(textOf).join(' ');
  await openWorkshop(records[0].proposal_id);
  assert(visibleText().includes('CURRENT ADVICE SENTINEL'));
  for (const change of ['candidate', 'contract', 'evaluation']) {
    records[0].acceptance_contracts = [copy(contract)]; records[0].evaluations = [copy(evaluation)];
    if (change === 'candidate') records[0].evaluations[0].candidate.revision = 'rev-b';
    if (change === 'contract') records[0].acceptance_contracts[0].contract_sha256 = 'f'.repeat(64);
    if (change === 'evaluation') records[0].evaluations[0].report_reference.record_sha256 = 'f'.repeat(64);
    await openWorkshop(records[0].proposal_id);
    assert(!visibleText().includes('CURRENT ADVICE SENTINEL'), change);
    assert(!visibleText().includes('CURRENT DISAGREEMENT SENTINEL'), change);
    assert(visibleText().includes('Historical Assurance'), change);
    assert(textOf(detail).includes('CURRENT ADVICE SENTINEL'), 'Historical advice must remain expandable');
  }
  process.stdout.write('workshop-client-ok\n');
})().catch(error => { console.error(error); process.exitCode = 1; });

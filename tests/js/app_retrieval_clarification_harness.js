const fs = require('fs');
const vm = require('vm');

class ClassList {
  constructor(owner, names = []) { this.owner = owner; this.names = new Set(names); }
  add(name) { this.names.add(name); this.sync(); }
  remove(name) { this.names.delete(name); this.sync(); }
  contains(name) { return this.names.has(name); }
  toggle(name, force) { if (force === undefined) force = !this.names.has(name); if (force) this.names.add(name); else this.names.delete(name); this.sync(); }
  sync() { this.owner._className = [...this.names].join(' '); }
}
class Element {
  constructor(classes = [], tagName = '') {
    this.tagName = tagName; this._className = classes.join(' '); this.classList = new ClassList(this, classes);
    this.listeners = {}; this.children = []; this.dataset = {}; this.style = {}; this.value = ''; this.textContent = '';
    this.disabled = false; this.files = []; this.parent = null;
  }
  set className(value) { this._className = value; this.classList.names = new Set(String(value).split(/\s+/).filter(Boolean)); }
  get className() { return this._className; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  append(...items) { items.forEach(item => { if (item instanceof Element) item.parent = this; this.children.push(item); }); }
  removeChild(item) { this.children.splice(this.children.indexOf(item), 1); item.parent = null; }
  remove() { if (this.parent) this.parent.removeChild(this); }
  get firstChild() { return this.children[0] || null; }
  focus() { this.focused = true; }
  setAttribute(name, value) { this[name] = String(value); }
  getAttribute(name) { return this[name]; }
  all() { return this.children.reduce((out, child) => child instanceof Element ? [...out, child, ...child.all()] : out, []); }
  matches(selector) {
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    if (selector === '#send') return this === nodes['#send'];
    return false;
  }
  querySelector(selector) { return this.all().find(item => item.matches(selector)) || null; }
  querySelectorAll(selector) { return this.all().filter(item => item.matches(selector)); }
  closest(selector) { return this.matches(selector) ? this : null; }
}

const selectors = ['#messages','#composer','#message','#send','#status','#auth','#auth-form','#token','#connect','#auth-error',
  '#developer-content','#detail-panel','#detail-content','#phoenix-name','.app-nav','#developer-sections','#detail-close',
  '#chat-view','#developer-view','#settings-view','#library-view','#history-view','#attachments','#attachment-tray',
  '#sound-settings','#presence-settings','#library-content','#library-search-form','#library-query','#history-content',
  '#history-search-form','#history-query','#history-domain'];
const nodes = Object.fromEntries(selectors.map(key => [key, new Element()]));
nodes['#auth'].classList.add('hidden'); nodes['#detail-panel'].classList.add('hidden');
global.window = { location: { origin: 'http://fawkes.local:8787' }, setTimeout, clearTimeout, setInterval, clearInterval,
  matchMedia() { return { matches: false }; }, dispatchEvent() {}, localStorage: { getItem() { return 'token'; }, setItem() {} } };
global.document = { querySelector(key) { return nodes[key]; }, querySelectorAll() { return []; }, addEventListener() {},
  createElement(tag) { return new Element([], tag); }, createElementNS(ns, tag) { return new Element([], tag); } };
global.Event = class { constructor(type, options) { this.type = type; Object.assign(this, options); } };

const clarification = {
  clarification_required: true, decision_id: 'ambiguity-decision-secret', resulting_retrieval_plan_identity: 'plan-secret',
  ambiguity_sets: [{ ambiguity_set_id: 'ambiguity-secret', clarification_required: true, choices: [
    { choice_id: 'choice-secret-a', evidence_id: 'evidence-secret-a', label: 'networking discussion from Aug 28' },
    { choice_id: 'choice-secret-b', evidence_id: 'evidence-secret-b', label: 'LSUA planning discussion from Aug 29' },
  ] }],
};
const posts = [];
const feedbackPosts = [];
let rejectChoice = false;
let rejectFeedback = false;
global.fetch = async (url, options = {}) => {
  if (url === '/api/chat') return { status: 200, ok: true, async json() { return { phoenix: { name: 'Fawkes' },
    conversation: { conversation_id: 'conversation-1' }, messages: [{ message_id: 'assistant-old', role: 'assistant',
      content: 'Ordinary Chat remains available.', created_at: '2026-08-31T12:00:00+00:00',
      context_inspector_available: true }] }; } };
  if (url === '/api/chat/messages/assistant-old/context-inspector') return { status: 200, ok: true, async json() { return {
    schema_version: 1, composition_status: 'retrieved_context_used', response_message_id: 'assistant-old', context_receipt_id: 'receipt-secret',
    package_id: 'package-secret', allocation_policy_version: 'allocation-v1',
    purpose_profile: { purpose: 'response_model_context', profile_version: '1' },
    source_domains: { memory: 1, native_archive: 1 }, selected_evidence_ids: ['e1', 'e2'], omitted_evidence_ids: ['e3'],
    indicators: { contradiction_group_ids: ['c1'], ambiguity_set_ids: [], uncertain_source_count: 1 },
    warnings: [], exclusions: [{ reason: 'budget' }], transmission: { status: 'authorized', manifest_id: 'permit-secret' },
    replay: { flight_id: 'assistant-old', evidence_sha256: 'flight-secret' }, contains_source_bodies: false,
    authority: { creates_authority: false, retrieval_authority: false, transmission_authority: false }
  }; } };
  if (url.endsWith('/context-feedback')) {
    feedbackPosts.push(JSON.parse(options.body));
    if (rejectFeedback) return { status: 409, ok: false, async json() { return { error: {
      code: 'context_inspection_invalid', message: 'Context inspection evidence is inconsistent.' } }; } };
    return { status: 201, ok: true, async json() { return { feedback: { feedback_id: 'hidden-feedback-id',
      effect: 'observational_only_no_automatic_change', authority: { creates_authority: false } } }; } };
  }
  if (url === '/api/preferences/sounds') return { status: 200, ok: true, async json() { return { preferences: {
    master_enabled: false, volume: 0.5, events: {} }, events: [] }; } };
  if (url === '/api/chat/messages') {
    const payload = JSON.parse(options.body); posts.push(payload);
    await new Promise(resolve => setTimeout(resolve, 5));
    if (rejectChoice) return { status: 400, ok: false, async json() { return { error: { code: 'invalid_clarification',
      message: 'That clarification choice is stale or belongs to another turn.' } }; } };
    if (!payload.retrieval_clarification) return { status: 201, ok: true, async json() { return {
      user_message_created_at: '2026-08-31T12:01:00+00:00', message: { message_id: 'assistant-clarify', role: 'assistant',
        content: 'I found two conversations. Which one do you mean?', created_at: '2026-08-31T12:01:01+00:00' },
      retrieval_clarification: clarification, media: [], events: [] }; } };
    return { status: 201, ok: true, async json() { return { user_message_created_at: '2026-08-31T12:02:00+00:00',
      message: { message_id: 'assistant-answer', role: 'assistant', content: 'Here is the requested context.',
        created_at: '2026-08-31T12:02:01+00:00' }, retrieval_clarification: null, media: [], events: [] }; } };
  }
  throw new Error(`Unexpected request ${url}`);
};

const textOf = node => [node.textContent, ...node.children.map(child => child instanceof Element ? textOf(child) : String(child))].join(' ');
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

(async () => {
  vm.runInThisContext(fs.readFileSync('src/app/static/app.js', 'utf8'), { filename: 'app.js' });
  await tick();
  if (!textOf(nodes['#messages']).includes('Ordinary Chat remains available.')) throw new Error('Ordinary Chat rendering changed');
  const inspector = nodes['#messages'].querySelector('.context-inspector');
  if (!inspector || !textOf(inspector).includes('Why this context?')) throw new Error('Context Inspector was not rendered');
  if (textOf(inspector).includes('receipt-secret')) throw new Error('Inspector loaded internal evidence before rider opened it');
  inspector.open = true; await inspector.listeners.toggle();
  if (!textOf(inspector).includes('Retrieved context was used.') || !textOf(inspector).includes('memory (1)')
      || !textOf(inspector).includes('Final evidence authorization: authorized')) throw new Error('Body-free context evidence was not rendered usefully');
  const feedbackButtons = inspector.querySelectorAll('.context-feedback-choice');
  if (feedbackButtons.length !== 5) throw new Error('Context feedback controls were not rendered');
  const feedbackFirst = feedbackButtons[0].listeners.click(); const feedbackRepeat = feedbackButtons[0].listeners.click();
  await Promise.all([feedbackFirst, feedbackRepeat]);
  if (feedbackPosts.length !== 1) throw new Error(`Repeated context feedback was submitted (${feedbackPosts.length})`);
  const expectedFeedback = { feedback_type: 'context_helped', context_receipt_id: 'receipt-secret',
    package_id: 'package-secret', allocation_decision_sha256: null, transmission_manifest_id: 'permit-secret',
    replay_flight_id: 'assistant-old' };
  if (JSON.stringify(feedbackPosts[0]) !== JSON.stringify(expectedFeedback)) throw new Error('Context feedback linkage changed');
  if (!feedbackButtons.every(button => button.disabled) || !textOf(inspector).includes('changes nothing automatically')) throw new Error('Recorded feedback remained actionable or claimed an effect');
  rejectFeedback = true;
  const rejectedFeedback = new Element([], 'section');
  renderContextFeedback(rejectedFeedback, { response_message_id: 'feedback-reject', context_receipt_id: 'receipt-reject',
    package_id: 'package-reject', allocation: {}, transmission: {}, replay: null });
  const rejectedFeedbackButtons = rejectedFeedback.querySelectorAll('.context-feedback-choice');
  await rejectedFeedbackButtons[0].listeners.click();
  if (!textOf(rejectedFeedback).includes('Feedback was not recorded') || rejectedFeedbackButtons.some(button => button.disabled)) throw new Error('Rejected feedback did not fail truthfully and recoverably');
  nodes['#message'].value = 'Which conversation was that?';
  await nodes['#composer'].listeners.submit({ preventDefault() {} });
  const buttons = nodes['#messages'].querySelectorAll('.clarification-choice');
  if (buttons.length !== 2 || buttons.some(button => button.tagName !== 'button' || button.type !== 'button')) throw new Error('Accessible native choice buttons were not rendered');
  const riderText = textOf(nodes['#messages']);
  for (const secret of ['ambiguity-secret','choice-secret','evidence-secret','plan-secret']) {
    if (riderText.includes(secret)) throw new Error(`Internal ID leaked into rider UI: ${secret}`);
  }
  const firstClick = buttons[0].listeners.click();
  const repeatedClick = buttons[0].listeners.click();
  await Promise.all([firstClick, repeatedClick]);
  if (posts.length !== 2) throw new Error(`Repeated click submitted ${posts.length - 1} choice requests`);
  const submitted = posts[1].retrieval_clarification;
  const expected = { originating_response_message_id: 'assistant-clarify', decision_id: 'ambiguity-decision-secret',
    retrieval_plan_identity: 'plan-secret', ambiguity_set_id: 'ambiguity-secret', choice_id: 'choice-secret-a',
    original_query: 'Which conversation was that?' };
  if (JSON.stringify(submitted) !== JSON.stringify(expected)) throw new Error(`Wrong structured payload ${JSON.stringify(submitted)}`);
  if (!buttons.every(button => button.disabled) || buttons[0]['aria-pressed'] !== 'true') throw new Error('Consumed controls remained actionable');
  if (!textOf(nodes['#messages']).includes('Here is the requested context.')) throw new Error('Normal assistant response flow was not used');

  rejectChoice = true;
  const rejectedHost = new Element([], 'article');
  renderRetrievalClarification(rejectedHost, clarification, { originatingResponseMessageId: 'assistant-rejected', originalQuery: 'Again?' });
  const rejectedButtons = rejectedHost.querySelectorAll('.clarification-choice');
  await rejectedButtons[0].listeners.click();
  if (!textOf(rejectedHost).includes('no longer valid for this turn')) throw new Error('Stale choice failure was not truthful');
  if (!rejectedButtons.every(button => button.disabled)) throw new Error('Rejected stale controls remained actionable');

  const malformedHost = new Element([], 'article');
  renderRetrievalClarification(malformedHost, { clarification_required: true }, { originatingResponseMessageId: 'x', originalQuery: 'x' });
  if (malformedHost.querySelectorAll('.clarification-choice').length || !textOf(malformedHost).includes('unavailable')) throw new Error('Malformed clarification did not fail safely');
  console.log('client-retrieval-clarification-ok');
})().catch(error => { console.error(error); process.exit(1); });

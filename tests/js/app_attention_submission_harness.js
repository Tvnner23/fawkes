const fs = require('fs');
const vm = require('vm');

class ClassList {
  constructor() { this.values = new Set(); }
  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    if (force === undefined) force = !this.values.has(value);
    force ? this.values.add(value) : this.values.delete(value);
  }
}
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.listeners = {}; this.dataset = {};
    this.classList = new ClassList(); this.textContent = ''; this.value = '';
    this.disabled = false; this.files = [];
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  append(...children) { this.children.push(...children); }
  removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
  get firstChild() { return this.children[0] || null; }
  closest() { return null; }
  focus() {}
  scrollIntoView() {}
  setAttribute(name, value) { this[name] = value; }
  querySelector() { return null; }
  click() { if (this._click) this._click(); }
}
function descendants(node) {
  return node.children.reduce((all, child) => all.concat(child, descendants(child)), []);
}

const scenario = process.env.FAWKES_ATTENTION_SUBMISSION_SCENARIO || 'stale-submit';
const embedded = scenario.startsWith('embedded-') || scenario === 'cross-projection-concurrent';
const attentionId = `attention-browser-${scenario}`;
const selectors = [
  '#messages','#composer','#message','#send','#attachments','#attachment-tray','#status',
  '#auth','#auth-form','#token','#connect','#auth-error','#developer-content',
  '#developer-build','#detail-panel','#detail-content','#sound-settings',
  '#presence-settings','#library-content','#library-search-form','#library-query',
  '#history-content','#history-search-form','#history-query','#history-domain',
  '#phoenix-name','.app-nav','#developer-sections','#detail-close','#chat-view',
  '#developer-view','#settings-view','#library-view','#history-view',
];
const nodes = Object.fromEntries(selectors.map(selector => [selector, new Element()]));
nodes['#developer-build'].textContent = 'Build: test-build';
const developerButton = new Element('button');
developerButton.dataset.view = 'developer';
developerButton._click = () => nodes['.app-nav'].listeners.click({target: {closest: () => developerButton}});
const attentionTab = new Element('button'); attentionTab.dataset.section = 'attention';

global.window = {
  location: {origin: 'https://localhost:8791',
    search: embedded ? '?view=developer' : `?view=developer&section=attention&attention=${attentionId}`},
  localStorage: {getItem: () => null, setItem() {}},
  setTimeout, clearTimeout, dispatchEvent() {},
};
global.CustomEvent = class {};
global.Event = class {};
global.document = {
  querySelector(selector) {
    if (selector === '.app-nav [data-view="developer"]') return developerButton;
    return nodes[selector] || null;
  },
  querySelectorAll(selector) {
    if (selector === '#developer-sections [data-section]') return [attentionTab];
    if (selector === '.app-nav [data-view]') return [developerButton];
    return [];
  },
  getElementById(id) {
    return descendants(nodes['#developer-content']).find(item => item.id === id) || null;
  },
  createElement: tag => new Element(tag),
  createElementNS: (_namespace, tag) => new Element(tag),
  addEventListener() {},
};

const expiry = scenario === 'crossing-expiry'
  ? new Date(Date.now() + 120).toISOString()
  : new Date(Date.now() + 60_000).toISOString();
const pending = {
  attention_id: attentionId,
  campaign_id: `campaign-${scenario}`,
  invocation_id: `invocation-${scenario}`,
  decision_nonce: `nonce-${scenario}`,
  state: 'needs_tanner', consumer_state: 'live', actionable: true,
  blocked_action: 'run one harmless readiness action',
  why_required: 'browser approval transport readiness',
  requested_authority: 'one harmless action', resources: [], reversible: true,
  protocol_binding: {
    rider_id: 'tanner', recipient_sha256: `recipient-${scenario}`,
    approval_binding_kind: 'independent_review_provider',
    approval_binding_sha256: `approval-${scenario}`,
    review_package_id: `package-${scenario}`,
    review_package_record_sha256: `package-record-${scenario}`,
    reviewer_worker_id: `reviewer-${scenario}`,
    reviewer_identity_sha256: `reviewer-digest-${scenario}`,
    reviewer_invocation_id: `invocation-${scenario}`,
    candidate_snapshot_id: `snapshot-${scenario}`,
    candidate_record_sha256: `candidate-record-${scenario}`,
    mutation_digest_sha256: `mutation-${scenario}`,
    exact_change_evidence_sha256: `exact-change-${scenario}`,
    authorized_scope_sha256: `scope-${scenario}`,
    method: 'item/commandExecution/requestApproval', item_id: `item-${scenario}`,
    approved_action_sha256: `action-${scenario}`,
  },
  protocol_binding_sha256: `binding-${scenario}`, expires_at: expiry,
  authority_binding_sha256: `authority-binding-${scenario}`,
};
let decisionPosts = 0;
let releaseDecision = null;
const campaignProjection = {campaign_id:pending.campaign_id,status:'needs_tanner',iteration:1,
  maximum_iterations:1,objective:'synthetic browser decision',current_stage:'needs_tanner',
  builder:{worker_id:'builder'},reviewer:{worker_id:'reviewer'},activity:[],
  needs_tanner:{reason:'synthetic_browser_test'}};
function exactAuthorityBinding() {
  return {attention_id:attentionId,campaign_id:pending.campaign_id,
    invocation_id:pending.invocation_id,rider_id:pending.protocol_binding.rider_id,
    recipient_sha256:pending.protocol_binding.recipient_sha256,
    approval_binding_kind:pending.protocol_binding.approval_binding_kind,
    approval_binding_sha256:pending.protocol_binding.approval_binding_sha256,
    review_package_id:pending.protocol_binding.review_package_id,
    review_package_record_sha256:pending.protocol_binding.review_package_record_sha256,
    reviewer_worker_id:pending.protocol_binding.reviewer_worker_id,
    reviewer_identity_sha256:pending.protocol_binding.reviewer_identity_sha256,
    reviewer_invocation_id:pending.protocol_binding.reviewer_invocation_id,
    candidate_snapshot_id:pending.protocol_binding.candidate_snapshot_id,
    candidate_record_sha256:pending.protocol_binding.candidate_record_sha256,
    mutation_digest_sha256:pending.protocol_binding.mutation_digest_sha256,
    exact_change_evidence_sha256:pending.protocol_binding.exact_change_evidence_sha256,
    authorized_scope_sha256:pending.protocol_binding.authorized_scope_sha256,
    method:pending.protocol_binding.method,item_id:pending.protocol_binding.item_id,
    action_digest:pending.protocol_binding.approved_action_sha256,
    protocol_binding_sha256:pending.protocol_binding_sha256,
    expires_at:pending.expires_at,decision_nonce:pending.decision_nonce};
}
function exactDecision(submitted) {
  const decision={attention_id:attentionId,campaign_id:pending.campaign_id,
    invocation_id:pending.invocation_id,choice:submitted.choice,
    decision_id:`decision-${scenario}`,lifecycle_state:'recorded_pending_consumption',
    protocol_binding_sha256:pending.protocol_binding_sha256,
    // Real canonical HTTP encoding sorts keys independently of the UI's order.
    authority_binding:Object.fromEntries(Object.entries(exactAuthorityBinding()).reverse()),
    authority_binding_sha256:pending.authority_binding_sha256,
    creates_continuing_authority:false,record_sha256:`decision-record-${scenario}`};
  if(['decision-substitution','failure-decision-substitution'].includes(scenario))decision.authority_binding.candidate_snapshot_id='snapshot-neighbor';
  if(['decision-omission','failure-decision-omission'].includes(scenario))delete decision.authority_binding.reviewer_invocation_id;
  if(['decision-inner-neighbor','failure-decision-inner-neighbor'].includes(scenario))decision.authority_binding.attention_id='attention-neighbor';
  if(['decision-extra-binding','failure-decision-extra-binding'].includes(scenario))decision.authority_binding.unexpected='neighbor';
  if(['decision-binding-digest','failure-decision-binding-digest'].includes(scenario))decision.authority_binding_sha256='authority-binding-neighbor';
  return decision;
}
global.fetch = async (path, options = {}) => {
  path = String(path); let status = 200; let data = {};
  if (path === '/api/chat') data = {phoenix:{name:'Fawkes'},conversation:{conversation_id:'c'},messages:[]};
  else if (path === '/api/status') data = {build:{release_id:'test-build'}};
  else if (path === '/api/development/dashboard') data = {};
  else if (path === '/api/development/codex-campaigns') data = {campaigns:embedded?[{live_activity:campaignProjection}]:[]};
  else if (path === '/api/development/attention') data = {attention:[pending]};
  else if (path.includes('/decision')) {
    decisionPosts += 1;
    const submitted = JSON.parse(options.body);
    if (scenario === 'embedded-concurrent' || scenario === 'cross-projection-concurrent') await new Promise(resolve => { releaseDecision=resolve; });
    if (scenario.startsWith('failure-decision-')) {
      status = 409;
      data = {error:{code:'synthetic_failure',message:'synthetic failed submission'},
        attention:{...pending,state:'approved_once',actionable:false,
          approval_outcome:'recorded_pending_consumption',decision_id:`decision-${scenario}`},
        decision:exactDecision(submitted),creates_authority:false,
        creates_continuing_authority:false};
    } else if (scenario === 'stale-submit' || scenario === 'embedded-stale') {
      status = 400;
      data = {error:{code:'invalid_attention_decision',message:'attention request is stale'},
        attention:{...pending,state:'expired',actionable:false,approval_outcome:'expired',decision_id:null},
        decision:null,creates_authority:false,creates_continuing_authority:false};
    } else {
      const returnedAttention=scenario==='response-substitution'
        ? {...pending,state:'approved_once',decision_id:`decision-${scenario}`,
          protocol_binding:{...pending.protocol_binding,candidate_snapshot_id:'snapshot-neighbor'}}
        : {...pending,state:'approved_once',decision_id:`decision-${scenario}`};
      data = {attention:returnedAttention,
        decision:exactDecision(submitted),
        creates_authority:false};
    }
  } else if (path.includes(`/api/development/attention/${attentionId}`)) {
    const crossed = scenario === 'crossing-expiry' && Date.now() >= Date.parse(expiry);
    data = {attention: crossed
      ? {...pending,state:'expired',actionable:false,approval_outcome:'expired',decision_id:null}
      : pending, decision:null};
  } else { status = 404; data = {error:{message:'Not found.'}}; }
  return {status,ok:status<400,json:async()=>data};
};

  require('../../src/app/static/attention-binding.js');
  window.FawkesAttentionBinding = globalThis.FawkesAttentionBinding;
vm.runInThisContext(fs.readFileSync('src/app/static/app.js','utf8'), {filename:'app.js'});

function textAndButtons() {
  const all = descendants(nodes['#developer-content']);
  return {all, text: all.map(item => item.textContent).join('\n'),
    decisions: all.filter(item => item.tagName === 'button'
      && /Approve Once|Deny|Cancel Campaign/.test(item.textContent))};
}
setTimeout(async () => {
  if (embedded) {
    vm.runInThisContext("developerSection='campaigns';renderDeveloperSection();");
    const first=textAndButtons();
    const approve=first.all.find(item=>item.tagName==='button'&&item.textContent==='Approve Once');
    const deny=first.all.find(item=>item.tagName==='button'&&item.textContent==='Deny');
    if(!approve||!deny)throw Error('embedded decision controls were not rendered');
    if(scenario==='cross-projection-concurrent'){
      const approved=approve.listeners.click();await Promise.resolve();
      global.__crossProjectionPending=pending;
      vm.runInThisContext(`developerSection='attention';requestedAttentionId=${JSON.stringify(attentionId)};exactAttentionState={attention:globalThis.__crossProjectionPending,decision:null};renderDeveloperSection();`);
      const exact=textAndButtons();
      const exactDeny=exact.all.find(item=>item.tagName==='button'&&item.textContent==='Deny');
      if(!exactDeny||!exactDeny.disabled)throw Error('exact projection did not observe shared submitting state');
      await exactDeny.listeners.click();
      if(decisionPosts!==1)throw Error(`cross-projection submission count ${decisionPosts}`);
      releaseDecision();await approved;
    }else if(scenario==='embedded-concurrent'){
      const approved=approve.listeners.click();await Promise.resolve();
      const denied=deny.listeners.click();await Promise.resolve();
      if(decisionPosts!==1)throw Error(`concurrent embedded submission count ${decisionPosts}`);
      releaseDecision();await approved;await denied;
    }else await approve.listeners.click();
    const final=textAndButtons();
    if(scenario==='embedded-stale'){
      if(!final.text.includes('Decision submission failed')||final.decisions.length!==0)
        throw Error(`embedded failure retained stale controls: ${final.text}`);
    }else if(scenario!=='cross-projection-concurrent'&&(!final.text.includes('Decision recorded')||final.decisions.length!==0))
      throw Error(`embedded success was not visibly terminal: ${final.text}`);
    if(decisionPosts!==1)throw Error(`unexpected embedded decision POST count ${decisionPosts}`);
    console.log(`attention-submission-ok ${scenario}`);process.exit(0);return;
  }
  if (scenario === 'crossing-expiry') {
    setTimeout(() => {
      const view = textAndButtons();
      if (!view.text.includes('already resolved') || view.decisions.length !== 0)
        throw Error(`crossed expiry left stale controls: ${view.text}`);
      if (decisionPosts !== 0) throw Error('expiry refresh submitted a decision');
      console.log('attention-submission-ok crossing-expiry');
      process.exit(0);
    }, 300);
    return;
  }
  const first = textAndButtons();
  const approve = first.all.find(item => item.tagName === 'button'
    && item.textContent === 'Approve Once');
  if (!approve) throw Error('Approve Once control was not rendered');
  await approve.listeners.click();
  const final = textAndButtons();
  if (scenario.startsWith('failure-decision-')) {
    const retained = vm.runInThisContext('exactAttentionState.decision');
    if (retained !== null) throw Error('mismatched failure decision was retained');
    if (!final.text.includes('Decision submission failed') || final.decisions.some(item=>!item.disabled))
      throw Error(`mismatched failure lifecycle remained actionable: ${final.text}`);
  } else if (scenario === 'stale-submit') {
    if (!final.text.includes('Decision submission failed')
        || !final.text.includes('invalid_attention_decision (400): attention request is stale')
        || !final.text.includes('already resolved') || final.decisions.length !== 0)
      throw Error(`failed submission did not visibly resolve: ${final.text}`);
  } else if (['response-substitution','decision-substitution','decision-omission',
      'decision-inner-neighbor','decision-extra-binding','decision-binding-digest'].includes(scenario)) {
    if (!final.text.includes('Decision submission failed') || final.decisions.some(item=>!item.disabled))
      throw Error(`substituted success response remained actionable: ${final.text}`);
  } else if (!final.text.includes('Decision recorded')
      || !final.text.includes('already resolved') || final.decisions.length !== 0) {
    throw Error(`successful submission did not visibly resolve: ${final.text}`);
  }
  if (decisionPosts !== 1) throw Error(`unexpected decision POST count ${decisionPosts}`);
  console.log(`attention-submission-ok ${scenario}`);
  process.exit(0);
}, 50);

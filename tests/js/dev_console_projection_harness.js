'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const moduleBox = {exports: {}};
const sandbox = {
  module: moduleBox,
  exports: moduleBox.exports,
  URL,
  Date,
  AbortController,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
};
sandbox.globalThis = sandbox;
vm.runInNewContext(
  fs.readFileSync('src/app/static/dev-console/console.js', 'utf8'),
  sandbox,
  {filename: 'dev-console/console.js'},
);
const consoleApi = moduleBox.exports;

const {
  parseIdleSeconds,
  classifyProjectionState,
  previewContextLabel,
  campaignObservation,
  activityHeading,
  campaignStatusLabel,
  isHorizontalSwipe,
  safeAttentionHref,
  normalizePayloads,
  normalizeRepositoryResponse,
  campaignGraphModel,
  campaignGraphStages,
  selectCampaign,
  architectureObservation,
  normalizeJobsResponse,
  normalizeRoadmapResponse,
  managedFeedObservation,
  ConsoleNavigation,
} = consoleApi;

for (const [name, value] of Object.entries({
  parseIdleSeconds,
  classifyProjectionState,
  previewContextLabel,
  campaignObservation,
  activityHeading,
  campaignStatusLabel,
  isHorizontalSwipe,
  safeAttentionHref,
  normalizePayloads,
  normalizeRepositoryResponse,
  campaignGraphModel,
  campaignGraphStages,
  selectCampaign,
  architectureObservation,
  normalizeJobsResponse,
  normalizeRoadmapResponse,
  managedFeedObservation,
  ConsoleNavigation,
})) {
  assert.ok(value, `missing testable export ${name}`);
}

// The inactivity policy is bounded even when configuration is hostile.
assert.strictEqual(parseIdleSeconds(undefined), 60);
assert.strictEqual(parseIdleSeconds('75'), 75);
assert.strictEqual(parseIdleSeconds('0'), 15);
assert.strictEqual(parseIdleSeconds('9999'), 600);
assert.strictEqual(parseIdleSeconds('not-a-number', 90), 90);

const observed = 1_000_000;
assert.strictEqual(classifyProjectionState({
  mode: 'sample', currentSuccess: true, previousSuccess: true,
  nowMs: observed, observedAtMs: observed,
}), 'sample');
assert.strictEqual(classifyProjectionState({
  currentSuccess: true, previousSuccess: true,
  nowMs: observed, observedAtMs: observed,
}), 'live');
assert.strictEqual(classifyProjectionState({
  currentSuccess: false, previousSuccess: true,
  nowMs: observed + 31_000, observedAtMs: observed,
}), 'stale');
assert.strictEqual(classifyProjectionState({
  currentSuccess: true, previousSuccess: true, buildMismatch: true,
  nowMs: observed, observedAtMs: observed,
}), 'stale');
assert.strictEqual(classifyProjectionState({
  currentSuccess: false, previousSuccess: false, disconnected: true,
  nowMs: observed, observedAtMs: 0,
}), 'disconnected');
assert.strictEqual(classifyProjectionState({
  currentSuccess: true, previousSuccess: false, malformed: true,
  nowMs: observed, observedAtMs: observed,
}), 'unavailable');
assert.strictEqual(previewContextLabel({mode: 'development_checkout'}), 'DEVELOPMENT PREVIEW');
assert.strictEqual(
  previewContextLabel({mode: 'development_checkout'}, `UNREVIEWED:${'a'.repeat(64)}`),
  `UNREVIEWED · ${'a'.repeat(12)}`,
);
assert.strictEqual(previewContextLabel({mode: 'approved_release'}), 'APPROVED RELEASE');
assert.strictEqual(campaignObservation([], 'live').label, 'EXECUTION UNAVAILABLE');
assert.strictEqual(campaignObservation([{status: 'succeeded', terminal: true}], 'live').label, 'NO OPEN CAMPAIGN RECORD');
assert.strictEqual(campaignObservation([{status: 'ready', terminal: false}], 'live').label, 'EXECUTION NOT OBSERVED');
assert.strictEqual(campaignObservation([{status: 'tanner_escalation', terminal: false}], 'live').label, 'EXECUTION NOT OBSERVED');
assert.strictEqual(campaignObservation([], 'stale').label, 'EXECUTION UNKNOWN');
assert.strictEqual(activityHeading('independent_review_retained'), 'Independent review recorded');
assert.strictEqual(campaignStatusLabel('failed_safe'), 'Stopped safely');

// Horizontal page gestures are distinct from vertical and code scrolling.
assert.strictEqual(isHorizontalSwipe(200, 100, 100, 106), true);
assert.strictEqual(isHorizontalSwipe(100, 100, 115, 220), false);
assert.strictEqual(isHorizontalSwipe(100, 100, 145, 100), false);
assert.strictEqual(isHorizontalSwipe(200, 100, 100, 106, {codeScroll: true}), false);

const attentionId = `attention-${'a'.repeat(64)}`;
const neighborId = `attention-${'b'.repeat(64)}`;
const attentionHref = `https://localhost:8791/?view=developer&section=attention&attention=${attentionId}`;
assert.strictEqual(
  safeAttentionHref(attentionHref, attentionId, 'https://localhost:8791/'),
  attentionHref,
);
assert.strictEqual(
  safeAttentionHref(attentionHref, neighborId, 'https://localhost:8791/'),
  '',
);
assert.strictEqual(
  safeAttentionHref(`javascript:alert(1)?attention=${attentionId}`, attentionId),
  '',
);
assert.strictEqual(
  safeAttentionHref(`${attentionHref}&attention=${attentionId}`, attentionId),
  '',
);
assert.strictEqual(
  safeAttentionHref(attentionHref, attentionId, 'https://127.0.0.1:8791/'),
  '',
);

const fixtureNow = Date.now();
const rawProjection = {
  current_campaign_id: 'campaign-safe',
  schema_version: 'fawkes.dev_console.read_only.v1',
  observed_at: new Date(fixtureNow).toISOString(),
  build: {
    mode: 'development_checkout', release_id: 'development-fixture',
    hidden_reasoning: 'never render this',
  },
  campaigns: [{
        campaign_id: 'campaign-safe',
        objective: 'One deterministic body-free fixture',
        status: 'needs_tanner',
        current_stage: 'review',
        iteration: 1,
        maximum_iterations: 2,
        builder: {worker_id: 'worker-safe'},
        reviewer: {worker_id: 'reviewer-safe'},
        activity: [{
          event_id: 'event-safe', kind: 'independent_review_retained',
          created_at: '2026-09-07T12:00:00+00:00',
          worker: {worker_id: 'reviewer-safe'},
          summary: {status: 'accepted', review_report_id: 'report-safe'},
          prompt_body: 'drop me',
        }],
        needs_tanner: {
          attention_id: attentionId,
          reason: 'Exact protected action needs Tanner.',
          detail_url: attentionHref,
        },
        managed_worker_activity: [{
          invocation_id: 'managed-fixture', worker_id: 'worker-safe',
          updated_at: new Date(fixtureNow).toISOString(), verified_at: new Date(fixtureNow).toISOString(), role: 'worker', state: 'running', events: [],
        }],
        creates_authority: false,
  }],
  attention: [{
      attention_id: attentionId,
      campaign_id: 'campaign-safe',
      invocation_id: 'wsl-review-fixture-1',
      state: 'needs_tanner',
      actionable: true,
      consumer_state: 'durably_resumable',
      blocked_action: 'Run one exact protected command',
      why_required: 'Tanner decision required',
      expires_at: new Date(fixtureNow + 60_000).toISOString(),
      detail_url: attentionHref,
      source_body: 'attention body',
      protocol_binding: {credential: 'must not render'},
  }],
  components: [
    {name: 'app_server', state: 'READY', credential: 'hidden'},
    {name: 'reviewer_launcher', state: 'IDLE', prompt: 'hidden'},
  ],
  jobs: [{
    job_id: 'campaign-safe', objective: 'Finish the Pi console', state: 'needs_you',
    recorded_status: 'needs_tanner', current_step: 'review',
    last_activity_at: '2026-09-07T12:00:00+00:00', accomplished: null,
    gained: null, next: 'Answer the exact pending request',
    successful: false, historical: false,
    worker: {worker_id: 'worker-safe'}, creates_authority: false,
  }],
  roadmap: {
    schema_version: 'fawkes.console.roadmap.v1',
    source_path: 'docs/phoenix/CANONICAL_ROADMAP.md', source_sha256: '4'.repeat(64),
    source_revision: '1'.repeat(40), coverage_complete: true,
    expected_phase_ids: Array.from({length: 40}, (_, number) => `phase-${number}`),
    phases: Array.from({length: 40}, (_, number) => ({
      id: `phase-${number}`, number, name: `Capability ${number}`,
      summary: `Lets Fawkes provide sourced capability number ${number} without claiming deployment.`,
      maturity: number === 9 ? 'implemented' : 'planned', source_status: 'canonical',
      source: 'docs/phoenix/CANONICAL_ROADMAP.md', group: number < 10 ? 'Foundations' : 'Roadmap',
      source_sha256: '4'.repeat(64), source_revision: '1'.repeat(40), source_bytes: 150000,
      source_excerpt: '',
      prerequisites: number === 1 ? ['phase-0'] : [], runtime_state: 'unknown',
    })),
    tracks: [{id: 'track-home', name: 'Dedicated home infrastructure',
      summary: 'Keeps Fawkes available when Tanner’s personal computer is shut down.',
      maturity: 'planned', source_status: 'recorded_requirement',
      source: 'Tanner console-completion roadmap addendum', group: 'Cross-cutting and product tracks',
      source_sha256: '5'.repeat(64), source_revision: '1'.repeat(40), source_bytes: 45,
      source_excerpt: 'Synthetic retained source: dedicated home availability.',
      mapped_component: 'infrastructure', prerequisites: [], runtime_state: 'unknown'}],
    creates_authority: false, creates_continuing_authority: false,
  },
  repository: {
    branch: 'fixture/console',
    head: '1'.repeat(40),
    comparison_base: '3'.repeat(40),
    selection_basis: 'head_commit_paths',
    status_summary: {
      dirty_paths: 2, tracked_changes: 1, untracked_paths: 1,
      staged_paths: 0, deleted_paths: 0,
    },
    files: [{
      path: 'src/app/server.py', mode: '100644', object_type: 'blob',
      object_id: '2'.repeat(40), head_change: 'M', worktree_state: 'modified',
      revision: '1'.repeat(40), review_status: 'not_projected',
      diff_excerpt: '@@ -1 +1 @@\n-old\n+new\n', private_body: 'hidden',
    }],
    creates_authority: false,
    creates_continuing_authority: false,
  },
  creates_authority: false,
  creates_continuing_authority: false,
};

const normalized = normalizePayloads(rawProjection, {
  baseUrl: 'https://localhost:8791/',
  expectedBuildId: 'development-fixture',
});
assert.strictEqual(normalized.ok, true);
assert.strictEqual(normalized.malformed, false);
assert.strictEqual(normalized.buildMismatch, false);
assert.strictEqual(normalized.build.release_id, 'development-fixture');
assert.strictEqual(normalized.campaigns.length, 1);
assert.strictEqual(normalized.campaigns[0].campaign_id, 'campaign-safe');
assert.strictEqual(normalized.attention.length, 1);
assert.strictEqual(normalized.components.length, 2);
assert.strictEqual(normalized.repository.files.length, 1);
assert.strictEqual(normalized.repository.files[0].path, 'src/app/server.py');
assert.strictEqual(normalized.jobs.length, 1);
assert.strictEqual(normalized.roadmap.phases.length, 40);
assert.strictEqual(normalizeJobsResponse(rawProjection.jobs).valid, true);
assert.strictEqual(normalizeRoadmapResponse(rawProjection.roadmap).valid, true);
assert.strictEqual(normalized.roadmap.tracks[0].source_sha256, '5'.repeat(64));
assert.strictEqual(normalizeRoadmapResponse({...rawProjection.roadmap,
  tracks: [{...rawProjection.roadmap.tracks[0], source_sha256: undefined}]}).valid, false);
assert.strictEqual(normalizeRoadmapResponse({...rawProjection.roadmap,
  expected_phase_ids: rawProjection.roadmap.expected_phase_ids.slice(1)}).valid, false);

const normalizedText = JSON.stringify(normalized);
for (const forbidden of [
  'never render this', 'wrapper source', 'private response', 'private chain',
  'top-level prompt', 'attention body', 'credential', 'hidden',
]) {
  assert.ok(!normalizedText.includes(forbidden), `unsafe value survived: ${forbidden}`);
}
assert.ok(normalizedText.includes(attentionHref), 'exact canonical Attention URL was lost');
assert.ok(!normalizedText.includes('private_body'), 'repository private field survived');

const graphCampaign = normalized.campaigns[0];
assert.strictEqual(selectCampaign([graphCampaign], '').campaign_id, 'campaign-safe');
const graphStages = campaignGraphStages(graphCampaign);
assert.strictEqual(graphStages.length, 6);
assert.strictEqual(graphStages.find(stage => stage.id === 'review').state, 'completed');
const graphModel = campaignGraphModel(graphCampaign);
assert.strictEqual(graphModel.edges.filter(edge => edge.established).length, 0);
assert.strictEqual(architectureObservation(normalized.components, 'clients', 'live'), 'READY');
assert.strictEqual(architectureObservation(normalized.components, 'workers', 'live'), 'IDLE');
assert.strictEqual(architectureObservation(normalized.components, 'application_git', 'live'), 'unavailable');

for (const repositoryMutation of [
  {...rawProjection.repository, creates_authority: true},
  {...rawProjection.repository, files: [{...rawProjection.repository.files[0], path: '../secret'}]},
  {...rawProjection.repository, files: [{...rawProjection.repository.files[0], revision: '3'.repeat(40)}]},
  {...rawProjection.repository, files: [{...rawProjection.repository.files[0], object_id: ''}]},
]) {
  assert.strictEqual(normalizeRepositoryResponse(repositoryMutation).valid, false);
}

const expiredProjection = normalizePayloads({
  ...rawProjection,
  attention: [{
    ...rawProjection.attention[0],
    expires_at: new Date(Date.now() - 1_000).toISOString(),
  }],
}, {baseUrl: 'https://localhost:8791/', expectedBuildId: 'development-fixture'});
assert.strictEqual(expiredProjection.ok, true);
assert.strictEqual(expiredProjection.attention[0].actionable, false);
assert.strictEqual(expiredProjection.attention[0].detail_url, '');

const substitutedAttention = normalizePayloads({
  ...rawProjection,
  attention: [{
    ...rawProjection.attention[0],
    detail_url: attentionHref.replace(attentionId, neighborId),
  }],
}, {baseUrl: 'https://localhost:8791/', expectedBuildId: 'development-fixture'});
assert.strictEqual(substitutedAttention.ok, true);
assert.strictEqual(substitutedAttention.attention[0].actionable, false);
assert.strictEqual(substitutedAttention.attention[0].detail_url, '');

const wrongBuild = normalizePayloads(rawProjection, {
  baseUrl: 'https://localhost:8791/', expectedBuildId: 'development-neighbor',
});
assert.strictEqual(wrongBuild.buildMismatch, true);

const malformed = normalizePayloads({
  ...rawProjection,
  campaigns: 'not-an-array',
});
assert.strictEqual(malformed.ok, false);
assert.strictEqual(malformed.malformed, true);

for (const mutation of [
  {actionable: false},
  {actionable: undefined},
  {consumer_state: 'unavailable'},
  {consumer_state: undefined},
  {invocation_id: ''},
  {invocation_id: 'invalid id with spaces'},
  {detail_url: attentionHref.replace('localhost', '127.0.0.1')},
]) {
  const projected = normalizePayloads({
    ...rawProjection,
    attention: [{...rawProjection.attention[0], ...mutation}],
  }, {baseUrl: 'https://localhost:8791/', expectedBuildId: 'development-fixture'});
  assert.strictEqual(projected.ok, true);
  assert.strictEqual(projected.attention[0].actionable, false);
  assert.strictEqual(projected.attention[0].detail_url, '');
}

// A deterministic scheduler proves inactivity return without wall-clock sleeps.
class Scheduler {
  constructor() { this.nextId = 0; this.pending = new Map(); }
  setTimeout(callback, milliseconds) {
    const id = ++this.nextId;
    this.pending.set(id, {callback, milliseconds});
    return id;
  }
  clearTimeout(id) { this.pending.delete(id); }
  runLast() {
    const entries = [...this.pending.entries()];
    assert.ok(entries.length > 0, 'idle timer was not armed');
    const [id, task] = entries[entries.length - 1];
    this.pending.delete(id);
    task.callback();
  }
  runEarliest() {
    const entries = [...this.pending.entries()];
    assert.ok(entries.length > 0, 'projection timer was not armed');
    entries.sort((left, right) => left[1].milliseconds - right[1].milliseconds);
    const [id, task] = entries[0];
    this.pending.delete(id);
    task.callback();
    return task.milliseconds;
  }
  runDelay(milliseconds) {
    const entry = [...this.pending.entries()].find(([, task]) => task.milliseconds === milliseconds);
    assert.ok(entry, `projection timer ${milliseconds}ms was not armed`);
    const [id, task] = entry;
    this.pending.delete(id);
    task.callback();
  }
}

class FakeClassList {
  constructor(node) { this.node = node; this.values = new Set(); }
  reset(value) {
    this.values = new Set(String(value || '').split(/\s+/).filter(Boolean));
  }
  add(...values) {
    values.forEach((value) => this.values.add(value));
    this.node._className = [...this.values].join(' ');
  }
  remove(...values) {
    values.forEach((value) => this.values.delete(value));
    this.node._className = [...this.values].join(' ');
  }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    const selected = force === undefined ? !this.values.has(value) : Boolean(force);
    if (selected) this.add(value); else this.remove(value);
    return selected;
  }
}

class FakeElement {
  constructor(tagName = 'div', id = '') {
    this.tagName = String(tagName).toLowerCase();
    this.id = id;
    this.children = [];
    this.parentNode = null;
    this.listeners = new Map();
    this.dataset = {};
    this.attributes = {};
    this.hidden = false;
    this.open = false;
    this.textContent = '';
    this.href = '';
    this.rel = '';
    this.content = '';
    this.scrollTop = 0;
    this._className = '';
    this.classList = new FakeClassList(this);
  }
  get className() { return this._className; }
  set className(value) {
    this._className = String(value || '');
    this.classList.reset(this._className);
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  replaceChildren(...children) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    this.append(...children);
  }
  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }
  async emit(name, event = {}) {
    const value = {
      target: this,
      preventDefault() { this.defaultPrevented = true; },
      ...event,
    };
    for (const callback of this.listeners.get(name) || []) await callback(value);
    return value;
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'class') this.className = value;
    if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase())] = String(value);
  }
  getBoundingClientRect() { return {left: 0, top: 0, width: 660, height: 400}; }
  removeAttribute(name) { delete this.attributes[name]; }
  matches(selector) {
    if (selector.includes(',')) return selector.split(',').some((part) => this.matches(part.trim()));
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    if (/^\.[a-z-]+$/.test(selector)) return this.classList.contains(selector.slice(1));
    if (/^[a-z]+\.[a-z-]+$/.test(selector)) {
      const [tag, name] = selector.split('.'); return this.tagName === tag && this.classList.contains(name);
    }
    if (/^\[data-[a-z-]+\]$/.test(selector)) return this.dataset[selector.slice(6, -1).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase())] !== undefined;
    if (selector === '.detail') return this.classList.contains('detail');
    if (selector === '.code-scroll') return this.classList.contains('code-scroll');
    if (selector === '.gesture-surface') return this.classList.contains('gesture-surface');
    if (selector === 'input' || selector === 'select' || selector === 'button') {
      return this.tagName === selector;
    }
    if (selector === '.console-page') return this.classList.contains('console-page');
    if (selector === 'details.console-card') {
      return this.tagName === 'details' && this.classList.contains('console-card');
    }
    if (selector === '[hidden]') return this.hidden;
    if (selector === '[data-page-link]') return this.dataset.pageLink !== undefined;
    if (selector === '[data-page-target]') return this.dataset.pageTarget !== undefined;
    if (selector === '[data-repository-path]') return this.dataset.repositoryPath !== undefined;
    if (selector === '[data-campaign-stage]') return this.dataset.campaignStage !== undefined;
    if (selector === '[data-architecture-node]') return this.dataset.architectureNode !== undefined;
    if (selector === '[data-architecture-mode]') return this.dataset.architectureMode !== undefined;
    if (selector === '[data-roadmap-id]') return this.dataset.roadmapId !== undefined;
    if (selector === '[data-copy-update-id]') return this.dataset.copyUpdateId !== undefined;
    if (selector === 'details.roadmap-group') return this.tagName === 'details' && this.classList.contains('roadmap-group');
    if (selector === '.prepared-update') return this.classList.contains('prepared-update');
    return false;
  }
  closest(selector) {
    let current = this;
    while (current) {
      if (current.matches(selector)) return current;
      current = current.parentNode;
    }
    return null;
  }
  querySelector(selector) {
    return descendantsOf(this).find((node) => node.matches(selector)) || null;
  }
  querySelectorAll(selector) {
    return descendantsOf(this).filter((node) => node.matches(selector));
  }
}

function descendantsOf(node) {
  const result = [];
  for (const child of node.children) {
    result.push(child, ...descendantsOf(child));
  }
  return result;
}

function textOf(node) {
  return [node.textContent, ...node.children.map(textOf)].join('\n');
}

function fakeDocument() {
  const byId = new Map();
  const make = (tag, id) => {
    const node = new FakeElement(tag, id);
    if (id) byId.set(id, node);
    return node;
  };
  const shell = make('main', 'dev-console');
  shell.dataset.idleSeconds = '60';
  const title = make('h1', 'page-title');
  const connection = make('span', 'connection-state');
  const lastSync = make('span', 'last-sync');
  const bridgeState = make('span', 'bridge-state');
  const previewContext = make('span', 'preview-context');
  const campaignState = make('span', 'campaign-state');
  const attentionState = make('span', 'attention-state');
  const updated = make('span', 'last-updated');
  const previous = make('button', 'previous-page');
  const next = make('button', 'next-page');
  const stack = make('section', 'page-stack');
  const summaryIntro = make('p', 'summary-intro');
  const attentionSlot = make('div', 'attention-slot');
  const activityFeed = make('div', 'activity-feed');
  const saveUpdate = make('button', 'save-console-update');
  const updateResult = make('p', 'update-result');
  const preparedUpdates = make('div', 'prepared-updates');
  const campaignSelector = make('select', 'campaign-selector');
  const campaignHistory = make('span', 'campaign-history-state');
  const campaignEmpty = make('div', 'campaign-empty');
  const campaignDashboard = make('div', 'campaign-dashboard');
  const campaignWidgets = make('div', 'campaign-widgets');
  const campaignGraph = make('svg', 'campaign-graph');
  const campaignDetail = make('section', 'campaign-detail');
  campaignDashboard.append(campaignWidgets, campaignGraph, campaignDetail);
  const repositoryWidgets = make('div', 'repository-widgets');
  const repositoryBrowser = make('div', 'repository-browser');
  const repositoryTree = make('nav', 'repository-tree');
  repositoryBrowser.append(repositoryTree);
  const repositoryDetailView = make('section', 'repository-detail-view');
  const repositoryBack = make('button', 'repository-back');
  const repositoryComparison = make('span', 'repository-comparison');
  const repositoryHeading = make('h3', 'repository-file-heading');
  const repositorySummary = make('p', 'repository-file-summary');
  const repositoryTechnical = make('details', 'repository-technical-details');
  const repositoryMetadata = make('div', 'repository-metadata');
  repositoryTechnical.append(repositoryMetadata);
  const repositoryDiff = make('pre', 'repository-diff');
  const repositoryEmpty = make('div', 'repository-empty');
  repositoryDetailView.append(repositoryBack, repositoryComparison, repositoryHeading,
    repositorySummary, repositoryTechnical, repositoryDiff);
  const architectureMap = make('svg', 'architecture-map');
  for (const nodeId of ['identity', 'archive', 'memory', 'library', 'clients', 'development',
    'attention', 'workers', 'application_git', 'embodiment']) {
    const node = make('g'); node.dataset.architectureNode = nodeId; architectureMap.append(node);
  }
  const architectureDetail = make('section', 'architecture-detail');
  const architectureReset = make('button', 'architecture-reset');
  const architectureOverview = make('div', 'architecture-overview');
  architectureOverview.append(architectureMap);
  const roadmapInventory = make('section', 'roadmap-inventory');
  const combinedView = make('section', 'combined-view');
  const combinedMap = make('svg', 'combined-map'); combinedMap.className = 'combined-map gesture-surface';
  const combinedSelect = make('select', 'combined-select');
  const combinedCoverage = make('p', 'combined-coverage');
  const combinedControls = make('div', 'combined-controls');
  for (const action of ['in', 'out', 'left', 'right', 'up', 'down', 'reset']) {
    const button = make('button'); button.dataset.combinedControl = action; combinedControls.append(button);
  }
  combinedView.append(combinedControls, combinedSelect, combinedCoverage, combinedMap);
  const roadmapFilter = make('input', 'roadmap-filter');
  const roadmapCoverage = make('p', 'roadmap-coverage');
  const roadmapGroups = make('div', 'roadmap-groups');
  roadmapInventory.append(roadmapFilter, roadmapCoverage, roadmapGroups);
  const architectureModes = ['current', 'roadmap', 'combined'].map((mode) => {
    const button = make('button'); button.dataset.architectureMode = mode; return button;
  });
  const pages = Array.from({length: 4}, (_, index) => {
    const page = make('section');
    page.className = 'console-page';
    page.dataset.page = String(index);
    page.hidden = index !== 0;
    return page;
  });
  pages[0].append(summaryIntro, attentionSlot, activityFeed, saveUpdate, updateResult, preparedUpdates);
  pages[1].append(campaignSelector, campaignHistory, campaignEmpty, campaignDashboard);
  pages[2].append(repositoryWidgets, repositoryBrowser, repositoryDetailView, repositoryEmpty);
  pages[3].append(architectureReset, ...architectureModes, architectureOverview,
    roadmapInventory, combinedView, architectureDetail);
  stack.append(...pages);
  const indicators = Array.from({length: 4}, (_, index) => {
    const button = make('button');
    button.dataset.pageTarget = String(index);
    return button;
  });
  shell.append(title, previewContext, connection, lastSync, bridgeState, campaignState, attentionState,
    previous, ...indicators, next, stack, updated);
  const buildMeta = make('meta');
  buildMeta.content = 'development-fixture';
  const contextMeta = make('meta');
  contextMeta.content = `UNREVIEWED:${'c'.repeat(64)}`;
  return {
    shell,
    pages,
    indicators,
    byId,
    buildMeta,
    document: {
      getElementById: (id) => byId.get(id) || null,
      querySelectorAll(selector) {
        if (selector === '.console-page') return pages;
        if (selector === '[data-page-target]') return indicators;
        if (selector === '[data-architecture-mode]') return architectureModes;
        return [];
      },
      querySelector(selector) {
        if (selector === 'meta[name="fawkes-build-id"]') return buildMeta;
        if (selector === 'meta[name="fawkes-console-context"]') return contextMeta;
        return null;
      },
      createElement: (tag) => make(tag),
      addEventListener: (...args) => shell.addEventListener(...args),
      removeEventListener: () => {},
      createElementNS: (_namespace, tag) => make(tag),
      createTextNode(value) {
        const node = make('#text');
        node.textContent = String(value);
        return node;
      },
    },
  };
}

const scheduler = new Scheduler();
const changes = [];
const navigation = new ConsoleNavigation({
  pageCount: 4,
  idleSeconds: 60,
  onChange: (page, reason) => changes.push({page, reason}),
  scheduler,
});
assert.strictEqual(navigation.page, 0);
navigation.go(2, 'indicator');
assert.strictEqual(navigation.page, 2);
navigation.next();
assert.strictEqual(navigation.page, 3);
navigation.next();
assert.strictEqual(navigation.page, 3);
navigation.previous();
assert.strictEqual(navigation.page, 2);
assert.strictEqual(navigation.swipe(200, 100, 100, 106), 3);
assert.strictEqual(navigation.page, 3);
assert.strictEqual(navigation.swipe(100, 100, 120, 220), 3);
assert.strictEqual(navigation.page, 3);

// Wheel rotation and a middle-click reset idle but cannot navigate or authorize.
const beforeInputPage = navigation.page;
navigation.activity('wheel');
navigation.activity('middle-click');
assert.strictEqual(navigation.page, beforeInputPage);
scheduler.runLast();
assert.strictEqual(navigation.page, 0);
assert.ok(changes.some(change => change.page === 0 && change.reason === 'idle'));
navigation.destroy();
assert.strictEqual(scheduler.pending.size, 0);

async function runDomFixture() {
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  const fixture = fakeDocument();
  const domScheduler = new Scheduler();
  let fetchCount = 0;
  const controller = consoleApi.boot({
    document: fixture.document,
    fetch: async () => { fetchCount += 1; throw new Error('sample mode must not fetch'); },
    scheduler: domScheduler,
    idleSeconds: 60,
    baseUrl: 'https://localhost:8791/',
    samplePayload: rawProjection,
    disableUpdateRefresh: true,
    pollIntervalMs: 0,
  });
  await settle();
  assert.strictEqual(fetchCount, 0);
  assert.strictEqual(fixture.shell.dataset.projectionState, 'sample');
  assert.strictEqual(fixture.byId.get('connection-state').textContent, 'SAMPLE Worker');
  assert.strictEqual(fixture.byId.get('preview-context').textContent, `UNREVIEWED · ${'c'.repeat(12)}`);
  assert.strictEqual(fixture.byId.get('campaign-state').textContent, 'SAMPLE CAMPAIGN DATA');
  assert.strictEqual(fixture.byId.get('attention-state').textContent, 'SAMPLE ATTENTION');
  const activityCards = descendantsOf(fixture.byId.get('activity-feed'))
    .filter((node) => node.matches('details.console-card'));
  assert.strictEqual(activityCards.length, 1);
  const rendered = textOf(fixture.shell);
  assert.ok(rendered.includes('Finish the Pi console'));
  assert.ok(rendered.includes('needs you'));
  assert.ok(!rendered.includes('wrapper source'));
  assert.ok(!rendered.includes('private response'));
  // Sample data is labeled and never offers a live decision deep link.
  assert.strictEqual(descendantsOf(fixture.byId.get('attention-slot'))
    .filter((node) => node.tagName === 'a').length, 0);

  await fixture.byId.get('next-page').emit('click');
  assert.strictEqual(controller.navigation.page, 1);
  assert.strictEqual(fixture.pages[0].hidden, true);
  assert.strictEqual(fixture.pages[1].hidden, false);
  await fixture.byId.get('page-stack').emit('pointerdown', {
    target: fixture.byId.get('page-stack'), clientX: 200, clientY: 100,
  });
  await fixture.byId.get('page-stack').emit('pointerup', {
    target: fixture.byId.get('page-stack'), clientX: 205, clientY: 220,
  });
  assert.strictEqual(controller.navigation.page, 1, 'vertical scrolling changed pages');
  await fixture.byId.get('page-stack').emit('pointerdown', {
    target: fixture.byId.get('page-stack'), clientX: 220, clientY: 100,
  });
  await fixture.byId.get('page-stack').emit('pointerup', {
    target: fixture.byId.get('page-stack'), clientX: 100, clientY: 105,
  });
  assert.strictEqual(controller.navigation.page, 2, 'horizontal swipe did not change page');
  const codeScroll = new FakeElement('pre');
  codeScroll.className = 'code-scroll';
  fixture.pages[2].appendChild(codeScroll);
  await fixture.byId.get('page-stack').emit('pointerdown', {
    target: codeScroll, clientX: 220, clientY: 100,
  });
  await fixture.byId.get('page-stack').emit('pointerup', {
    target: codeScroll, clientX: 100, clientY: 105,
  });
  assert.strictEqual(controller.navigation.page, 2, 'code scrolling changed pages');

  controller.navigation.go(0, 'fixture');
  await fixture.shell.emit('click', {target: activityCards[0]});
  const middle = await fixture.shell.emit('auxclick', {target: fixture.shell, button: 1});
  assert.strictEqual(middle.defaultPrevented, true);
  assert.strictEqual(activityCards[0].open, true, 'wheel click did not expand selection');
  await fixture.shell.emit('wheel', {target: fixture.shell});
  assert.strictEqual(controller.navigation.page, 0, 'wheel rotation navigated pages');
  controller.navigation.go(3, 'fixture');
  domScheduler.runLast();
  assert.strictEqual(controller.navigation.page, 0, 'inactivity did not return to summary');
  controller.stop();

  // Live data uses GET-only same-origin reads and may expose only the exact
  // canonical Attention URL. A later failure retains data but suppresses it.
  const liveFixture = fakeDocument();
  let failReads = false;
  const readCalls = [];
  let liveNow = fixtureNow;
  const projectionScheduler = new Scheduler();
  let projectionPayload = rawProjection;
  const fetchProjection = async (path, options) => {
    readCalls.push({path, options});
    if (failReads) throw new Error('fixture disconnect');
    return {ok: true, status: 200, json: async () => projectionPayload};
  };
  const liveController = consoleApi.boot({
    document: liveFixture.document,
    fetch: fetchProjection,
    scheduler: new Scheduler(),
    projectionScheduler,
    now: () => liveNow,
    baseUrl: 'https://localhost:8791/',
    pollIntervalMs: 0,
    disableUpdateRefresh: true,
  });
  await settle();
  assert.strictEqual(liveFixture.shell.dataset.projectionState, 'live');
  assert.strictEqual(liveFixture.byId.get('connection-state').textContent, '◉ Live');
  assert.strictEqual(liveFixture.byId.get('campaign-state').textContent, 'EXECUTION NOT OBSERVED');
  assert.strictEqual(liveFixture.byId.get('attention-state').textContent, 'ACTION REQUIRED');
  assert.deepStrictEqual(
    [...new Set(readCalls.map((call) => call.path))].sort(),
    ['/api/development/dev-console'],
  );
  assert.strictEqual(readCalls.length, 1, 'compact projection must use one request');
  assert.ok(readCalls.every((call) => call.options.method === 'GET'));
  assert.ok(readCalls.every((call) => call.options.credentials === 'same-origin'));
  const links = descendantsOf(liveFixture.byId.get('attention-slot'))
    .filter((node) => node.tagName === 'a');
  assert.strictEqual(links.length, 1);
  assert.strictEqual(links[0].href, attentionHref);
  assert.ok(textOf(liveFixture.byId.get('campaign-graph')).includes('Review'));
  assert.ok(descendantsOf(liveFixture.byId.get('campaign-graph'))
    .some(node => node.attributes.class === 'graph-edge reference-edge'));
  assert.ok(textOf(liveFixture.byId.get('architecture-detail')).includes('REFERENCE SYSTEM COMPONENT'));
  assert.ok(textOf(liveFixture.byId.get('architecture-detail')).includes('Reference maturity is not runtime health'));
  const gitStep = descendantsOf(liveFixture.byId.get('campaign-graph'))
    .find(node => node.dataset.campaignStage === 'git');
  await liveFixture.byId.get('campaign-graph').emit('click', {target: gitStep});
  assert.ok(textOf(liveFixture.byId.get('campaign-detail')).includes('Git'));
  const repositoryFile = descendantsOf(liveFixture.byId.get('repository-tree'))
    .find(node => node.dataset.repositoryPath === 'src/app/server.py');
  liveFixture.byId.get('repository-tree').scrollTop = 33;
  await liveFixture.byId.get('repository-tree').emit('click', {target: repositoryFile});
  assert.strictEqual(liveFixture.byId.get('repository-browser').hidden, true);
  assert.strictEqual(liveFixture.byId.get('repository-detail-view').hidden, false);
  assert.ok(textOf(liveFixture.byId.get('repository-detail-view')).includes('src/app/server.py'));
  assert.ok(textOf(liveFixture.byId.get('repository-detail-view')).includes('CONNECTED · CURRENT READ-ONLY DATA'));
  await liveFixture.byId.get('repository-back').emit('click');
  assert.strictEqual(liveFixture.byId.get('repository-browser').hidden, false);
  assert.strictEqual(liveFixture.byId.get('repository-tree').scrollTop, 33);
  const workersNode = descendantsOf(liveFixture.byId.get('architecture-map'))
    .find(node => node.dataset.architectureNode === 'workers');
  await liveFixture.byId.get('architecture-map').emit('click', {target: workersNode});
  assert.ok(textOf(liveFixture.byId.get('architecture-detail')).includes('Workers and Reviewers'));
  const roadmapMode = fixture => descendantsOf(fixture.shell)
    .find(node => node.dataset.architectureMode === 'roadmap');
  await roadmapMode(liveFixture).emit('click');
  assert.strictEqual(liveFixture.byId.get('architecture-overview').hidden, true);
  assert.strictEqual(liveFixture.byId.get('roadmap-inventory').hidden, false);
  assert.ok(textOf(liveFixture.byId.get('roadmap-coverage')).includes('40 canonical phases'));
  const homeTrack = descendantsOf(liveFixture.byId.get('roadmap-groups'))
    .find(node => node.dataset.roadmapId === 'track-home');
  await liveFixture.byId.get('roadmap-groups').emit('click', {target: homeTrack});
  assert.ok(textOf(liveFixture.byId.get('architecture-detail')).includes('personal computer is shut down'));
  assert.ok(textOf(liveFixture.byId.get('architecture-detail')).includes('5'.repeat(64)));
  assert.ok(!textOf(liveFixture.byId.get('architecture-detail')).includes('4'.repeat(64)));
  assert.ok(textOf(liveFixture.byId.get('architecture-detail')).includes('Synthetic retained source'));

  // A polling refresh rebuilds cards but preserves the stable selection,
  // expansion, and vertical position. It never leaves wheel click bound to a
  // detached old node.
  const oldLiveCard = descendantsOf(liveFixture.byId.get('activity-feed'))
    .find((node) => node.matches('details.console-card'));
  oldLiveCard.open = true;
  liveFixture.byId.get('activity-feed').scrollTop = 47;
  await liveFixture.shell.emit('click', {target: oldLiveCard});
  await liveController.refresh();
  assert.ok(textOf(liveFixture.byId.get('architecture-detail')).includes('5'.repeat(64)));
  const refreshedLiveCard = descendantsOf(liveFixture.byId.get('activity-feed'))
    .find((node) => node.matches('details.console-card'));
  assert.notStrictEqual(refreshedLiveCard, oldLiveCard);
  assert.strictEqual(refreshedLiveCard.open, true);
  assert.strictEqual(refreshedLiveCard.classList.contains('selected'), true);
  assert.strictEqual(liveFixture.byId.get('activity-feed').scrollTop, 47);
  const refreshedWheel = await liveFixture.shell.emit('auxclick', {
    target: liveFixture.shell, button: 1,
  });
  assert.strictEqual(refreshedWheel.defaultPrevented, true);
  assert.strictEqual(refreshedLiveCard.open, false);
  projectionPayload = {...rawProjection, campaigns: [], jobs: []};
  await liveController.refresh();
  assert.strictEqual(liveFixture.byId.get('campaign-state').textContent, 'EXECUTION UNAVAILABLE');
  assert.ok(textOf(liveFixture.byId.get('activity-feed')).includes('does not mean Fawkes has no history'));
  const removedWheel = await liveFixture.shell.emit('auxclick', {
    target: liveFixture.shell, button: 1,
  });
  assert.strictEqual(removedWheel.defaultPrevented, true);
  assert.strictEqual(descendantsOf(liveFixture.byId.get('activity-feed'))
    .filter((node) => node.matches('details.console-card')).length, 0);

  // Expiry is invalidated at the exact boundary without another fetch.
  liveNow = Date.parse(rawProjection.attention[0].expires_at);
  projectionScheduler.runDelay(60_000);
  assert.strictEqual(descendantsOf(liveFixture.byId.get('attention-slot'))
    .filter((node) => node.tagName === 'a').length, 0);
  failReads = true;
  await liveController.refresh();
  assert.strictEqual(liveFixture.shell.dataset.projectionState, 'stale');
  assert.strictEqual(descendantsOf(liveFixture.byId.get('attention-slot'))
    .filter((node) => node.tagName === 'a').length, 0);
  assert.strictEqual(liveFixture.byId.get('attention-state').textContent, 'ATTENTION UNKNOWN');
  liveController.stop();

  const disconnectedFixture = fakeDocument();
  const disconnectedController = consoleApi.boot({
    document: disconnectedFixture.document,
    fetch: async () => { throw new Error('offline'); },
    scheduler: new Scheduler(),
    baseUrl: 'https://localhost:8791/',
    pollIntervalMs: 0,
    disableUpdateRefresh: true,
  });
  await settle();
  assert.strictEqual(disconnectedFixture.shell.dataset.projectionState, 'disconnected');
  assert.strictEqual(disconnectedFixture.byId.get('connection-state').textContent, '⊘ Disconnected');
  assert.strictEqual(disconnectedFixture.byId.get('campaign-state').textContent, 'EXECUTION UNKNOWN');
  disconnectedController.stop();

  const malformedFixture = fakeDocument();
  const malformedPayload = {...rawProjection, campaigns: 'invalid'};
  const malformedController = consoleApi.boot({
    document: malformedFixture.document,
    fetch: async () => ({ok: true, status: 200, json: async () => malformedPayload}),
    scheduler: new Scheduler(),
    baseUrl: 'https://localhost:8791/',
    pollIntervalMs: 0,
    disableUpdateRefresh: true,
  });
  await settle();
  assert.strictEqual(malformedFixture.shell.dataset.projectionState, 'unavailable');
  malformedController.stop();

  // The clock used for freshness is sampled only after the response arrives,
  // and an older overlapping refresh can never replace the newer response.
  const overlapFixture = fakeDocument();
  const pending = [];
  let overlapNow = fixtureNow;
  let overlapClockSamples = 0;
  const overlapFetch = () => new Promise((resolve) => pending.push(resolve));
  const overlapController = consoleApi.boot({
    document: overlapFixture.document,
    fetch: overlapFetch,
    scheduler: new Scheduler(),
    projectionScheduler: new Scheduler(),
    now: () => { overlapClockSamples += 1; return overlapNow; },
    baseUrl: 'https://localhost:8791/',
    pollIntervalMs: 0,
    disableUpdateRefresh: true,
  });
  await settle();
  assert.strictEqual(pending.length, 1);
  assert.strictEqual(overlapClockSamples, 0, 'freshness clock was sampled before fetch completed');
  const newerRefresh = overlapController.refresh();
  await settle();
  assert.strictEqual(pending.length, 2);
  assert.strictEqual(overlapClockSamples, 0, 'overlapping fetch sampled freshness too early');
  const newer = JSON.parse(JSON.stringify(rawProjection));
  newer.observed_at = new Date(fixtureNow + 2_000).toISOString();
  newer.components.push({name: 'development_coordinator', state: 'NEWER'});
  overlapNow = fixtureNow + 2_000;
  pending[1]({ok: true, status: 200, json: async () => newer});
  await newerRefresh;
  assert.ok(textOf(overlapFixture.byId.get('architecture-detail')).includes('NEWER'));
  const older = JSON.parse(JSON.stringify(rawProjection));
  older.observed_at = new Date(fixtureNow + 1_000).toISOString();
  older.components.push({name: 'development_coordinator', state: 'OLDER'});
  overlapNow = fixtureNow + 3_000;
  pending[0]({ok: true, status: 200, json: async () => older});
  await settle();
  assert.ok(textOf(overlapFixture.byId.get('architecture-detail')).includes('NEWER'));
  assert.ok(!textOf(overlapFixture.byId.get('architecture-detail')).includes('OLDER'));
  overlapController.stop();
}

module.exports = {FakeElement, fakeDocument, textOf, consoleApi, Scheduler, rawProjection};

if (require.main === module) runDomFixture().then(() => {
  process.stdout.write('dev-console-projection-ok\n');
}).catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});

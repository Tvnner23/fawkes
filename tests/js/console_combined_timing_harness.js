'use strict';

const assert = require('assert');
const fs = require('fs');
const {consoleApi: api, FakeElement, fakeDocument, textOf, Scheduler, rawProjection} = require('./dev_console_projection_harness.js');
const supplied = JSON.parse(fs.readFileSync(0, 'utf8'));
const normalized = api.normalizeRoadmapResponse(supplied.roadmap);
assert.strictEqual(normalized.valid, true, 'actual Python inventory must survive normalization');
const roadmap = normalized.roadmap;
const model = api.combinedModel(roadmap);
const ids = new Set(model.nodes.map(node => node.id));
assert.strictEqual(ids.size, model.nodes.length, 'shared entities must appear once');
assert.strictEqual(model.nodes.filter(node => node.kind === 'component').length, 10);
for (let number = 0; number < 40; number++) assert.ok(ids.has(`phase-${number}`));
for (const item of roadmap.tracks) assert.ok(ids.has(item.id));
const connected = new Set(['combined-root']);
for (let i = 0; i < model.nodes.length; i++) for (const edge of model.edges) {
  assert.ok(ids.has(edge.from) && ids.has(edge.to), 'all edges have actual endpoints');
  if (connected.has(edge.from)) connected.add(edge.to);
  if (connected.has(edge.to)) connected.add(edge.from);
}
assert.strictEqual(connected.size, ids.size, 'the whole inventory forms one connected diagram');
const prerequisites = model.edges.filter(edge => edge.kind === 'prerequisite');
assert.deepStrictEqual(JSON.parse(JSON.stringify(prerequisites.map(edge => [edge.from, edge.to]))),
  [['phase-0', 'track-presence'], ['phase-1', 'track-presence']]);
assert.strictEqual(model.edges.filter(edge => edge.kind === 'architecture').length, 11);
for (const item of [...roadmap.phases, ...roadmap.tracks]) {
  const node = model.nodes.find(node => node.id === item.id);
  for (const key of ['source', 'source_sha256', 'source_revision', 'source_excerpt', 'maturity', 'runtime_state']) {
    assert.strictEqual(node[key], item[key], `source-bound ${key} was changed`);
  }
  const associated = model.nodes.find(candidate => candidate.id === node.parent && candidate.kind === 'component');
  const parent = model.nodes.find(candidate => candidate.id === node.parent);
  assert.strictEqual(parent.kind, associated ? 'component' : 'group');
  if (!associated) assert.ok(parent.name.startsWith('Unmapped'));
}
assert.strictEqual(model.nodes.find(n=>n.id==='phase-15').parent, 'memory');
assert.ok(model.nodes.find(n=>n.id==='memory').maturity.includes('expansions planned'));
assert.strictEqual(model.nodes.filter(n=>n.kind==='phase'&&n.parent.startsWith('unmapped')).length, 0);
const renamed=JSON.parse(JSON.stringify(roadmap)); renamed.phases[15].name='Unmapped revised capability';
assert.ok(api.combinedModel(renamed).nodes.find(n=>n.id==='phase-15').parent.startsWith('unmapped'));
for (const mutation of [value => value.tracks.push(value.tracks[0]),
  value => value.phases[2].prerequisites.push('missing-phase'), value => value.phases[1].number = 2]) {
  const value = JSON.parse(JSON.stringify(supplied.roadmap)); mutation(value);
  assert.strictEqual(api.normalizeRoadmapResponse(value).valid, false, 'invalid coverage must fail closed');
}

const fixture = fakeDocument();
const el = id => fixture.byId.get(id);
const elements = {map: el('architecture-map'), detail: el('architecture-detail'),
  overview: el('architecture-overview'), inventory: el('roadmap-inventory'), groups: el('roadmap-groups'),
  coverage: el('roadmap-coverage'), filter: el('roadmap-filter'),
  modes: fixture.document.querySelectorAll('[data-architecture-mode]'),
  combined: el('combined-view'), combinedMap: el('combined-map'), combinedSelect: el('combined-select'),
  combinedCoverage: el('combined-coverage'), combinedState: api.combinedState()};
const state = elements.combinedState;
for (const group of model.groups) state.expanded.add(group.id);
api.renderRoadmapInventory(fixture.document, elements, roadmap, {mode: 'combined'});
assert.strictEqual(elements.overview.hidden, true);
assert.strictEqual(elements.inventory.hidden, true, 'Combined cannot stack the Roadmap list');
assert.strictEqual(elements.combined.hidden, false);
assert.strictEqual(elements.combinedMap.querySelectorAll('[data-combined-id]').length, model.nodes.length);
const layout = api.combinedLayout(model, state.expanded);
const boxes = Array.from(layout.positions.values());
for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++) {
  const x = boxes[a], y = boxes[b];
  assert.ok(x.x + x.width <= y.x || y.x + y.width <= x.x || x.y + x.height <= y.y || y.y + y.height <= x.y,
    'diagram nodes cannot overlap, including expanded groups');
}
api.focusCombined(model, state, 'track-console-controls');
api.renderRoadmapInventory(fixture.document, elements, roadmap, {mode: 'combined'});
assert.ok(textOf(elements.detail).includes(roadmap.tracks.find(item => item.id === state.selected).summary));
const details = elements.detail.querySelector('details.roadmap-source-details');
details.open = true;
elements.detail.scrollTop = 120;
api.combinedControl(state, 'left'); api.combinedControl(state, 'in');
const retained = {x: state.x, y: state.y, zoom: state.zoom, selected: state.selected, expanded: Array.from(state.expanded)};
api.renderRoadmapInventory(fixture.document, elements, roadmap, {mode: 'combined'});
assert.deepStrictEqual({x: state.x, y: state.y, zoom: state.zoom, selected: state.selected, expanded: Array.from(state.expanded)}, retained);
assert.strictEqual(elements.detail.querySelector('details.roadmap-source-details'), details);
assert.strictEqual(details.open, true);
assert.strictEqual(elements.detail.scrollTop, 120);
api.combinedControl(state, 'fit', layout);
assert.ok(layout.width * state.zoom <= 660 && layout.height * state.zoom <= 400);
api.combinedControl(state, 'reset'); assert.strictEqual(state.zoom, 1);
api.renderRoadmapInventory(fixture.document, elements, roadmap, {mode: 'roadmap', selectedId: 'phase-18'});
assert.strictEqual(elements.overview.hidden, true);
assert.strictEqual(elements.inventory.hidden, false);
assert.strictEqual(elements.combined.hidden, true);
const roadmapGroups = elements.groups.children.slice();
roadmapGroups[0].open = true;
api.renderRoadmapInventory(fixture.document, elements, roadmap, {mode: 'roadmap', selectedId: 'phase-18'});
assert.strictEqual(elements.groups.children[0].open, true);
api.renderRoadmapInventory(fixture.document, elements, roadmap, {mode: 'current'});
assert.strictEqual(elements.overview.hidden, false);
assert.strictEqual(elements.inventory.hidden, true);
assert.strictEqual(elements.map.querySelectorAll('[data-architecture-node]').length, 10);

const reporting = api.normalizeConsoleReporting(supplied.campaigns[0].console_reporting);
const completed = reporting.intervals.find(item => item.stage === 'worker');
const observed = Date.parse(reporting.observed_at);
assert.strictEqual(api.intervalSeconds(completed, reporting, 'live', observed), 65);
assert.strictEqual(api.intervalSeconds(completed, reporting, 'disconnected', observed + 80000), 65);
assert.strictEqual(api.formatDuration(65), '01:05');
assert.strictEqual(api.formatDuration(3665), '01:01:05');
assert.strictEqual(api.formatDuration(null), '—');
for (const end of ['2026-09-11T03:00:00Z', 'invalid', '2026-02-30T00:00:00Z', '2026-09-12T00:00:00Z']) {
  assert.strictEqual(api.intervalSeconds({...completed, ended_at: end}, reporting, 'live', observed), null);
}
const active = {...completed, ended_at: '', active_verified: true, duration_seconds: 540};
assert.strictEqual(api.intervalSeconds(active, reporting, 'live', observed + 5000), 545);
assert.strictEqual(api.intervalSeconds(active, reporting, 'stale', observed + 10000), 545);
assert.strictEqual(api.intervalSeconds(active, reporting, 'disconnected', observed + 80000), 545);
assert.strictEqual(api.intervalSeconds({...active, last_displayed_seconds: undefined}, reporting, 'live', observed + 80000), 540);
assert.strictEqual(api.intervalSeconds({...active, active_verified: false}, reporting, 'live', observed), null);
assert.strictEqual(api.intervalSeconds(active, reporting, 'live', observed - 1), null);
const campaign = api.normalizeCampaignProjection(supplied.campaigns[0]);
assert.strictEqual(api.campaignGraphModel(campaign).stages.find(stage => stage.id === 'review').state, 'waiting');
const campaignElements = Object.fromEntries(['selector', 'history', 'empty', 'dashboard', 'widgets', 'graph', 'detail'].map(key =>
  [key, new FakeElement(key === 'graph' ? 'svg' : 'div')]));
api.renderCampaignDashboard(fixture.document, campaignElements, [campaign], '', 'worker');
api.updateStageTimers(campaignElements.graph, campaign, 'live', observed);
assert.ok(textOf(campaignElements.graph).includes('01:05'));
assert.ok(textOf(campaignElements.detail).includes(completed.started_at));
assert.ok(textOf(campaignElements.detail).includes('builder_runs/iteration=1/completed_at'));
assert.strictEqual(api.intervalSeconds({...completed, duration_seconds: null}, reporting, 'live', observed), null);
// Exercise the actual normalization-to-detail path, not just the formatter.
for (const invalid of [
  {duration_seconds: null, started_at: '', ended_at: ''},
  {duration_seconds: '65'}, {duration_seconds: false}, {duration_seconds: -1},
  {duration_seconds: 0, started_at: '', ended_at: ''},
  {duration_seconds: 65, ended_at: '2026-09-11T03:00:00Z'},
  {duration_seconds: 65, started_at: ''}, {duration_seconds: 65, source_references: []}
]) {
  const raw = {...supplied.campaigns[0], console_reporting: {
    ...supplied.campaigns[0].console_reporting, intervals: [{...completed, ...invalid}]
  }};
  const projected = api.normalizeCampaignProjection(raw);
  api.renderCampaignDashboard(fixture.document, campaignElements, [projected], '', 'worker');
  const detail = textOf(campaignElements.detail);
  assert.ok(detail.includes(' · — · '), `unreliable detail must show dash: ${JSON.stringify(invalid)}`);
  assert.ok(!detail.includes(' · 00:00 · '), 'unknown must not turn into measured zero');
}
const zero = {...supplied.campaigns[0], console_reporting: {
  ...supplied.campaigns[0].console_reporting, intervals: [
    {...completed, ended_at: completed.started_at, duration_seconds: 0}]
}};
api.renderCampaignDashboard(fixture.document, campaignElements, [api.normalizeCampaignProjection(zero)], '', 'worker');
assert.ok(textOf(campaignElements.detail).includes(' · 00:00 · '), 'proven zero interval remains valid');
for (const status of ['cancelled', 'expired', 'denied']) {
  const closed = api.normalizeCampaignProjection({...supplied.campaigns[0], status,
    console_reporting: {...supplied.campaigns[0].console_reporting,
      intervals: [{stage: 'terminal', attempt: 1, state: status, source_references: ['events/closed']}]}});
  assert.strictEqual(api.campaignGraphModel(closed).stages.find(stage => stage.id === 'terminal').state, 'blocked');
}
for (const status of ['waiting', 'done', 'failed', 'closed', 'needs_you', 'unknown']) {
  const job = {...supplied.jobs[0], state: status, successful: status === 'done',
    historical: ['done', 'failed', 'closed'].includes(status)};
  const normalizedJobs = api.normalizeJobsResponse([job]);
  assert.strictEqual(normalizedJobs.valid, true);
  api.renderJobs(fixture.document, el('activity-feed'), normalizedJobs.jobs, 'disconnected');
  const rendered = textOf(el('activity-feed'));
  for (const key of ['objective', 'current_step', 'accomplished', 'next']) assert.ok(rendered.includes(job[key]));
  assert.ok(rendered.includes('Last known ' + status.replace('_', ' ')));
}

async function interactive() {
  const documentFixture = fakeDocument();
  const now = Date.now();
  const payload = {...rawProjection, observed_at: new Date(now).toISOString(),
    roadmap: supplied.roadmap, campaigns: supplied.campaigns, jobs: supplied.jobs};
  const controller = api.boot({document: documentFixture.document,
    fetch: async () => ({ok: true, status: 200, json: async () => payload}),
    scheduler: new Scheduler(), projectionScheduler: new Scheduler(), now: () => now,
    pollIntervalMs: 0, disableUpdateRefresh: true, baseUrl: 'https://localhost:8791/'});
  try {
    await controller.refresh();
    const get = id => documentFixture.byId.get(id);
    const modes = documentFixture.document.querySelectorAll('[data-architecture-mode]');
    controller.navigation.go(3, 'test');
    await modes.find(node => node.dataset.architectureMode === 'combined').emit('click');
    assert.strictEqual(get('combined-view').hidden, false);
    const graph = get('combined-map');
    const group = graph.querySelectorAll('[data-combined-id]').find(node => node.dataset.combinedId === 'clients');
    await graph.emit('click', {target: group});
    assert.ok(graph.querySelectorAll('[data-combined-id]').some(node => node.dataset.combinedId === 'track-phone'));
    await graph.emit('pointerdown', {target: graph, pointerId: 1, button: 0, clientX: 100, clientY: 100});
    await graph.emit('pointermove', {target: graph, pointerId: 1, clientX: 160, clientY: 140});
    await graph.emit('pointerup', {target: graph, pointerId: 1, clientX: 160, clientY: 140});
    const layer = graph.querySelector('[data-combined-layer]');
    const transform = layer.attributes.transform;
    const dragClick = await graph.emit('click', {target: group});
    assert.strictEqual(dragClick.defaultPrevented, true, 'drag must not collapse a group');
    assert.strictEqual(controller.navigation.page, 3);
    await controller.refresh();
    assert.strictEqual(graph.querySelector('[data-combined-layer]'), layer, 'refresh must not break pointer capture');
    assert.strictEqual(layer.attributes.transform, transform);
    assert.ok(graph.querySelectorAll('[data-combined-id]').some(node => node.dataset.combinedId === 'track-phone'));
    await graph.emit('pointerdown', {target: graph, pointerId: 1, button: 0, clientX: 100, clientY: 100});
    await graph.emit('pointerdown', {target: graph, pointerId: 2, button: 0, clientX: 200, clientY: 100});
    await graph.emit('pointermove', {target: graph, pointerId: 2, clientX: 250, clientY: 100});
    await graph.emit('pointerup', {target: graph, pointerId: 2, clientX: 250, clientY: 100});
    await graph.emit('pointerup', {target: graph, pointerId: 1, clientX: 100, clientY: 100});
    assert.notStrictEqual(layer.attributes.transform, transform, 'pinch must zoom the same graph');
    await graph.emit('keydown', {target: group, key: 'Enter'});
    assert.ok(!graph.querySelectorAll('[data-combined-id]').some(node => node.dataset.combinedId === 'track-phone'));
    const picker = get('combined-select'); picker.value = 'phase-39';
    await picker.emit('change');
    assert.ok(textOf(get('architecture-detail')).includes('phase-39'));
    const selectedTransform = graph.querySelector('[data-combined-layer]').attributes.transform;
    await modes.find(node => node.dataset.architectureMode === 'current').emit('click');
    assert.ok(textOf(get('architecture-detail')).includes('Development campaign'));
    await modes.find(node => node.dataset.architectureMode === 'combined').emit('click');
    assert.strictEqual(graph.querySelector('[data-combined-layer]').attributes.transform, selectedTransform);
    await get('architecture-reset').emit('click');
    assert.notStrictEqual(graph.querySelector('[data-combined-layer]').attributes.transform, selectedTransform);
  } finally {controller.stop();}
}
interactive().then(() => process.stdout.write('console-combined-timing-ok\n')).catch(error => {
  process.stderr.write(error.stack + '\n'); process.exitCode = 1;
});

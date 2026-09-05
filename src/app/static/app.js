const messages = document.querySelector('#messages');
const composer = document.querySelector('#composer');
const input = document.querySelector('#message');
const send = document.querySelector('#send');
const attachmentInput = document.querySelector('#attachments');
const attachmentTray = document.querySelector('#attachment-tray');
const status = document.querySelector('#status');
const auth = document.querySelector('#auth');
const authForm = document.querySelector('#auth-form');
const tokenInput = document.querySelector('#token');
const connect = document.querySelector('#connect');
const authError = document.querySelector('#auth-error');
const developerContent = document.querySelector('#developer-content');
const developerBuild = document.querySelector('#developer-build');
const detailPanel = document.querySelector('#detail-panel');
const detailContent = document.querySelector('#detail-content');
const soundSettings = document.querySelector('#sound-settings');
const presenceSettings = document.querySelector('#presence-settings');
const libraryContent = document.querySelector('#library-content');
const librarySearchForm = document.querySelector('#library-search-form');
const libraryQuery = document.querySelector('#library-query');
const historyContent = document.querySelector('#history-content');
const historySearchForm = document.querySelector('#history-search-form');
const historyQuery = document.querySelector('#history-query');
const historyDomain = document.querySelector('#history-domain');
function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function replaceContent(node, ...children) { clearNode(node); children.forEach(child => node.append(child)); }
function setAuthError(message) {
  authError.textContent = message || '';
  authError.classList.toggle('hidden', !message);
}
let token = '';
let csrfToken = '';
let conversationId = null;
let developerData = null;
let testCenterData = null;
const testProbePreviews = {};
let developerSection = 'observations';
let requestedAttentionId = null;
let exactAttentionState = null;
// One browser-local lifecycle per canonical Attention identity. Exact-link and
// embedded campaign projections must observe the same in-flight decision.
const attentionSubmissions = new Map();
let exactAttentionLoadGeneration = 0;
let campaignPoll = null;
let testCenterPoll = null;
let recoveryGeneration = 0;
let pendingAttachments = [];
let chatRequestPending = false;
const attachmentRetention = new WeakMap();
function emitWindowEvent(name, detail) {
  if (typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') window.dispatchEvent(new CustomEvent(name, { detail }));
}
function emitPresence(eventId, occurrenceId) { emitWindowEvent('fawkes:presence-event', { event_id: eventId, occurrence_id: occurrenceId }); }

class FawkesEventAudio {
  constructor() { this.catalog = new Map(); this.preferences = null; this.seen = new Set(); this.unlocked = false; }
  configure(payload) { this.preferences = payload && payload.preferences; this.catalog = new Map(((payload && payload.events) || []).map(item => [item.event_id, item])); }
  unlock() { this.unlocked = true; }
  async emit(event) {
    const eventId = event && event.event_id; const occurrence = event && event.occurrence_id;
    if (!eventId || !occurrence || this.seen.has(`${eventId}:${occurrence}`)) return { status: 'duplicate_or_invalid' };
    this.seen.add(`${eventId}:${occurrence}`);
    const item = this.catalog.get(eventId); const prefs = this.preferences;
    if (!prefs || !prefs.master_enabled || !prefs.events[eventId]) return { status: 'disabled' };
    if (!item || !item.approved || !item.available || !item.asset_url) return { status: 'asset_unavailable' };
    if (!this.unlocked || typeof Audio !== 'function') return { status: 'playback_unavailable' };
    try { const audio = new Audio(item.asset_url); audio.volume = prefs.volume; await audio.play(); return { status: 'played' }; }
    catch (error) { return { status: 'playback_blocked' }; }
  }
}
const eventAudio = new FawkesEventAudio();

async function loadSoundSettings() {
  try { const data = await request('/api/preferences/sounds'); eventAudio.configure(data); if (soundSettings) renderSoundSettings(data); return data; }
  catch (error) { if (soundSettings) replaceContent(soundSettings, element('p', 'dev-empty', error.message)); return null; }
}
async function saveSoundSetting(changes) {
  const data = await request('/api/preferences/sounds', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) });
  eventAudio.configure(data); renderSoundSettings(data);
}
async function loadPresenceSettings() {
  try { const data = await request('/api/presence'); if (presenceSettings) renderPresenceSettings(data); return data; }
  catch (error) { if (presenceSettings) replaceContent(presenceSettings, element('p', 'dev-empty', error.message)); return null; }
}
async function savePresenceSetting(changes) {
  const data = await request('/api/preferences/presence', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) });
  renderPresenceSettings(data); emitWindowEvent('fawkes:connected', { token, phoenix: { instance_id: data.phoenix_instance_id } }); return data;
}
function renderPresenceSettings(data) {
  if (!presenceSettings) return; clearNode(presenceSettings); const policy = data.presentation_policy;
  const card = element('section', 'settings-card'); card.append(element('h3', '', 'Phoenix Presence'));
  card.append(soundToggle('Show Fawkes', policy.enabled, false, value => savePresenceSetting({ enabled: value }).catch(error => showError(error.message))));
  card.append(soundToggle('Reduce motion', policy.reduced_motion, false, value => savePresenceSetting({ reduced_motion: value }).catch(error => showError(error.message))));
  const motionRow = element('label', 'sound-control'); const motionCopy = element('span', 'sound-control-copy'); motionCopy.append(element('strong', '', 'Expression level'), element('small', '', 'Presentation intensity, not personality.'));
  const select = document.createElement('select'); ['off', 'subtle', 'expressive'].forEach(value => { const option = document.createElement('option'); option.value = value; option.textContent = readable(value); option.selected = policy.motion === value; select.append(option); });
  select.addEventListener('change', () => savePresenceSetting({ motion: select.value }).catch(error => showError(error.message))); motionRow.append(motionCopy, select); card.append(motionRow);
  const phraseRow = element('label', 'sound-control'); const phraseCopy = element('span', 'sound-control-copy'); phraseCopy.append(element('strong', '', 'Invocation phrase'), element('small', '', 'Typed in-app invocation only. This is not authentication or permission.'));
  const phrase = document.createElement('input'); phrase.type = 'text'; phrase.maxLength = 80; phrase.value = policy.invocation_phrase;
  phrase.addEventListener('change', () => savePresenceSetting({ invocation_phrase: phrase.value }).catch(error => showError(error.message))); phraseRow.append(phraseCopy, phrase); card.append(phraseRow);
  card.append(element('p', 'media-disclosure', data.health.reason)); presenceSettings.append(card);
}
function soundToggle(label, checked, disabled, onChange) {
  const row = element('label', `sound-control${disabled ? ' unavailable' : ''}`); const copy = element('span', 'sound-control-copy'); copy.append(element('strong', '', label));
  const control = document.createElement('input'); control.type = 'checkbox'; control.checked = checked; control.disabled = disabled; control.addEventListener('change', () => onChange(control.checked)); row.append(copy, control); return row;
}
function renderSoundSettings(data) {
  clearNode(soundSettings); const prefs = data.preferences; const card = element('section', 'settings-card'); card.append(element('h3', '', 'Fawkes event sounds'));
  card.append(soundToggle('Master sounds', prefs.master_enabled, false, value => saveSoundSetting({ master_enabled: value }).catch(error => showError(error.message))));
  const volumeRow = element('label', 'sound-control'); const volumeCopy = element('span', 'sound-control-copy'); volumeCopy.append(element('strong', '', 'Master volume'), element('small', '', `${Math.round(prefs.volume * 100)}%`));
  const volume = document.createElement('input'); volume.type = 'range'; volume.min = '0'; volume.max = '1'; volume.step = '0.05'; volume.value = prefs.volume; volume.addEventListener('change', () => saveSoundSetting({ volume: Number(volume.value) }).catch(error => showError(error.message))); volumeRow.append(volumeCopy, volume); card.append(volumeRow);
  data.events.forEach(item => { const row = soundToggle(item.label, prefs.events[item.event_id], !item.approved, value => saveSoundSetting({ events: { [item.event_id]: value } }).catch(error => showError(error.message))); row.querySelector('.sound-control-copy').append(element('small', 'sound-availability', item.available ? item.asset_identity : (item.approved ? 'Approved asset not installed' : 'Sound not yet rider-approved'))); card.append(row); });
  card.append(element('p', 'media-disclosure', 'Browser playback begins only after rider interaction. Missing assets stay silent; Fawkes never substitutes another sound.')); soundSettings.append(card);
}
async function loadLibrary() {
  try {
    const data = await request('/api/library'); clearNode(libraryContent);
    if (!data.sources.length) { libraryContent.append(element('p', 'dev-empty', 'No retained sources yet. Chat attachments remain temporary unless you explicitly select Keep in Library. Retained PDFs are extracted locally with page-aware provenance.')); return; }
    data.sources.forEach(source => {
      const card = element('article', 'settings-card');
      card.append(element('h3', '', source.title), element('p', 'meta', `${source.media_type} · ${source.original_filename || 'source'} · retained ${dateLabel(source.created_at)}`), element('p', 'meta', 'Content-addressed original · Phoenix-isolated'));
      const latest = (source.extractions || [])[0];
      if (latest) {
        const pages = latest.metadata && latest.metadata.extracted_page_count;
        card.append(element('p', 'library-state success', `Searchable extraction · ${pages || latest.segment_count} page segment(s) · ${latest.extractor} ${latest.extractor_version}`));
      } else if (source.media_type === 'application/pdf') {
        card.append(element('p', 'library-state warning', 'Original retained · searchable extraction not available yet.'));
        const retry = element('button', 'library-extract', 'EXTRACT / RETRY'); retry.type = 'button'; retry.dataset.extractSource = source.source_id; card.append(retry);
      } else card.append(element('p', 'library-state', 'Original retained · this media type has no text extraction.'));
      libraryContent.append(card);
    });
  } catch (error) { replaceContent(libraryContent, element('p', 'dev-empty', error.message)); }
}
async function searchLibrary(query) {
  const data = await request('/api/library/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) }); clearNode(libraryContent);
  if (!data.results.length) { libraryContent.append(element('p', 'dev-empty', 'No matching retained passage was found.')); return; }
  data.results.forEach(result => { const card = element('article', 'settings-card'); const location = result.location || {}; card.append(element('h3', '', result.source_title), element('p', '', result.text), element('p', 'meta', [location.chapter, location.section, location.page_label && `page ${location.page_label}`].filter(Boolean).join(' · ') || 'Source locator retained')); libraryContent.append(card); });
}
async function searchHistory(query, domainChoice) {
  const domains = domainChoice === 'both' ? ['native_archive', 'inherited_history'] : [domainChoice];
  const data = await request('/api/history/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, domains }) });
  clearNode(historyContent);
  const statusLine = Object.entries(data.domain_status).map(([domain, state]) => `${readable(domain)}: ${readable(state.status)}`).join(' · ');
  historyContent.append(element('p', 'meta', `${statusLine} · Results never enter Chat or Memory.`));
  if (!data.results.length) { historyContent.append(element('p', 'dev-empty', 'No matching evidence was found in the available selected domains.')); return; }
  data.results.forEach(result => {
    const card = element('article', 'settings-card');
    card.append(element('h3', '', result.domain === 'inherited_history' ? 'Inherited founding history' : 'Native canonical Archive'));
    card.append(element('p', '', result.navigation_snippet));
    card.append(element('p', 'meta', `${result.history_era} · ${result.role || 'unknown speaker'} · ${dateLabel(result.created_at)} · ${result.native_boundary_status}`));
    if (result.domain === 'inherited_history') card.append(element('p', 'meta', `${result.relationship_provenance} · identity ${result.identity_attribution} · ${result.provider_source.provider}`));
    const open = element('button', 'library-extract', 'OPEN EXACT ORIGINAL'); open.type = 'button';
    open.dataset.historyDomain = result.evidence_reference.domain; open.dataset.historyEvidence = result.evidence_reference.evidence_id;
    card.append(open, element('p', 'media-disclosure', 'This excerpt is for navigation only. Open the original source for authoritative text.'));
    historyContent.append(card);
  });
}
async function openHistoricalEvidence(domain, evidenceId) {
  const evidence = await request(`/api/history/evidence/${encodeURIComponent(domain)}/${encodeURIComponent(evidenceId)}`);
  clearNode(detailContent);
  detailContent.append(element('p', 'eyebrow', evidence.domain === 'inherited_history' ? 'Inherited source evidence' : 'Native Archive source evidence'));
  detailContent.append(element('h2', '', 'Exact original text'));
  detailContent.append(element('p', 'meta', `${evidence.history_era} · ${evidence.native_boundary_status || 'boundary not asserted'} · ${evidence.authority_class}`));
  if (evidence.identity_attribution) detailContent.append(element('p', 'meta', `Identity attribution: ${evidence.identity_attribution} · Relationship provenance: ${evidence.relationship_provenance}`));
  const original = element('pre', 'detail-json'); original.textContent = evidence.exact_original_text || '(Original source contains no text.)'; detailContent.append(original);
  detailContent.append(element('p', 'media-disclosure', 'The navigation snippet is not authoritative. This text was resolved from the immutable original evidence reference.'));
  detailPanel.classList.remove('hidden');
}

function renderAttachmentTray() {
  clearNode(attachmentTray);
  attachmentTray.classList.toggle('hidden', !pendingAttachments.length);
  if (!pendingAttachments.length) return;
  pendingAttachments.forEach((item, index) => {
    const chip = element('span', 'attachment-chip');
    if (item.type.startsWith('image/')) {
      const preview = document.createElement('img');
      preview.className = 'attachment-preview'; preview.alt = '';
      preview.src = URL.createObjectURL(item);
      preview.addEventListener('load', () => URL.revokeObjectURL(preview.src), { once: true });
      chip.append(preview);
    } else chip.append(element('span', 'attachment-kind', item.type.startsWith('audio/') ? '♪' : 'PDF'));
    chip.append(element('span', 'attachment-name', item.name));
    const keepLabel = element('label', 'attachment-keep');
    const keep = document.createElement('input'); keep.type = 'checkbox';
    keep.checked = attachmentRetention.get(item) === true;
    keep.addEventListener('change', () => { attachmentRetention.set(item, keep.checked); renderAttachmentTray(); });
    keepLabel.append(keep, element('span', '', 'Keep in Library'));
    chip.append(keepLabel);
    const remove = element('button', 'attachment-remove', '×');
    remove.type = 'button'; remove.setAttribute('aria-label', `Remove ${item.name}`);
    remove.addEventListener('click', () => { pendingAttachments.splice(index, 1); renderAttachmentTray(); });
    chip.append(remove); attachmentTray.append(chip);
  });
  const keepCount = pendingAttachments.filter(item => attachmentRetention.get(item) === true).length;
  attachmentTray.append(element('p', 'media-disclosure', keepCount
    ? `${keepCount} selected for explicit durable Library retention. Other attachments remain temporary. Analysis may use the configured external AI provider; Library PDF extraction is local.`
    : 'Temporary analysis · sent to the configured external AI provider · not added to Library · not written to durable temporary storage; request-memory references are released after the request (not securely zeroized)'));
}
function fileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
    reader.readAsDataURL(file);
  });
}

function headers() { return token ? { Authorization: `Bearer ${token}` } : {}; }
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function readable(value) { return String(value || '').replace(/_/g, ' '); }
function dateLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
function messageTimeLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return '';
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}
function addMessageTimestamp(node, createdAt) {
  const label = messageTimeLabel(createdAt);
  if (!label) return;
  const timestamp = element('time', 'message-time', label);
  timestamp.dateTime = createdAt;
  timestamp.title = dateLabel(createdAt);
  node.append(timestamp);
}
function safeHttpUrl(value) {
  try {
    const parsed = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch (error) { return null; }
}
function appendInline(parent, text, citations = []) {
  const citationMap = {};
  citations.forEach(item => { citationMap[item.url] = item; });
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;
  let position = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > position) parent.append(element('span', '', text.slice(position, match.index)));
    const tokenValue = match[0];
    if (tokenValue.startsWith('**')) {
      parent.append(element('strong', '', tokenValue.slice(2, -2)));
    } else if (tokenValue.startsWith('`')) {
      parent.append(element('code', '', tokenValue.slice(1, -1)));
    } else {
      const linkMatch = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(tokenValue);
      const href = linkMatch && safeHttpUrl(linkMatch[2]);
      if (href) {
        const citation = citationMap[linkMatch[2]];
        const link = element('a', citation ? 'citation-link' : 'conversation-link', linkMatch[1]);
        link.href = citation ? citation.display_url : href;
        link.target = '_blank'; link.rel = 'noopener noreferrer';
        if (citation) link.title = `Source: ${citation.title}`;
        parent.append(link);
      } else parent.append(element('span', '', linkMatch ? linkMatch[1] : tokenValue));
    }
    position = pattern.lastIndex;
  }
  if (position < text.length) parent.append(element('span', '', text.slice(position)));
}
function markdownTable(lines, start, citations) {
  if (start + 1 >= lines.length || !/^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$/.test(lines[start + 1])) return null;
  const cells = line => line.trim().replace(/^\||\|$/g, '').split('|').map(item => item.trim());
  const headers = cells(lines[start]);
  const rows = [];
  let index = start + 2;
  while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
    const row = cells(lines[index]);
    if (row.length !== headers.length) break;
    rows.push(row); index += 1;
  }
  const wrapper = element('div', 'table-scroll');
  const table = element('table', 'message-table');
  const head = element('thead'); const headRow = element('tr');
  headers.forEach(value => { const cell = element('th'); appendInline(cell, value, citations); headRow.append(cell); });
  head.append(headRow); table.append(head);
  const body = element('tbody');
  rows.forEach(row => { const rowNode = element('tr'); row.forEach(value => { const cell = element('td'); appendInline(cell, value, citations); rowNode.append(cell); }); body.append(rowNode); });
  table.append(body); wrapper.append(table);
  return { node: wrapper, next: index };
}
function renderRichText(container, text, citations = []) {
  const lines = String(text || '').split('\n');
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    const table = markdownTable(lines, index, citations);
    if (table) { container.append(table.node); index = table.next; continue; }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) { const node = element(`h${heading[1].length + 2}`); appendInline(node, heading[2], citations); container.append(node); index += 1; continue; }
    if (/^```/.test(line)) {
      const codeLines = []; index += 1;
      while (index < lines.length && !/^```/.test(lines[index])) { codeLines.push(lines[index]); index += 1; }
      container.append(element('pre', '', codeLines.join('\n'))); index += 1; continue;
    }
    const bullet = /^\s*[-*]\s+(.+)$/.exec(line);
    const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (bullet || ordered) {
      const list = element(bullet ? 'ul' : 'ol');
      const matcher = bullet ? /^\s*[-*]\s+(.+)$/ : /^\s*\d+[.)]\s+(.+)$/;
      while (index < lines.length) {
        const item = matcher.exec(lines[index]); if (!item) break;
        const listItem = element('li'); appendInline(listItem, item[1], citations); list.append(listItem); index += 1;
      }
      container.append(list); continue;
    }
    const quote = /^>\s?(.+)$/.exec(line);
    if (quote) { const node = element('blockquote'); appendInline(node, quote[1], citations); container.append(node); index += 1; continue; }
    const paragraphLines = [line]; index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s|^```|^\s*[-*]\s+|^\s*\d+[.)]\s+|^>/.test(lines[index])) {
      if (markdownTable(lines, index, citations)) break;
      paragraphLines.push(lines[index]); index += 1;
    }
    const paragraph = element('p'); appendInline(paragraph, paragraphLines.join(' '), citations); container.append(paragraph);
  }
}
function visualFallback(block) {
  const details = element('details', 'visual-fallback');
  details.append(element('summary', '', 'Text version'), element('p', '', block.fallback));
  return details;
}
function renderTableBlock(block) {
  const wrapper = element('div', 'table-scroll');
  const table = element('table', 'message-table structured-table');
  const head = element('thead'); const row = element('tr');
  block.columns.forEach(value => row.append(element('th', '', value))); head.append(row); table.append(head);
  const body = element('tbody');
  block.rows.forEach(values => { const item = element('tr'); values.forEach(value => item.append(element('td', '', value))); body.append(item); });
  table.append(body); wrapper.append(table); return wrapper;
}
function renderDiagramBlock(block) {
  const diagram = element('div', `flow-diagram ${block.direction}`);
  block.nodes.forEach((node, index) => {
    diagram.append(element('div', 'flow-node', node.label));
    if (index < block.nodes.length - 1) diagram.append(element('div', 'flow-arrow', block.direction === 'horizontal' ? '→' : '↓'));
  });
  if (block.edges.some(edge => edge.label)) {
    const legend = element('ul', 'flow-legend');
    block.edges.forEach(edge => { if (edge.label) legend.append(element('li', '', edge.label)); });
    diagram.append(legend);
  }
  return diagram;
}
const chartColors = ['#e47b48', '#68a7d3', '#79b98a', '#c18ad6', '#e3b653', '#d86f82', '#73b8aa', '#9a94dc'];
function svgNode(tag, attributes = {}) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
  return node;
}
function renderPieChart(block) {
  const wrapper = element('div', 'pie-layout');
  const svg = svgNode('svg', { viewBox: '0 0 240 240', role: 'img', 'aria-label': block.fallback });
  const points = block.series[0].points; const total = points.reduce((sum, point) => sum + point.value, 0);
  let angle = -Math.PI / 2;
  points.forEach((point, index) => {
    if (point.value <= 0) return;
    if (point.value === total) {
      const circle = svgNode('circle', { cx: 120, cy: 120, r: 95, fill: chartColors[index % chartColors.length] });
      const fullTitle = svgNode('title'); fullTitle.textContent = `${point.label}: ${point.value}`;
      circle.append(fullTitle); svg.append(circle); angle += Math.PI * 2; return;
    }
    const next = angle + (point.value / total) * Math.PI * 2;
    const x1 = 120 + 95 * Math.cos(angle); const y1 = 120 + 95 * Math.sin(angle);
    const x2 = 120 + 95 * Math.cos(next); const y2 = 120 + 95 * Math.sin(next);
    const large = next - angle > Math.PI ? 1 : 0;
    const path = svgNode('path', { d: `M120 120 L${x1} ${y1} A95 95 0 ${large} 1 ${x2} ${y2} Z`, fill: chartColors[index % chartColors.length] });
    const title = svgNode('title'); title.textContent = `${point.label}: ${point.value}`; path.append(title); svg.append(path); angle = next;
  });
  if (block.chart_type === 'donut') svg.append(svgNode('circle', { cx: 120, cy: 120, r: 49, class: 'donut-hole' }));
  const legend = element('ul', 'chart-legend');
  points.forEach((point, index) => {
    const item = element('li'); const swatch = element('span', 'legend-swatch');
    swatch.style.backgroundColor = chartColors[index % chartColors.length];
    item.append(swatch, element('span', '', `${point.label}: ${point.value}`)); legend.append(item);
  });
  wrapper.append(svg, legend); return wrapper;
}
function renderScatterChart(block) {
  const svg = svgNode('svg', { viewBox: '0 0 600 260', role: 'img', 'aria-label': block.fallback });
  const points = block.series.flatMap(series => series.points.map(point => ({ ...point, series: series.name })));
  const xs = points.map(point => point.x); const ys = points.map(point => point.y);
  const minX = Math.min(...xs); const maxX = Math.max(...xs); const minY = Math.min(...ys); const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1; const spanY = maxY - minY || 1;
  svg.append(svgNode('path', { d: 'M45 25 V220 H575', class: 'chart-axis' }));
  block.series.forEach((series, seriesIndex) => series.points.forEach(point => {
    const dot = svgNode('circle', {
      cx: 45 + ((point.x - minX) / spanX) * 510,
      cy: 210 - ((point.y - minY) / spanY) * 170,
      r: 6, fill: chartColors[seriesIndex % chartColors.length], class: 'scatter-dot',
    });
    const title = svgNode('title'); title.textContent = `${series.name} ${point.label || ''}: ${point.x}, ${point.y}`; dot.append(title); svg.append(dot);
  }));
  return svg;
}
function renderMultiBarChart(block) {
  const labels = block.series[0].points.map(point => point.label);
  const maximum = block.chart_type === 'stacked_bar'
    ? Math.max(...labels.map((label, index) => block.series.reduce((sum, series) => sum + series.points[index].value, 0)), 1)
    : Math.max(...block.series.flatMap(series => series.points.map(point => point.value)), 1);
  const chart = element('div', `multi-bar ${block.chart_type}`);
  labels.forEach((label, pointIndex) => {
    const row = element('div', 'multi-bar-row'); row.append(element('span', 'chart-label', label));
    const bars = element('div', 'multi-bar-values');
    block.series.forEach((series, seriesIndex) => {
      const point = series.points[pointIndex]; const bar = element('span', 'multi-bar-segment');
      bar.style.width = `${Math.max(1, (point.value / maximum) * 100)}%`;
      bar.style.backgroundColor = chartColors[seriesIndex % chartColors.length];
      bar.title = `${series.name}: ${point.value}`; bar.setAttribute('aria-label', bar.title); bars.append(bar);
    });
    row.append(bars); chart.append(row);
  });
  const legend = element('div', 'inline-legend');
  block.series.forEach((series, index) => { const swatch = element('span', 'legend-swatch'); swatch.style.backgroundColor = chartColors[index % chartColors.length]; legend.append(swatch, element('span', '', series.name)); });
  chart.append(legend); return chart;
}
function renderChartBlock(block) {
  if (block.chart_type === 'pie' || block.chart_type === 'donut') return renderPieChart(block);
  if (block.chart_type === 'scatter') return renderScatterChart(block);
  if (block.chart_type === 'grouped_bar' || block.chart_type === 'stacked_bar') return renderMultiBarChart(block);
  const chart = element('div', `data-chart ${block.chart_type}`);
  const values = [];
  block.series.forEach(series => series.points.forEach(point => values.push(point.value)));
  const minimum = Math.min(0, ...values); const maximum = Math.max(0, ...values);
  const span = maximum - minimum || 1;
  if (block.chart_type === 'line' || block.chart_type === 'area') {
    block.series.forEach(series => {
      const group = element('section', 'chart-series line-series');
      group.append(element('h5', '', series.name));
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 600 220');
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', `${series.name}: ${series.points.map(point => `${point.label} ${point.value}`).join(', ')}`);
      const coordinates = series.points.map((point, index) => ({
        x: series.points.length === 1 ? 300 : 45 + (index / (series.points.length - 1)) * 510,
        y: 175 - ((point.value - minimum) / span) * 135,
        point,
      }));
      const axis = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      axis.setAttribute('d', 'M 38 28 V 180 H 570'); axis.setAttribute('class', 'chart-axis'); svg.append(axis);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
      line.setAttribute('points', coordinates.map(item => `${item.x},${item.y}`).join(' '));
      line.setAttribute('class', 'chart-line');
      if (block.chart_type === 'area') {
        const area = svgNode('polygon', {
          points: `45,180 ${coordinates.map(item => `${item.x},${item.y}`).join(' ')} 555,180`,
          class: 'chart-area',
        });
        svg.append(area);
      }
      svg.append(line);
      coordinates.forEach(item => {
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', item.x); dot.setAttribute('cy', item.y); dot.setAttribute('r', '5'); dot.setAttribute('class', 'chart-dot');
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${item.point.label}: ${item.point.value}`; dot.append(title); svg.append(dot);
      });
      group.append(svg);
      const labels = element('div', 'line-labels');
      series.points.forEach(point => labels.append(element('span', '', point.label)));
      group.append(labels); chart.append(group);
    });
    return chart;
  }
  block.series.forEach(series => {
    const group = element('section', 'chart-series');
    group.append(element('h5', '', series.name));
    series.points.forEach(point => {
      const row = element('div', 'chart-row');
      row.append(element('span', 'chart-label', point.label));
      const track = element('span', 'chart-track'); const bar = element('span', 'chart-bar');
      bar.style.width = `${Math.max(2, ((point.value - minimum) / span) * 100)}%`;
      track.append(bar); row.append(track, element('span', 'chart-value', String(point.value))); group.append(row);
    });
    chart.append(group);
  });
  return chart;
}
function renderTimelineBlock(block) {
  const timeline = element('ol', 'timeline-visual');
  block.items.forEach(item => {
    const entry = element('li');
    entry.append(element('time', 'timeline-date', item.date), element('strong', '', item.label));
    if (item.detail) entry.append(element('p', '', item.detail)); timeline.append(entry);
  });
  return timeline;
}
const presentationRenderers = {
  table: renderTableBlock,
  diagram: renderDiagramBlock,
  chart: renderChartBlock,
  timeline: renderTimelineBlock,
};
function renderPresentationBlock(block) {
  const figure = element('figure', `visual-card visual-${block.type}`);
  figure.setAttribute ? figure.setAttribute('aria-label', `${block.type}: ${block.title}`) : null;
  const format = block.type === 'chart' ? block.chart_type : (block.type === 'diagram' ? 'flow' : block.type);
  if (figure.setAttribute) figure.setAttribute('data-visual-format', format);
  figure.append(element('h4', '', block.title));
  if (block.source_scope === 'illustrative') {
    figure.append(element('span', 'visual-scope', 'Illustrative values'));
  }
  const renderer = presentationRenderers[block.type];
  if (renderer) figure.append(renderer(block));
  if (block.caption) figure.append(element('figcaption', '', block.caption));
  figure.append(visualFallback(block)); return figure;
}
function renderSources(citations) {
  if (!citations || !citations.length) return null;
  const section = element('section', 'source-section');
  section.append(element('h4', '', 'Sources'));
  const list = element('div', 'source-list');
  citations.forEach((citation, index) => {
    const link = element('a', 'source-card');
    link.href = citation.display_url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.append(element('span', 'source-number', String(index + 1)), element('span', 'source-title', citation.title));
    if (citation.source_role !== 'unknown') link.append(element('span', 'source-role', readable(citation.source_role)));
    list.append(link);
  });
  section.append(list); return section;
}
function addMessage(role, content, extra = '', presentation = null, createdAt = null) {
  const node = element('div', `bubble ${role} ${extra}`);
  if (role === 'assistant') {
    const envelope = presentation && [1, 2].includes(presentation.schema_version) ? presentation : null;
    const body = element('div', 'message-body');
    renderRichText(body, envelope ? envelope.text : content, envelope ? envelope.citations : []);
    node.append(body);
    if (envelope) envelope.blocks.forEach(block => node.append(renderPresentationBlock(block)));
    const sources = envelope && renderSources(envelope.citations); if (sources) node.append(sources);
  } else node.textContent = content;
  addMessageTimestamp(node, createdAt);
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}
function renderMediaLifecycle(node, media) {
  if (!node || !media || !media.length) return;
  const section = element('section', 'media-lifecycle'); section.append(element('h4', '', 'Attachments'));
  media.forEach(item => {
    const retention = item.library_retention || { status: 'temporary_not_retained' };
    const card = element('div', `media-lifecycle-item status-${retention.status || 'unknown'}`);
    card.append(element('strong', '', item.name || 'Attachment'));
    if (retention.status === 'retained') {
      const extraction = retention.extraction || {};
      card.append(element('span', 'library-state success', extraction.status === 'searchable'
        ? `Kept in Library · ${extraction.segment_count} page segment(s) searchable`
        : extraction.status === 'failed' ? 'Kept in Library · extraction needs attention' : 'Kept in Library'));
      if (extraction.status === 'failed') card.append(element('small', 'test-failure', extraction.message || 'Extraction failed; retry from Library.'));
    } else if (retention.status === 'failed') {
      card.append(element('span', 'library-state warning', 'Keep in Library failed'));
      card.append(element('small', 'test-failure', retention.message || 'The original was not retained.'));
    } else card.append(element('span', 'library-state', 'Temporary · not retained'));
    section.append(card);
  });
  node.append(section);
}
function renderContextInspectorDetails(details, value) {
  clearNode(details);
  const status = value.composition_status === 'retrieved_context_used'
    ? 'Retrieved context was used.' : 'No retrieved evidence was used.';
  details.append(element('p', 'context-inspector-status', status));
  const profile = value.purpose_profile || {};
  details.append(element('p', 'meta', `Purpose: ${readable(profile.purpose || 'unknown')} · Profile ${profile.profile_version || 'unknown'}`));
  const domains = Object.entries(value.source_domains || {});
  details.append(element('p', '', domains.length
    ? `Sources: ${domains.map(([domain, count]) => `${readable(domain)} (${count})`).join(', ')}`
    : 'Sources: none'));
  const selected = Array.isArray(value.selected_evidence_ids) ? value.selected_evidence_ids.length : 0;
  const omitted = Array.isArray(value.omitted_evidence_ids) ? value.omitted_evidence_ids.length : 0;
  details.append(element('p', '', `Selected ${selected} · Omitted ${omitted}`));
  const indicators = value.indicators || {};
  details.append(element('p', '', `Contradiction groups ${(indicators.contradiction_group_ids || []).length} · Ambiguity sets ${(indicators.ambiguity_set_ids || []).length} · Uncertain sources ${indicators.uncertain_source_count || 0}`));
  const transmission = value.transmission || {};
  details.append(element('p', '', `Final evidence authorization: ${readable(transmission.status || 'unknown')}`));
  if ((value.warnings || []).length) details.append(element('p', 'context-inspector-warning', `Warnings: ${value.warnings.map(readable).join(', ')}`));
  if ((value.exclusions || []).length) details.append(element('p', 'meta', `${value.exclusions.length} policy exclusion(s) recorded.`));
  const evidence = element('details', 'technical-details');
  evidence.append(element('summary', '', 'Receipt and Replay references'), element('pre', '', JSON.stringify({
    context_receipt_id: value.context_receipt_id, package_id: value.package_id,
    allocation_policy_version: value.allocation_policy_version,
    permit_manifest_id: transmission.manifest_id || null, replay: value.replay || null,
  }, null, 2)));
  details.append(evidence);
  renderContextFeedback(details, value);
}
const contextFeedbackOptions = [
  ['context_helped', 'Context helped'],
  ['context_irrelevant', 'Context was irrelevant'],
  ['important_context_missing', 'Important context was missing'],
  ['wrong_source_or_history', 'Wrong source or history'],
  ['clarification_preferred', 'Clarification would have been better'],
];
function renderContextFeedback(details, value) {
  const section = element('section', 'context-feedback');
  section.append(element('p', 'context-feedback-prompt', 'Was this context choice useful?'));
  const controls = element('div', 'context-feedback-controls');
  const statusNode = element('p', 'context-feedback-status');
  let pending = false; let recorded = false; let chosen = null;
  const buttons = contextFeedbackOptions.map(([feedbackType, label]) => {
    const button = element('button', 'context-feedback-choice', label);
    button.type = 'button'; button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', async () => {
      if (pending || recorded || chosen !== null) return;
      pending = true; chosen = feedbackType; buttons.forEach(item => { item.disabled = true; });
      button.setAttribute('aria-pressed', 'true'); statusNode.textContent = 'Recording feedback…';
      try {
        await request(`/api/chat/messages/${encodeURIComponent(value.response_message_id)}/context-feedback`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
            feedback_type: feedbackType, context_receipt_id: value.context_receipt_id,
            package_id: value.package_id,
            allocation_decision_sha256: (value.allocation || {}).decision_sha256 || null,
            transmission_manifest_id: (value.transmission || {}).manifest_id || null,
            replay_flight_id: (value.replay || {}).flight_id || null,
          }),
        });
        recorded = true; statusNode.textContent = 'Feedback recorded as Development evidence. It changes nothing automatically.';
      } catch (error) {
        statusNode.classList.add('context-inspector-error');
        statusNode.textContent = `Feedback was not recorded: ${error.message}`;
        chosen = null; buttons.forEach(item => { item.disabled = false; }); button.setAttribute('aria-pressed', 'false');
      } finally { pending = false; }
    });
    return button;
  });
  controls.append(...buttons); section.append(controls, statusNode); details.append(section);
}
function renderContextInspector(node, message) {
  if (!node || !message || message.role !== 'assistant' || message.context_inspector_available !== true
      || typeof message.message_id !== 'string') return null;
  const container = element('details', 'context-inspector');
  const summary = element('summary', '', 'Why this context?');
  const body = element('div', 'context-inspector-body');
  body.append(element('p', 'meta', 'Open to inspect body-free composition evidence.'));
  container.append(summary, body); node.append(container);
  let loaded = false;
  container.addEventListener('toggle', async () => {
    if (!container.open || loaded) return;
    loaded = true; replaceContent(body, element('p', 'meta', 'Loading context evidence…'));
    try {
      const value = await request(`/api/chat/messages/${encodeURIComponent(message.message_id)}/context-inspector`);
      if (!value || value.contains_source_bodies !== false || !value.authority || value.authority.creates_authority !== false) {
        throw new Error('The context evidence was malformed and was not displayed.');
      }
      renderContextInspectorDetails(body, value);
    } catch (error) {
      replaceContent(body, element('p', 'context-inspector-error', `Context inspection unavailable: ${error.message}`));
    }
  });
  return container;
}
function showError(message) { addMessage('error', message); }
async function request(url, options = {}) {
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller ? window.setTimeout(() => controller.abort(), 15000) : null;
  let response;
  try { response = await fetch(url, { credentials: 'same-origin', ...options, signal: controller ? controller.signal : options.signal, headers: { ...headers(), ...(csrfToken ? {'X-Fawkes-CSRF-Token': csrfToken} : {}), ...(options.headers || {}) } }); }
  catch (error) { const safe = new Error(error && error.name === 'AbortError' ? 'Fawkes did not answer within 15 seconds. Reload this exact decision link or check Fawkes Status.' : 'Fawkes could not be reached. Reload this exact decision link or check Fawkes Status.'); safe.code='request_unavailable'; throw safe; }
  finally { if (timer) window.clearTimeout(timer); }
  const data = await response.json().catch(() => ({ error: { message: 'Fawkes is unavailable right now.' } }));
  if (response.status === 401) { auth.classList.remove('hidden'); throw new Error('Access token required.'); }
  if (!response.ok) {
    const error = new Error((data.error && data.error.message) || 'Fawkes is unavailable right now.');
    error.status = response.status; error.code = data.error && data.error.code;
    error.payload = data;
    throw error;
  }
  return data;
}

function canonicalAttentionIdentity(attention) {
  const binding=attention.protocol_binding||{};
  return {attention_id:attention.attention_id,campaign_id:attention.campaign_id,invocation_id:attention.invocation_id,rider_id:binding.rider_id||'tanner',recipient_sha256:binding.recipient_sha256||null,approval_binding_kind:binding.approval_binding_kind||null,approval_binding_sha256:binding.approval_binding_sha256||null,review_package_id:binding.review_package_id||null,review_package_record_sha256:binding.review_package_record_sha256||null,reviewer_worker_id:binding.reviewer_worker_id||null,reviewer_identity_sha256:binding.reviewer_identity_sha256||null,reviewer_invocation_id:binding.reviewer_invocation_id||null,candidate_snapshot_id:binding.candidate_snapshot_id||null,candidate_record_sha256:binding.candidate_record_sha256||null,mutation_digest_sha256:binding.mutation_digest_sha256||binding.workspace_changes_sha256||null,exact_change_evidence_sha256:binding.exact_change_evidence_sha256||null,authorized_scope_sha256:binding.authorized_scope_sha256||binding.allowed_scope_sha256||null,method:binding.method||null,item_id:binding.item_id||null,action_digest:binding.approved_action_sha256||null,protocol_binding_sha256:attention.protocol_binding_sha256||null,expires_at:attention.expires_at||null,decision_nonce:attention.decision_nonce||null};
}

function canonicalAttentionIdentityMatches(attention, expected, expectedAuthorityBindingSha256) {
  if (!attention || !expected) return false;
  return JSON.stringify(canonicalAttentionIdentity(attention)) === JSON.stringify(expected)
    && typeof expectedAuthorityBindingSha256 === 'string'
    && attention.authority_binding_sha256 === expectedAuthorityBindingSha256;
}

function canonicalDecisionIdentityMatches(decision, expected, expectedAuthorityBindingSha256, choice) {
  if (!decision || decision.attention_id !== expected.attention_id
      || decision.campaign_id !== expected.campaign_id
      || decision.invocation_id !== expected.invocation_id
      || decision.choice !== choice
      || decision.protocol_binding_sha256 !== expected.protocol_binding_sha256
      || decision.authority_binding_sha256 !== expectedAuthorityBindingSha256
      || typeof decision.decision_id !== 'string' || !decision.decision_id
      || typeof decision.record_sha256 !== 'string' || !decision.record_sha256
      || decision.creates_continuing_authority !== false) return false;
  const binding=decision.authority_binding||{};
  return JSON.stringify(binding) === JSON.stringify(expected);
}

function requireCanonicalDecisionResult(result, expected, expectedAuthorityBindingSha256, choice) {
  if (!result || !canonicalAttentionIdentityMatches(result.attention, expected, expectedAuthorityBindingSha256)
      || !canonicalDecisionIdentityMatches(result.decision, expected, expectedAuthorityBindingSha256, choice)) {
    throw Object.assign(new Error('Fawkes returned a mismatched decision lifecycle. The page was refreshed without trusting it.'),
      {code:'decision_response_mismatch',status:409});
  }
  return result;
}

function canonicalFailureDecisionResult(result, expected, expectedAuthorityBindingSha256, choice) {
  if (!result || !canonicalAttentionIdentityMatches(
      result.attention, expected, expectedAuthorityBindingSha256)) return null;
  if (result.decision != null && !canonicalDecisionIdentityMatches(
      result.decision, expected, expectedAuthorityBindingSha256, choice)) return null;
  return {attention:result.attention,decision:result.decision||null};
}

function clarificationViewModel(value) {
  if (!value || value.clarification_required !== true || typeof value.decision_id !== 'string'
      || typeof value.resulting_retrieval_plan_identity !== 'string' || !Array.isArray(value.ambiguity_sets)) return null;
  const ambiguity = value.ambiguity_sets.find(item => item && item.clarification_required === true);
  if (!ambiguity || typeof ambiguity.ambiguity_set_id !== 'string' || !Array.isArray(ambiguity.choices)
      || ambiguity.choices.length < 2) return null;
  const choices = ambiguity.choices.map(item => item && typeof item.choice_id === 'string'
    && typeof item.label === 'string' && item.label.trim()
    ? { choiceId: item.choice_id, label: item.label.trim() } : null);
  if (choices.some(item => !item) || new Set(choices.map(item => item.choiceId)).size !== choices.length) return null;
  return { decisionId: value.decision_id, retrievalPlanIdentity: value.resulting_retrieval_plan_identity,
    ambiguitySetId: ambiguity.ambiguity_set_id, choices };
}

function clarificationFailureMessage(error) {
  if (error && error.code === 'invalid_clarification') return 'That choice is no longer valid for this turn. Please ask the question again.';
  if (error && error.code === 'conversation_changed') return 'The conversation changed before that choice was submitted. Please ask the question again.';
  return `I couldn't submit that choice. ${error && error.message ? error.message : 'Please try again.'}`;
}

function renderRetrievalClarification(node, metadata, binding) {
  if (!metadata || metadata.clarification_required !== true) return null;
  const model = clarificationViewModel(metadata);
  const section = element('section', 'retrieval-clarification');
  section.setAttribute('aria-label', 'Clarify retrieved conversation');
  const statusNode = element('p', 'clarification-status');
  statusNode.setAttribute('role', 'status'); statusNode.setAttribute('aria-live', 'polite');
  if (!model || !binding || typeof binding.originatingResponseMessageId !== 'string'
      || typeof binding.originalQuery !== 'string' || !binding.originalQuery.trim()) {
    statusNode.classList.add('clarification-failure');
    statusNode.textContent = 'These clarification choices are unavailable. Please ask the question again.';
    section.append(statusNode); node.append(section); return section;
  }
  const controls = element('div', 'clarification-choices');
  controls.setAttribute('role', 'group'); controls.setAttribute('aria-label', 'Choose what Fawkes should retrieve');
  const state = { submitting: false, consumed: false };
  const buttons = model.choices.map(choice => {
    const button = element('button', 'clarification-choice', choice.label);
    button.type = 'button'; button.setAttribute('aria-label', `Choose ${choice.label}`);
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', async () => {
      if (state.submitting || state.consumed || button.disabled) return;
      state.submitting = true; buttons.forEach(item => { item.disabled = true; });
      button.setAttribute('aria-pressed', 'true'); statusNode.textContent = `Using ${choice.label}…`;
      try {
        await submitChatTurn(`Use ${choice.label}.`, [], {
          originating_response_message_id: binding.originatingResponseMessageId,
          decision_id: model.decisionId,
          retrieval_plan_identity: model.retrievalPlanIdentity,
          ambiguity_set_id: model.ambiguitySetId,
          choice_id: choice.choiceId,
          original_query: binding.originalQuery,
        });
        state.consumed = true; statusNode.textContent = `Selected: ${choice.label}.`;
        buttons.forEach(item => { item.disabled = true; });
      } catch (error) {
        const terminal = error && (error.code === 'invalid_clarification' || error.code === 'conversation_changed');
        statusNode.classList.add('clarification-failure'); statusNode.textContent = clarificationFailureMessage(error);
        if (!terminal) buttons.forEach(item => { item.disabled = false; });
        button.setAttribute('aria-pressed', 'false');
      } finally { state.submitting = false; }
    });
    return button;
  });
  controls.append(...buttons); section.append(controls, statusNode); node.append(section); return section;
}
async function loadChat(loginAttempt = false) {
  status.textContent = 'Connecting…';
  setAuthError('');
  if (loginAttempt) { connect.disabled = true; connect.textContent = 'Connecting…'; }
  try {
    const data = await request('/api/chat');
    auth.classList.add('hidden');
    conversationId = data.conversation.conversation_id;
    document.querySelector('#phoenix-name').textContent = data.phoenix.name;
    emitWindowEvent('fawkes:connected', { token, phoenix: data.phoenix });
    clearNode(messages);
    data.messages.forEach(message => { const node = addMessage(message.role, message.content, '', message.presentation, message.created_at); renderMediaLifecycle(node, message.media); renderContextInspector(node, message); });
    if (!data.messages.length) addMessage('empty', 'This is the same Fawkes, in a new place. Start wherever you are.');
    status.textContent = 'Present';
    const lastMessage = data.messages.length ? data.messages[data.messages.length - 1] : null;
    if (lastMessage && lastMessage.role === 'user') recoverReply(lastMessage.message_id);
    return true;
  } catch (error) {
    status.textContent = 'Offline';
    if (error.message === 'Access token required.') {
      if (loginAttempt) setAuthError('That access token was not accepted. Check it and try again.');
    } else {
      auth.classList.remove('hidden');
      setAuthError(`Could not connect to Fawkes at ${window.location.origin}. ${error.message}`);
    }
    return false;
  } finally {
    if (loginAttempt) { connect.disabled = false; connect.textContent = 'Connect'; }
  }
}

function wait(milliseconds) {
  return new Promise(resolve => window.setTimeout(resolve, milliseconds));
}

async function recoverReply(userMessageId) {
  const generation = ++recoveryGeneration;
  send.disabled = true;
  status.textContent = 'Finishing the pending reply…';
  for (let attempt = 0; attempt < 30 && generation === recoveryGeneration; attempt += 1) {
    await wait(3000);
    try {
      const data = await request('/api/chat');
      const index = data.messages.findIndex(message => message.message_id === userMessageId);
      const reply = index >= 0 ? data.messages[index + 1] : null;
      if (reply && reply.role === 'assistant') {
        clearNode(messages);
        data.messages.forEach(message => { const node = addMessage(message.role, message.content, '', message.presentation, message.created_at); renderContextInspector(node, message); });
        status.textContent = 'Present';
        send.disabled = false;
        return;
      }
    } catch (error) {
      // The normal connection UI handles authentication. Keep this recovery
      // path quiet while a request is still completing server-side.
    }
  }
  if (generation === recoveryGeneration) {
    status.textContent = 'Reply delayed — your message is preserved';
    send.disabled = false;
  }
}

function pill(value) { return element('span', 'pill', readable(value)); }
function emptyState(text) { replaceContent(developerContent, element('p', 'dev-empty', text)); }
function observationCard(record) {
  const card = element('button', 'dev-card');
  card.type = 'button';
  card.dataset.observationId = record.observation_id;
  card.append(pill(record.category), pill(record.status));
  card.append(element('h3', '', record.observed_pattern || record.current_interpretation));
  if (record.rider_evaluation) card.append(pill(`rider: ${record.rider_evaluation}`));
  if (record.development_signal) card.append(pill(`signal: ${record.development_signal}`));
  if (record.longitudinal_status) card.append(pill(record.longitudinal_status));
  card.append(element('p', '', record.uncertainty));
  card.append(element('p', 'meta', `${(record.evidence && record.evidence.length) || 0} evidence item(s) · ${dateLabel(record.updated_at)}`));
  return card;
}
function proposalCard(record) {
  const card = element('article', 'dev-card');
  card.append(pill(record.category), pill(record.status));
  card.append(element('h3', '', record.observation || 'Development proposal'));
  card.append(element('p', '', record.proposed_change || 'No proposed change recorded.'));
  card.append(element('p', 'meta', `${readable(record.origin || 'legacy proposal')} · ${dateLabel(record.created_at)}`));
  return card;
}
function reviewCard(record) {
  const card = element('article', 'dev-card');
  card.append(pill(record.status), pill(record.source));
  card.append(element('h3', '', record.reason || 'Human review item'));
  card.append(element('p', '', record.content || 'No content recorded.'));
  card.append(element('p', 'meta', dateLabel(record.created_at)));
  if (record.source === 'development_proposal' && record.status === 'needs_review') {
    const actions = element('div', 'review-actions');
    ['approve', 'reject'].forEach(decision => {
      const button = element('button', `review-${decision}`, decision === 'approve' ? 'Approve proposal' : 'Reject');
      button.type = 'button';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          await request(`/api/development/proposals/${encodeURIComponent(record.candidate_id)}/review`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision }),
          });
          await loadDeveloper();
        } catch (error) { showError(error.message); button.disabled = false; }
      });
      actions.append(button);
    });
    card.append(actions, element('p', 'meta', 'Approval records a rider decision only; it does not automatically alter personality, prompts, memory, policy, or code.'));
  }
  return card;
}
function testPlatform() {
  return { client: 'web', device: window.innerWidth <= 600 ? 'mobile_viewport' : 'desktop_viewport',
    color_scheme: window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark' };
}
function acceptanceBlock(type) {
  if (type === 'table') return { type: 'table', title: 'Acceptance comparison', caption: '', fallback: 'Alpha is ready; Beta is reviewing.', source_scope: 'synthetic_test_fixture', source_urls: [], columns: ['Item', 'Status'], rows: [['Alpha', 'Ready'], ['Beta', 'Reviewing']] };
  if (type === 'diagram') return { type: 'diagram', title: 'Acceptance flow', caption: '', fallback: 'Request leads to capability, then visible result.', source_scope: 'synthetic_test_fixture', source_urls: [], direction: 'horizontal', nodes: [{ id: 'request', label: 'Rider request' }, { id: 'capability', label: 'Capability' }, { id: 'result', label: 'Visible result' }], edges: [{ from: 'request', to: 'capability', label: '' }, { from: 'capability', to: 'result', label: '' }] };
  if (type === 'timeline') return { type: 'timeline', title: 'Acceptance timeline', caption: '', fallback: 'Requested, tested, visible.', source_scope: 'synthetic_test_fixture', source_urls: [], items: [{ date: 'Step 1', label: 'Requested', detail: '' }, { date: 'Step 2', label: 'Tested', detail: '' }, { date: 'Step 3', label: 'Visible', detail: '' }] };
  const values = { pie: 100, bar: 80, line: 60, donut: 40 };
  return { type: 'chart', chart_type: type, title: `${readable(type)} acceptance`, caption: '', fallback: `${type} chart test fixture.`, source_scope: 'synthetic_test_fixture', source_urls: [], x_label: 'Metric', y_label: 'Value', series: [{ name: 'Acceptance', points: [{ label: 'Visible', value: values[type] }, { label: 'Fallback', value: type === 'line' ? 30 : 0 }] }] };
}
function validateAcceptanceBlock(block) {
  if (!block || typeof block !== 'object') throw new Error('Presentation result is not an object.');
  if (!presentationRenderers[block.type]) throw new Error(`Unsupported presentation type: ${block.type || 'missing'}.`);
  if (typeof block.title !== 'string' || typeof block.fallback !== 'string') throw new Error('Presentation title or text fallback is missing.');
  if (block.type === 'timeline' && !Array.isArray(block.items)) throw new Error('Timeline result is missing its items array.');
  if (block.type === 'chart' && (!Array.isArray(block.series) || block.series.some(series => !Array.isArray(series.points)))) throw new Error('Chart result is missing series/points data.');
  if (block.type === 'table' && (!Array.isArray(block.columns) || !Array.isArray(block.rows))) throw new Error('Table result is missing columns/rows data.');
  if (block.type === 'diagram' && (!Array.isArray(block.nodes) || !Array.isArray(block.edges))) throw new Error('Diagram result is missing nodes/edges data.');
}
function renderAcceptanceBlocks(preview, blocks) {
  clearNode(preview); const rendered = []; const errors = [];
  (Array.isArray(blocks) ? blocks : []).forEach((block, index) => {
    try { validateAcceptanceBlock(block); const node = renderPresentationBlock(block); preview.append(node); rendered.push(node); }
    catch (error) {
      errors.push({ index, message: error.message });
      const failure = element('article', 'acceptance-render-error');
      failure.append(element('strong', '', 'Preview unavailable'), element('p', '', error.message)); preview.append(failure);
    }
  });
  return { rendered, errors };
}
async function runClientProbe(test, preview) {
  const began = performance.now();
  if (test.client_probe === 'event_audio') {
    let result = 'pass'; let actual = ''; let failureStage = null;
    try {
      if (!eventAudio.preferences) await loadSoundSettings();
      const occurrence = `acceptance-${test.run_id}`;
      const first = await eventAudio.emit({ event_id: 'message.sent', occurrence_id: occurrence });
      const second = await eventAudio.emit({ event_id: 'message.sent', occurrence_id: occurrence });
      if (second.status !== 'duplicate_or_invalid') throw new Error('Duplicate semantic event was not suppressed.');
      if (!['played', 'asset_unavailable', 'playback_unavailable', 'playback_blocked', 'disabled'].includes(first.status)) throw new Error(`Unexpected playback status: ${first.status}`);
      actual = `Browser controller handled event (${first.status}); duplicate suppressed. Physical audibility requires rider/device verification.`;
      replaceContent(preview, element('p', 'meta', actual));
    } catch (error) { result = 'fail'; failureStage = 'client event-audio controller'; actual = error.message; }
    await request(`/api/development/test-center/runs/${encodeURIComponent(test.run_id)}/complete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ result, actual, duration_ms: performance.now() - began, failure_stage: failureStage, technical_details: { probe: test.client_probe, physical_audio_verified: false } }) });
    return [];
  }
  if (test.client_probe === 'phoenix_presence') {
    let result = 'pass', failureStage = null, actual = '';
    try {
      const api = window.FawkesPresence; const controller = api && api.controller;
      if (!controller || !controller.profile) throw new Error('Presence controller or profile is not mounted');
      const before = api.health(); controller.invoke(); const after = api.health();
      const host = document.querySelector('#presence-render-host');
      if (!host || host.dataset.visible !== 'true') throw new Error('Presence surface is not visibly mounted');
      if (after.state !== 'invoked') throw new Error(`Invocation did not reach Presence; state=${after.state}`);
      actual = `${after.renderer.renderer} renderer visible; invocation transitioned ${before.state} → ${after.state}; 3D physical verification=${after.renderer.assetLoaded === true}`;
    } catch (error) { result = 'fail'; failureStage = 'client Presence rendering/interaction'; actual = error.message; }
    const health = window.FawkesPresence && window.FawkesPresence.health();
    await request(`/api/development/test-center/runs/${encodeURIComponent(test.run_id)}/complete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ result, actual, duration_ms: performance.now() - began, failure_stage: failureStage, technical_details: { probe: test.client_probe, physical_device_verified: false, three_dimensional_verified: !!(health && health.renderer && health.renderer.assetLoaded) } }) });
    return [];
  }
  let blocks = [];
  if (test.client_probe === 'four_charts') blocks = ['pie', 'bar', 'line', 'donut'].map(acceptanceBlock);
  if (test.client_probe === 'table') blocks = [acceptanceBlock('table')];
  if (test.client_probe === 'diagram') blocks = [acceptanceBlock('diagram')];
  if (test.client_probe === 'timeline') blocks = [acceptanceBlock('timeline')];
  if (test.client_probe === 'malformed_timeline') blocks = [{ ...acceptanceBlock('timeline'), items: undefined }];
  // Retain the exact probe payload before reporting completion. Any polling
  // refresh that observes PASS/FAIL can therefore render the same preview
  // atomically instead of briefly showing a result with an empty body.
  testProbePreviews[test.test_id] = blocks;
  let result = 'pass'; let failureStage = null; let actual = '';
  try {
    const outcome = renderAcceptanceBlocks(preview, blocks);
    if (outcome.errors.length) throw new Error(outcome.errors.map(item => item.message).join('; '));
    const rendered = outcome.rendered;
    const formats = [...rendered].map(node => node.getAttribute('data-visual-format'));
    if (rendered.length !== blocks.length) throw new Error(`Expected ${blocks.length} visible blocks; found ${rendered.length}.`);
    if (formats.some((value, index) => value !== (blocks[index].chart_type || (blocks[index].type === 'diagram' ? 'flow' : blocks[index].type)))) throw new Error('Rendered formats did not match the structured payload.');
    actual = `${rendered.length} visible visualization(s): ${formats.join(' / ')}`;
  } catch (error) { result = 'fail'; failureStage = 'client rendering'; actual = error.message; }
  await request(`/api/development/test-center/runs/${encodeURIComponent(test.run_id)}/complete`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ result, actual, duration_ms: performance.now() - began, failure_stage: failureStage,
      technical_details: { probe: test.client_probe, browser_component: 'renderPresentationBlock' } }),
  });
  return blocks;
}
async function failClientProbe(test, error) {
  try {
    await request(`/api/development/test-center/runs/${encodeURIComponent(test.run_id)}/complete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result: 'fail', actual: error && error.message ? error.message : 'Unexpected client probe failure.', duration_ms: 0, failure_stage: 'client probe orchestration', technical_details: { probe: test.client_probe } }),
    });
  } catch (completionError) { /* The next snapshot remains honest if transport itself is unavailable. */ }
}
function showProbeResult(testId, blocks) {
  testProbePreviews[testId] = blocks;
  const preview = developerContent.querySelector(`[data-preview-for="${testId}"]`);
  if (!preview) return;
  renderAcceptanceBlocks(preview, blocks);
}
function statusLabel(value) { return readable(value).toUpperCase(); }
function renderTestCenter() {
  clearNode(developerContent);
  if (!testCenterData) { emptyState('Loading Capability Test Center…'); return; }
  const header = element('section', 'test-summary');
  const summary = testCenterData.summary;
  header.append(element('div', 'test-summary-row'));
  header.firstChild.append(element('div', '', `${summary.passing} / ${summary.total} PASSING`));
  const all = element('button', 'test-all', 'TEST ALL'); all.type = 'button'; all.dataset.testAll = 'true'; header.firstChild.append(all);
  const meter = element('div', 'test-meter'); const fill = element('span', ''); fill.style.width = `${summary.total ? (summary.passing / summary.total) * 100 : 0}%`; meter.append(fill); header.append(meter);
  header.append(element('p', 'meta', 'Manual rider runs, automated coverage, and end-to-end/UI evidence remain separate. Gray means no rider run—not success.'));
  developerContent.append(header);
  const groups = {};
  testCenterData.tests.forEach(test => { (groups[test.group] ||= []).push(test); });
  Object.entries(groups).forEach(([name, tests]) => {
    const group = element('section', 'test-group'); group.append(element('h3', '', name));
    tests.forEach(test => {
      const card = element('article', `test-card status-${test.status}`); card.dataset.testId = test.test_id;
      const top = element('div', 'test-card-top'); top.append(element('strong', '', test.title));
      top.append(element('span', 'test-status', statusLabel(test.status)));
      const button = element('button', 'test-one', test.status === 'testing' ? 'TESTING…' : 'TEST'); button.type = 'button'; button.dataset.runTest = test.test_id; button.disabled = !test.runnable || test.status === 'testing'; top.append(button); card.append(top);
      const layers = element('div', 'test-layers'); test.layers.forEach(layer => layers.append(pill(layer))); card.append(layers);
      if (test.status === 'testing') card.append(element('p', 'test-activity', 'Running now…'));
      if (test.missing_reason) card.append(element('p', 'test-missing', test.missing_reason));
      const run = test.last_run;
      if (run && run.status !== 'testing') {
        const details = element('details', 'test-details'); details.append(element('summary', '', 'View result'));
        details.append(element('p', '', `What was tested: ${test.what}`), element('p', '', `Expected: ${run.expected || test.expected}`), element('p', '', `Actual: ${run.actual || 'No result detail.'}`));
        if (run.failure_stage) details.append(element('p', 'test-failure', `Failure stage: ${run.failure_stage}`));
        details.append(element('p', 'meta', `Duration: ${Number(run.duration_ms || 0).toFixed(1)} ms · Last tested: ${dateLabel(run.completed_at)} · Version ${test.test_version}`));
        const technical = element('details', 'technical-details'); technical.append(element('summary', '', 'Technical details'), element('pre', '', JSON.stringify(run.technical_details || {}, null, 2))); details.append(technical); card.append(details);
      }
      const preview = element('div', 'acceptance-preview'); preview.dataset.previewFor = test.test_id; card.append(preview);
      if (testProbePreviews[test.test_id]) renderAcceptanceBlocks(preview, testProbePreviews[test.test_id]);
      group.append(card);
    });
    developerContent.append(group);
  });
}
async function loadTestCenter() {
  try { testCenterData = await request('/api/development/test-center'); renderTestCenter();
    const running = testCenterData.tests.some(item => item.status === 'testing');
    if (running && !testCenterPoll) testCenterPoll = window.setInterval(loadTestCenter, 700);
    if (!running && testCenterPoll) { window.clearInterval(testCenterPoll); testCenterPoll = null; }
  } catch (error) { emptyState(error.message); }
}
async function triggerAcceptance(testId) {
  const test = testCenterData.tests.find(item => item.test_id === testId);
  if (test) { test.status = 'testing'; renderTestCenter(); }
  const started = await request(`/api/development/test-center/tests/${encodeURIComponent(testId)}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ platform: testPlatform() }) });
  if (started.client_probe) {
    const preview = developerContent.querySelector(`[data-preview-for="${testId}"]`);
    let blocks = [];
    try { blocks = await runClientProbe(started, preview); }
    catch (error) { await failClientProbe(started, error); }
    await loadTestCenter(); showProbeResult(testId, blocks); return;
  }
  await loadTestCenter();
}
async function triggerAllAcceptance() {
  testCenterData.tests.filter(item => item.runnable && item.run_all).forEach(item => { item.status = 'testing'; }); renderTestCenter();
  const result = await request('/api/development/test-center/run-all', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ platform: testPlatform() }) });
  const probeResults = [];
  for (const started of result.tests.filter(item => item.client_probe)) {
    const preview = developerContent.querySelector(`[data-preview-for="${started.test_id}"]`);
    try { probeResults.push([started.test_id, await runClientProbe(started, preview)]); }
    catch (error) { await failClientProbe(started, error); probeResults.push([started.test_id, []]); }
  }
  await loadTestCenter();
  probeResults.forEach(([testId, blocks]) => showProbeResult(testId, blocks));
}
const PHOENIX_BOARD_CAMPAIGN_LIMIT = 6;
const PHOENIX_BOARD_ACTIVITY_LIMIT = 3;
function phoenixBoardText(value, fallback = 'Unavailable') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}
function phoenixBoardWorker(value, role) {
  const identity = value && typeof value === 'object' ? phoenixBoardText(value.worker_id) : 'Unavailable';
  const state = value && typeof value === 'object' ? phoenixBoardText(value.state, 'State unavailable') : 'State unavailable';
  return `${role}: ${identity} · ${state}`;
}
function phoenixBoardOutcome(record, activity) {
  const allowed = {
    succeeded: 'Accepted', cancelled: 'Rolled back / cancelled', failed: 'Rejected / failed safely',
    failed_safe: 'Rejected / failed safely', failed_rolled_back: 'Rolled back',
    rolled_back_after_evidence_failure: 'Rolled back'
  };
  if (allowed[record.status]) return allowed[record.status];
  for (let index = activity.length - 1; index >= 0; index -= 1) {
    const summary = activity[index] && activity[index].summary;
    const statusValue = summary && summary.status;
    if (allowed[statusValue]) return allowed[statusValue];
    if (statusValue === 'pass' || statusValue === 'accepted') return 'Accepted';
    if (statusValue === 'correction_required' || statusValue === 'rejected') return 'Rejected / correction required';
  }
  return 'No recent accepted, rejected, or rolled-back outcome';
}
function renderPhoenixBoard(campaigns, attentionItems) {
  const board = element('section', 'growth-card phoenix-board');
  board.append(element('h2', '', 'Worker Pulse / Phoenix Board'));
  board.append(element('p', 'meta', 'Read-only rebuild from the loaded campaign and Attention projections. It grants no authority.'));
  const boundedCampaigns = campaigns.slice(0, PHOENIX_BOARD_CAMPAIGN_LIMIT);
  if (!boundedCampaigns.length) {
    board.append(element('p', 'dev-empty', 'No campaign pulse is available.'));
    return board;
  }
  boundedCampaigns.forEach(record => {
    const activity = Array.isArray(record.activity) ? record.activity : [];
    const recent = activity.slice(-PHOENIX_BOARD_ACTIVITY_LIMIT);
    const pending = attentionItems.find(item => item && item.campaign_id === record.campaign_id && item.state === 'needs_tanner');
    const firstAt = activity.length ? Date.parse(activity[0].created_at) : NaN;
    const lastAt = activity.length ? Date.parse(activity[activity.length - 1].created_at) : NaN;
    const elapsed = Number.isFinite(firstAt) && Number.isFinite(lastAt) ? `${Math.max(0, Math.round((lastAt - firstAt) / 1000))}s recorded` : 'Unavailable';
    const latestSummary = recent.length && recent[recent.length - 1].summary && typeof recent[recent.length - 1].summary === 'object' ? recent[recent.length - 1].summary : null;
    const checkpoint = recent.length ? `${readable(phoenixBoardText(recent[recent.length - 1].kind, 'checkpoint unavailable'))} · ${dateLabel(recent[recent.length - 1].created_at)}` : 'Unavailable';
    const failure = latestSummary ? phoenixBoardText(latestSummary.failure, 'None reported') : 'None reported';
    const pulse = element('article', 'dev-card phoenix-board-campaign');
    pulse.append(element('h3', '', phoenixBoardText(record.campaign_id, 'Unknown campaign')));
    pulse.append(element('p', '', phoenixBoardText(record.objective, 'Objective unavailable')));
    pulse.append(element('p', 'meta', `${readable(phoenixBoardText(record.current_stage, record.status || 'unknown'))} · iteration ${record.iteration || 0}/${record.maximum_iterations || 0} · elapsed ${elapsed}`));
    pulse.append(element('p', '', phoenixBoardWorker(record.builder, 'Worker')),
      element('p', '', phoenixBoardWorker(record.reviewer, 'Reviewer')),
      element('p', '', `Active scope: ${latestSummary ? phoenixBoardText(latestSummary.task_scope_id) : 'Unavailable'}`),
      element('p', '', `Authority: ${record.creates_authority === false ? 'None created' : 'Unavailable — no authority inferred'}`),
      element('p', '', `Provider / model usage: Unavailable in canonical projection`),
      element('p', '', `Attention: ${pending ? `NEEDS_TANNER · ${phoenixBoardText(pending.why_required, 'Reason unavailable')}` : 'No pending NEEDS_TANNER request'}`),
      element('p', '', `Bounded deadline: ${pending && pending.expires_at ? dateLabel(pending.expires_at) : 'None present'}`),
      element('p', '', `Last checkpoint: ${checkpoint}`),
      element('p', '', `Last failure: ${failure}`),
      element('p', '', `External-state isolation: ${record.exact_worker_bodies_remain_in_worker_exchange === true && record.hidden_chain_of_thought_exposed === false ? 'Confirmed by projection' : 'Unavailable'}`),
      element('p', '', `Recent outcome: ${phoenixBoardOutcome(record, recent)}`));
    const away = recent.map(item => `${readable(phoenixBoardText(item.kind, 'activity'))} (${dateLabel(item.created_at)})`);
    pulse.append(element('p', 'meta', `While Tanner was away (${recent.length}/${PHOENIX_BOARD_ACTIVITY_LIMIT} most recent): ${away.length ? away.join(' · ') : 'No recent activity'}`));
    board.append(pulse);
  });
  if (campaigns.length > boundedCampaigns.length) board.append(element('p', 'meta', `${campaigns.length - boundedCampaigns.length} older campaign(s) omitted by the fixed board limit.`));
  return board;
}
function renderDeveloperSection() {
  if (developerSection === 'tests') { renderTestCenter(); return; }
  clearNode(developerContent);
  if (developerSection === 'attention') {
    const card = element('article', 'dev-card attention-decision-card');
    card.id = requestedAttentionId ? `attention-${requestedAttentionId}` : 'attention-inbox';
    if (!requestedAttentionId) {
      card.append(element('h2', '', 'Tanner Attention Inbox'));
      card.append(element('p', '', 'Select an exact pending request from a Fawkes notification or Campaigns.'));
      developerContent.append(card); return;
    }
    if (exactAttentionState && exactAttentionState.error) {
      card.append(element('h2', '', 'Attention request unavailable'));
      card.append(element('p', '', exactAttentionState.error));
      developerContent.append(card); return;
    }
    const attention = exactAttentionState && exactAttentionState.attention;
    const attentionDecision = exactAttentionState && exactAttentionState.decision;
    if (!attention) { card.append(element('h2', '', 'Loading exact Tanner decision…')); developerContent.append(card); return; }
    const exactAttentionSubmission=attentionSubmissions.get(attention.attention_id)||null;
    if (exactAttentionSubmission && exactAttentionSubmission.attention_id === attention.attention_id) {
      const status=exactAttentionSubmission.status;
      const heading=status==='submitting'?'Submitting exact decision…':status==='refreshing'?'Refreshing expired request…':status==='failed'?'Decision submission failed':status==='resolved'?'Decision recorded':'Decision status';
      const summary=status==='failed'?`${exactAttentionSubmission.code||'decision_submission_failed'} (${exactAttentionSubmission.http_status||'no HTTP status'}): ${exactAttentionSubmission.message}`:status==='submitting'?'Fawkes is validating this exact identity. Do not submit it again.':status==='refreshing'?'The displayed deadline elapsed. Controls are closed while canonical state is reloaded.':'The browser received the canonical resolved lifecycle.';
      const submission=element('section',status==='failed'?'attention-urgent':'attention-summary');
      submission.append(element('h2','',heading),element('p','attention-submission-status',summary));
      card.append(submission);
    }
    if (attention.state !== 'needs_tanner') {
      card.append(element('h2', '', 'This attention request is already resolved'));
      const outcome=(attentionDecision&&attentionDecision.lifecycle_state)||attention.approval_outcome||attention.state;
      const outcomeText={recorded_pending_consumption:'Tanner approved this exact action; delivery to its live or resumable consumer is pending.',consumed:'The exact one-time grant was consumed by the live invocation.',resumed:'A restart-safe bounded continuation consumed the exact one-time grant.',completed:'The exact approved action completed.',failed_safe:'The approved action or continuation failed safely without continuing authority.'}[outcome]||`Current state: ${readable(outcome)}.`;
      card.append(element('h3', '', 'Decision outcome'),element('p', '', outcomeText));
      if(attentionDecision)card.append(element('p','attention-receipt',`Recorded decision: ${readable(attentionDecision.choice)} — ${attention.campaign_id} — ${attention.attention_id}`));
      card.append(element('p', '', 'No continuing authority was created, and this resolved request cannot authorize another action.'));
      if(attentionDecision){const details=document.createElement('details');details.append(element('summary','','Technical lifecycle evidence'),element('pre','',JSON.stringify(attentionDecision,null,2)));card.append(details);}
      developerContent.append(card); return;
    }
    if (attention.expires_at) {
      const deadline=element('section','attention-urgent');
      const timezone=Intl.DateTimeFormat().resolvedOptions().timeZone||'local timezone';
      const remaining=element('p','attention-countdown');
      const updateRemaining=()=>{const deadlineMilliseconds=Date.parse(attention.expires_at);if(!Number.isFinite(deadlineMilliseconds)){remaining.textContent='Time remaining unavailable';return;}const seconds=Math.max(0,Math.ceil((deadlineMilliseconds-Date.now())/1000));const minutes=Math.floor(seconds/60);remaining.textContent=`Time remaining: ${minutes}m ${seconds%60}s`;if(seconds>0){window.setTimeout(updateRemaining,Math.min(1000,Math.max(1,deadlineMilliseconds-Date.now())));return;}const current=attentionSubmissions.get(attention.attention_id);if(!current||current.status!=='refreshing'){attentionSubmissions.set(attention.attention_id,{status:'refreshing',attention_id:attention.attention_id});renderDeveloperSection();window.setTimeout(()=>loadExactAttention({preserveSubmission:true}),0);}};
      deadline.append(element('h2','',`URGENT — TANNER DECISION REQUIRED BEFORE ${dateLabel(attention.expires_at)} (${timezone})`),remaining,
        element('p','',`Why this deadline exists: ${attention.expiration_reason||'The exact action has a bounded safety lifetime.'}`),
        element('p','',`If Tanner does nothing: ${attention.expiration_effect||'The request expires and fails closed.'}`),
        element('p','',attention.can_request_again===true?'Fawkes may create a new exact request with new evidence if the action is still required.':'A replacement request is not currently confirmed.'),
        element('p','',attention.work_lost===true?'Some work or opportunity may be lost at expiry.':'No completed work or opportunity is expected to be lost; the blocked action remains unperformed.'));
      card.append(deadline);updateRemaining();
    }
    if (attention.actionable === false || attention.consumer_state === 'unavailable' || (attention.expires_at && Date.parse(attention.expires_at) <= Date.now())) {
      card.append(element('h2', '', 'This approval is no longer available'));
      card.append(element('p', '', attention.consumer_state === 'unavailable' || attention.actionable === false ? 'The exact consumer is no longer verifiably live or safely resumable. Fawkes did not record a decision or grant.' : 'The displayed decision period expired. Fawkes did not record an approval.'));
      card.append(element('p', '', 'Historical evidence remains available below. No decision controls are offered; a still-required action needs a new exact request.'));
      const inactiveDetails=document.createElement('details');inactiveDetails.append(element('summary','','Historical technical evidence'),element('pre','',JSON.stringify({campaign_id:attention.campaign_id,invocation_id:attention.invocation_id,attention_id:attention.attention_id,consumer_state:attention.consumer_state,stored_consumer_state:attention.stored_consumer_state,consumer_unavailable_reason:attention.consumer_unavailable_reason,protocol_binding:attention.protocol_binding},null,2)));card.append(inactiveDetails);
      developerContent.append(card); return;
    }
    if (typeof attention.authority_binding_sha256 !== 'string' || !attention.authority_binding_sha256) {
      card.append(element('h2', '', 'This approval is unavailable'));
      card.append(element('p', '', 'The canonical Attention authority-binding identity is missing. No decision controls are offered.'));
      developerContent.append(card); return;
    }
    const rawAction=String(attention.blocked_action||'');
    const harmlessNoop=rawAction.includes('powershell.exe')&&rawAction.includes('exit 0');
    const actionSummary=harmlessNoop?'Run one no-op PowerShell command across the protected WSL-to-Windows boundary.':rawAction;
    const reversible=attention.reversible===true?'Confirmed reversible.':attention.reversible===false?'Not reversible.':'Not confirmed; the provider did not declare reversibility.';
    card.append(element('h2', '', 'Tanner: Fawkes is paused and needs your decision'));
    const qualification=attention.qualification_instruction||null;
    const qualificationChoice=qualification&&qualification.choice==='approve_once'?'Approve Once':qualification&&qualification.choice==='deny'?'Deny':null;
    const qualificationLabel=qualification&&qualification.label?qualification.label:null;
    [['Qualification instruction',qualificationChoice?`Qualification instruction: Select ${qualificationChoice} — ${qualificationLabel}. This synthetic instruction is separate from Fawkes’s low-risk recommendation and overrides neither real policy nor future decisions.`:'No qualification-specific choice is prescribed.'],
     ['What Fawkes wants to do',actionSummary],['Why Fawkes stopped',attention.why_required],
     ['Why Tanner’s permission is required','Crossing this protected operating-system boundary requires an exact authenticated Rider decision.'],
     ['What will change if approved',harmlessNoop?'The one command will run once and should make no persistent change.':'Only the exact requested action may run once.'],
     ['What will not change','No continuing authority, campaign scope, production release, credentials, or default policy will change.'],
     ['Who or what is affected','Only this Development campaign and its current Worker attempt.'],
     ['Risk level',harmlessNoop?'Low — the command exits successfully without writing files or changing configuration.':'Not automatically classified — review the stated action and material risks before deciding.'],
     ['Reversibility',reversible],['Permission duration',attention.expires_at?`One use before ${dateLabel(attention.expires_at)}; afterward it is stale.`:'No arbitrary countdown. This request remains pending until resolved or its underlying action becomes unavailable.'],
     ['Continuing authority','None. Approval is consumed by this exact action and cannot authorize later work.'],
     ['Fawkes’s risk-based recommendation',harmlessNoop?(qualificationChoice==='Deny'?'The action is low risk, but this qualification explicitly requires Deny; follow the qualification instruction.':'Approve Once is reasonable because the exact command is a no-op and creates no continuing authority.'):'No recommendation is available; Tanner should decide from the stated risk and scope.']].forEach(([label,value])=>{const section=element('section','attention-summary');section.append(element('h3','',label),element('p','',value));card.append(section);});
    const technical=document.createElement('details');technical.className='attention-technical';technical.append(element('summary','','Technical details'),element('pre','',JSON.stringify({campaign_id:attention.campaign_id,invocation_id:attention.invocation_id,worker:attention.worker,exact_action:attention.blocked_action,requested_authority:attention.requested_authority,resources:attention.resources,reversible:attention.reversible,expires_at:attention.expires_at,provider_code:attention.provider_code,protocol_binding:attention.protocol_binding},null,2)));card.append(technical);
    const choices = element('div', 'development-actions');
    [['approve_once','Approve Once','Allow only this exact action one time. No continuing authority.'],
     ['deny','Deny','Reject only this action. No authority is granted.'],
     ['cancel_campaign','Cancel Campaign','Stop this campaign safely. No authority is granted.']].forEach(([choice,label,consequence]) => {
      const immutableIdentity=canonicalAttentionIdentity(attention);
      const immutableAuthorityBindingSha256=attention.authority_binding_sha256;
      const box=element('div','attention-choice'); const button=element('button','',label); button.type='button';
      button.disabled=Boolean(exactAttentionSubmission&&exactAttentionSubmission.attention_id===attention.attention_id&&['submitting','refreshing','failed','resolved'].includes(exactAttentionSubmission.status));
      const humanTarget=qualificationLabel||'this Fawkes request';
      button.addEventListener('click', async()=>{if(window.confirm&&!window.confirm(`${label} for ${humanTarget}\n\n${consequence}`))return;const current=attentionSubmissions.get(immutableIdentity.attention_id);if(current&&['submitting','refreshing','failed','resolved'].includes(current.status))return;attentionSubmissions.set(immutableIdentity.attention_id,{status:'submitting',attention_id:immutableIdentity.attention_id,choice});renderDeveloperSection();try{const result=requireCanonicalDecisionResult(await request(`/api/development/codex-campaigns/${encodeURIComponent(immutableIdentity.campaign_id)}/attention/${encodeURIComponent(immutableIdentity.attention_id)}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({choice,identity:immutableIdentity})}),immutableIdentity,immutableAuthorityBindingSha256,choice);exactAttentionState=result;attentionSubmissions.set(immutableIdentity.attention_id,{status:'resolved',attention_id:immutableIdentity.attention_id,choice});renderDeveloperSection();}catch(error){attentionSubmissions.set(immutableIdentity.attention_id,{status:'failed',attention_id:immutableIdentity.attention_id,choice,code:error.code||'decision_submission_failed',http_status:error.status||null,message:error.message});const failureLifecycle=canonicalFailureDecisionResult(error.payload,immutableIdentity,immutableAuthorityBindingSha256,choice);if(failureLifecycle){exactAttentionState=failureLifecycle;renderDeveloperSection();}else{await loadExactAttention({preserveSubmission:true});}showError(error.message);}});
      box.append(button,element('p','meta',consequence)); choices.append(box);
    });
    card.append(choices, element('p','meta','Notification delivery and opening this page grant no authority. Only an authenticated choice above can decide this exact request.'));
    developerContent.append(card); return;
  }
  if (!developerData) { emptyState('Loading Development…'); return; }
  if (developerSection === 'campaigns') {
    const campaigns = (developerData && developerData.autonomous_campaigns) || [];
    const attentionItems = (developerData && developerData.attention) || [];
    developerContent.append(renderPhoenixBoard(campaigns, attentionItems));
    const create = element('article', 'growth-card'); create.id = 'campaign-create-card';
    create.append(element('h3', '', 'Start an authorized bounded Worker task'));
    const objective = document.createElement('textarea'); objective.id = 'campaign-objective'; objective.placeholder = 'Exact Tanner-approved objective';
    const scope = document.createElement('textarea'); scope.id = 'campaign-scope'; scope.placeholder = 'Allowed file paths, one per line';
    const tests = document.createElement('textarea'); tests.id = 'campaign-tests'; tests.placeholder = 'Validation argv JSON, e.g. [[".venv/bin/python","-B","-m","unittest","tests.test_name"]]';
    const prepare = element('button', '', 'Prepare exact scope'); prepare.type = 'button';
    const proposal = element('pre', 'hidden'); const authorize = element('button', 'hidden', 'Authorize and launch WORKER'); authorize.type = 'button';
    let payload = null;
    prepare.addEventListener('click', () => {
      const allowed = scope.value.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
      let validation; try { validation = JSON.parse(tests.value || '[]'); } catch (_error) { proposal.textContent = 'Validation commands must be JSON argv arrays.'; proposal.classList.remove('hidden'); return; }
      if (!objective.value.trim() || !allowed.length || !Array.isArray(validation) || !validation.length || validation.some(command => !Array.isArray(command) || !command.length)) { proposal.textContent = 'Objective, at least one allowed path, and at least one argv validation command are required.'; proposal.classList.remove('hidden'); authorize.classList.add('hidden'); return; }
      const campaignId = `rider-campaign-${Date.now()}`;
      payload = { campaign_id: campaignId, explicitly_authorized: true, target_builder: 'codex_repo', objective_mode: 'repository_write', objective: objective.value.trim(), allowed_scope: allowed,
        acceptance_condition_ids: ['objective-satisfied', 'tests-pass', 'scope-held'], acceptance_conditions: {'objective-satisfied': 'The exact authorized objective is satisfied.', 'tests-pass': 'The declared focused validation passes.', 'scope-held': 'No mutation occurs outside the exact allowed scope.'},
        source_sections: [], validation_commands: validation, rider_authorization_reference: `authenticated-development-${campaignId}`,
        recovery_references: [{reference_type: 'phase0_recovery', reference_id: `pre-${campaignId}`} ] };
      proposal.textContent = JSON.stringify(payload, null, 2); proposal.classList.remove('hidden'); authorize.classList.remove('hidden');
    });
    authorize.addEventListener('click', () => {
      if (!payload) return; authorize.disabled = true; status.textContent = 'WORKER running — this view may be closed safely';
      request('/api/development/codex-campaigns', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}).catch(error => showError(error.message));
      if (!campaignPoll) campaignPoll = window.setInterval(loadDeveloper, 2000);
    });
    create.append(objective, scope, tests, prepare, proposal, authorize); developerContent.append(create);
    if (!campaigns.length) { developerContent.append(element('p', 'dev-empty', 'No autonomous Development campaigns recorded yet.')); return; }
    campaigns.forEach(record => {
      const card = element('article', 'dev-card');
      card.append(pill(record.status), pill(`${record.iteration}/${record.maximum_iterations}`));
      card.append(element('h3', '', record.campaign_id));
      card.append(element('p', '', record.objective));
      card.append(element('p', 'meta', `${readable(record.current_stage)} · WORKER ${record.builder.worker_id} · REVIEWER ${record.reviewer.worker_id}`));
      (record.activity || []).forEach(event => {
        const row = element('div', 'evidence');
        row.append(pill(readable(event.kind)), element('span', 'meta', dateLabel(event.created_at)));
        if (event.summary) row.append(element('pre', '', JSON.stringify(event.summary, null, 2)));
        card.append(row);
      });
      if (record.needs_tanner) card.append(element('p', '', `Needs Tanner: ${readable(record.needs_tanner.reason)}`));
      const attention = (developerData.attention || []).find(item => item.campaign_id === record.campaign_id && item.state === 'needs_tanner');
      const embeddedSubmission=attention ? (attentionSubmissions.get(attention.attention_id)||null) : null;
      if (embeddedSubmission) {
        const heading=embeddedSubmission.status==='submitting'?'Submitting exact decision…':embeddedSubmission.status==='failed'?'Decision submission failed':'Decision recorded';
        const summary=embeddedSubmission.status==='failed'?`${embeddedSubmission.code||'decision_submission_failed'} (${embeddedSubmission.http_status||'no HTTP status'}): ${embeddedSubmission.message}`:embeddedSubmission.status==='submitting'?'Fawkes is validating this exact identity. All decision controls are closed.':'The canonical exact decision was recorded. No further decision is available.';
        const submission=element('section',embeddedSubmission.status==='failed'?'attention-urgent':'attention-summary');
        submission.append(element('h2','',heading),element('p','attention-submission-status',summary));card.append(submission);
      }
      if (attention && !embeddedSubmission) {
        const decision = element('article', 'evidence attention-decision-card');
        decision.id = `attention-${attention.attention_id}`;
        decision.append(element('h2', '', 'Tanner: Fawkes is paused and needs your decision'));
        decision.append(element('p', '', `Why Fawkes stopped: ${attention.why_required}`));
        decision.append(element('p', '', `Requested one-time authority: ${attention.requested_authority}`));
        decision.append(element('pre', '', JSON.stringify({invocation_id: attention.invocation_id,
          worker: attention.worker, blocked_action: attention.blocked_action,
          resources: attention.resources, requested_authority: attention.requested_authority,
          reversible: attention.reversible, expires_at: attention.expires_at}, null, 2)));
        const choices = element('div', 'development-actions');
        const embeddedIdentity=canonicalAttentionIdentity(attention);
        const embeddedAuthorityBindingSha256=attention.authority_binding_sha256;
        if (typeof embeddedAuthorityBindingSha256 !== 'string' || !embeddedAuthorityBindingSha256) {
          decision.append(element('p', 'attention-urgent', 'The canonical Attention authority-binding identity is missing. No decision controls are offered.'));
          card.append(decision);
          return;
        }
        [['approve_once','Approve Once'],
         ['deny','Deny'],
         ['cancel_campaign','Cancel Campaign']].forEach(([choice,label]) => {
          const button = element('button', '', label); button.type = 'button';
          button.addEventListener('click', async () => {
            if (attentionSubmissions.has(embeddedIdentity.attention_id)) return;
            attentionSubmissions.set(embeddedIdentity.attention_id,{status:'submitting',attention_id:embeddedIdentity.attention_id,campaign_id:embeddedIdentity.campaign_id,choice});
            renderDeveloperSection();
            try { requireCanonicalDecisionResult(await request(`/api/development/codex-campaigns/${encodeURIComponent(embeddedIdentity.campaign_id)}/attention/${encodeURIComponent(embeddedIdentity.attention_id)}/decision`,
              {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({choice,identity:embeddedIdentity})}),embeddedIdentity,embeddedAuthorityBindingSha256,choice);attentionSubmissions.set(embeddedIdentity.attention_id,{status:'resolved',attention_id:embeddedIdentity.attention_id,campaign_id:embeddedIdentity.campaign_id,choice});await loadDeveloper(); }
            catch (error) { attentionSubmissions.set(embeddedIdentity.attention_id,{status:'failed',attention_id:embeddedIdentity.attention_id,campaign_id:embeddedIdentity.campaign_id,choice,code:error.code||'decision_submission_failed',http_status:error.status||null,message:error.message});await loadDeveloper();showError(error.message); }
          }); choices.append(button);
        });
        decision.append(element('p', 'meta', 'No choice grants continuing authority. Notification delivery never counts as approval.'));
        decision.append(choices); card.append(decision);
      }
      const controls = element('div', 'development-actions');
      const inspect = element('button', '', 'Exact diff / tests / evidence'); inspect.type = 'button'; inspect.addEventListener('click', () => openCampaignEvidence(record.campaign_id)); controls.append(inspect);
      const review = element('button', '', 'Review Current Candidate'); review.type = 'button'; review.disabled = record.status !== 'awaiting_independent_review'; review.addEventListener('click', async () => { review.disabled = true; await request(`/api/development/codex-campaigns/${encodeURIComponent(record.campaign_id)}/review`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}); await loadDeveloper(); }); controls.append(review);
      card.append(controls);
      developerContent.append(card);
    });
    return;
  }
  let records;
  if (developerSection === 'observations') records = developerData.observations;
  if (developerSection === 'corrections') records = developerData.corrections;
  if (developerSection === 'defects') records = developerData.system_defects;
  if (developerSection === 'base') records = developerData.base_phoenix_candidates;
  if (['observations', 'corrections', 'defects', 'base'].includes(developerSection)) {
    if (!records || !records.length) { emptyState(`No ${readable(developerSection)} recorded yet.`); return; }
    records.forEach(record => developerContent.append(observationCard(record)));
    return;
  }
  if (developerSection === 'proposals') {
    if (!developerData.development_proposals.length) { emptyState('No development proposals recorded yet.'); return; }
    developerData.development_proposals.forEach(record => developerContent.append(proposalCard(record)));
    return;
  }
  if (developerSection === 'review') {
    if (!developerData.human_review_items.length) { emptyState('No human-review items recorded yet.'); return; }
    developerData.human_review_items.forEach(record => developerContent.append(reviewCard(record)));
    return;
  }
  if (developerSection === 'memory') {
    const triage = developerData.memory_triage || { status_counts: {}, review_items: [], queued_count: 0 };
    const summary = element('article', 'growth-card');
    summary.append(element('h3', '', 'Memory processing ledger'));
    summary.append(element('p', '', `${triage.queued_count || 0} queued candidate(s). This is triage evidence—not a remember/don’t-remember switch.`));
    Object.entries(triage.status_counts || {}).sort().forEach(([name, count]) => summary.append(pill(`${name}: ${count}`)));
    developerContent.append(summary);
    (triage.review_items || []).forEach(record => {
      const card = element('article', 'dev-card');
      card.append(pill('needs review'), pill((record.assessment && record.assessment.audit && record.assessment.audit.tier) || 'uncertain'));
      card.append(element('h3', '', record.candidate_content || 'Memory candidate'));
      card.append(element('p', '', record.decision_reason || 'This candidate could not be safely resolved automatically.'));
      card.append(element('p', 'meta', dateLabel(record.updated_at)));
      developerContent.append(card);
    });
    return;
  }
  if (developerSection === 'progression') {
    if (!developerData.progression.length) { emptyState('No longitudinal progression events recorded yet.'); return; }
    developerData.progression.forEach(item => {
      const event = element('article', 'history-event');
      event.append(pill(item.event_type), element('span', 'meta', dateLabel(item.created_at)));
      if (item.details.interpretation) event.append(element('p', '', item.details.interpretation));
      if (item.details.current && item.details.current.interpretation) event.append(element('p', '', item.details.current.interpretation));
      if (item.details.reason) event.append(element('p', '', item.details.reason));
      developerContent.append(event);
    });
    return;
  }
  if (developerSection === 'presentation') {
    const presentation = element('article', 'growth-card');
    presentation.append(element('h3', '', 'Presentation development is intentionally inactive'));
    presentation.append(element('p', '', 'Future versioned, reversible visual and avatar development will appear here when supported by reviewed evidence. Core Chat, navigation, security, settings, and Developer controls will remain stable.'));
    developerContent.append(presentation);
    return;
  }
  const growth = element('article', 'growth-card');
  growth.append(element('h3', '', 'Phoenix self-evaluation is intentionally deferred'));
  growth.append(element('p', '', 'Future growth assessments may interpret longitudinal evidence and develop meaningful subcategories. They will remain provenance-linked, revisable, and separate from observation records—without arbitrary scores or frozen personality dimensions.'));
  developerContent.append(growth);
}
async function openCampaignEvidence(campaignId) {
  detailPanel.classList.remove('hidden'); replaceContent(detailContent, element('p', 'dev-empty', 'Loading exact Worker Exchange evidence…'));
  try { const value = await request(`/api/development/codex-campaigns/${encodeURIComponent(campaignId)}/evidence`); replaceContent(detailContent, element('h2', '', campaignId), element('pre', '', JSON.stringify(value, null, 2))); }
  catch (error) { replaceContent(detailContent, element('p', 'dev-empty', error.message)); }
}
async function openRuntimeStatus() {
  detailPanel.classList.remove('hidden'); replaceContent(detailContent, element('p', 'dev-empty', 'Loading component state…'));
  try { const value = await request('/api/development/runtime-status'); const controls = element('div', 'development-actions');
    [['stack','start'],['stack','stop'],['stack','restart'],['app_server','restart'],['discord_bridge','restart']].forEach(([component, action]) => { const button = element('button', '', `${readable(action)} ${readable(component)}`); button.type='button'; button.addEventListener('click', async () => { button.disabled=true; try { await request('/api/development/runtime-control', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({component,action})}); } finally { button.disabled=false; } }); controls.append(button); });
    replaceContent(detailContent, element('h2', '', 'Fawkes component status and failures'), controls, element('pre', '', JSON.stringify(value, null, 2))); }
  catch (error) { replaceContent(detailContent, element('p', 'dev-empty', error.message)); }
}
async function loadDeveloper() {
  status.textContent = 'Loading Development…';
  try {
    developerData = await request('/api/development/dashboard');
    const campaignData = await request('/api/development/codex-campaigns');
    const attentionData = await request('/api/development/attention');
    developerData.autonomous_campaigns = (campaignData.campaigns || []).map(item => item.live_activity);
    developerData.attention = attentionData.attention || [];
    auth.classList.add('hidden');
    if (developerSection === 'attention' && requestedAttentionId) await loadExactAttention();
    else renderDeveloperSection();
    if (developerSection === 'tests') await loadTestCenter();
    status.textContent = 'Development observatory';
  } catch (error) {
    if (developerSection === 'attention' && requestedAttentionId) {
      exactAttentionState = {error: error.status === 401 ? 'Authenticate to inspect this exact Tanner attention request.' : error.message};
      renderDeveloperSection();
    } else emptyState(error.message);
    status.textContent = 'Needs attention';
  }
}
async function verifyBuildIdentity() {
  if (!developerBuild) return;
  try {
    const value = await request('/api/status');
    const serverId = value && value.build && value.build.release_id;
    const pageId = developerBuild.textContent.replace(/^Build:\s*/, '').trim();
    developerBuild.textContent = serverId === pageId ? `Build: ${serverId}` : `BUILD MISMATCH — page ${pageId} / API ${serverId}`;
    developerBuild.classList.toggle('auth-error', serverId !== pageId);
  } catch (error) { developerBuild.textContent = `Build identity unavailable: ${error.message}`; }
}
async function loadExactAttention(options={}) {
  if (!requestedAttentionId) { exactAttentionState=null;renderDeveloperSection(); return; }
  const requested = requestedAttentionId; const generation = ++exactAttentionLoadGeneration;
  exactAttentionState={loading:true}; renderDeveloperSection();
  try {
    const result = await request(`/api/development/attention/${encodeURIComponent(requested)}`);
    if (generation !== exactAttentionLoadGeneration || requested !== requestedAttentionId) return;
    if (!result.attention || result.attention.attention_id !== requested) throw new Error('Fawkes returned a different attention identity. No decision controls were shown.');
    exactAttentionState = result;
    const submission=attentionSubmissions.get(requested);
    if(submission&&submission.status==='refreshing')attentionSubmissions.set(requested,{...submission,status:result.attention.state==='needs_tanner'?'failed':'resolved',code:result.attention.state==='needs_tanner'?'deadline_refresh_inconclusive':null,message:result.attention.state==='needs_tanner'?'The server still reports this request as pending after its displayed deadline. Controls remain closed.':null});
  }
  catch (error) { if(generation!==exactAttentionLoadGeneration||requested!==requestedAttentionId)return; exactAttentionState={error:error.status===404?'This attention ID is unknown or no longer retained.':error.message}; }
  renderDeveloperSection();
  window.setTimeout(()=>{ const card=document.getElementById(`attention-${requested}`); if(card) card.scrollIntoView({block:'center'}); },0);
}
async function openObservation(observationId) {
  detailPanel.classList.remove('hidden');
  replaceContent(detailContent, element('p', 'dev-empty', 'Loading observation…'));
  try {
    const data = await request(`/api/development/observations/${encodeURIComponent(observationId)}`);
    const record = data.observation;
    clearNode(detailContent);
    detailContent.append(pill(record.category), pill(record.status));
    detailContent.append(element('h2', '', record.observed_pattern || record.current_interpretation));
    detailContent.append(element('p', '', record.uncertainty));
    detailContent.append(element('h3', '', 'Rider evaluation'));
    detailContent.append(pill(record.rider_evaluation || 'not provided'), pill(record.development_signal || 'observe only'));
    if (record.rider_reason) detailContent.append(element('p', '', record.rider_reason));
    detailContent.append(element('p', 'meta', `${readable(record.longitudinal_status || 'isolated')} · ${readable(record.confidence_state || 'tentative')}`));
    detailContent.append(element('h3', '', 'Phoenix interpretation'));
    detailContent.append(element('p', '', record.phoenix_interpretation || 'Not recorded. Reserved for future Phoenix self-reflection; rider evaluation is kept separate.'));
    detailContent.append(element('p', 'meta', `Observed by ${readable(record.observed_by)} · ${dateLabel(record.created_at)}`));
    detailContent.append(element('h3', '', 'Evidence'));
    record.evidence.forEach(item => {
      const evidence = element('article', `evidence ${item.relation}`);
      evidence.append(pill(item.relation), element('span', 'meta', `${item.role} · ${dateLabel(item.observed_at)}`));
      evidence.append(element('p', '', item.content));
      evidence.append(element('p', 'meta', 'Canonical conversation evidence · provenance retained'));
      detailContent.append(evidence);
    });
    detailContent.append(element('h3', '', 'Interpretation history'));
    data.history.forEach(item => {
      const event = element('article', 'history-event');
      event.append(pill(item.event_type), element('span', 'meta', dateLabel(item.created_at)));
      if (item.details.reason) event.append(element('p', '', item.details.reason));
      if (item.details.current && item.details.current.interpretation) event.append(element('p', '', item.details.current.interpretation));
      detailContent.append(event);
    });
  } catch (error) { replaceContent(detailContent, element('p', 'dev-empty', error.message)); }
}

async function submitChatTurn(text, media = [], retrievalClarification = null) {
  if (chatRequestPending) { const error = new Error('Another Chat request is already in progress.'); error.code = 'request_in_progress'; throw error; }
  chatRequestPending = true;
  const emptyMessage = messages.querySelector('.empty');
  if (emptyMessage) emptyMessage.remove();
  recoveryGeneration += 1;
  const visibleText = text + (media.length ? `\n\n📎 ${media.map(item => item.name).join(', ')}` : '');
  const pending = addMessage('user', visibleText, 'pending');
  send.disabled = true; status.textContent = media.length ? 'Analyzing media…' : 'Thinking…';
  const requestOccurrence = `request-${Date.now()}-${Math.random()}`;
  emitWindowEvent('fawkes:message-submitting', { message: text, occurrence_id: requestOccurrence });
  emitPresence('presence.request_processing_started', requestOccurrence);
  const slowNotice = window.setTimeout(() => {
    if (send.disabled) status.textContent = 'Still working — research can take a minute. Your message is preserved.';
  }, 12000);
  try {
    const attachments = await Promise.all(media.map(async item => ({ name: item.name, mime_type: item.type,
      privacy: 'potentially_private', keep_in_library: attachmentRetention.get(item) === true,
      retention_title: item.name, data: await fileAsBase64(item) })));
    const payload = { conversation_id: conversationId, message: text, attachments };
    if (retrievalClarification) payload.retrieval_clarification = retrievalClarification;
    const data = await request('/api/chat/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    pending.classList.remove('pending'); addMessageTimestamp(pending, data.user_message_created_at);
    const assistant = addMessage('assistant', data.message.content, '', data.message.presentation, data.message.created_at);
    renderMediaLifecycle(assistant, data.media);
    renderContextInspector(assistant, data.message);
    renderRetrievalClarification(assistant, data.retrieval_clarification, {
      originatingResponseMessageId: data.message.message_id, originalQuery: text,
    });
    status.textContent = 'Present'; emitPresence('presence.response_displayed', data.message.message_id);
    if (!eventAudio.preferences) await loadSoundSettings();
    for (const semanticEvent of (data.events || [])) { await eventAudio.emit(semanticEvent); emitPresence(semanticEvent.event_id, semanticEvent.occurrence_id); }
    return data;
  } catch (error) {
    if (retrievalClarification) pending.remove(); else pending.classList.remove('pending');
    status.textContent = 'Needs attention'; throw error;
  } finally {
    window.clearTimeout(slowNotice); send.disabled = false; chatRequestPending = false; input.focus();
  }
}

authForm.addEventListener('submit', async event => {
  event.preventDefault();
  const credential = tokenInput.value.trim(); tokenInput.value = '';
  connect.disabled=true; connect.textContent='Connecting…'; setAuthError('');
  try {
    const session = await request('/api/session', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential})});
    // Older local test servers may still return an empty 204. They can serve
    // read-only views, but the server will reject decisions without this token.
    csrfToken = session && session.authenticated_rider === 'tanner'
      && typeof session.csrf_token === 'string' ? session.csrf_token : '';
    token=''; const connected=await loadChat(true); if(connected&&requestedAttentionId)await loadExactAttention();
  } catch(error) { setAuthError(error.message); auth.classList.remove('hidden'); }
  finally { connect.disabled=false; connect.textContent='Connect'; }
});
composer.addEventListener('submit', async event => {
  event.preventDefault(); const text = input.value.trim(); if (!text || send.disabled) return;
  const media = pendingAttachments; pendingAttachments = []; renderAttachmentTray();
  input.value = '';
  try {
    await submitChatTurn(text, media);
  } catch (error) { showError(error.message); }
});
if (attachmentInput) attachmentInput.addEventListener('change', () => {
  const selected = [...attachmentInput.files];
  if (selected.length + pendingAttachments.length > 4) { showError('Attach no more than four files.'); attachmentInput.value = ''; return; }
  const tooLarge = selected.find(file => file.size > 16 * 1024 * 1024);
  if (tooLarge) { showError(`${tooLarge.name} is larger than 16 MB.`); attachmentInput.value = ''; return; }
  pendingAttachments.push(...selected); attachmentInput.value = ''; renderAttachmentTray();
});
input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    if (composer.requestSubmit) composer.requestSubmit();
    else composer.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  }
});
document.querySelector('.app-nav').addEventListener('click', event => {
  const button = event.target.closest('[data-view]'); if (!button) return;
  document.querySelectorAll('.app-nav [data-view]').forEach(item => item.classList.toggle('active', item === button));
  document.querySelector('#chat-view').classList.toggle('hidden', button.dataset.view !== 'chat');
  document.querySelector('#developer-view').classList.toggle('hidden', button.dataset.view !== 'developer');
  const settingsView = document.querySelector('#settings-view'); if (settingsView) settingsView.classList.toggle('hidden', button.dataset.view !== 'settings');
  const libraryView = document.querySelector('#library-view'); if (libraryView) libraryView.classList.toggle('hidden', button.dataset.view !== 'library');
  const historyView = document.querySelector('#history-view'); if (historyView) historyView.classList.toggle('hidden', button.dataset.view !== 'history');
  if (button.dataset.view === 'developer') loadDeveloper();
  else if (button.dataset.view === 'settings') { loadSoundSettings(); loadPresenceSettings(); }
  else if (button.dataset.view === 'library') loadLibrary();
  else if (button.dataset.view === 'history') status.textContent = 'Manual history inspection';
  else status.textContent = 'Present';
});
if (librarySearchForm) librarySearchForm.addEventListener('submit', event => { event.preventDefault(); const query = libraryQuery.value.trim(); if (query) searchLibrary(query).catch(error => showError(error.message)); });
if (libraryContent) libraryContent.addEventListener('click', event => {
  const button = event.target.closest('[data-extract-source]'); if (!button) return;
  button.disabled = true; button.textContent = 'EXTRACTING…';
  request(`/api/library/sources/${encodeURIComponent(button.dataset.extractSource)}/extract`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    .then(loadLibrary).catch(error => { showError(error.message); button.disabled = false; button.textContent = 'EXTRACT / RETRY'; });
});
if (historySearchForm) historySearchForm.addEventListener('submit', event => {
  event.preventDefault(); const query = historyQuery.value.trim();
  if (query) searchHistory(query, historyDomain.value).catch(error => showError(error.message));
});
if (historyContent) historyContent.addEventListener('click', event => {
  const button = event.target.closest('[data-history-evidence]'); if (!button) return;
  openHistoricalEvidence(button.dataset.historyDomain, button.dataset.historyEvidence).catch(error => showError(error.message));
});
if (document.addEventListener) document.addEventListener('pointerdown', event => {
  eventAudio.unlock();
  const button = event.target.closest('button');
  if (button && !button.matches('#send')) eventAudio.emit({ event_id: 'ui.button_clicked', occurrence_id: `${Date.now()}-${Math.random()}` });
}, { passive: true });
document.querySelector('#developer-sections').addEventListener('click', event => {
  const button = event.target.closest('[data-section]'); if (!button) return;
  developerSection = button.dataset.section;
  document.querySelectorAll('#developer-sections [data-section]').forEach(item => item.classList.toggle('active', item === button));
  renderDeveloperSection();
  if (developerSection === 'tests') loadTestCenter();
  if (developerSection === 'attention') loadExactAttention();
});
developerContent.addEventListener('click', event => {
  const run = event.target.closest('[data-run-test]');
  if (run) { triggerAcceptance(run.dataset.runTest).catch(error => { showError(error.message); loadTestCenter(); }); return; }
  const runAll = event.target.closest('[data-test-all]');
  if (runAll) { triggerAllAcceptance().catch(error => { showError(error.message); loadTestCenter(); }); return; }
  const card = event.target.closest('[data-observation-id]');
  if (card) openObservation(card.dataset.observationId);
});
document.querySelector('#detail-close').addEventListener('click', () => detailPanel.classList.add('hidden'));
detailPanel.addEventListener('click', event => { if (event.target === detailPanel) detailPanel.classList.add('hidden'); });
const startDevelopment = document.querySelector('#start-development-task');
if (startDevelopment) startDevelopment.addEventListener('click', () => { developerSection = 'campaigns'; renderDeveloperSection(); const field=document.querySelector('#campaign-objective'); if(field) field.focus(); });
const liveActivity = document.querySelector('#open-live-activity');
if (liveActivity) liveActivity.addEventListener('click', () => { developerSection = 'campaigns'; loadDeveloper(); if (!campaignPoll) campaignPoll = window.setInterval(loadDeveloper, 2000); });
const runtimeStatus = document.querySelector('#open-runtime-status');
if (runtimeStatus) runtimeStatus.addEventListener('click', openRuntimeStatus);
const startup = new URLSearchParams(window.location.search);
if (startup.get('view') === 'developer') {
  requestedAttentionId = startup.get('attention');
  if (startup.get('section') === 'attention' || requestedAttentionId) developerSection = 'attention';
}
loadChat().then(connected => {
  if (startup.get('view') === 'developer') {
    const developerButton=document.querySelector('.app-nav [data-view="developer"]');
    if(connected&&developerButton)developerButton.click();
    else {
      const chatView=document.querySelector('#chat-view');const developerView=document.querySelector('#developer-view');
      if(chatView)chatView.classList.add('hidden');if(developerView)developerView.classList.remove('hidden');
      exactAttentionState={error:'Authenticate to inspect this exact Tanner attention request.'};renderDeveloperSection();
    }
    document.querySelectorAll('#developer-sections [data-section]').forEach(item => item.classList.toggle('active', item.dataset.section === developerSection));
  }
});
verifyBuildIdentity();

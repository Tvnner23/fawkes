const fs = require('fs');
const vm = require('vm');

class ClassList {
  constructor(names = []) { this.names = new Set(names); }
  add(name) { this.names.add(name); }
  remove(name) { this.names.delete(name); }
  contains(name) { return this.names.has(name); }
  toggle(name, force) {
    if (force === undefined) force = !this.names.has(name);
    if (force) this.names.add(name); else this.names.delete(name);
  }
}

class Element {
  constructor(classes = [], tagName = '') {
    this.tagName = tagName;
    this.classList = new ClassList(classes);
    this.listeners = {};
    this.children = [];
    this.value = '';
    this.textContent = '';
    this.disabled = false;
    this.dataset = {};
    this.style = {};
  }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  append(...items) { this.children.push(...items); }
  removeChild(item) { this.children.splice(this.children.indexOf(item), 1); }
  get firstChild() { return this.children[0] || null; }
  querySelector() { return null; }
  closest() { return null; }
  focus() {}
  setAttribute(name, value) { this[name] = String(value); }
}

const selectors = [
  '#messages', '#composer', '#message', '#send', '#status', '#auth',
  '#auth-form', '#token', '#connect', '#auth-error', '#developer-content',
  '#detail-panel', '#detail-content', '#phoenix-name', '.app-nav',
  '#developer-sections', '#detail-close', '#chat-view', '#developer-view',
];
const nodes = Object.fromEntries(selectors.map(selector => [selector, new Element()]));
nodes['#auth'].classList.add('hidden');
nodes['#detail-panel'].classList.add('hidden');

global.window = {
  location: { origin: 'http://fawkes.local:8787' },
  setTimeout, clearTimeout,
  localStorage: {
    getItem() { throw new Error('storage denied'); },
    setItem() { throw new Error('storage denied'); },
  },
};
global.document = {
  querySelector(selector) { return nodes[selector]; },
  querySelectorAll() { return []; },
  createElement(tagName) { return new Element([], tagName); },
  createElementNS(namespace, tagName) { return new Element([], tagName); },
};
global.Event = class { constructor(type, options) { this.type = type; Object.assign(this, options); } };

const requests = [];
let sessionEstablished = false;
global.fetch = async (url, options) => {
  requests.push({ url, options });
  if (url === '/api/session') {
    const supplied = JSON.parse(options.body || '{}').credential;
    if (supplied === 'correct-token') sessionEstablished = true;
    return { status: sessionEstablished ? 204 : 401, ok: sessionEstablished,
      async json() { return sessionEstablished ? {} : { error: { message: 'That Fawkes app credential was not accepted.' } }; } };
  }
  if (!sessionEstablished) {
    return {
      status: 401,
      ok: false,
      async json() { return { error: { message: 'Access token required.' } }; },
    };
  }
  return {
    status: 200,
    ok: true,
    async json() {
      return {
        phoenix: { name: 'Fawkes' },
        conversation: { conversation_id: 'conversation-1' },
        messages: [{
          message_id: 'assistant-1', role: 'assistant', content: 'Fallback answer.',
          created_at: '2026-08-30T20:15:00+00:00',
          presentation: {
            schema_version: 2,
            text: 'See the [official report](https://official.example/report?utm_source=openai).',
            blocks: [{
              type: 'table', title: 'Comparison', caption: 'Two choices',
              fallback: 'A is online and B is on campus.', source_scope: 'research',
              source_urls: ['https://official.example/report?utm_source=openai'],
              columns: ['Course', 'Format'], rows: [['A', 'Online'], ['B', 'Campus']],
            }, {
              type: 'chart', chart_type: 'pie', title: 'Formats', caption: '',
              fallback: 'Online is 70 and campus is 30.', source_scope: 'user_supplied',
              source_urls: [], series: [{ name: 'Formats', points: [
                { label: 'Online', value: 70 }, { label: 'Campus', value: 30 },
              ] }], x_label: '', y_label: '',
            }],
            citations: [{
              citation_id: 'source-1', label: 'official report', title: 'Official report',
              url: 'https://official.example/report?utm_source=openai',
              display_url: 'https://official.example/report', source_role: 'primary_official',
            }],
            rejected_blocks: [],
          },
        }],
      };
    },
  };
};

function tick() { return new Promise(resolve => setTimeout(resolve, 0)); }

(async () => {
  const source = fs.readFileSync('src/app/static/app.js', 'utf8');
  vm.runInThisContext(source, { filename: 'app.js' });
  await tick();
  if (typeof nodes['#auth-form'].listeners.submit !== 'function') {
    throw new Error('Connect submit handler was not registered');
  }

  nodes['#token'].value = 'correct-token';
  await nodes['#auth-form'].listeners.submit({ preventDefault() {} });

  const authenticated = requests.find(item => item.url === '/api/session');
  if (!authenticated) throw new Error('Authenticated request was not sent');
  const destination = new URL(requests[requests.length - 1].url, window.location.origin).href;
  if (destination !== 'http://fawkes.local:8787/api/chat') {
    throw new Error(`Unexpected destination: ${destination}`);
  }
  if (nodes['#status'].textContent !== 'Present') {
    throw new Error(`Unexpected connection status: ${nodes['#status'].textContent}`);
  }
  if (!nodes['#auth'].classList.contains('hidden')) {
    throw new Error('Login screen remained visible after authentication');
  }
  if (nodes['#auth-error'].textContent) {
    throw new Error(`Unexpected login error: ${nodes['#auth-error'].textContent}`);
  }
  function descendants(node) {
    return node.children.reduce((all, child) => [child, ...all, ...descendants(child)], []);
  }
  function chartBlock(chartType, series, title) {
    return {
      type: 'chart', chart_type: chartType, title, caption: 'Illustrative values.',
      fallback: `${title} has a readable text fallback.`, source_scope: 'illustrative',
      source_urls: [], series, x_label: 'X', y_label: 'Y',
    };
  }
  const labeled = [{ name: 'Values', points: [{ label: 'A very long mobile label', value: 10 }, { label: 'B', value: 25 }] }];
  const xy = [{ name: 'Samples', points: [{ label: 'A', x: 1, y: 4 }, { label: 'B', x: 3, y: 8 }] }];
  const aligned = [
    { name: 'First', points: [{ label: 'A', value: 10 }, { label: 'B', value: 20 }] },
    { name: 'Second', points: [{ label: 'A', value: 15 }, { label: 'B', value: 12 }] },
  ];
  addMessage('assistant', 'Four visuals.', '', { schema_version: 2, text: 'Four visuals.', citations: [], blocks: [
    chartBlock('bar', labeled, 'Bar'), chartBlock('line', labeled, 'Line'),
    chartBlock('pie', [{ name: 'Whole', points: [{ label: 'All', value: 100 }, { label: 'None', value: 0 }] }], 'Pie'),
    chartBlock('scatter', xy, 'Scatter'),
  ] });
  addMessage('assistant', 'Four more.', '', { schema_version: 2, text: 'Four more.', citations: [], blocks: [
    chartBlock('donut', labeled, 'Donut'), chartBlock('area', labeled, 'Area'),
    chartBlock('grouped_bar', aligned, 'Grouped'), chartBlock('stacked_bar', aligned, 'Stacked'),
  ] });
  addMessage('assistant', 'Structure.', '', { schema_version: 2, text: 'Structure.', citations: [], blocks: [{
    type: 'timeline', title: 'Timeline', caption: '', fallback: 'First, then second.',
    source_scope: 'user_supplied', source_urls: [], items: [
      { date: 'Day 1', label: 'First', detail: 'Begin' }, { date: 'Day 2', label: 'Second', detail: 'Finish' },
    ],
  }, {
    type: 'diagram', title: 'Flow', caption: '', fallback: 'Input leads to output.',
    source_scope: 'reasoning', source_urls: [], direction: 'horizontal',
    nodes: [{ id: 'input', label: 'Input' }, { id: 'output', label: 'Output' }],
    edges: [{ from: 'input', to: 'output', label: 'process' }],
  }] });
  const rendered = descendants(nodes['#messages']);
  if (!rendered.some(node => node.tagName === 'table' && node.className.includes('message-table'))) {
    throw new Error('Structured table was not rendered');
  }
  if (!rendered.some(node => node.className === 'pie-layout')) {
    throw new Error('Pie chart was not rendered');
  }
  const formats = rendered.filter(node => node.className && node.className.includes('visual-card'))
    .map(node => node['data-visual-format']);
  ['bar', 'line', 'pie', 'scatter', 'donut', 'area', 'grouped_bar', 'stacked_bar', 'timeline', 'flow']
    .forEach(format => { if (!formats.includes(format)) throw new Error(`${format} was not rendered`); });
  if (rendered.filter(node => node.className && node.className.includes('visual-card')).length < 12) {
    throw new Error('Multiple visualizations in one response were not rendered');
  }
  if (!rendered.some(node => node.className === 'visual-scope' && node.textContent === 'Illustrative values')) {
    throw new Error('Illustrative provenance label was not rendered');
  }
  if (!rendered.some(node => node.tagName === 'circle' && node.r === '95')) {
    throw new Error('A 100-percent pie slice was not rendered as a complete circle');
  }
  const sourceCard = rendered.find(node => node.className === 'source-card');
  if (!sourceCard || sourceCard.href !== 'https://official.example/report') {
    throw new Error('Clean mobile source card was not rendered');
  }
  const timestamp = rendered.find(node => node.tagName === 'time' && node.className === 'message-time');
  if (!timestamp || timestamp.dateTime !== '2026-08-30T20:15:00+00:00') {
    throw new Error('Authoritative message timestamp was not rendered');
  }
  console.log('client-login-flow-ok');
})().catch(error => { console.error(error); process.exit(1); });

'use strict';
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),vm=require('node:vm');
const context={module:{exports:{}},console};vm.createContext(context);
vm.runInContext(fs.readFileSync('src/app/static/dev-console/worker.js','utf8'),context);
const api=context.module.exports;
const m=(id,text=id,role='worker')=>({message_id:id,turn_id:'turn-'+id,role,phase:'final_answer',text,content_sha256:crypto.createHash('sha256').update(text).digest('hex')});
const page=(ids,messages,cursor=null)=>({page_item_ids:ids,messages,next_cursor:cursor});
const cache=()=>({messages:[],anchor:null,gap:null});
let c=cache();api.advanceHead(c,page(['tool-first','a'],[m('a')]));
assert.equal(c.anchor,'tool-first');assert.deepEqual(c.messages.map(x=>x.message_id),['a']);
api.advanceHead(c,page(['new-tool','b','tool-first'],[m('b','PC reply','user'),m('a')]));
assert.deepEqual(c.messages.map(x=>x.message_id),['b','a']);assert.equal(c.anchor,'new-tool');
// More than one full page arrives while disconnected. Keep old text until the
// complete ordered gap is traversed, including all-tools intermediate pages.
api.advanceHead(c,page(['front','newest'],[m('newest')],'cursor-1'));
assert.deepEqual(c.messages.map(x=>x.message_id),['b','a']);
api.advanceHead(c,page(['tool-mid'],[],'cursor-2'),true);
assert.equal(c.gap.cursor,'cursor-2');
api.advanceHead(c,page(['middle','new-tool'],[m('middle')],'cursor-old'),true);
assert.deepEqual(c.messages.map(x=>x.message_id),['newest','middle','b','a']);assert.equal(c.anchor,'front');assert.equal(c.gap,null);
// The same streaming item is updated, never appended twice or ordered by prose.
api.advanceHead(c,page(['front','newest'],[m('newest','complete outward-facing text')]));
assert.equal(c.messages[0].text,'complete outward-facing text');assert.equal(c.messages.length,4);
const older=api.mergeMessages(c.messages,[m('a'),m('old','earlier PC instruction','user')],true);
assert.deepEqual(older.map(x=>x.message_id),['newest','middle','b','a','old']);
// A cursor loop/end that cannot reach the retained anchor must not fabricate a
// complete conversation or replace the previous good history.
const old=c.messages.slice();api.advanceHead(c,page(['far'],[m('far')],'cycle'));
assert.throws(()=>api.advanceHead(c,page(['gap'],[m('gap')],'cycle'),true),/continuity/);
assert.deepEqual(c.messages,old);
assert.throws(()=>api.advanceHead(c,page(['gap2'],[m('gap2')],null),true),/continuity/);
assert.deepEqual(c.messages,old);
let empty=cache();api.advanceHead(empty,page([],[]));api.advanceHead(empty,page(['first'],[m('first')]));
assert.equal(empty.anchor,'first');assert.equal(empty.messages.length,1);
const base={schema_version:'fawkes.worker_conversation.v1',thread_id:'01a06f22-5b47-72c1-9b9c-b70157913436',state:'active',can_reply:true,verified_at:new Date().toISOString(),messages:[],latest_final:null};
for(const delta of [{page_item_ids:['a','a']},{completed_turn_ids:['x','x']},{page_item_ids:[1]},{completed_turn_ids:[null]},{next_cursor:''}])assert.throws(()=>api.projection({...base,...delta}));
console.log('worker-history-frontier-ok: ordered gaps, tools-only pages, overlap, PC messages, loops and identity validation; no provider/Pi claim');
// Design correction: concise surface text must not discard normalized evidence.
const {fakeDocument,FakeElement,textOf,consoleApi,rawProjection}=require('./dev_console_projection_harness.js');
const fixture=fakeDocument(),doc=fixture.document;
const raw=JSON.parse(JSON.stringify(rawProjection.jobs[0]));
raw.is_current_objective=true;raw.state='done';
raw.accomplished='A'.repeat(1790)+'ACCOMPLISHED-END';
raw.gained='G'.repeat(1180)+'GAIN-END';
raw.public_result='PUBLIC-RESULT-PRESERVED';
const normalized=consoleApi.normalizeJobsResponse([raw]);assert.equal(normalized.valid,true);
consoleApi.renderJobs(doc,fixture.byId.get('activity-feed'),normalized.jobs,'live');
const rendered=textOf(fixture.byId.get('activity-feed'));
for(const key of ['accomplished','gained','public_result'])assert.ok(rendered.includes(normalized.jobs[0][key]),key+' must survive in Details');
const elements={selector:fixture.byId.get('campaign-selector'),history:fixture.byId.get('campaign-history-state'),
  empty:fixture.byId.get('campaign-empty'),dashboard:fixture.byId.get('campaign-dashboard'),
  widgets:fixture.byId.get('campaign-widgets'),graph:fixture.byId.get('campaign-graph'),detail:fixture.byId.get('campaign-detail')};
for(const id of ['campaign-objective','campaign-focus','campaign-stage-board']){
  const node=new FakeElement('div');node.textContent='OLD CAMPAIGN';fixture.byId.set(id,node);
}
consoleApi.renderCampaignDashboard(doc,elements,[],null,null,'live');
for(const id of ['campaign-objective','campaign-focus','campaign-stage-board'])assert.equal(textOf(fixture.byId.get(id)),'');
assert.equal(elements.history.textContent,'NO ACTIVE CAMPAIGN');assert.equal(elements.dashboard.hidden,true);
console.log('design-correction-dom-ok: complete normalized details, public result, empty-campaign identity');

// Run the actual boot, scroll handler and render path through multiple opaque
// lifecycle pages. No DOM helper independently guesses a completed turn.
async function olderLifecycleCases(){
 const settle=async()=>{for(let i=0;i<15;i++)await new Promise(r=>setImmediate(r));};
 for(const cycle of [false,true]){
  const nodes=new Map();
  for(const id of ['worker-page','worker-reply','worker-send-reply','worker-send-update','worker-session-state','worker-reply-result','worker-copy-result','worker-session-identity','worker-final-message','worker-final-identity','worker-conversation-history','worker-older','worker-newest','worker-reply-form','worker-keyboard','worker-keyboard-toggle','worker-reading','worker-progress','worker-new-activity','worker-history-state']){
   const e=new FakeElement('div',id);e.value='';nodes.set(id,e);
  }
  const reading=nodes.get('worker-reading');reading.scrollHeight=2000;reading.clientHeight=300;
  const latest=m('new-final');latest.turn_id='turn-25';
  const old={...m('old-progress'),turn_id:'turn-1',phase:'commentary'};
  const calls=[],store=new Map();let intervals=0;
  const reply=delta=>({...base,state:'idle',latest_final:latest,active_turn_ids:[],known_turn_ids:['turn-25'],
    completed_turn_ids:['turn-25'],messages:[latest],page_item_ids:['new-final'],next_cursor:'items-old',next_turn_cursor:'turns-8',...delta});
  const cx={module:{exports:{}},console,TextEncoder,AbortController,setTimeout,clearTimeout,
   setInterval:()=>++intervals,clearInterval(){},crypto,MutationObserver:class{observe(){}disconnect(){}},
   localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},
   fetch:async path=>{
    calls.push(path);let value;
    if(path.endsWith('?cursor=items-old'))value=reply({messages:[old],page_item_ids:['old-progress'],next_cursor:null});
    else if(path.endsWith('?turn_cursor=turns-8'))value=reply({known_turn_ids:['turn-17'],completed_turn_ids:['turn-17'],next_turn_cursor:cycle?'turns-8':'turns-16'});
    else if(path.endsWith('?turn_cursor=turns-16'))value=reply({known_turn_ids:['turn-1'],completed_turn_ids:['turn-1'],next_turn_cursor:null});
    else if(path==='/api/development/worker')value=reply({});
    else throw Error('Unexpected request '+path);
    return {ok:true,json:async()=>value};
   }};
  vm.createContext(cx);vm.runInContext(fs.readFileSync('src/app/static/dev-console/worker.js','utf8'),cx);
  const ui=cx.module.exports.boot({getElementById:id=>nodes.get(id),createElement:tag=>new FakeElement(tag)});
  await settle();await reading.emit('scroll');await settle();
  assert(calls.some(p=>p.endsWith('?cursor=items-old')),'upward scroll must actually load earlier messages');
  assert(nodes.get('worker-conversation-history').querySelectorAll('.worker-history-message').some(e=>e.dataset.messageId==='old-progress'));
  await ui.refresh();await settle();await ui.refresh();await settle();
  const bundles=nodes.get('worker-conversation-history').querySelectorAll('.worker-progress-bundle');
  assert.equal(bundles.some(e=>e.dataset.bundleId==='turn-1'),!cycle);
  assert.equal(nodes.get('worker-final-message').textContent,latest.text);
  assert.equal(nodes.get('worker-progress').hidden,true);
  if(cycle)assert.match(nodes.get('worker-reply-result').textContent,/did not advance/);
  assert(calls.every(p=>!p.includes('/replies')&&!p.includes('/clipboard')));
  ui.stop();
 }
 console.log('older-lifecycle-boot-ok: scroll access, multi-page completion, cursor-cycle rejection and latest-final isolation');
}
olderLifecycleCases().catch(error=>{console.error(error);process.exitCode=1;});

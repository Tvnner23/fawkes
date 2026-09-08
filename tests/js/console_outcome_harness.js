'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
class El{
  constructor(){this.hidden=true;this.open=false;this.dataset={};this.listeners={};this.children=[];this.value='Retained draft';this.selectionStart=4;}
  addEventListener(k,f){this.listeners[k]=f;}removeEventListener(k){delete this.listeners[k];}
  click(){if(this.listeners.click)this.listeners.click();}
  close(){this.open=false;}showModal(){this.open=true;this.shows=(this.shows||0)+1;}
  focus(){this.focused=true;}matches(){return this.typing===true;}
  querySelector(){return this.children.find(c=>c.dataset.objectiveOutcome)||null;}
  prepend(c){this.children.unshift(c);}
}
const ids=['objective-outcome-dialog','objective-outcome-title','objective-outcome-objective',
 'objective-outcome-result','objective-outcome-source','objective-outcome-reply','objective-outcome-close',
 'worker-keyboard','worker-keyboard-toggle','worker-reply','page-menu'];
const nodes=new Map(ids.map(id=>[id,new El()]));
let card=new El(),reply=0,otherModal=false,failedStorage=false,writeFailure=false,readbackMismatch=false;
const listeners={},store=new Map(),d=nodes.get('objective-outcome-dialog');
const doc={activeElement:new El(),getElementById:id=>nodes.get(id),createElement:()=>new El(),
 querySelector:s=>s==='dialog[open]'?(otherModal||d.open?{}:null):s==='.current-briefing'?card:null,
 addEventListener:(k,f)=>listeners[k]=f,removeEventListener:k=>delete listeners[k]};
nodes.get('worker-keyboard-toggle').listeners.click=()=>nodes.get('worker-keyboard').hidden=true;
const events={},cx={module:{exports:{}},console,JSON,Set,Date,
 localStorage:{getItem:k=>{if(failedStorage)throw Error();return store.get(k)||null;},
 setItem:(k,v)=>{if(failedStorage||writeFailure)throw Error('QuotaExceededError');if(!readbackMismatch)store.set(k,v);}},
 addEventListener:(k,f)=>events[k]=f,removeEventListener:k=>delete events[k],
 __fawkesMatrix:{active:false,wake(){throw Error('status must not wake Matrix');}}};
vm.createContext(cx);vm.runInContext(fs.readFileSync('src/app/static/dev-console/outcome.js','utf8'),cx);
const api=cx.module.exports;
const job={job_id:'root-job',is_current_objective:true,objective:'Whole requested task',state:'needs_you',
 next:'Renew the exact expired ticket, not another command.',blocker_identity:'1'.repeat(64),last_activity_at:'2026-09-14T12:00:00Z',source_record_sha256:'a'.repeat(64)};
const p={current_campaign_id:job.job_id,jobs:[job]};
let ui=api.boot(doc,()=>reply++);
function native(pending=false){events['fawkes:native-worker-attention']({detail:{connected:true,pending}});}
function update(state='live'){card=new El();ui.update(p,state);}
assert.equal(api.notice({...p,current_campaign_id:'another'},'live'),null);
assert.equal(api.notice({...p,jobs:[job,job]},'live'),null);
for(const state of ['working','waiting','failed','closed','unknown','done'])
 assert.equal(api.notice({...p,jobs:[{...job,state,successful:true}]},'live'),null);
update();assert(!d.open,'no prompt before native-priority state is known');
native();assert(d.open);assert(d.dataset.tone==='blocked');assert(nodes.get('objective-outcome-result').textContent.includes('exact expired'));
nodes.get('objective-outcome-close').click();assert(!d.open);update();native();assert(!d.open,'seen notice does not repeat');
ui.stop();ui=api.boot(doc,()=>reply++);update();native();assert(!d.open,'reload preserves notice acknowledgement');
listeners.click({target:{closest:()=>true}});assert(d.open,'manual reopening remains available');
nodes.get('objective-outcome-reply').click();assert(!d.open);assert.equal(reply,1);
assert.equal(nodes.get('worker-reply').value,'Retained draft');assert.equal(nodes.get('worker-reply').selectionStart,4);
job.next='A different actual decision';job.blocker_identity='2'.repeat(64);doc.activeElement.typing=true;update();assert(!d.open,'typing is not interrupted');
doc.activeElement.typing=false;nodes.get('worker-keyboard').hidden=false;update();assert(!d.open,'touch keyboard is not displaced');
nodes.get('worker-keyboard').hidden=true;cx.__fawkesMatrix.active=true;update();assert(!d.open);
cx.__fawkesMatrix.active=false;otherModal=true;update();assert(!d.open);
otherModal=false;native(true);update();assert(!d.open,'native permission takes precedence');
native(false);assert(d.open);native(true);assert(!d.open,'incoming real request releases status modal');
job.state='done';job.successful=true;job.next='next';
job.objective_closeout={event_id:'closed-1',result:'All required work and checks recorded.',recorded_at:'2026-09-14T12:00:00Z',gate_count:3};
native(false);update();assert(d.open);assert(nodes.get('objective-outcome-title').textContent.includes('Task complete'));
update('disconnected');assert(nodes.get('objective-outcome-title').textContent.includes('Last known'));
nodes.get('objective-outcome-close').click();job.objective_closeout.event_id='closed-2';
update('stale');assert(!d.open,'stale completion never auto-opens');
job.parent_campaign_id='parent';update();assert(!d.open);assert.equal(card.children.length,0,'child is never whole completion');
delete job.parent_campaign_id;update();assert(d.open);job.state='working';update();assert(!d.open,'new execution withdraws old prompt');
ui.stop();failedStorage=true;ui=api.boot(doc,()=>reply++);job.state='needs_you';job.next='third decision';update();native();
assert(!d.open,'unreliable storage uses manual entry, not auto-loop');assert(card.children.length);
listeners.click({target:{closest:()=>true}});assert(d.open);
ui.stop();
failedStorage=false;store.clear();writeFailure=true;
for(let reload=0;reload<2;reload++){
 ui=api.boot(doc,()=>reply++);update();native();
 assert(!d.open,'readable but unwritable storage never auto-opens, including reload');
 assert(card.children.length,'manual entry survives storage write failure');
 listeners.click({target:{closest:()=>true}});assert(d.open,'explicit opening works without persistence');ui.stop();
}
writeFailure=false;readbackMismatch=true;ui=api.boot(doc,()=>reply++);update();native();
assert(!d.open,'read-back mismatch never permits automatic modal');ui.stop();
readbackMismatch=false;store.clear();ui=api.boot(doc,()=>reply++);update();native();assert(d.open);
cx.__fawkesManagedAttentionPending=true;events['fawkes:attention-pending']({detail:{pending:true}});
assert(!d.open,'managed permission event releases the modal immediately');
update();native();listeners.click({target:{closest:()=>true}});
assert(!d.open,'neither manual entry nor native empty poll masks managed permission');
cx.__fawkesManagedAttentionPending=false;events['fawkes:attention-pending']({detail:{pending:false}});
assert(!d.open,'interrupted status does not repeat after managed resolution');
listeners.click({target:{closest:()=>true}});assert(d.open);
cx.__fawkesManagedAttentionPending=true;update();assert(!d.open,'projection polling reconciles a missed managed event');
ui.stop();assert(!events['fawkes:attention-pending'],'stop detaches managed listener');
cx.__fawkesManagedAttentionPending=false;
store.clear();ui=api.boot(doc,()=>reply++);job.state='needs_you';job.blocker_identity='3'.repeat(64);job.next='Identical wording';update();native();assert(d.open);
nodes.get('objective-outcome-close').click();update();native();assert(!d.open);
job.source_record_sha256='b'.repeat(64);job.last_activity_at='2026-09-14T13:00:00Z';update();assert(!d.open,'same blocker survives unrelated observation updates quietly');
job.state='working';update();job.state='needs_you';job.blocker_identity='4'.repeat(64);update();assert(d.open,'new canonical decision with identical words opens');
nodes.get('objective-outcome-close').click();ui.stop();ui=api.boot(doc,()=>reply++);update();native();assert(!d.open,'same new decision stays acknowledged after reload');
job.blocker_identity=null;update();assert(!d.open,'missing identity does not guess automatic notice identity');listeners.click({target:{closest:()=>true}});assert(d.open,'unknown identity remains manually accessible');ui.stop();
const cbox={module:{exports:{}},URL,Date,setTimeout,clearTimeout,setInterval,clearInterval,AbortController};cbox.globalThis=cbox;vm.createContext(cbox);vm.runInContext(fs.readFileSync('src/app/static/dev-console/console.js','utf8'),cbox);
const raw={...job,blocker_identity:'5'.repeat(64),recorded_status:'tanner_escalation',successful:false,historical:false,creates_authority:false};
assert.equal(cbox.module.exports.normalizeJobsResponse([raw]).jobs[0].blocker_identity,raw.blocker_identity,'normalization preserves complete blocker binding');
console.log('objective-outcome-identity-lifecycle-focus-storage-ok');

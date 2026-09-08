'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm'),crypto=require('crypto');
const thread='01a06f22-5b47-72c1-9b9c-b70157913436';
const final=(id,text='Exact reply\nC:\\Users\\Tanner\\file.txt\nPlease enter the Pi password in the native terminal.')=>({message_id:id,turn_id:'turn-'+id,role:'worker',phase:'final_answer',text,content_sha256:crypto.createHash('sha256').update(text).digest('hex')});
const value=f=>({thread_id:thread,state:'idle',verified_at:new Date().toISOString(),latest_final:f,completed_turn_ids:f?[f.turn_id]:[]});
class El{
 constructor(){this.hidden=true;this.open=false;this.dataset={};this.listeners={};this.children=[];this.value='Retain draft';}
 addEventListener(k,f){this.listeners[k]=f;}removeEventListener(k){delete this.listeners[k];}
 click(){this.listeners.click?.();}close(){this.open=false;}showModal(){this.open=true;this.shows=(this.shows||0)+1;}
 focus(){}matches(){return this.typing===true;}querySelector(){return this.children.find(c=>c.dataset.objectiveOutcome)||null;}prepend(e){this.children.unshift(e);}
}
const ids=['objective-outcome-dialog','objective-outcome-title','objective-outcome-objective','objective-outcome-result','objective-outcome-source','objective-outcome-reply','objective-outcome-close','worker-keyboard','worker-keyboard-toggle','worker-reply','page-menu'];
const nodes=new Map(ids.map(id=>[id,new El()])),store=new Map(),events={},dialog=nodes.get(ids[0]),card=new El();
let replied=0,broken=false;
const doc={activeElement:new El(),getElementById:id=>nodes.get(id),createElement:()=>new El(),querySelector:s=>s==='dialog[open]'?(dialog.open?dialog:null):s==='.current-briefing'?card:null,addEventListener(){},removeEventListener(){}};
const cx={module:{exports:{}},console,JSON,Set,Date,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>{if(broken)throw Error('quota');store.set(k,v);}},addEventListener:(k,f)=>events[k]=f,removeEventListener:k=>delete events[k],__fawkesMatrix:{active:false,wake(){throw Error('ordinary final must remain quiet in Matrix');}}};
vm.createContext(cx);vm.runInContext(fs.readFileSync('src/app/static/dev-console/outcome.js','utf8'),cx);
const api=cx.module.exports;
const observe=p=>events['fawkes:worker-message-observation']({detail:p?{connected:true,projection:p}:{connected:false}});
const native=pending=>events['fawkes:native-worker-attention']({detail:{connected:true,pending}});
const update=()=>ui.update({jobs:[],current_campaign_id:null},'live');
let ui=api.boot(doc,()=>replied++);native(false);observe(value(final('old')));assert(!dialog.open,'initial old final is a baseline, not new work');
observe(value(final('new')));assert(dialog.open);assert.equal(nodes.get('objective-outcome-result').textContent,final('new').text);
assert.match(nodes.get('objective-outcome-title').textContent,/Worker replied/);
assert.match(nodes.get('objective-outcome-objective').textContent,/does not by itself/);
assert.match(nodes.get('objective-outcome-source').textContent,/Message new/);
nodes.get('objective-outcome-reply').click();assert.equal(replied,1);assert.equal(nodes.get('worker-reply').value,'Retain draft');
observe(value(final('new')));assert(!dialog.open,'duplicate head does not alert');ui.stop();
ui=api.boot(doc,()=>replied++);native(false);observe(value(final('new')));assert(!dialog.open,'reload preserves baseline and seen identity');
const incomplete=value(final('streaming'));incomplete.completed_turn_ids=[];observe(incomplete);assert(!dialog.open,'streamed final without completed-turn evidence is not final');
native(true);observe(value(final('waiting')));assert(!dialog.open,'actual native request takes precedence');native(false);assert(dialog.open);
nodes.get('objective-outcome-close').click();doc.activeElement.typing=true;observe(value(final('while-typing')));assert(!dialog.open);doc.activeElement.typing=false;update();assert(dialog.open);
nodes.get('objective-outcome-close').click();cx.__fawkesMatrix.active=true;observe(value(final('matrix')));assert(!dialog.open);cx.__fawkesMatrix.active=false;update();assert(dialog.open);
observe(null);assert.match(nodes.get('objective-outcome-title').textContent,/Last known/);nodes.get('objective-outcome-close').click();update();assert(!dialog.open);
observe({...value(final('other-thread')),thread_id:'00000000-0000-0000-0000-000000000000'});assert(!dialog.open,'replacement thread cannot inherit pending alert');
broken=true;observe(value(final('storage-failure')));assert(!dialog.open,'no auto modal without durable acknowledgment');
broken=false;ui.stop();ui=api.boot(doc,()=>replied++);native(false);observe(value(final('storage-failure')));assert(dialog.open,'recover storage on reload without falsely claiming the failed notice was delivered');
nodes.get('objective-outcome-close').click();
// An already-acknowledged canonical blocker must not permanently mask later
// final replies. Both identities remain separate; neither grants permission.
ui.update({current_campaign_id:'campaign',jobs:[{job_id:'campaign',is_current_objective:true,state:'needs_you',next:'Known blocker',blocker_identity:'a'.repeat(64)}]},'live');assert(dialog.open);
nodes.get('objective-outcome-close').click();observe(value(final('after-blocker')));assert(dialog.open);assert.equal(nodes.get('objective-outcome-result').textContent,final('after-blocker').text);
const blocked={current_campaign_id:'campaign',jobs:[{job_id:'campaign',is_current_objective:true,state:'needs_you',next:'Known blocker',blocker_identity:'a'.repeat(64)}]};
for(let n=0;n<3;n++){
 ui.update(blocked,'live');observe(value(final('after-blocker')));native(false);
 assert(dialog.open,'D1: unchanged campaign/Worker/native-empty polls must not dismiss the displayed reply');
 assert.equal(nodes.get('objective-outcome-result').textContent,final('after-blocker').text);
}
observe(value(final('following-reply')));assert(dialog.open);assert.equal(nodes.get('objective-outcome-result').textContent,final('after-blocker').text,'new reply cannot replace a message still being read');
nodes.get('objective-outcome-close').click();ui.update(blocked,'live');assert(dialog.open);assert.equal(nodes.get('objective-outcome-source').textContent.includes('following-reply'),true);
nodes.get('objective-outcome-close').click();ui.update(blocked,'live');assert(!dialog.open);assert.match(card.children[0].textContent,/Worker replied/,'last corresponding reply remains manually retrievable instead of old acknowledged blocker');
ui.stop();ui=api.boot(doc,()=>replied++);native(false);ui.update(blocked,'live');observe(value(final('following-reply')));
assert(!dialog.open,'recovery does not replay acknowledged notices');assert.match(card.children[0].textContent,/Worker replied/,'reload restores latest reply entry');
ui.stop();assert(!events['fawkes:worker-message-observation']);
for(const f of [{...final('x'),phase:'commentary'},{...final('x'),role:'user'},{...final('x'),content_sha256:'wrong'}])assert.equal(api.finalNotice(value(f)),null);
console.log('worker-final-notice: exact public message, completed-turn identity, first-sync baseline, replay/reload, priority, typing, Matrix, disconnect, thread mismatch, storage failure and blocker independence passed; no provider/Pi claim');

async function hiddenPageTransport(){
 const {FakeElement}=require('./dev_console_projection_harness.js');
 const names=['worker-page','worker-reply','worker-send-reply','worker-send-update','worker-session-state','worker-reply-result','worker-copy-result','worker-session-identity','worker-final-message','worker-final-identity','worker-conversation-history','worker-older','worker-newest','worker-reply-form','worker-keyboard','worker-keyboard-toggle','worker-reading','worker-progress','worker-new-activity','worker-history-state'];
 const elements=new Map(names.map(id=>{const e=new FakeElement('div',id);e.value='';return [id,e];}));elements.get('worker-page').hidden=true;
 let now=100000,fail=false;const calls=[],observed=[],storage=new Map();
 class Clock extends Date{static now(){return now;}}
 const state={...value(final('hidden')),schema_version:'fawkes.worker_conversation.v1',can_reply:true,messages:[],page_item_ids:[],active_turn_ids:[],next_cursor:'must-not-walk-while-hidden'};
 const context={module:{exports:{}},console,TextEncoder,AbortController,setTimeout,clearTimeout,Date:Clock,
   MutationObserver:class{observe(){}disconnect(){}},setInterval(){return 1;},clearInterval(){},
   CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},dispatchEvent:e=>observed.push(e),
   localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
   fetch:async path=>{calls.push(path);if(fail)throw Error('offline');return {ok:true,json:async()=>state};}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('src/app/static/dev-console/worker.js','utf8'),context);
 const controller=context.module.exports.boot({getElementById:id=>elements.get(id),createElement:tag=>new FakeElement(tag)});
 const settle=async()=>{for(let n=0;n<8;n++)await new Promise(r=>setImmediate(r));};await settle();
 assert.equal(calls.length,1);assert.equal(observed[0].detail.projection.latest_final.message_id,'hidden');
 await controller.refresh();assert.equal(calls.length,1,'hidden head is limited to one check per ten seconds');
 now+=10000;await controller.refresh();assert.equal(calls.length,2);
 assert(calls.every(p=>p==='/api/development/worker'),'hidden pages do not walk history, send replies, or request clipboard');
 fail=true;now+=10000;await controller.refresh();assert.equal(observed.at(-1).detail.connected,false);
 // D2: the older cursor exists only AFTER a real visible head was loaded.
 // A hidden reading box then has zero dimensions, as in an actual browser.
 fail=false;elements.get('worker-page').hidden=false;
 elements.get('worker-reading').scrollHeight=2000;elements.get('worker-reading').clientHeight=300;
 state.messages=[state.latest_final];state.page_item_ids=[state.latest_final.message_id];
 await controller.refresh();await settle();
 elements.get('worker-page').hidden=true;elements.get('worker-reading').scrollHeight=0;elements.get('worker-reading').clientHeight=0;
 fail=true;now+=10000;const before=calls.length;await controller.refresh();await settle();
 assert.equal(calls.length,before+1,'D2: failed hidden head must not continue into older history or receipt queries');
 await elements.get('worker-reading').emit('scroll');await settle();
 assert.equal(calls.length,before+1,'hidden scroll event cannot traverse retained older cursor');
 controller.stop();console.log('hidden-page actual Worker boot passed: authenticated head observation, bounded polling, no mutation calls, disconnect event');
}
hiddenPageTransport().catch(error=>{console.error(error);process.exitCode=1;});

'use strict';
// Offline DOM contract: no HTTP server, provider, or real permission decision.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.listeners={};this.hidden=false;this.textContent='';this.scrollTop=2400;this.classList={toggle(){}};this.rect={top:0,height:0};}
  append(...items){this.children.push(...items);} appendChild(x){this.append(x);return x;}
  replaceChildren(...items){this.children=items;} setAttribute(k,v){this[k]=v;}
  addEventListener(k,f){this.listeners[k]=f;} removeEventListener(k){delete this.listeners[k];} querySelectorAll(){return [];}
  showModal(){assert(!this.open);this.open=true;this.modalStarts=(this.modalStarts||0)+1;} close(){this.open=false;}
  getBoundingClientRect(){return this.rect;} focus(options){this.focused=options;}
  click(){if(this.onclick)this.onclick();if(this.listeners.click)this.listeners.click();}
}
const nodes=new Map(['worker-page','worker-reading','worker-native-cards','worker-native-status','worker-native-result',
 'worker-native-history-items','worker-native-older','worker-keyboard','worker-keyboard-toggle','worker-reply',
 'worker-native-dialog','worker-native-dialog-scroll','worker-native-dialog-title','worker-native-open','worker-native-close'].map(id=>[id,new Element()]));
const reading=nodes.get('worker-reading'),cards=nodes.get('worker-native-cards'),status=nodes.get('worker-native-status');
reading.rect={top:100,height:350};status.rect={top:-2200,height:24};
nodes.get('worker-reply').value='Keep my draft';nodes.get('worker-reply').selectionStart=7;
nodes.get('worker-keyboard-toggle').onclick=()=>{nodes.get('worker-keyboard').hidden=!nodes.get('worker-keyboard').hidden;};
const events=new Map(),storage=new Map(),sent=[],THREAD='01a06f22-5b47-72c1-9b9c-b70157913436';
const request={thread_id:THREAD,request_key:'a'.repeat(64),action_sha256:'b'.repeat(64),logical_request_sha256:'c'.repeat(64),
 actionable:true,needs_decision:true,native_pending:true,status:'pending',created_at:'now',expires_at:'later',
 description:{environment:'local',command:'read only',cwd:'/tmp',turn_id:'turn',item_id:'item',reason:'Check deployment',
 choices:[{choice_id:'d'.repeat(64),label:'Once',scope:'One action'},{choice_id:'e'.repeat(64),label:'Save prefix',scope:'Exact saved prefix'},
 {choice_id:'f'.repeat(64),label:'Cancel',scope:'Interrupt turn'}]}};
let value={thread_id:THREAD,connected:true,pending_count:1,requests:[request],next_cursor:null};
const cx={module:{exports:{}},console,JSON,AbortController,CustomEvent:class{constructor(type,options={}){this.type=type;Object.assign(this,options);}},
 setTimeout,clearTimeout,setInterval:()=>1,clearInterval(){},crypto:{randomUUID:()=>THREAD},
 localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
 sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
 addEventListener:(name,f)=>events.set(name,f),removeEventListener:name=>events.delete(name),
 dispatchEvent:e=>{if(events.has(e.type))events.get(e.type)(e);},
 fetch:async(url,options)=>{sent.push({url,method:options.method||'GET'});return{ok:true,json:async()=>value};}};
vm.createContext(cx);vm.runInContext(fs.readFileSync('src/app/static/dev-console/worker-native.js','utf8'),cx);
const doc={getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag)};
const ui=cx.module.exports.boot(doc),settle=()=>new Promise(resolve=>setImmediate(resolve));
async function main(){
 await settle();
 const dialog=nodes.get('worker-native-dialog'),scroll=nodes.get('worker-native-dialog-scroll'),title=nodes.get('worker-native-dialog-title');
 const card=cards.children[0];card.rect={top:-2300,height:750};
 assert.equal(reading.scrollTop,2400,'ordinary incoming request must not move reading position');
 assert(!dialog.open,'incoming requests must not force open a modal');
 cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));
 assert(dialog.open);assert.equal(scroll.scrollTop,0);assert.equal(reading.scrollTop,2400,'conversation does not jump to a card');
 assert(title.focused.preventScroll);assert(nodes.get('worker-keyboard').hidden);
 assert.equal(nodes.get('worker-reply').value,'Keep my draft');assert.equal(nodes.get('worker-reply').selectionStart,7);
 assert.equal(card.children.find(e=>e.className==='worker-native-choices').children.filter(e=>e.tagName==='button').length,3);
 scroll.scrollTop=170;const before=reading.scrollTop;await ui.refresh();assert.equal(reading.scrollTop,before,'polling does not force conversation focus');
 assert.equal(scroll.scrollTop,170,'unchanged polling preserves dialog reading');
 card.children.find(e=>e.className==='worker-native-choices').children[0].click();
 assert.equal(scroll.scrollTop,170,'selecting an option does not jump to the top or submit');
 assert(cards.children[0].children.some(e=>e.className==='native-confirm'));
 nodes.get('worker-native-close').click();assert(!dialog.open);assert.equal(reading.scrollTop,before);
 nodes.get('worker-native-open').click();assert(dialog.open,'history remains reachable');assert.equal(dialog.modalStarts,2);
 cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));assert.equal(dialog.modalStarts,2,'no second modal instance');
 nodes.get('worker-native-close').click();
 await settle();
 nodes.get('worker-page').hidden=true;reading.scrollTop=1800;cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));
 assert.equal(reading.scrollTop,1800,'hidden page is not scrolled by a delayed navigation event');
 nodes.get('worker-page').hidden=false;
 value={...value,pending_count:0,requests:[{...request,status:'resolved',actionable:false,needs_decision:false,native_pending:false}]};
 await ui.refresh();cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));await settle();
 assert(title.focused.preventScroll,'PC-resolved request reveals current status, not stale choices');assert.equal(cards.children.length,0);
 assert(title.textContent.includes('history'));assert(nodes.get('worker-native-history-items').children.length===1);
 value={...value,connected:false};await ui.refresh();reading.scrollTop=1800;cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));
 assert(status.textContent.includes('empty queue is not confirmed'));
 assert(title.textContent.includes('unavailable'));
 assert(sent.every(e=>e.method==='GET'),'navigation never sends decision, CSRF, or ordinary chat');
 ui.stop();assert(!events.has('fawkes:show-native-worker-decision'));assert(!dialog.open);
 assert(!nodes.get('worker-native-open').listeners.click);
 console.log('native-decision-navigation-ok: single modal, close without decision, preserved conversation, draft, refresh, selection, history, PC race, disconnect, no submission');
}
async function keyboardIsolation(){
 const {FakeElement,fakeDocument,consoleApi,Scheduler,rawProjection}=require('./dev_console_projection_harness.js');
 const fixture=fakeDocument(),page=new FakeElement('section');page.className='console-page';page.dataset.page='4';fixture.pages.push(page);
 const button=new FakeElement('button');button.dataset.pageTarget='4';fixture.indicators.push(button);
 const controller=consoleApi.boot({document:fixture.document,fetch:async()=>({ok:true,status:200,json:async()=>rawProjection}),scheduler:new Scheduler(),projectionScheduler:new Scheduler(),baseUrl:'https://localhost:8791/',pollIntervalMs:0,disableUpdateRefresh:true});
 try{
  await settle();controller.navigation.go(4);
  const dialog=new FakeElement('dialog','worker-native-dialog'),title=new FakeElement('h2','worker-native-dialog-title');dialog.appendChild(title);
  // Reproduce D1 using the actual console boot/registered handler, not a copy.
  await fixture.shell.emit('keydown',{target:title,key:'ArrowLeft'});
  assert.equal(controller.navigation.page,3,'negative control must reproduce the background navigation defect');
  controller.navigation.go(4);
  const markup=fs.readFileSync('src/app/static/dev-console/index.html','utf8');
  const tag=markup.match(/<dialog\b[^>]*id="worker-native-dialog"[^>]*>/)[0];
  dialog.className=(tag.match(/class="([^"]+)"/)||[])[1]||'';
  for(const target of [title,dialog]){
   for(const key of ['ArrowLeft','ArrowRight','Escape','Tab']){
    const event=await fixture.shell.emit('keydown',{target,key});
    assert.equal(controller.navigation.page,4,'dialog keys must not navigate the background');
    assert(!event.defaultPrevented,'browser keeps native dialog Escape/Tab behavior');
   }
  }
  const outside=new FakeElement('div');
  await fixture.shell.emit('keydown',{target:outside,key:'ArrowLeft'});
  assert.equal(controller.navigation.page,3,'normal console navigation remains available outside modal');
  console.log('native-dialog-keyboard-owner-ok');
 }finally{controller.stop();ui.stop();}
}
(process.argv.includes('--keyboard')?keyboardIsolation():main()).catch(error=>{console.error(error);process.exitCode=1;});

'use strict';
// Offline DOM contract: no HTTP server, provider, or real permission decision.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.listeners={};this.hidden=false;this.textContent='';this.scrollTop=2400;this.classList={toggle(){}};this.rect={top:0,height:0};}
  append(...items){this.children.push(...items);} appendChild(x){this.append(x);return x;}
  replaceChildren(...items){this.children=items;} setAttribute(k,v){this[k]=v;}
  addEventListener(k,f){this.listeners[k]=f;} querySelectorAll(){return [];}
  getBoundingClientRect(){return this.rect;} focus(options){this.focused=options;}
  click(){if(this.onclick)this.onclick();if(this.listeners.click)this.listeners.click();}
}
const nodes=new Map(['worker-page','worker-reading','worker-native-cards','worker-native-status','worker-native-result',
 'worker-native-history-items','worker-native-older','worker-keyboard','worker-keyboard-toggle','worker-reply'].map(id=>[id,new Element()]));
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
 const card=cards.children[0];card.rect={top:-2300,height:750};
 assert.equal(reading.scrollTop,2400,'ordinary incoming request must not move reading position');
 cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));
 assert.equal(reading.scrollTop,0,'explicit opening reveals card above retained conversation');
 assert(card.focused.preventScroll);assert(nodes.get('worker-keyboard').hidden);
 assert.equal(nodes.get('worker-reply').value,'Keep my draft');assert.equal(nodes.get('worker-reply').selectionStart,7);
 assert.equal(card.children.find(e=>e.className==='worker-native-choices').children.filter(e=>e.tagName==='button').length,3);
 const before=reading.scrollTop;await ui.refresh();assert.equal(reading.scrollTop,before,'polling does not keep forcing focus');
 nodes.get('worker-page').hidden=true;reading.scrollTop=1800;cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));
 assert.equal(reading.scrollTop,1800,'hidden page is not scrolled by a delayed navigation event');
 nodes.get('worker-page').hidden=false;
 value={...value,pending_count:0,requests:[{...request,status:'resolved',actionable:false,needs_decision:false,native_pending:false}]};
 await ui.refresh();cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));
 assert(status.focused.preventScroll,'PC-resolved request reveals current status, not stale choices');assert.equal(cards.children.length,0);
 value={...value,connected:false};await ui.refresh();reading.scrollTop=1800;cx.dispatchEvent(new cx.CustomEvent('fawkes:show-native-worker-decision'));
 assert(status.textContent.includes('empty queue is not confirmed'));
 assert(sent.every(e=>e.method==='GET'),'navigation never sends decision, CSRF, or ordinary chat');
 ui.stop();assert(!events.has('fawkes:show-native-worker-decision'));
 console.log('native-decision-navigation-ok: reveal, keyboard/draft, refresh, hidden page, PC race, disconnect, no submission');
}
main().catch(error=>{console.error(error);process.exitCode=1;});

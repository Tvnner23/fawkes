"use strict";
const assert=require('node:assert/strict');
const {gesture}=require('../../deploy/pi_console_idle_hold.js');
let calls=0,progress=[];const make=()=>gesture(()=>0,(p,t)=>progress.push([p,t]),()=>calls++);
let g=make();g.down(1,0);assert.equal(g.up(1,100),'tap');g.tick(4000);assert.equal(calls,0);
g=make();g.down(1,0);g.tick(200);assert.match(progress.at(-1)[1],/Release to cancel/);assert.equal(g.up(1,900),'cancel');g.tick(4000);assert.equal(calls,0);
g=make();g.down(1,0);g.tick(2999);assert.equal(calls,0);g.tick(3000);g.tick(6000);assert.equal(calls,1);assert.equal(g.up(1,6001),'suppress');assert.equal(g.down(2,7000),false);
g=make();g.down(1,0);g.tick(2400);g.cancel();g.tick(4000);assert.equal(calls,1);
g=make();g.down(1,0);assert.equal(g.down(2,500),false);assert.equal(g.up(2,1000),'none');g.cancel();assert.equal(g.pending(),false);
g=make();g.down(1,0);assert.equal(g.up(1,3000),'suppress');assert.equal(calls,2);g.tick(4000);assert.equal(calls,2);
console.log('6 pure gesture cases passed; no physical event or OS shutdown performed.');

// Exercise the real installed listeners with controlled input evidence. These
// constructed trusted flags are synthetic test data, never physical Pi proof.
const {install}=require('../../deploy/pi_console_idle_hold.js');
function fixture(){
 let time=0,seq=0;const intervals=new Map(),events=new Map(),devents=new Map();
 const button={isConnected:true,getBoundingClientRect:()=>({left:10,right:90,top:10,bottom:60,width:80,height:50}),closest:()=>button};
 const other={closest:()=>null};
 const hint={style:{},setAttribute(){},remove(){},textContent:''};
 const input={value:'exact unsent draft',dispatchEvent(){}};
 const doc={hidden:false,activeElement:{blur(){}},createElement:()=>hint,
  documentElement:{appendChild(){}},getElementById:id=>id==='worker-reply'?input:null,
  addEventListener:(k,f)=>devents.set(k,f)};
 const win={document:doc,AbortController,Event,performance:{now:()=>time},
  crypto:{randomUUID:()=> '12345678-1234-4123-8123-123456789abc'},
  addEventListener:(k,f)=>{if(!events.has(k))events.set(k,[]);events.get(k).push(f);},
  setInterval:f=>{intervals.set(++seq,f);return seq;},clearInterval:id=>intervals.delete(id)};
 install(win,{});
 const fire=(kind,extra={})=>{const e={target:button,isTrusted:true,isPrimary:true,button:0,pointerId:1,clientX:30,clientY:30,
  prevented:false,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...extra};
  for(const f of events.get(kind)||[])f(e);return e;};
 return {win,doc,button,other,hint,fire,tick(t){time=t;for(const f of [...intervals.values()])f();},
  take:()=>win.__fawkesIdleShutdown.take(),hide(){doc.hidden=true;devents.get('visibilitychange')();}};
}
let f=fixture();f.fire('pointerdown');f.tick(100);f.fire('pointerup');assert.equal(f.take(),null);assert.equal(f.fire('click').prevented,false);
f=fixture();f.fire('pointerdown');f.tick(200);assert.match(f.hint.textContent,/Release to cancel/);f.tick(3000);assert.ok(f.take());assert.equal(f.take(),null);f.fire('pointerup');f.tick(5000);assert.equal(f.fire('click').prevented,true);
f=fixture();f.fire('pointerdown');f.tick(2500);f.fire('pointerup');assert.equal(f.fire('click').prevented,true);assert.equal(f.fire('click',{target:f.other}).prevented,false);f.tick(4000);assert.equal(f.take(),null);
for(const kind of ['pointercancel','blur','pagehide']){f=fixture();f.fire('pointerdown');f.tick(2000);f.fire(kind);f.tick(5000);assert.equal(f.take(),null,kind);}
f=fixture();f.fire('pointerdown');f.tick(2000);f.hide();f.tick(5000);assert.equal(f.take(),null);
f=fixture();f.fire('pointerdown');f.tick(2500);f.fire('pointermove',{clientX:91});f.fire('pointermove',{clientX:30});f.tick(5000);assert.equal(f.take(),null);
f=fixture();f.fire('pointerdown');f.tick(2900);f.fire('pointerup',{clientX:95});f.tick(5000);assert.equal(f.take(),null);
f=fixture();f.fire('pointerdown');f.button.isConnected=false;f.tick(5000);assert.equal(f.take(),null);
f=fixture();f.fire('pointerdown');f.fire('pointerdown',{pointerId:2,isPrimary:false});f.tick(5000);assert.equal(f.take(),null);
for(const flags of [{isTrusted:false},{button:2},{isPrimary:false}]){f=fixture();f.fire('pointerdown',flags);f.tick(5000);assert.equal(f.take(),null);}
f=fixture();f.fire('pointerdown');assert.equal(f.fire('contextmenu').prevented,true);f.tick(3000);assert.equal(f.fire('beforeinput').prevented,true);assert.equal(f.fire('keydown').prevented,true);
console.log('15 installed-listener scenarios passed, synthetic input only.');
for(const mode of ['leave-return','secondary','blur','pagehide']){
 f=fixture();f.fire('pointerdown');f.tick(300);assert.equal(f.win.__fawkesIdleShutdown.holding,true);
 if(mode==='leave-return'){f.fire('pointermove',{clientX:91});f.fire('pointermove',{clientX:30});}
 else if(mode==='secondary')f.fire('pointerdown',{pointerId:2,isPrimary:false});
 else f.fire(mode);
 f.tick(1800);f.fire('pointerup');assert.equal(f.take(),null,mode);
 assert.equal(f.fire('click').prevented,true,mode);assert.equal(f.win.__fawkesIdleShutdown.holding,false);
}
f=fixture();f.fire('pointerdown');f.tick(300);f.fire('pointercancel');f.tick(3000);
f.fire('pointerdown');f.tick(3100);f.fire('pointerup');assert.equal(f.fire('click').prevented,false);assert.equal(f.take(),null);
console.log('5 late-release cancellation/fresh-gesture regressions passed, synthetic only.');
f=fixture();f.fire('pointerdown');assert.equal(f.win.__fawkesIdleShutdown.navigationBlocked,true);
f.tick(3000);assert.equal(f.win.__fawkesIdleShutdown.navigationBlocked,true);
f.take();assert.equal(f.win.__fawkesIdleShutdown.navigationBlocked,true);
console.log('1 completed-intent navigation barrier regression passed, synthetic only.');
f=fixture();let lease=f.win.__fawkesIdleShutdown.beginNavigation();assert.equal(typeof lease,'string');
assert.equal(f.fire('pointerdown').prevented,true);f.tick(4000);assert.equal(f.win.__fawkesIdleShutdown.holding,false);assert.equal(f.take(),null);
assert.equal(f.fire('beforeinput').prevented,true);assert.equal(f.fire('click',{target:f.other}).prevented,true);
assert.equal(f.win.__fawkesIdleShutdown.endNavigation('wrong'),false);assert.equal(f.win.__fawkesIdleShutdown.navigationBlocked,true);
assert.equal(f.win.__fawkesIdleShutdown.endNavigation(lease),true);f.fire('pointerup');assert.equal(f.fire('click').prevented,true);
f.tick(5000);f.fire('pointerdown');f.tick(5100);f.fire('pointerup');assert.equal(f.fire('click').prevented,false);
f=fixture();f.fire('pointerdown');assert.equal(f.win.__fawkesIdleShutdown.beginNavigation(),null);f.tick(3000);assert.ok(f.take());assert.equal(f.win.__fawkesIdleShutdown.beginNavigation(),null);
f=fixture();lease=f.win.__fawkesIdleShutdown.beginNavigation();f.fire('pointerdown');f.fire('pointercancel');f.win.__fawkesIdleShutdown.endNavigation(lease);f.tick(1000);assert.equal(f.fire('click',{target:f.other}).prevented,false);
console.log('3 navigation-reservation interleaving/recovery scenarios passed, synthetic only.');
module.exports={fixture};

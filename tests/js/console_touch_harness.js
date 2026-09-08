'use strict';
const assert=require('assert');
const fs=require('fs'),vm=require('vm'),path=require('path');
const moduleBox={exports:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/app/static/dev-console/console.js'),'utf8'),
 {module:moduleBox,Date,URL,setTimeout,clearTimeout,setInterval,clearInterval,AbortController});
const api=moduleBox.exports;
let clock=1000;const actualNow=Date.now;Date.now=()=>clock;
function fixture(mode=true) {
 const events={},selection={isCollapsed:true,removeAllRanges(){this.cleared=true}};
 const outer={nodeType:1,style:{userSelect:'text'},scrollTop:0,scrollHeight:1600,clientHeight:500};
 const inner={nodeType:1,style:{userSelect:''},scrollTop:0,scrollHeight:800,clientHeight:200,parentElement:outer};
 const target={nodeType:1,style:{},scrollHeight:0,clientHeight:0,parentElement:inner,
  editable:false,closest(s){return s.startsWith('#')?outer:this.editable?this:null}};
 const doc={body:{},addEventListener(k,v){events[k]=v},removeEventListener(k){delete events[k]}};
 const env={__fawkesMatrixConfig:{emulatedPointerScroll:mode},getSelection:()=>selection,
  getComputedStyle:n=>({overflowY:n===target?'visible':'auto'})};
 const stop=api.attachContentScrolling(doc,env);
 function event(type,x,y,extra={}) {
  const e={type,clientX:x,clientY:y,pointerId:1,pointerType:'mouse',isPrimary:true,button:0,
   cancelable:true,target,detail:1,preventDefault(){this.prevented=true},stopPropagation(){this.stopped=true},
   stopImmediatePropagation(){this.stopped=true},...extra};events[type](e);return e;
 }
 return {event,events,outer,inner,target,selection,stop};
}
try {
 let f=fixture();f.event('pointerdown',50,300);f.event('pointermove',52,180);
 assert.equal(f.inner.scrollTop,120);assert.equal(f.outer.scrollTop,0);
 assert(f.event('pointerup',52,180).prevented);
 assert(f.event('click',52,180).prevented,'drag cannot approve/deny or enter Idle');
 assert.equal(f.inner.style.userSelect,'');
 f.event('pointerdown',52,180);f.event('pointerup',52,180);
 assert(!f.event('click',52,180).prevented,'new deliberate tap is allowed');
 f.event('pointerdown',50,180);f.event('pointermove',50,280);f.event('pointerup',50,280);
 assert.equal(f.inner.scrollTop,20,'downward swipe scrolls toward top');
 f.inner.scrollTop=590;f.event('pointerdown',50,300);f.event('pointermove',50,200);
 assert.equal(f.inner.scrollTop,600);assert.equal(f.outer.scrollTop,90,'nested remainder scrolls outer content');
 f.event('pointercancel',50,200);assert(f.event('click',50,200).prevented);
 assert.equal(f.inner.style.userSelect,'');f.stop();assert.equal(Object.keys(f.events).length,0);
 f=fixture();f.event('pointerdown',50,300,{pointerType:'touch'});
 assert(!f.event('pointermove',50,150,{pointerType:'touch'}).prevented,'native touch pan remains native');
 assert.equal(f.inner.scrollTop,0,'native scrolling is not duplicated in JS');
 f.event('pointercancel',50,150,{pointerType:'touch'});assert(f.event('click',50,150).prevented);
 f.stop();
 f=fixture(false);f.event('pointerdown',50,300);f.event('pointermove',50,150);
 assert.equal(f.inner.scrollTop,0,'ordinary desktop mouse selection is unchanged');f.stop();
 f=fixture();f.target.editable=true;f.event('pointerdown',50,300);f.event('pointermove',50,150);
 assert.equal(f.inner.scrollTop,0,'inputs and native selection controls are not drag scrollers');f.stop();
 f=fixture();f.selection.isCollapsed=false;f.event('pointerdown',50,300);f.event('pointermove',50,150);
 assert.equal(f.inner.scrollTop,0,'existing text selection remains operable');f.stop();
 f=fixture();f.event('pointerdown',50,300);clock+=500;f.event('pointermove',50,150);
 assert.equal(f.inner.scrollTop,0,'hold then drag permits text selection');f.stop();
 f=fixture();f.event('pointerdown',50,300);f.event('pointermove',200,298);
 assert.equal(f.inner.scrollTop,0,'horizontal page swipe is not vertical scrolling');
 f.event('pointerup',200,298);assert(f.event('click',200,298).prevented);
 assert(!f.event('click',200,298,{detail:0}).prevented,'keyboard activation is distinct');f.stop();
 for(const jitter of [1,-1,7,-7]) {
  f=fixture();f.event('pointerdown',50,300);f.event('pointermove',50+jitter,300);
  f.event('pointermove',52,180);assert.equal(f.inner.scrollTop,120,'sub-threshold initial sideways jitter cannot disable vertical scrolling');
  f.event('pointerup',52,180);assert(f.event('click',52,180).prevented);f.stop();
 }
 f=fixture();f.event('pointerdown',50,150);f.event('pointermove',51,150);
 f.event('pointermove',50,300);assert.equal(f.inner.scrollTop,0,'down swipe at top stays bounded');
 f.event('pointerup',50,300);assert(f.event('click',50,300).prevented);f.stop();
 f=fixture();f.event('pointerdown',50,300);f.event('pointermove',51,300);clock+=500;
 f.event('pointermove',52,180);assert.equal(f.inner.scrollTop,0,'threshold repair preserves hold-to-select');f.stop();
 console.log('console-touch-gesture-ok: native touch, observed Pi mouse fallback, nested scrolling, taps, drag guards, selection, inputs, cancellation, keyboard');
} finally {Date.now=actualNow}

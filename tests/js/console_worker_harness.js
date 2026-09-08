"use strict";
const assert=require('node:assert/strict');
const fs=require('node:fs');
const crypto=require('node:crypto');
const vm=require('node:vm');
function load(name){const context={module:{exports:{}},console};vm.createContext(context);vm.runInContext(fs.readFileSync('src/app/static/dev-console/'+name,'utf8'),context);return context.module.exports;}
const api=load('worker.js');
const text='```powershell\r\n& "C:\\Users\\Tanner\\My File.ps1"\r\n```\nDecision? café 🐦\n';
const digest=crypto.createHash('sha256').update(text).digest('hex');
const thread='01a06f22-5b47-72c1-9b9c-b70157913436';
const final={role:'worker',phase:'final_answer',text,content_sha256:digest,message_id:'m1',turn_id:'t1'};
const projection={schema_version:'fawkes.worker_conversation.v1',thread_id:thread,messages:[final],latest_final:final,
    state:'idle',can_reply:true,verified_at:'2026-09-12T00:00:00+00:00'};
assert.equal(api.projection(projection).latest_final.text,text);
assert.throws(()=>api.projection({...projection,thread_id:'other'}));
assert.throws(()=>api.projection({...projection,latest_final:{...final,phase:'commentary'}}));
assert.throws(()=>api.projection({...projection,verified_at:'unknown'}));
const expected={thread_id:thread,message_id:'m1',content_sha256:digest};
const update={worker_message:expected,content:text,content_sha256:digest,snapshot_id:'console-update-'+digest,
    windows_clipboard:{status:'copied',code:'verified_windows_readback',snapshot_id:'console-update-'+digest,content_sha256:digest,copied_at:'now'}};
assert.match(api.copyStatus(update,expected),/^Copied verbatim to Windows/);
assert.doesNotMatch(api.copyStatus({...update,windows_clipboard:{status:'unknown'}},expected),/^Copied/);
assert.doesNotMatch(api.copyStatus({...update,windows_clipboard:{...update.windows_clipboard,code:'saved_only'}},expected),/^Copied/);
assert.throws(()=>api.copyStatus({...update,worker_message:{...expected,thread_id:'other'}},expected));
const plain=value=>JSON.parse(JSON.stringify(value));
assert.deepEqual(plain(api.insertKey('Hello',5,5,'Space')),{text:'Hello ',position:6});
assert.deepEqual(plain(api.insertKey('Hi 🐦',5,5,'Backspace')),{text:'Hi ',position:3});
assert.deepEqual(plain(api.insertKey('Hello',1,4,'i')),{text:'Hio',position:2});
const html=fs.readFileSync('src/app/static/dev-console/index.html','utf8');
assert(!html.includes('id="save-console-update"'));
assert(html.includes('id="reply-to-worker"'));
assert(html.indexOf('id="worker-send-update"')>html.indexOf('id="worker-page"'));
assert(html.includes('id="worker-reply-form"')&&html.includes('id="worker-keyboard"'));
assert.equal(load('console.js').PAGE_TITLES.length,5);
console.log('16 Worker-page assertions passed; no browser, clipboard or provider claim.');

// Exercise the complete production boot/event/storage/request path, not a
// duplicate implementation of its idempotency or connection-state decisions.
const {FakeElement,fakeDocument,consoleApi,Scheduler,rawProjection}=require('./dev_console_projection_harness.js');
const settle=async()=>{for(let i=0;i<12;i++)await new Promise(r=>setImmediate(r));};
function environment(store=new Map(),options={}){
  const elements=new Map();
  for(const id of ['worker-page','worker-reply','worker-send-reply','worker-send-update','worker-session-state','worker-reply-result','worker-copy-result','worker-session-identity','worker-final-message','worker-final-identity','worker-conversation-history','worker-older','worker-newest','worker-reply-form','worker-keyboard','worker-keyboard-toggle']){
    const e=new FakeElement('div',id);e.value='';elements.set(id,e);
  }
  let fail=options.fail||false,drop=options.drop||false,postFail=options.postFail||false,lookupFail=options.lookupFail||false;
  const posts=[];let last=null,now=Date.now(),lookupCount=0,projectionCount=0;
  const deferred=[];let intervalCallback=null,projectionPending=false,resolveProjection=null;
  class ClockDate extends Date {static now(){return now;}}
  const response=(body,ok=true)=>({ok,status:ok?200:400,json:async()=>body});
  const context={module:{exports:{}},console,Date:ClockDate,TextEncoder,AbortController,setTimeout,clearTimeout,
    setInterval:fn=>{intervalCallback=fn;return 1;},clearInterval:()=>{},crypto:{randomUUID:()=>crypto.randomUUID()},
    MutationObserver:class{observe(){}disconnect(){}},
    localStorage:{getItem:k=>store.get(k)||null,setItem(k,v){if(fail)throw Error('synthetic quota');if(!drop)store.set(k,v);}},
    fetch:async(path,opts)=>{
      if(path==='/api/session/console-csrf')return response({csrf_token:'synthetic'});
      if(path==='/api/development/worker'){
        projectionCount++;const result=response({...projection,verified_at:new Date(now).toISOString()});
        if(projectionPending)return new Promise(resolve=>{resolveProjection=()=>resolve(result);});
        return result;
      }
      if(path.includes('/replies/')){
        lookupCount++;
        if(options.lookupPending)return new Promise(resolve=>deferred.push(resolve));
        return lookupFail?response({error:{message:'No durable intent exists'}},false):response(last);
      }
      if(path.endsWith('/replies')){
        const body=JSON.parse(opts.body);posts.push(body);
        if(postFail)throw Error('synthetic failure before server intent');
        last={...body,status:'queued'};return response(last);
      }
      if(path.endsWith('/clipboard')){posts.push(JSON.parse(opts.body));return response(update);}
      throw Error('unexpected route '+path);
    }};
  vm.createContext(context);vm.runInContext(fs.readFileSync('src/app/static/dev-console/worker.js','utf8'),context);
  const controller=context.module.exports.boot({getElementById:id=>elements.get(id),createElement:tag=>new FakeElement(tag)});
  return {elements,posts,controller,store,setFail(v){fail=v;},setPostFail(v){postFail=v;},setLookupFail(v){lookupFail=v;},
    advance(ms){now+=ms;},counts(){return {lookupCount,projectionCount};},
    tick(){intervalCallback();},holdProjection(){projectionPending=true;},releaseProjection(){projectionPending=false;resolveProjection();},
    finishLookup(ok=true){deferred.shift()(ok?response(last):response({error:{message:'Slow receipt failed'}},false));}};
}
async function recoveryCases(){
  const key='fawkes-worker-page-v1';
  // G17-001: no request may leave after failed or silently discarded storage.
  for(const options of [{fail:true},{drop:true}]){
    const store=new Map([[key,JSON.stringify({draft:'Same reply',pendingReply:null,pendingCopy:null})]]);
    const first=environment(store,options);await settle();
    assert.equal(first.elements.get('worker-session-state').dataset.connection,'idle');
    const history=first.elements.get('worker-conversation-history');
    assert.equal(history.children[0].dataset.role,'worker');
    assert.match(history.children[0].children[0].textContent,/^WORKER \/\/ FINAL/);
    assert.equal(history.children[0].children[1].textContent,text);
    await first.elements.get('worker-reply-form').emit('submit');assert.equal(first.posts.length,0);
    assert.equal(first.elements.get('worker-send-reply').disabled,true);first.controller.stop();
    const reload=environment(store);await settle();await reload.elements.get('worker-reply-form').emit('submit');
    assert.equal(reload.posts.length,1);assert.equal(reload.posts[0].text,'Same reply');
    assert.equal(JSON.parse(store.get(key)).pendingReply.reply_id,reload.posts[0].reply_id);reload.controller.stop();
  }
  // Same failure boundary also protects final-message copy identity.
  const copy=environment(new Map(),{fail:true});await settle();
  await copy.elements.get('worker-send-update').emit('click');assert.equal(copy.posts.length,0);
  assert.match(copy.elements.get('worker-copy-result').textContent,/not attempted/);copy.controller.stop();
  const invalid=environment();await settle();
  for(const text of ['x\0','🐦'.repeat(4001)]){
    invalid.elements.get('worker-reply').value=text;await invalid.elements.get('worker-reply').emit('input');
    await invalid.elements.get('worker-reply-form').emit('submit');assert.equal(invalid.posts.length,0);
    assert.equal(JSON.parse(invalid.store.get(key)).pendingReply,null);
  }
  invalid.elements.get('worker-reply').value='Corrected reply';await invalid.elements.get('worker-reply').emit('input');
  await invalid.elements.get('worker-reply-form').emit('submit');assert.equal(invalid.posts.length,1);invalid.controller.stop();
  // G17-003: failed/missing intent lookup is not loss of healthy projection.
  const retry=environment(new Map(),{postFail:true,lookupFail:true});await settle();
  retry.elements.get('worker-reply').value='Retain this exact reply';await retry.elements.get('worker-reply').emit('input');
  await retry.elements.get('worker-reply-form').emit('submit');const firstId=retry.posts[0].reply_id;
  await retry.controller.refresh();
  assert.match(retry.elements.get('worker-session-state').textContent,/^Connected/);
  assert.equal(retry.elements.get('worker-send-update').disabled,false);
  assert.equal(retry.elements.get('worker-send-reply').disabled,false);
  retry.setPostFail(false);await retry.elements.get('worker-reply-form').emit('submit');
  assert.equal(retry.posts[1].reply_id,firstId);retry.controller.stop();
  const recovered=environment(retry.store,{lookupFail:true});await settle();
  assert.match(recovered.elements.get('worker-session-state').textContent,/^Connected/);
  assert.equal(recovered.elements.get('worker-send-update').disabled,false);
  await recovered.elements.get('worker-reply-form').emit('submit');
  assert.equal(recovered.posts[0].reply_id,firstId);recovered.controller.stop();
  // G17-R1-002: receipt latency must not serialize healthy projection or copy.
  const slow=environment(new Map(),{lookupPending:true});await settle();
  slow.elements.get('worker-reply').value='One identity';await slow.elements.get('worker-reply').emit('input');
  await slow.elements.get('worker-reply-form').emit('submit');const slowId=slow.posts[0].reply_id;
  const waiting=slow.controller.refresh();await settle();
  assert.equal(slow.elements.get('worker-send-update').disabled,false);
  assert.equal(slow.elements.get('worker-send-reply').disabled,false);
  const before=slow.counts().projectionCount;slow.advance(16000);
  await slow.controller.refresh();await settle();
  assert(slow.counts().projectionCount>before);assert.equal(slow.counts().lookupCount,1);
  assert.equal(slow.elements.get('worker-send-update').disabled,false);
  await slow.elements.get('worker-send-update').emit('click');assert.equal(slow.posts.length,2);
  slow.finishLookup(false);await waiting;await settle();
  assert.equal(JSON.parse(slow.store.get(key)).pendingReply.reply_id,slowId);
  assert.equal(slow.elements.get('worker-send-update').disabled,false);
  await slow.elements.get('worker-reply-form').emit('submit');assert.equal(slow.posts[2].reply_id,slowId);
  slow.controller.stop();
  // The same freshness boundary must change the label, not only disable actions.
  const stale=environment();await settle();stale.holdProjection();stale.advance(16000);stale.tick();await settle();
  assert.equal(stale.elements.get('worker-send-update').disabled,true);
  assert.match(stale.elements.get('worker-session-state').textContent,/^Stale/);
  stale.releaseProjection();await settle();
  assert.match(stale.elements.get('worker-session-state').textContent,/^Connected/);
  assert.equal(stale.elements.get('worker-send-update').disabled,false);stale.controller.stop();
  // G17-006: actual console boot must leave cursor navigation to the textarea.
  const fixture=fakeDocument();const page=new FakeElement('section');page.className='console-page';page.dataset.page='4';fixture.pages.push(page);
  const button=new FakeElement('button');button.dataset.pageTarget='4';fixture.indicators.push(button);
  const boot=consoleApi.boot({document:fixture.document,fetch:async()=>({ok:true,status:200,json:async()=>rawProjection}),scheduler:new Scheduler(),projectionScheduler:new Scheduler(),baseUrl:'https://localhost:8791/',pollIntervalMs:0,disableUpdateRefresh:true});
  await settle();boot.navigation.go(4);
  const input=new FakeElement('textarea','worker-reply');const original=input.matches.bind(input);
  input.matches=selector=>selector==='textarea'||original(selector);
  for(const key of ['ArrowLeft','ArrowRight']){
    const event=await fixture.shell.emit('keydown',{target:input,key});
    assert(!event.defaultPrevented);assert.equal(boot.navigation.page,4);
  }
  const editable=new FakeElement();editable.matches=selector=>selector.split(',').some(part=>part.trim()==="[contenteditable]:not([contenteditable='false'])");
  const event=await fixture.shell.emit('keydown',{target:editable,key:'ArrowLeft'});
  assert(!event.defaultPrevented);assert.equal(boot.navigation.page,4);
  // G17-R1-003: selecting/editing text is not a page-navigation gesture.
  const stack=fixture.document.getElementById('page-stack');
  for(const target of [input,editable]){
    await stack.emit('pointerdown',{target,clientX:200,clientY:400});
    await stack.emit('pointerup',{target,clientX:300,clientY:402});
    assert.equal(boot.navigation.page,4);
  }
  boot.stop();
  console.log('11 complete-boot recovery/input scenarios passed; no real network, clipboard or provider.');
}
recoveryCases().catch(error=>{console.error(error);process.exitCode=1;});

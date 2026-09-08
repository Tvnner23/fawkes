'use strict';
const assert=require('assert'),fs=require('fs'),vm=require('vm');
class Node {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.hidden=false;this.style={};this.textContent='';}
  append(...items){this.children.push(...items)} appendChild(item){this.append(item);return item}
  replaceChildren(...items){this.children=items} setAttribute(k,v){this[k]=v}
  addEventListener(k,fn){this.listeners[k]=fn}
  remove(){} getContext(){return {fillRect(){},fillText(){}}}
}
const descendants=n=>[n,...n.children.flatMap(descendants)];
const panel=new Node('section'),body=new Node('body'),events={},wake=[];
const stored=new Map();
let latestTimer=null;
const root={document:{getElementById:id=>id==='native-permission'?panel:null,createElement:t=>new Node(t),body},
  sessionStorage:{getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)},
  addEventListener:(name,fn)=>events[name]=fn,dispatchEvent:event=>{if(event.type==='fawkes:attention-pending')wake.push(event.detail.pending)},
  CustomEvent:class {constructor(type,options){this.type=type;Object.assign(this,options)}},Date,JSON,console,
  __fawkesMatrix:{active:true,wake(){this.active=false;wake.push('woke')}},
  setTimeout(fn,ms){latestTimer=fn;return {unref(){}}},clearTimeout(){}};
root.window=root;root.globalThis=root;let value=null,posts=[],lost=false,offline=false;
root.fetch=async(path,options)=>{
  if(offline)throw Error('fixture disconnected');
  if(path==='/api/session/console-csrf')return {ok:true,json:async()=>({csrf_token:'synthetic-csrf'})};
  if(options.method==='POST'){
    const submitted=JSON.parse(options.body);posts.push(submitted);
    value={attention:{...value.attention,state:'approved_once'},decision:{
      attention_id:submitted.identity.attention_id,campaign_id:submitted.identity.campaign_id,
      invocation_id:submitted.identity.invocation_id,choice:submitted.choice,decision_id:'fixture-decision',
      record_sha256:'record',protocol_binding_sha256:submitted.identity.protocol_binding_sha256,
      authority_binding_sha256:'authority',authority_binding:Object.fromEntries(Object.entries(submitted.identity).reverse()),
      creates_continuing_authority:false,consumed:true,lifecycle_state:'completed'}};
    if(lost)throw Error('lost HTTP response');
  }
  return {ok:true,json:async()=>value};
};
vm.runInNewContext(fs.readFileSync('src/app/static/attention-binding.js','utf8'),root);
vm.runInNewContext(fs.readFileSync('src/app/static/native-attention.js','utf8'),root);
const binding=root.FawkesAttentionBinding;
function fixture(id){
  return {attention:{attention_id:id,campaign_id:'fixture-campaign',invocation_id:'fixture-invocation',
    state:'needs_tanner',actionable:true,authority_binding_sha256:'authority',protocol_binding_sha256:'protocol',
    decision_nonce:'nonce-'+id,expires_at:new Date(Date.now()+60000).toISOString(),worker:{worker_id:'fixture-worker'},
    blocked_action:'harmless fixture only',protocol_binding:{method:'item/commandExecution/requestApproval',
      item_id:id,candidate_snapshot_id:'fixture-candidate',candidate_record_sha256:'candidate',
      mutation_digest_sha256:'mutation',native_decision_choices:['approve_once','deny','cancel_campaign']}},decision:null};
}
const buttons=()=>descendants(panel).filter(x=>x.tagName==='button');
const launcher=()=>body.children.filter(x=>x.id==='permission-launcher').at(-1);
const connection=()=>body.children.filter(x=>x.id==='permission-connection').at(-1);
async function main(){
  assert(launcher().hidden,'no unverified initial request can display Permissions');
  assert(!connection().hidden,'unknown queue is not a confirmed empty queue');
  await events['fawkes:console-observation']({detail:{attention:[]}});
  assert.deepEqual(wake,[],'ordinary activity must not wake Matrix');
  assert(launcher().hidden);assert(connection().hidden,'confirmed empty queue hides permission connection warning');
  value=fixture('attention-one');
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  assert(wake.includes('woke'));assert(buttons().some(x=>x.textContent==='Approve Once'));
  const technical=descendants(panel).find(x=>x.tagName==='details');
  assert.equal(technical.open,false,'technical material starts collapsed');
  assert(descendants(technical).some(x=>x.textContent==='Show technical details'));
  assert(descendants(technical).some(x=>x.textContent===value.attention.blocked_action),'recorded command stays available in technical details');
  assert(descendants(panel).some(x=>x.textContent==='Why — Worker’s stated reason'));
  assert(descendants(panel).some(x=>x.textContent.includes('not independently verified necessity')));
  const overviewIndex=panel.children.findIndex(x=>x.className==='permission-explanation');
  assert(overviewIndex>=0&&overviewIndex<panel.children.findIndex(x=>x.textContent==='Approve Once'),'explanation precedes decisions');
  assert.equal(buttons().find(x=>x.textContent==='Approve Once').className,'permission-approve_once');
  technical.open=true;technical.ontoggle();
  assert(!launcher().hidden,'exact pending request reveals Permissions');
  const wakesBeforeReconnect=wake.filter(x=>x==='woke').length;
  events['fawkes:console-disconnected']({});
  assert(!launcher().hidden&&launcher().textContent.includes('last known'),'disconnect cannot claim a previously pending request disappeared');
  assert.equal(launcher().className,'','unverified request stops pulsing');
  assert(!connection().hidden,'disconnect must remain visible, not empty');
  root.__fawkesMatrix.active=true;
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  assert.equal(descendants(panel).find(x=>x.tagName==='details').open,true,'same request retains expanded technical details across reconnect');
  assert.equal(wake.filter(x=>x==='woke').length,wakesBeforeReconnect,'same pending request must not wake again after reconnect');
  assert(root.__fawkesMatrix.active);
  root.FawkesNativeAttention.attach(root.document,root.fetch);
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  assert.equal(wake.filter(x=>x==='woke').length,wakesBeforeReconnect,'reload retains cosmetic wake identity without deciding');
  assert.equal(posts.length,0);
  const original=binding.canonicalAttentionIdentity(value.attention);
  let middlePrevented=false;panel.listeners.auxclick({preventDefault(){middlePrevented=true},stopPropagation(){}});
  assert(middlePrevented);assert.equal(posts.length,0);
  buttons().find(x=>x.textContent==='Approve Once').onclick();
  assert.equal(posts.length,0,'first click selects; it cannot decide');
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  const confirm=buttons().find(x=>x.textContent==='Confirm Approve Once');assert(confirm,'refresh preserves confirmation selection');
  lost=true;
  await Promise.all([confirm.onclick(),confirm.onclick()]);
  assert.equal(posts.length,1,'double click and lost response must not resubmit');
  assert.deepEqual(posts[0].identity,JSON.parse(JSON.stringify(original)));
  assert(descendants(panel).some(x=>x.textContent.includes('Executed — exact action completed')));
  assert(!buttons().some(x=>x.textContent==='Approve Once'));
  assert(launcher().hidden,'resolved request cannot keep Permissions visible');
  const resolved=value, expected=binding.canonicalAttentionIdentity(value.attention);
  assert(binding.requireCanonicalDecisionResult(value,expected,'authority','approve_once'));
  assert(binding.canonicalAttentionIdentityMatches(value.attention,Object.fromEntries(Object.entries(expected).reverse()),'authority'));
  for(const key of Object.keys(expected)) {
    for(const bad of [undefined,{},42,expected[key]===null?'changed':null]) {
      const changed={...value.decision.authority_binding};
      if(bad===undefined)delete changed[key];else changed[key]=bad;
      assert(!binding.canonicalDecisionIdentityMatches({...value.decision,authority_binding:changed},expected,'authority','approve_once'),key);
    }
  }
  assert(!binding.canonicalDecisionIdentityMatches({...value.decision,authority_binding:{...expected,extra:null}},expected,'authority','approve_once'));
  root.FawkesNativeAttention.attach(root.document,root.fetch);
  await events['fawkes:console-observation']({detail:{attention:[]}});
  assert(descendants(panel).some(x=>x.textContent.includes('Executed — exact action completed')),'reload must recover canonical outcome');
  assert.equal(posts.length,1);
  offline=true;events['fawkes:console-disconnected']({});
  assert(descendants(panel).some(x=>x.textContent.includes('Disconnected / stale')));
  assert.equal(posts.length,1);
  offline=false;
  await events['fawkes:console-observation']({detail:{attention:[]}});
  assert(descendants(panel).some(x=>x.textContent.includes('Executed — exact action completed')));
  assert.equal(posts.length,1,'reconnect observes only');
  value=fixture('attention-two');value.attention.protocol_binding.native_decision_choices=['deny'];
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  assert(!buttons().some(x=>x.textContent==='Approve Once'));
  assert(buttons().some(x=>x.textContent==='Deny action'));
  value=fixture('attention-three');
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  buttons().find(x=>x.textContent==='Approve Once').onclick();
  const oldConfirm=buttons().find(x=>x.textContent==='Confirm Approve Once');
  value=fixture('attention-four');
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  assert.equal(descendants(panel).find(x=>x.tagName==='details').open,false,'new exact request starts its own details');
  assert(!buttons().some(x=>x.textContent==='Confirm Approve Once'),'selection for A must not become confirmation for B');
  await oldConfirm.onclick();assert.equal(posts.length,1,'a delayed confirmation cannot retarget another request');
  lost=false;buttons().find(x=>x.textContent==='Deny action').onclick();
  await buttons().find(x=>x.textContent==='Confirm Deny action').onclick();
  assert.equal(posts.length,2);assert.equal(posts[1].choice,'deny');
  root.FawkesNativeAttention.attach(root.document,root.fetch);
  await events['fawkes:console-observation']({detail:{attention:[]}});
  assert(descendants(panel).some(x=>x.textContent.includes('Denied — campaign stopped safely')));
  assert.equal(posts.length,2);
  assert(launcher().hidden,'denial confirmed by canonical owner clears Permissions');
  value=fixture('attention-expired');value.attention.expires_at=new Date(Date.now()-1).toISOString();
  root.FawkesNativeAttention.attach(root.document,root.fetch);
  await events['fawkes:console-observation']({detail:{attention:[]}});
  assert(launcher().hidden,'expired requests never expose Permissions');
  value=fixture('attention-cancelled');value.attention.state='cancelled';value.attention.actionable=false;
  await events['fawkes:console-observation']({detail:{attention:[]}});
  assert(launcher().hidden,'cancelled historical request does not expose Permissions');
  value=fixture('attention-reconnected');
  await events['fawkes:console-observation']({detail:{attention:[value.attention]}});
  assert(!launcher().hidden,'new pending request remains discoverable after history');
  const beforeExpiryPosts=posts.length;
  const expiryCallback=latestTimer;
  const clock=Date.now()+120000;
  root.Date=class extends Date {static now(){return clock}};
  expiryCallback();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert(launcher().hidden,'local deadline clears attention immediately without another poll');
  assert(!buttons().some(x=>x.textContent==='Approve Once'),'deadline disables choices');
  assert.equal(posts.length,beforeExpiryPosts,'expiry only observes, never submits');
  root.Date=Date;
  value=fixture('attention-prior-resolved');value.attention.state='expired';value.attention.actionable=false;
  const first={attention_id:value.attention.attention_id,actionable:true,state:'needs_tanner',expires_at:new Date(Date.now()+60000).toISOString()};
  const second=fixture('attention-next').attention;
  const oldFetch=root.fetch;
  const readNext=async(path,opts)=>{
    if(path.endsWith('/attention-next'))return {ok:true,json:async()=>({attention:second,decision:null})};
    return oldFetch(path,opts);
  };
  root.FawkesNativeAttention.attach(root.document,readNext);
  await events['fawkes:console-observation']({detail:{attention:[first,second]}});
  assert(!launcher().hidden,'resolving first queue entry must reveal another pending request');
  assert(descendants(panel).some(x=>x.textContent.includes('attention-next')));
  assert.equal(posts.length,beforeExpiryPosts);
  value={attention:{...second,invocation_id:'neighbor'},decision:null};
  root.FawkesNativeAttention.attach(root.document,root.fetch);
  await events['fawkes:console-observation']({detail:{attention:[]}});
  assert(descendants(panel).some(x=>x.textContent.includes('Remembered request identity mismatch')));
  assert(!buttons().some(x=>x.textContent==='Approve Once'));
  console.log('pi-native-attention-dom-ok');
}
main().catch(error=>{console.error(error);process.exitCode=1});

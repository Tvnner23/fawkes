(function(root) {
  'use strict';
  const binding = root.FawkesAttentionBinding;
  const labels = {approve_once:'Approve Once', deny:'Deny action', cancel_campaign:'Cancel campaign'};
  function outcome(value) {
    const event=value && value.attention, decision=value && value.decision;
    if (!event) return 'Unavailable — no exact request';
    if (event.state === 'expired'||(!decision&&Number.isFinite(Date.parse(event.expires_at))&&Date.parse(event.expires_at)<=Date.now())) return 'Expired — no approval is available';
    if (!decision) return event.actionable === true ? 'Waiting for Tanner' : 'Unavailable — action is not verifiably live';
    if (decision.choice === 'deny') return 'Denied — campaign stopped safely';
    if (decision.choice === 'cancel_campaign') return 'Cancelled — campaign ended';
    const lifecycle=decision.lifecycle_state || event.approval_outcome;
    if (['completed','live_action_completed','action_completed'].includes(lifecycle)) return 'Executed — exact action completed';
    if (String(lifecycle).includes('failed') || String(lifecycle).includes('expired')) return 'Failed — no retry authorized';
    if (decision.consumed === true) return 'Approval consumed — awaiting recorded action outcome';
    return 'Approval recorded — awaiting single-use consumption';
  }
  function attach(document, fetchImpl) {
    const panel=document.getElementById('native-permission');
    if (!panel || !binding) return null;
    let current=null, selected=null, csrf='', sending=false, stale=true, closedId=null, sequence=0;
    let lastRender=null, lastFailure='', expiryTimer=null, pendingQueue=[];
    const locatorKey='fawkes.native-attention.locator.v1';
    const wakeKey='fawkes.native-attention.woken.v1';
    let woken=[];
    try {
      const saved=JSON.parse(root.sessionStorage.getItem(wakeKey));
      if(Array.isArray(saved))woken=saved.filter(x=>typeof x==='string'&&x.length<=1100).slice(-128);
    }catch(_){/* Cosmetic memory only, never permission authority. */}
    function locator(value) {
      if (!value || typeof value !== 'object' || Array.isArray(value)
          || Object.keys(value).length!==3) return null;
      const keys=['attention_id','campaign_id','invocation_id'];
      return keys.every(k=>typeof value[k]==='string' && /^[A-Za-z0-9_.:-]{1,256}$/.test(value[k]))
        ? Object.fromEntries(keys.map(k=>[k,value[k]])) : null;
    }
    let remembered=null;
    try {remembered=locator(JSON.parse(root.sessionStorage.getItem(locatorKey)));}catch(_){/* Storage is optional, never authority. */}
    function remember(event) {
      remembered=locator({attention_id:event.attention_id,campaign_id:event.campaign_id,invocation_id:event.invocation_id});
      try {if(remembered)root.sessionStorage.setItem(locatorKey,JSON.stringify(remembered));}catch(_){}
    }
    const button=document.createElement('button'); button.id='permission-launcher'; button.textContent='⚠ Permissions';
    button.type='button';button.hidden=true;
    document.body.append(button);
    const connection=document.createElement('p');connection.id='permission-connection';
    connection.setAttribute('role','status');document.body.append(connection);
    function needsDecision(value) {
      const event=value&&value.attention;
      return Boolean(event&&!value.decision&&event.state==='needs_tanner'&&event.actionable===true
        &&Number.isFinite(Date.parse(event.expires_at))&&Date.parse(event.expires_at)>Date.now());
    }
    function updateLauncher() {
      const pending=needsDecision(current);
      button.hidden=!pending;
      button.textContent=stale?'⚠ Permissions · last known':'⚠ Permissions';
      button.className=pending&&!stale?'needs-tanner':'';
      connection.hidden=!stale;
      connection.textContent=stale?'Permissions unavailable — checking connection':'';
      if(expiryTimer!==null)root.clearTimeout(expiryTimer);
      expiryTimer=null;
      if(pending) {
        expiryTimer=root.setTimeout(()=>{
          selected=null;cosmeticPending(false);updateLauncher();render();
          if(current&&!sending)refreshExact(current.attention.attention_id);
        },Math.min(2147483647,Math.max(1,Date.parse(current.attention.expires_at)-Date.now())));
        if(expiryTimer&&expiryTimer.unref)expiryTimer.unref();
      }
    }
    function element(tag,text) {const x=document.createElement(tag);x.textContent=text;return x;}
    async function request(path, options) {
      const response=await fetchImpl(path,{credentials:'same-origin',cache:'no-store',...options,
        headers:{'Content-Type':'application/json',...(csrf ? {'X-Fawkes-CSRF-Token':csrf} : {}),...(options&&options.headers||{})}});
      const value=await response.json();
      if (!response.ok) throw Object.assign(new Error(value.error&&value.error.message||'Request failed'),{status:response.status,code:value.error&&value.error.code,payload:value});
      return value;
    }
    function cosmeticPending(pending) {
      // No Rider-activity POST and no decision. Companion patch pins Matrix
      // while permission is pending; existing companion can at least wake.
      const event=current&&current.attention;
      const id=pending&&event ? JSON.stringify([event.attention_id,event.campaign_id,
        event.invocation_id,event.authority_binding_sha256]) : null;
      const shouldWake=Boolean(id&&!woken.includes(id));
      if(shouldWake) {
        woken=[...woken,id].slice(-128);
        try {root.sessionStorage.setItem(wakeKey,JSON.stringify(woken));}catch(_){}
      }
      root.dispatchEvent(new CustomEvent('fawkes:attention-pending',{detail:{pending,wake:shouldWake}}));
      if (shouldWake && root.__fawkesMatrix && root.__fawkesMatrix.active) root.__fawkesMatrix.wake();
    }
    function render(message) {
      updateLauncher();
      const signature=JSON.stringify([current,selected,Boolean(csrf),sending,stale,needsDecision(current),message||'',lastFailure]);
      if(signature===lastRender)return;
      lastRender=signature;
      panel.replaceChildren(element('h2','Native Worker permission'));
      const close=element('button','Back to console');close.type='button';close.onclick=()=>{panel.hidden=true;closedId=current&&current.attention.attention_id;};panel.append(close);
      panel.append(element('p','Fawkes-managed Workers only. Your separately opened Codex CLI is not connected here.'));
      if (message) panel.append(element('p',message));
      if (!current) {panel.append(element('p','No exact managed permission request is available.'));return;}
      const event=current.attention, protocol=event.protocol_binding||{};
      panel.append(element('p','Managed task paths: '+(Array.isArray(protocol.managed_scope)?protocol.managed_scope.join(', '):'See exact canonical scope binding in Details')));
      panel.append(element('p',stale?'Disconnected / stale — decisions disabled':outcome(current)));
      if(lastFailure)panel.append(element('p','Last submission: '+lastFailure+'. The canonical outcome above is authoritative.'));
      for (const [name,value] of [['Worker',event.worker&&event.worker.worker_id],['Task',event.campaign_id],['Requested action',event.blocked_action],['Path / destination',(event.resources||[]).join('\n')],['Why',event.why_required],['Scope',protocol.native_scope_explanation||'Unknown native scope; no controls offered'],['Deadline',event.expires_at||'Unavailable']]) panel.append(element('p',name+': '+String(value||'Unavailable')));
      const details=element('details','');details.append(element('summary','Exact request details'),element('pre',JSON.stringify({requested_authority:event.requested_authority||'Unavailable',identity:binding.canonicalAttentionIdentity(event),protocol},null,2)));panel.append(details);
      if (!csrf) {
        const form=document.createElement('form'), input=document.createElement('input'), submit=element('button','Authenticate for decisions');
        input.type='password';input.autocomplete='current-password';input.placeholder='Existing app credential';submit.type='submit';form.append(input,submit);
        form.onsubmit=async e=>{e.preventDefault();const credential=input.value;input.value='';try{const session=await request('/api/session',{method:'POST',body:JSON.stringify({credential})});csrf=session.csrf_token||'';render();}catch(error){render(error.message);}};
        panel.append(form);
      }
      const offered=protocol.native_decision_choices;
      if (stale || sending || current.decision || event.state!=='needs_tanner' || event.actionable!==true || !csrf || !Array.isArray(offered) || !event.authority_binding_sha256 || !event.expires_at || Date.parse(event.expires_at)<=Date.now()) return;
      if (selected) {
        panel.append(element('p',selected==='approve_once'?'Confirm this exact action once. This does not accept code, increase budget, or authorize future work.':selected==='deny'?'Deny this action. The managed campaign stops safely.':'Cancel the entire selected campaign and interrupt this turn.'));
        const confirmedChoice=selected, confirmedIdentity=binding.canonicalAttentionIdentity(event);
        const confirmedDigest=event.authority_binding_sha256;
        const confirm=element('button','Confirm '+labels[selected]);confirm.type='button';confirm.onclick=()=>submit(confirmedChoice,confirmedIdentity,confirmedDigest);
        const back=element('button','Go back');back.type='button';back.onclick=()=>{selected=null;render();};panel.append(confirm,back);
      } else for (const choice of offered) if(labels[choice]) {
        const control=element('button',labels[choice]);control.type='button';control.onclick=()=>{
          if(!current || !binding.canonicalAttentionIdentityMatches(current.attention,binding.canonicalAttentionIdentity(event),event.authority_binding_sha256))return;
          selected=choice;render();};panel.append(control);
      }
    }
    async function submit(choice,expectedIdentity,expectedDigest) {
      if(sending||stale||!needsDecision(current)||!labels[choice]||selected!==choice
        ||!binding.canonicalAttentionIdentityMatches(current.attention,expectedIdentity,expectedDigest))return;
      const event=current.attention, identity=binding.canonicalAttentionIdentity(event), expected=event.authority_binding_sha256;
      sending=true;selected=null;render('Sending exact decision…');
      try {
        const response=await request('/api/development/codex-campaigns/'+encodeURIComponent(identity.campaign_id)+'/attention/'+encodeURIComponent(identity.attention_id)+'/decision', {method:'POST',body:JSON.stringify({choice,identity})});
        current=binding.requireCanonicalDecisionResult(response,identity,expected,choice);stale=false;
      } catch(error) {
        lastFailure=error.message;
        stale=true;render('Submission failed: '+error.message+'. Checking the canonical record; not sending again.');
      } finally {sending=false;await refreshExact(identity.attention_id);}
    }
    async function refreshExact(id, expectedLocator) {
      const generation=++sequence;
      try {
        const value=await request('/api/development/attention/'+encodeURIComponent(id));
        if(generation!==sequence)return;
        if(!value.attention||value.attention.attention_id!==id)throw new Error('Exact Attention identity mismatch');
        if(expectedLocator && ['attention_id','campaign_id','invocation_id'].some(k=>value.attention[k]!==expectedLocator[k]))throw new Error('Remembered request identity mismatch');
        if (current&&current.attention.attention_id===id&&!binding.canonicalAttentionIdentityMatches(value.attention,binding.canonicalAttentionIdentity(current.attention),current.attention.authority_binding_sha256))throw new Error('Request binding changed');
        if(value.decision) {
          if(!Object.prototype.hasOwnProperty.call(labels,value.decision.choice))throw new Error('Unknown recorded decision');
          binding.requireCanonicalDecisionResult(value,binding.canonicalAttentionIdentity(value.attention),value.attention.authority_binding_sha256,value.decision.choice);
        }
        if (!current || current.attention.attention_id !== id) {selected=null;lastFailure='';}
        current=value;stale=false;
        remember(value.attention);
        if (selected && !(current.attention.protocol_binding.native_decision_choices||[]).includes(selected)) selected=null;
        if (current.decision || current.attention.state !== 'needs_tanner' || !current.attention.actionable) selected=null;
        if (needsDecision(current) && closedId!==id) panel.hidden=false;
        cosmeticPending(needsDecision(current));render();
        if(!needsDecision(current)) {
          pendingQueue=pendingQueue.filter(x=>x.attention_id!==id);
          if(pendingQueue.length&&!sending)await refreshExact(pendingQueue[0].attention_id);
        }
      } catch(error) {if(generation!==sequence)return;stale=true;selected=null;cosmeticPending(false);render('Refresh failed: '+error.message);}
    }
    button.onclick=()=>{panel.hidden=false;closedId=null;render();};
    root.addEventListener('fawkes:console-observation', async e=>{
      if(!csrf)try {csrf=(await request('/api/session/console-csrf',{method:'POST',body:'{}'})).csrf_token||'';}catch(_){/* Existing sessions remain read-only until authenticated. */}
      const pending=(e.detail.attention||[]).filter(x=>needsDecision({attention:x}));
      pendingQueue=pending.slice(0,128);
      const id=(pending[0]||{}).attention_id||(current&&current.attention.attention_id)||(remembered&&remembered.attention_id);
      const recovering=!pending.length&&!current;
      if(id&&!sending)await refreshExact(id,recovering?remembered:null);
      else if(!id){stale=false;render();}
    });
    root.addEventListener('fawkes:console-disconnected',()=>{sequence++;stale=true;selected=null;cosmeticPending(false);render('Connection lost; no decision was sent.');});
    // Middle/wheel gestures and the complete wake gesture must never choose a decision.
    panel.addEventListener('auxclick',e=>{e.preventDefault();e.stopPropagation();});
    panel.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight')e.stopPropagation();});
    render();
    return {refreshExact,outcome:()=>outcome(current)};
  }
  const api={attach,outcome};root.FawkesNativeAttention=api;
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root.document)attach(root.document,root.fetch.bind(root));
})(typeof window!=='undefined'?window:globalThis);

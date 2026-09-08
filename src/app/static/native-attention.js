(function(root) {
  'use strict';
  const binding = root.FawkesAttentionBinding;
  const labels = {approve_once:'Approve Once', deny:'Deny action', cancel_campaign:'Cancel campaign'};
  // Display-only best effort. Canonical request/decision bytes are untouched.
  // Unknown secret formats may still need manual care; this is not a guarantee.
  function displayText(value) {
    return String(value == null ? '' : value)
      .replace(/(\b(?:password|passwd|secret|token|api[_-]?key|authorization)\b["']?\s*[:=]\s*)(?:(?:Bearer|Basic|token)\s+)?("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|[^\s,;\n]+)/gi,'$1[redacted]')
      .replace(/\bBearer\s+[^\s"',;]+/gi,'Bearer [redacted]')
      .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g,'[redacted]')
      .replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi,'$1[redacted]@');
  }
  // Explanations are display-only projections of this exact observed request.
  // Do not infer shell effects, safety, or task necessity from arbitrary text.
  function explainRequest(event,decision=null) {
    const p=event.protocol_binding||{}, method=p.method;
    let kind=null;
    try {
      const a=JSON.parse(event.requested_authority);
      if(a&&typeof a==='object'&&!Array.isArray(a)&&a.method===method&&typeof a.kind==='string')kind=a.kind;
    }catch(_){/* Recorded display text can be shortened or masked; do not guess subtype. */}
    const actions={
      'item/commandExecution/requestApproval':kind==='command'?'Run a command requested by this managed Worker.':kind==='writeStdin'?'Send input to a running command. One-action approval is not supported here.':'Perform a command-related operation. The command/input subtype is unavailable; see the recorded restriction below.',
      execCommandApproval:'Run a command requested by this managed Worker.',
      applyPatchApproval:'Apply the requested file changes.',
      'item/fileChange/requestApproval':'Make a file change. This request does not supply the complete changes for one-action approval.',
      'item/permissions/requestApproval':'Grant permissions for a whole turn or session, rather than one action.'
    };
    const strings=value=>Array.isArray(value)?value.filter(x=>typeof x==='string'&&x.trim()):[];
    const scope=strings(p.managed_scope), resources=strings(event.resources);
    const reason=typeof event.why_required==='string'&&event.why_required.trim();
    const expires=typeof event.expires_at==='string'&&Number.isFinite(Date.parse(event.expires_at))
      ?new Date(event.expires_at).toLocaleString():null;
    const once=Array.isArray(p.native_decision_choices)&&p.native_decision_choices.includes('approve_once');
    const claim=decision&&typeof decision.claim_expires_at==='string'&&Number.isFinite(Date.parse(decision.claim_expires_at))
      ?new Date(decision.claim_expires_at).toLocaleString():null;
    const responseDeadline=expires?'Response deadline: '+expires+'. ':'Response deadline is unknown. ';
    const duration=decision&&decision.choice!=='approve_once'?'No approval was granted; there is no approval to consume.':decision
      ?(decision.consumed?'Already consumed once; it cannot be used again. ':'')+(claim?'Owner-recorded claim deadline: '+claim+'. ':'The owner’s claim deadline is unavailable. ')
      :'After approval, the owner gives the Worker a separate 60-second window to claim this action once. ';
    return {
      what:actions[method]||'Unknown request type. Its effects cannot be explained from the available record.',
      why:reason&&reason!=='Codex requested native approval'?reason:'The Worker did not supply a task-specific reason.',
      affects:[scope.length?'Managed task paths: '+scope.join(', '):'Managed task paths are not available.',
        resources.length?'Request-reported locations: '+resources.join(', '):'No affected locations were reported.',
        'These are recorded scope and locations, not proof of every effect. Other files, devices, services or settings affected are not independently established.'].join(' '),
      authority:once?'Approve Once allows only this exact requested action in this Worker run, once. It does not approve code, extend the task or budget, or grant future access.':'One-action approval is not available for this request. Only the choices supplied by the approval owner can be offered.',
      duration:responseDeadline+duration+'The response deadline and claim window are separate; neither promises how long execution will take.',
      scopeDetails:typeof p.native_scope_explanation==='string'?p.native_scope_explanation:'Native scope is unavailable.'
    };
  }
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
    let lastRender=null, lastFailure='', expiryTimer=null, pendingQueue=[], technicalOpen=false, historyShowing=false;
    let nativeWorkerPending=false,nativeWorkerConnected=null;
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
      button.hidden=!(pending||nativeWorkerPending);
      button.textContent=nativeWorkerPending&&!pending?'⚠ Needs decision · Worker':stale?'⚠ Permissions · last known':'⚠ Permissions';
      button.className=(pending&&!stale)||nativeWorkerPending?'needs-tanner':'';
      connection.hidden=!stale&&nativeWorkerConnected!==false;
      connection.textContent=stale?'Managed permissions unavailable — checking connection':nativeWorkerConnected===false?'Native Worker approvals unavailable — use PC terminal':'';
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
    function element(tag,text) {const x=document.createElement(tag);x.textContent=displayText(text);return x;}
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
      root.__fawkesManagedAttentionPending=pending;
      root.dispatchEvent(new CustomEvent('fawkes:attention-pending',{detail:{pending:pending||root.__fawkesNativeWorkerPending===true,wake:shouldWake}}));
      if (shouldWake && root.__fawkesMatrix && root.__fawkesMatrix.active) root.__fawkesMatrix.wake();
    }
    function render(message) {
      updateLauncher();
      if(historyShowing&&!needsDecision(current))return;
      historyShowing=false;
      const signature=JSON.stringify([current,selected,Boolean(csrf),sending,stale,needsDecision(current),message||'',lastFailure]);
      if(signature===lastRender)return;
      lastRender=signature;
      panel.replaceChildren(element('h2','Native Worker permission'));
      const close=element('button','Back to console');close.type='button';close.onclick=()=>{panel.hidden=true;closedId=current&&current.attention.attention_id;};panel.append(close);
      panel.append(element('p','Fawkes-managed Workers only. Your separately opened Codex CLI is not connected here.'));
      if (message) panel.append(element('p',message));
      if (!current) {panel.append(element('p','No exact managed permission request is available.'));return;}
      const event=current.attention, protocol=event.protocol_binding||{};
      panel.append(element('p',stale?'Disconnected / stale — decisions disabled':outcome(current)));
      if(lastFailure)panel.append(element('p','Last submission: '+lastFailure+'. The canonical outcome above is authoritative.'));
      const task=element('p','Worker: '+String(event.worker&&event.worker.worker_id||'Unknown')+' · Task: '+String(event.campaign_id||'Unknown'));
      task.className='permission-task';task.title=task.textContent;panel.append(task);
      const explanation=explainRequest(event,current.decision), overview=element('dl','');overview.className='permission-explanation';
      for(const [name,value] of [['What Fawkes wants to do',explanation.what],['Why — Worker’s stated reason',explanation.why],['What it may affect',explanation.affects],['What your approval allows',explanation.authority+' Recorded scope / restriction: '+explanation.scopeDetails],['How long it lasts',explanation.duration]]) {
        overview.append(element('dt',name),element('dd',value));
      }
      panel.append(overview,element('p','The Worker’s reason is a claim about this task, not independently verified necessity or a safety assessment.'));
      const details=element('details','');details.open=technicalOpen;
      details.ontoggle=()=>{technicalOpen=details.open;};
      details.append(element('summary','Show technical details'),element('h3','Recorded command / file changes'),element('pre',String(event.blocked_action||'Unavailable')),
        element('p','Recognizable credential values are masked in this display; exact audit material stays with the authenticated owner. Masking cannot identify every secret format.'),
        element('p','Display text is the approval service’s recorded view and may be shortened or masked. The decision remains bound to the exact waiting operation.'),
        element('p',explanation.scopeDetails),element('pre',JSON.stringify({worker:event.worker,task:event.campaign_id,requested_authority:event.requested_authority||'Unavailable',resources:event.resources,deadline:event.expires_at,identity:binding.canonicalAttentionIdentity(event),protocol},null,2)));panel.append(details);
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
        const confirm=element('button','Confirm '+labels[selected]);confirm.type='button';confirm.className='permission-'+selected;confirm.onclick=()=>submit(confirmedChoice,confirmedIdentity,confirmedDigest);
        const back=element('button','Go back');back.type='button';back.onclick=()=>{selected=null;render();};panel.append(confirm,back);
      } else for (const choice of offered) if(labels[choice]) {
        const control=element('button',labels[choice]);control.type='button';control.className='permission-'+choice;control.onclick=()=>{
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
        if (!current || current.attention.attention_id !== id) {selected=null;lastFailure='';technicalOpen=false;}
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
    button.onclick=()=>{if(nativeWorkerPending&&!needsDecision(current)){
      const worker=document.querySelector('[data-page-target="4"]');
      if(worker){
        worker.click();
        // Opening the page preserves conversation scroll; explicitly opening
        // a decision must instead reveal its card. This never selects a choice.
        root.dispatchEvent(new root.CustomEvent('fawkes:show-native-worker-decision'));
      }
      return;
    }panel.hidden=false;closedId=null;render();};
    root.addEventListener('fawkes:native-worker-attention',e=>{
      nativeWorkerPending=e.detail&&e.detail.pending===true;
      nativeWorkerConnected=e.detail&&e.detail.connected===true;updateLauncher();
    });
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
    const historyButton=document.getElementById('permission-history');
    if(historyButton)historyButton.addEventListener('click',async()=>{
      panel.hidden=false; selected=null; historyShowing=true;
      try {
        const result=await request('/api/development/attention?observation=true');
        const records=Array.isArray(result.attention)?result.attention:[];
        const history=records.filter(item=>item.state!=='needs_tanner').slice(-64).reverse();
        panel.replaceChildren(element('h2','Permission history — read only'));
        const close=element('button','Back to console');close.type='button';close.onclick=()=>{panel.hidden=true;historyShowing=false;lastRender=null;};panel.append(close);
        panel.append(element('p','A decision receipt and its operation outcome are separate. Opening history never submits a decision.'));
        if(!history.length)panel.append(element('p','No resolved permission records were returned.'));
        for(const item of history) {
          const card=element('details','');
          card.append(element('summary',`${item.campaign_id||'Unknown campaign'} · ${item.state||'Unknown'} · ${item.created_at||'Unknown time'}`),
            element('p','Request: '+item.attention_id),element('p','Action: '+(item.blocked_action||'Not projected')),
            element('p','Worker’s stated reason: '+(item.why_required||'Not recorded')),
            element('p','Operation outcome: '+(item.approval_outcome||'Not recorded')),
            element('p','Decision identity: '+(item.decision_id||'Consult exact owner record')));
          panel.append(card);
        }
        // Force the next authoritative pending refresh to redraw its own card.
        lastRender=null;
      }catch(error){panel.replaceChildren(element('p','Permission history unavailable: '+error.message));
        const close=element('button','Back to console');close.type='button';close.onclick=()=>{panel.hidden=true;historyShowing=false;lastRender=null;};panel.append(close);}
    });
    // Middle/wheel gestures and the complete wake gesture must never choose a decision.
    panel.addEventListener('auxclick',e=>{e.preventDefault();e.stopPropagation();});
    panel.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight')e.stopPropagation();});
    render();
    return {refreshExact,outcome:()=>outcome(current)};
  }
    const api={attach,outcome,explainRequest,displayText};root.FawkesNativeAttention=api;
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root.document)attach(root.document,root.fetch.bind(root));
})(typeof window!=='undefined'?window:globalThis);

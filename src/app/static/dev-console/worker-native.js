(function(root){
  'use strict';
  const URL='/api/development/worker/approvals', HEX=/^[a-f0-9]{64}$/, UUID=/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/;
  function boot(doc){
    const by=id=>doc.getElementById(id),cards=by('worker-native-cards');if(!cards||!root.fetch)return null;
    const status=by('worker-native-status'),result=by('worker-native-result'),history=by('worker-native-history-items'),reading=by('worker-reading');
    let current=null,selected=null,attempt=null,loading=false,sending=false,signature='',cursor=null;
    let historyRecords=[],woken=new Set();
    const savedKey='fawkes-native-worker-selection-v1',wakeKey='fawkes-native-worker-woken-v1';
    try{const a=JSON.parse(root.localStorage.getItem(savedKey)||'null');if(a&&UUID.test(a.submission_id))attempt=a;
      const w=JSON.parse(root.sessionStorage.getItem(wakeKey)||'[]');if(Array.isArray(w))w.slice(-128).forEach(id=>woken.add(id));}catch(_){}
    const element=(tag,text,cls)=>{const e=doc.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;};
    async function request(path,data){
      const controller=new AbortController(),timer=root.setTimeout(()=>controller.abort(),20000);
      try{
        const options={credentials:'same-origin',cache:'no-store',signal:controller.signal};
        if(data!==undefined){
          const r=await root.fetch('/api/session/console-csrf',{...options,method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
          if(!r.ok)throw new Error('A current Tanner sign-in is required');
          options.method='POST';options.headers={'Content-Type':'application/json','X-Fawkes-CSRF-Token':(await r.json()).csrf_token};options.body=JSON.stringify(data);
        }
        const r=await root.fetch(path,options),v=await r.json();if(!r.ok)throw new Error(v.error&&v.error.message||'Native approval connection unavailable');return v;
      }finally{root.clearTimeout(timer);}
    }
    function pending(value){
      const ids=value&&value.connected?value.requests.filter(r=>r.needs_decision).map(r=>r.logical_request_sha256):[];
      const wake=ids.some(id=>!woken.has(id));ids.forEach(id=>woken.add(id));
      try{root.sessionStorage.setItem(wakeKey,JSON.stringify(Array.from(woken).slice(-128)));}catch(_){}
      const outstanding=!!(value&&value.connected&&value.pending_count>0);
      root.__fawkesNativeWorkerPending=outstanding;
      root.dispatchEvent(new CustomEvent('fawkes:native-worker-attention',{detail:{pending:outstanding,connected:!!(value&&value.connected)}}));
      root.dispatchEvent(new CustomEvent('fawkes:attention-pending',{detail:{pending:outstanding||root.__fawkesManagedAttentionPending===true,wake}}));
      if(wake&&root.__fawkesMatrix&&root.__fawkesMatrix.active)root.__fawkesMatrix.wake();
    }
    function render(){
      if(!current)return;
      const next=JSON.stringify([current.requests,current.connected,selected,sending,historyRecords]);if(next===signature)return;signature=next;
      const open=new Set(Array.from(cards.querySelectorAll('details[open]')).map(e=>e.dataset.requestKey));
      const previous=cards.getBoundingClientRect().height,preserve=reading.scrollTop>previous+80;
      cards.replaceChildren();history.replaceChildren();
      const rows=current.requests.concat(historyRecords.filter(r=>!current.requests.some(x=>x.request_key===r.request_key)));
      for(const r of rows){
        const active=r.actionable===true&&current.connected===true;
        const card=element('article','','worker-native-card');card.dataset.requestKey=r.request_key;card.classList.toggle('needs-decision',r.needs_decision===true);
        card.appendChild(element('h3',r.needs_decision?(active?'⚠ Needs your decision':'⚠ Needs your decision on PC'):'Native request · '+r.status));
        const d=r.description;
        if(d){
          card.append(element('p','Fawkes wants to run a command in '+d.environment+'.'),
            element('p','Worker’s stated reason: '+(d.reason||'No task-specific reason was supplied.')),
            element('p','Request location: '+d.cwd+'. Effects beyond the command and supplied locations are not independently established. This is not a safety claim.','meta'),
            element('p','Waiting operation: '+d.turn_id+' / '+d.item_id,'meta'));
          const detail=element('details','');detail.dataset.requestKey=r.request_key;detail.open=open.has(r.request_key);
          detail.append(element('summary','Show technical details'),element('pre',d.command,'worker-message'),
            element('p','Request '+r.request_key+' · '+r.created_at+' · Pi response window ends '+r.expires_at+' or sooner if Codex resolves/disconnects. This does not specify execution duration.','meta'));card.appendChild(detail);
          if(d.command_actions)detail.append(element('p','Codex’s best-effort parsed actions (not independently verified effects):','meta'),element('pre',JSON.stringify(d.command_actions,null,2),'worker-message'));
          if(active&&!r.selection){
            const choices=element('div','','worker-native-choices');
            for(const c of d.choices){
              const button=element('button',c.label,'native-choice');button.type='button';button.disabled=sending;
              button.setAttribute('aria-pressed',String(!!selected&&selected.request_key===r.request_key&&selected.choice_id===c.choice_id));
              button.onclick=()=>{selected={request_key:r.request_key,choice_id:c.choice_id};render();};
              choices.append(button,element('p',c.scope,'native-permission-scope'));
            }
            card.appendChild(choices);
            if(selected&&selected.request_key===r.request_key){const c=d.choices.find(x=>x.choice_id===selected.choice_id);
              if(c){const button=element('button','Confirm: '+c.label,'native-confirm');button.type='button';button.disabled=sending;button.onclick=()=>decide(r,c);card.appendChild(button);}}
          }
        }else card.appendChild(element('p',r.explanation||'Unsupported native action. Answer the PC terminal.'));
        if(r.selection)card.appendChild(element('p','Pi selection: '+r.selection.label+' · '+r.selection.state+'. This is separate from execution.','meta'));
        if(r.operation)card.appendChild(element('p','Observed command outcome: '+r.operation.status+' · '+r.operation.observed_at,'native-outcome native-outcome-'+(['completed','failed','declined'].includes(r.operation.status)?r.operation.status:'unknown')));
        if(r.explanation&&d)card.appendChild(element('p',r.explanation,'meta'));
        (r.native_pending||r.needs_decision||r.status==='submitted'?cards:history).appendChild(card);
      }
      if(preserve)reading.scrollTop+=cards.getBoundingClientRect().height-previous;
      by('worker-native-older').hidden=!cursor;
    }
    async function decide(r,c){
      if(sending||!current||!current.connected||!r.actionable)return;
      const exact={thread_id:current.thread_id,request_key:r.request_key,action_sha256:r.action_sha256,choice_id:c.choice_id};
      if(attempt&&attempt.request_key===r.request_key){if(attempt.choice_id!==c.choice_id){result.textContent='The earlier selection is unresolved; it cannot be replaced with another decision.';return;}}
      else attempt={...exact,submission_id:root.crypto.randomUUID()};
      try{const body=JSON.stringify(attempt);root.localStorage.setItem(savedKey,body);if(root.localStorage.getItem(savedKey)!==body)throw new Error('Selection identity could not be retained');}
      catch(error){result.textContent='No decision sent: '+error.message;return;}
      sending=true;render();result.textContent='Submitting only this exact native choice…';
      try{
        const receipt=await request(URL+'/decision',attempt);
        if(receipt.thread_id!==exact.thread_id||receipt.request_key!==exact.request_key||receipt.action_sha256!==exact.action_sha256||!receipt.selection
          ||receipt.selection.submission_id!==attempt.submission_id||receipt.selection.choice_id!==exact.choice_id)throw new Error('Native receipt identity differs');
        result.textContent='Selection recorded · '+receipt.selection.state+'. Native resolution and execution are separate observations.';selected=null;
      }catch(error){result.textContent='Decision not confirmed · '+error.message+'. Original selection identity retained; no automatic resend.';}
      finally{sending=false;signature='';refresh();}
    }
    async function refresh(older=null){
      if(loading||sending)return;loading=true;
      try{
        const v=await request(URL+(older?'?cursor='+encodeURIComponent(older):''));
        if(!UUID.test(v.thread_id)||current&&v.thread_id!==current.thread_id||typeof v.connected!=='boolean'||!Array.isArray(v.requests)
          ||v.requests.some(r=>r.thread_id!==v.thread_id||!HEX.test(r.request_key)||!HEX.test(r.action_sha256)||!HEX.test(r.logical_request_sha256)))throw new Error('Native projection identity differs');
        if(older){historyRecords=historyRecords.concat(v.requests.filter(r=>!historyRecords.some(x=>x.request_key===r.request_key)));cursor=v.next_cursor;}
        else{current=v;if(!historyRecords.length)cursor=v.next_cursor;}
        status.textContent=current.connected?(current.pending_count?'Native Worker request waiting · PC and Pi share this operation':'Native Worker approvals connected · no active request')
          :'Native approval connection unavailable · an empty queue is not confirmed. Use the PC terminal.';
        pending(current);render();
      }catch(error){status.textContent='Native approvals unavailable · '+error.message;
        if(current)current={...current,connected:false,requests:current.requests.map(r=>({...r,actionable:false}))};pending(null);render();}
      finally{loading=false;}
    }
    function revealDecision(){
      const page=by('worker-page');
      if(!page||page.hidden||!reading)return;
      // Explicit attention navigation, not a background refresh. Give the
      // request room without discarding draft text or changing any decision.
      const keyboard=by('worker-keyboard'),toggle=by('worker-keyboard-toggle');
      if(keyboard&&!keyboard.hidden&&toggle)toggle.click();
      const request=current&&current.connected&&current.requests.find(r=>r.needs_decision||r.native_pending);
      const card=request&&Array.from(cards.children).find(e=>e.dataset.requestKey===request.request_key);
      // A PC resolution may win just before this click. Reveal the truthful
      // current status instead; never revive a resolved request or send input.
      const target=card||status;
      reading.scrollTop+=target.getBoundingClientRect().top-reading.getBoundingClientRect().top;
      target.tabIndex=-1;target.focus({preventScroll:true});
    }
    root.addEventListener('fawkes:show-native-worker-decision',revealDecision);
    by('worker-native-older').addEventListener('click',()=>refresh(cursor));
    const timer=root.setInterval(()=>refresh(),5000);refresh();
    return{refresh,stop:()=>{root.clearInterval(timer);root.removeEventListener('fawkes:show-native-worker-decision',revealDecision);}};
  }
  const api={boot};root.FawkesNativeWorkerApprovals=api;
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root.document)boot(root.document);
})(typeof window==='object'?window:globalThis);

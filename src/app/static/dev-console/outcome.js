(function(root,factory){
  "use strict";
  const api=factory(root);
  if(typeof module==="object"&&module.exports)module.exports=api;
  root.FawkesObjectiveOutcome=api;
})(typeof globalThis==="object"?globalThis:this,function(root){
  "use strict";
  function finalNotice(value){
    const f=value&&value.latest_final;
    if(!value||!f||!Array.isArray(value.completed_turn_ids)||!value.completed_turn_ids.includes(f.turn_id)
        ||!['active','idle'].includes(value.state)||f.role!=='worker'||f.phase!=='final_answer'
        ||typeof f.text!=='string'||!f.text||typeof f.message_id!=='string'||typeof f.turn_id!=='string'
        ||!/^[a-f0-9]{64}$/.test(f.content_sha256||'')
        ||!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value.thread_id||'')
        ||!Number.isFinite(Date.parse(value.verified_at)))return null;
    return {key:JSON.stringify([value.thread_id,f.turn_id,f.message_id,f.content_sha256]),
      kind:'worker_reply',live:true,title:'Worker replied',job:value.thread_id,
      objective:'This execution turn finished. That does not by itself mean the whole task is complete.',
      result:f.text,time:value.verified_at,evidence:f.content_sha256,turn:f.turn_id,message:f.message_id,
      button:'Reply to Worker'};
  }
  function notice(projection,state){
    if(!projection||!Array.isArray(projection.jobs))return null;
    const jobs=projection.jobs.filter(j=>j.is_current_objective&&j.job_id===projection.current_campaign_id);
    if(jobs.length!==1)return null;
    const j=jobs[0],live=state==="live";
    if(j.state==="needs_you"){
      const next=String(j.next||"Open Worker to review the recorded blocker.");
      const identity=/^[a-f0-9]{64}$/.test(j.blocker_identity||"")?j.blocker_identity:null;
      return {key:JSON.stringify([j.job_id,"needs_you",identity]),autoEligible:!!identity,job:j.job_id,kind:"blocked",live,
        title:live?"Paused — needs your decision":"Last known pause — connection not verified",
        objective:j.objective,result:next,time:j.last_activity_at,
        evidence:j.source_record_sha256,button:"Reply to Worker"};
    }
    const c=j.objective_closeout;
    if(j.state==="done"&&j.successful===true&&!j.parent_campaign_id&&c
        &&c.event_id&&c.result&&Number.isFinite(Date.parse(c.recorded_at))&&c.gate_count>0){
      return {key:JSON.stringify([j.job_id,"complete",c.event_id]),job:j.job_id,kind:"complete",live,
        title:live?"Task complete — ready for your next task":"Last known completion — connection not verified",
        objective:j.objective,result:c.result,time:c.recorded_at,
        evidence:j.source_record_sha256,button:"Reply to Worker"};
    }
    return null;
  }
  function boot(doc,reply){
    const dialog=doc.getElementById("objective-outcome-dialog");
    if(!dialog)return null;
    const by=id=>doc.getElementById(id);
    let current=null,campaignCurrent=null,workerCurrent=null,workerObservedAt=0;
    let shownKey=null,nativeKnown=false,nativePending=false;
    let baseline=null;
    try{baseline=JSON.parse(root.localStorage.getItem('fawkes-worker-notice-baseline-v1')||'null');}catch(_){}
    const seen=new Set();let durable=false;
    try{
      const values=JSON.parse(root.localStorage.getItem("fawkes-objective-notices-v1")||"[]");
      if(!Array.isArray(values)||values.length>128||values.some(x=>typeof x!=="string"))throw Error();
      values.forEach(x=>seen.add(x));durable=true;
    }catch(_){}
    function acknowledge(){
      if(!current)return false;
      seen.add(current.key);
      try{
        const value=JSON.stringify(Array.from(seen).slice(-128));
        root.localStorage.setItem("fawkes-objective-notices-v1",value);
        durable=root.localStorage.getItem("fawkes-objective-notices-v1")===value;
      }catch(_){durable=false;}
      return durable;
    }
    function content(){
      if(!current)return;
      by("objective-outcome-title").textContent=current.title;
      by("objective-outcome-objective").textContent=current.objective;
      by("objective-outcome-result").textContent=current.result;
      by("objective-outcome-source").textContent=current.kind==='worker_reply'
        ? 'Worker '+current.job+' · Turn '+current.turn+' · Message '+current.message
          +' · verified '+current.time+' · content '+current.evidence+'. Complete public final reply; not a new permission or whole-task closeout.'
        : "Campaign "+current.job+" · recorded "+(current.time||"time unavailable")
        +" · source "+(current.evidence||"digest unavailable")
        +". This is a recorded status, not a permission or a new acceptance receipt.";
      by("objective-outcome-reply").textContent=current.button;
      dialog.dataset.tone=current.kind;
    }
    function hide(){
      if(dialog.open)dialog.close();
      shownKey=null;
    }
    function open(explicit){
      if(!current||(!explicit&&!current.live)||dialog.open)return;
      if(!explicit&&current.kind==='worker_reply'&&Date.now()-workerObservedAt>=15000)return;
      // Do not displace typing, native decisions, menu gestures, or Matrix.
      if(doc.querySelector("dialog[open]")||nativePending||root.__fawkesManagedAttentionPending===true
          ||root.__fawkesMatrix&&root.__fawkesMatrix.active)return;
      if(!explicit&&(current.autoEligible===false||!durable||!nativeKnown||nativePending||root.__fawkesManagedAttentionPending===true
          ||doc.activeElement&&doc.activeElement.matches("input,textarea,select,[contenteditable='true']")
          ||!by("worker-keyboard").hidden||by("page-menu").open||seen.has(current.key)))return;
      if(explicit&&!by("worker-keyboard").hidden)by("worker-keyboard-toggle").click();
      // Prove write/read-back before an automatic modal can steal focus.
      // Unreliable storage keeps the manual entry available, including reloads.
      const persisted=acknowledge();
      if(!explicit&&!persisted)return;
      content();dialog.showModal();shownKey=current.key;
      by("objective-outcome-title").focus({preventScroll:true});
    }
    function close(){acknowledge();hide();}
    function show(){open(true);}
    function answer(){close();reply();}
    function attention(event){
      nativeKnown=event.detail&&event.detail.connected===true;
      nativePending=event.detail&&event.detail.pending===true;
      // A real permission takes priority, even if this status was already open.
      if(nativePending)hide();
      else open(false);
    }
    function managedAttention(){
      if(root.__fawkesManagedAttentionPending===true)hide();
      else open(false);
    }
    function reconcile(){
      const retained=[campaignCurrent,workerCurrent].find(n=>n&&current&&n.key===current.key);
      // Acknowledgment suppresses duplicate alerts; it is NOT a dismissal.
      // Keep a displayed message stable while the user reads it. A newer reply
      // waits until this dialog closes, rather than replacing its text/focus.
      let next=dialog.open&&current&&current.kind==='worker_reply'&&workerCurrent&&current.job===workerCurrent.job
        ? {...current,live:workerCurrent.live,title:workerCurrent.live?'Worker replied':workerCurrent.title}
        : dialog.open ? retained : null;
      if(!next)next=campaignCurrent&&!seen.has(campaignCurrent.key)&&campaignCurrent.autoEligible!==false
        ? campaignCurrent : workerCurrent&&!seen.has(workerCurrent.key) ? workerCurrent : workerCurrent||retained||campaignCurrent;
      if(dialog.open&&(!next||next.key!==shownKey))hide();
      current=next;
      if(root.__fawkesManagedAttentionPending===true)hide();
      const card=doc.querySelector('.current-briefing');
      if(current&&card&&!card.querySelector('[data-objective-outcome]')){
        const button=doc.createElement('button');button.type='button';button.dataset.objectiveOutcome='true';
        button.className='objective-outcome-entry';card.prepend(button);
      }
      const entry=card&&card.querySelector('[data-objective-outcome]');
      if(entry){entry.hidden=!current;if(current)entry.textContent=!current.live?'Last known status · view details'
        :current.kind==='worker_reply'?'✉ Worker replied · view message'
        :current.kind==='complete'?'✓ Task complete · view result':'⚠ Needs your decision · view prompt';}
      if(dialog.open)content();else open(false);
    }
    function workerObservation(event){
      const detail=event.detail||{};
      if(detail.connected!==true){
        if(workerCurrent)workerCurrent={...workerCurrent,live:false,title:'Last known Worker reply — connection not verified'};
        reconcile();return;
      }
      const value=detail.projection,next=finalNotice(value);
      if(!value||!['active','idle'].includes(value.state)){
        if(workerCurrent)workerCurrent={...workerCurrent,live:false,title:'Last known Worker reply — Worker is not currently attached'};
        reconcile();return;
      }
      // First synchronization establishes a baseline, not an invented new
      // completion. Persist it before any automatic notification is eligible.
      if(!baseline){
        if(!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value.thread_id||''))return;
        const initial={thread:value.thread_id,key:next&&next.key};
        try{
          const body=JSON.stringify(initial);root.localStorage.setItem('fawkes-worker-notice-baseline-v1',body);
          if(root.localStorage.getItem('fawkes-worker-notice-baseline-v1')!==body)return;
          baseline=initial;
        }catch(_){return;}
      }
      if(!value||baseline.thread!==value.thread_id){workerCurrent=null;reconcile();return;}
      workerObservedAt=Date.now();
      workerCurrent=next&&next.key!==baseline.key?next:null;
      reconcile();
    }
    by("objective-outcome-close").addEventListener("click",close);
    by("objective-outcome-reply").addEventListener("click",answer);
    dialog.addEventListener("cancel",close);
    root.addEventListener("fawkes:native-worker-attention",attention);
    root.addEventListener("fawkes:attention-pending",managedAttention);
    root.addEventListener('fawkes:worker-message-observation',workerObservation);
    const click=event=>{
      if(event.target.closest&&event.target.closest("[data-objective-outcome]"))show();
    };
    doc.addEventListener("click",click);
    return {
      update(projection,state){
        campaignCurrent=notice(projection,state);
        if(workerCurrent&&Date.now()-workerObservedAt>=15000)
          workerCurrent={...workerCurrent,live:false,title:'Last known Worker reply — verification overdue'};
        reconcile();
      },
      stop(){
        hide();root.removeEventListener("fawkes:native-worker-attention",attention);
        root.removeEventListener("fawkes:attention-pending",managedAttention);
        root.removeEventListener('fawkes:worker-message-observation',workerObservation);
        doc.removeEventListener("click",click);
        by("objective-outcome-close").removeEventListener("click",close);
        by("objective-outcome-reply").removeEventListener("click",answer);
        dialog.removeEventListener("cancel",close);
      }
    };
  }
  return {notice,finalNotice,boot};
});

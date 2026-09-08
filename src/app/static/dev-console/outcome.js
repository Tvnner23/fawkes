(function(root,factory){
  "use strict";
  const api=factory(root);
  if(typeof module==="object"&&module.exports)module.exports=api;
  root.FawkesObjectiveOutcome=api;
})(typeof globalThis==="object"?globalThis:this,function(root){
  "use strict";
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
    let current=null,shownKey=null,nativeKnown=false,nativePending=false;
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
      by("objective-outcome-source").textContent="Campaign "+current.job+" · recorded "+(current.time||"time unavailable")
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
    by("objective-outcome-close").addEventListener("click",close);
    by("objective-outcome-reply").addEventListener("click",answer);
    dialog.addEventListener("cancel",close);
    root.addEventListener("fawkes:native-worker-attention",attention);
    root.addEventListener("fawkes:attention-pending",managedAttention);
    const click=event=>{
      if(event.target.closest&&event.target.closest("[data-objective-outcome]"))show();
    };
    doc.addEventListener("click",click);
    return {
      update(projection,state){
        const next=notice(projection,state);
        if(dialog.open&&(!next||next.key!==shownKey))hide();
        current=next;
        if(root.__fawkesManagedAttentionPending===true)hide();
        // Rendering replaces briefing nodes, but never the open dialog body.
        const card=doc.querySelector(".current-briefing");
        if(current&&card&&!card.querySelector("[data-objective-outcome]")){
          const button=doc.createElement("button");
          button.type="button";button.dataset.objectiveOutcome="true";
          button.className="objective-outcome-entry";
          button.textContent=current.live?current.kind==="complete"?"✓ Task complete · view result":"⚠ Needs your decision · view prompt":"Last known status · view details";
          card.prepend(button);
        }
        if(dialog.open)content();else open(false);
      },
      stop(){
        hide();root.removeEventListener("fawkes:native-worker-attention",attention);
        root.removeEventListener("fawkes:attention-pending",managedAttention);
        doc.removeEventListener("click",click);
        by("objective-outcome-close").removeEventListener("click",close);
        by("objective-outcome-reply").removeEventListener("click",answer);
        dialog.removeEventListener("cancel",close);
      }
    };
  }
  return {notice,boot};
});

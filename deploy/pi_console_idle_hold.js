/* Pi-local Idle gesture. No network, permission decision, or desktop shutdown. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.FawkesIdleHold = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  function gesture(now, report, complete) {
    let active = null, consumed = false;
    return {
      down(id, time) { if (active || consumed) return false; active={id, start:time}; return true; },
      tick(time) {
        if (!active || consumed) return;
        const elapsed=Math.max(0,time-active.start);
        if (elapsed>=180) report(Math.min(1,elapsed/3000), "Release to cancel");
        if (elapsed>=3000) { consumed=true;active=null;complete(); }
      },
      up(id,time) {
        if (consumed) return "suppress";
        if (!active || active.id!==id) return "none";
        if(time-active.start>=3000){consumed=true;active=null;complete();return "suppress";}
        const elapsed=time-active.start;active=null;report(0,"");
        return elapsed<180 ? "tap" : "cancel";
      },
      cancel() { const had=!!active;active=null;if(!consumed)report(0,"");return had; },
      pending() { return !!active; },
      consumed() { return consumed; }
    };
  }
  function install(win, config) {
    if (win.__fawkesIdleShutdown) return;
    const doc=win.document, abort=new win.AbortController();
    let button=null,pointer=null,timer=0,blockUntil=0,pending=null,issued=false,lastPoint=null;
    const cancelledPointers=new Set(),navigationPointers=new Set();
    let navigationToken=null,navigationClickUntil=0,summaryActivation=null;
    const hint=doc.createElement("div");hint.id="pi-shutdown-progress";hint.setAttribute("role","status");
    hint.style.cssText="box-sizing:border-box;grid-column:1 / -1;flex:0 0 auto;width:100%;max-width:100%;background:#14212d;color:#ffd166;padding:8px 12px;border:1px solid #ffd166;border-radius:8px;font:18px/1.3 system-ui;pointer-events:none;display:none";
    doc.documentElement.appendChild(hint);
    const place=()=>{
      const header=button?.closest?.(".worker-toolbar,.console-header");
      if(header?.appendChild){if(hint.parentNode!==header)header.appendChild(hint);hint.style.position="static";hint.style.marginTop="8px";}
      else {if(hint.parentNode!==doc.body&&doc.body?.appendChild)doc.body.appendChild(hint);
        hint.style.position="fixed";hint.style.left="12px";hint.style.right="12px";hint.style.bottom="12px";hint.style.width="calc(100% - 24px)";}
    };
    const show=(fraction,text)=>{if(text)place();hint.style.display=text?"block":"none";hint.textContent=text?"Hold to shut down Pi · "+(fraction*3).toFixed(1)+" / 3.0s · "+text:"";};
    const state=gesture(()=>win.performance.now(),show,()=>{
      issued=true;blockUntil=Infinity;win.clearInterval(timer);hint.style.display="block";hint.textContent="Saving… Shutting down…";
      const input=doc.getElementById("worker-reply");
      if(input)input.dispatchEvent(new win.Event("input",{bubbles:true}));
      if(doc.activeElement?.blur)doc.activeElement.blur();
      pending={id:win.crypto.randomUUID(),created:Date.now()};
    });
    function cancel(){if(state.cancel()){if(pointer!==null)cancelledPointers.add(pointer);blockUntil=win.performance.now()+700;win.clearInterval(timer);}pointer=null;}
    function inside(e){const r=button?.getBoundingClientRect();return !!r&&button.isConnected&&r.width>0&&r.height>0&&e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;}
    const options={capture:true,signal:abort.signal};
    win.addEventListener("pointerdown",e=>{
      if(navigationToken){navigationPointers.add(e.pointerId);e.preventDefault();e.stopImmediatePropagation();return;}
      if(state.pending()&&e.pointerId!==pointer){cancel();return;}
      const target=e.target.closest&&e.target.closest("#console-idle,#fawkes-matrix-idle-button");
      if(!target||!e.isTrusted||!e.isPrimary||e.button!==0||issued)return;
      if(state.pending()){cancel();return;}
      // A fresh primary down starts a distinct gesture. A cancelled original
      // remains guarded until its release, however long that release takes.
      cancelledPointers.clear();blockUntil=0;
      button=target;pointer=e.pointerId;lastPoint=e;state.down(pointer,win.performance.now());
      timer=win.setInterval(()=>{if(!inside(lastPoint)){cancel();return;}state.tick(win.performance.now());},40);
    },options);
    win.addEventListener("pointermove",e=>{
      if(e.pointerId!==pointer||!state.pending())return;
      lastPoint=e;if(!inside(e))cancel();
    },options);
    win.addEventListener("pointerup",e=>{
      if(navigationPointers.has(e.pointerId)){navigationPointers.delete(e.pointerId);navigationClickUntil=win.performance.now()+700;e.preventDefault();e.stopImmediatePropagation();return;}
      if(cancelledPointers.has(e.pointerId)){cancelledPointers.delete(e.pointerId);blockUntil=win.performance.now()+700;return;}
      if(e.pointerId!==pointer)return;
      if(!inside(e)){cancel();return;}
      const action=state.up(pointer,win.performance.now());pointer=null;win.clearInterval(timer);
      if(action!=="tap")blockUntil=issued?Infinity:win.performance.now()+700;
    },options);
    win.addEventListener("pointercancel",e=>{if(navigationPointers.delete(e.pointerId))navigationClickUntil=win.performance.now()+700;if(e.pointerId===pointer)cancel();},options);
    win.addEventListener("contextmenu",e=>{if(state.pending()&&e.target.closest?.("#console-idle,#fawkes-matrix-idle-button"))e.preventDefault();},options);
    win.addEventListener("pagehide",cancel,options);
    win.addEventListener("blur",cancel,options);
    doc.addEventListener("visibilitychange",()=>{if(doc.hidden)cancel();},options);
    win.addEventListener("click",e=>{
      if(navigationToken&&!issued&&!e.isTrusted&&e.target===summaryActivation)return;
      if(navigationToken||navigationPointers.size>0||win.performance.now()<navigationClickUntil||issued||((cancelledPointers.size>0||win.performance.now()<blockUntil)&&e.target.closest?.("#console-idle,#fawkes-matrix-idle-button"))) {
        e.preventDefault();e.stopImmediatePropagation();
      }
    },options);
    for(const kind of ["keydown","beforeinput"]){win.addEventListener(kind,e=>{if(issued||navigationToken){e.preventDefault();e.stopImmediatePropagation();}},options);}
    win.__fawkesIdleShutdown={
      get holding(){return state.pending();},
      get navigationBlocked(){return state.pending()||issued||!!navigationToken;},
      beginNavigation(){
        if(state.pending()||issued||navigationToken)return null;
        navigationToken=win.crypto.randomUUID();place();hint.style.display="block";
        hint.textContent="Saving state / changing page…";
        return navigationToken;
      },
      endNavigation(token){
        if(token!==navigationToken||!navigationToken)return false;
        navigationToken=null;show(0,"");return true;
      },
      selectSummary(token){
        if(!navigationToken||token!==navigationToken||issued)return false;
        const controls=doc.querySelectorAll('#dev-console button[data-page-target="0"]');
        const pages=doc.querySelectorAll('#dev-console .console-page[data-page="0"]');
        if(controls.length!==1||pages.length!==1)return false;
        const target=controls[0];
        if(!target.isConnected||target.disabled||target.getAttribute('aria-disabled')==='true')return false;
        summaryActivation=target;
        try{target.click();}finally{summaryActivation=null;}
        return doc.querySelector('#dev-console')?.dataset.page==='0'&&target.getAttribute('aria-current')==='page'&&!pages[0].hidden;
      },
      take(){const value=pending;pending=null;return value;},
      result(message){hint.style.display="block";hint.textContent=message;},
      destroy(){abort.abort();win.clearInterval(timer);hint.remove();delete win.__fawkesIdleShutdown;}
    };
  }
  return {gesture,install};
});

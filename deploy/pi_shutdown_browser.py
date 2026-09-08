"""Pi-local state and gesture bridge using the companion's single CDP reader."""
import json
from pathlib import Path
from pi_shutdown_state import SaveError,THREAD

ORIGIN='http://127.0.0.1:8791'
STORAGE=['fawkes-worker-page-v1','fawkes-console-update-retry-v1','fawkes-native-worker-selection-v1','fawkes-worker-notice-baseline-v1','fawkes-objective-notices-v1']
def capture_expression():
 return '''(() => {
 if(location.origin!==%s || location.pathname!=='/dev-console')return null;
 const storage={};for(const key of %s){const value=localStorage.getItem(key);if(value!==null)storage[key]=value;}
 const input=document.getElementById('worker-reply');
 if(input){let saved=JSON.parse(storage['fawkes-worker-page-v1']||'{}');saved.draft=input.value;storage['fawkes-worker-page-v1']=JSON.stringify(saved);}
 const root=document.getElementById('dev-console');
 const worker=document.getElementById('worker-reading');
 const scrolling=document.querySelector('.console-page:not([hidden]) .page-scroll');
 const deferred=window.__fawkesPiRestoredView;
 return {storage,page:deferred?.page||root?.dataset.page||'unknown',scroll:deferred?.scroll||{worker:worker?.scrollTop||0,console:scrolling?.scrollTop||0}};
})()'''%(json.dumps(ORIGIN),json.dumps(STORAGE))

class BrowserShutdown:
 def __init__(self,browser,owner,thread_id,waiting_url,gesture_source,matrix_source=''):
  self.browser=browser;self.owner=owner;self.thread_id=thread_id
  self.waiting_url=waiting_url;self.gesture_source=gesture_source
  self.matrix_source=matrix_source
  if thread_id!=THREAD:raise SaveError('Wrong Worker binding')
  self.last=None;self.restore_script=None;self.navigation_token=None
 def can_navigate(self):
  return self.browser.evaluate('!window.__fawkesIdleShutdown?.navigationBlocked') is True
 def begin_navigation(self):
  if self.navigation_token is not None:return False
  token=self.browser.evaluate('window.__fawkesIdleShutdown?.beginNavigation()||null')
  if not isinstance(token,str) or len(token)!=36:return False
  self.navigation_token=token
  return True
 def finish_navigation(self):
  token=self.navigation_token
  if token is None:return
  # A navigated document has its own independent owner. Never release its
  # reservation with an old token. On RPC failure retain the token for retry.
  self.browser.evaluate('window.__fawkesIdleShutdown?.endNavigation('+json.dumps(token)+')')
  self.navigation_token=None
 def abort_navigation(self):
  # Do not release controls while timed-out navigation may still complete.
  self.browser.call('Page.stopLoading',{},self.browser.session)
  self.finish_navigation()
 def select_summary(self,expression):
  if self.navigation_token is None or expression.count('summary.click();')!=1:
   raise SaveError('No exact reserved Summary action')
  action='if(!window.__fawkesIdleShutdown?.selectSummary('+json.dumps(self.navigation_token)+'))return false;'
  return self.browser.evaluate(expression.replace('summary.click();',action))
 def restore_hook(self):
  saved=self.owner.restore(self.thread_id)
  if saved is None:return
  # Run before application listeners so reply identities/draft are recovered
  # without dispatching a chat, clipboard or approval action.
  code='''(() => {if(location.origin!==%s)return;
 const saved=%s;for(const [key,value] of Object.entries(saved.storage)){if(localStorage.getItem(key)===null)localStorage.setItem(key,value);}
 window.__fawkesPiRestoredView={page:saved.page,scroll:saved.scroll};
 })();'''%(json.dumps(ORIGIN),json.dumps(saved,ensure_ascii=True))
  if self.restore_script:
   self.browser.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':self.restore_script},self.browser.session)
  self.restore_script=self.browser.call('Page.addScriptToEvaluateOnNewDocument',{'source':code},self.browser.session)['identifier']
 def install(self):
  code='''(() => {
 if(!document.body||!((location.origin===%s&&['/','/dev-console'].includes(location.pathname))||location.href===%s))return false;
 if(window.__fawkesIdleShutdown)return true;
 if(!window.__fawkesMatrix){%s}
 %s
 if((location.href===%s||location.pathname==='/')&&!document.getElementById('console-idle')){
  const b=document.createElement('button');b.id='console-idle';b.textContent='Idle';b.type='button';
  b.style.cssText='position:fixed;right:12px;top:12px;min-width:68px;min-height:48px;font:18px system-ui;background:#14212d;color:#f3f7fc;border:1px solid #61768a;border-radius:10px';
  b.onclick=()=>window.__fawkesMatrix?.enter();document.body.appendChild(b);
 }
 window.FawkesIdleHold.install(window,{});
 // Restore saved reading positions when that page is deliberately opened.
 // Normal startup still selects Summary and never auto-sends saved drafts.
 if(window.__fawkesPiRestoredView&&!window.__fawkesPiViewObserver){
  const root=document.getElementById('dev-console'),saved=window.__fawkesPiRestoredView;
  if(root){const restore=()=>{if(root.dataset.page!==saved.page)return;
   const scrolling=document.querySelector('.console-page:not([hidden]) .page-scroll');
   const worker=document.getElementById('worker-reading');
   const targets=saved.page==='4'?[[worker,saved.scroll.worker??saved.scroll.console??0]]:[[scrolling,saved.scroll.console||0]];
   if(targets.some(([e,n])=>!e||e.clientHeight<=0||e.scrollHeight-e.clientHeight<n))return;
   for(const [e,n] of targets)e.scrollTop=n;
   if(targets.some(([e,n])=>Math.abs(e.scrollTop-n)>1))return;
   delete window.__fawkesPiRestoredView;window.__fawkesPiViewObserver?.disconnect();window.__fawkesPiViewResize?.disconnect();};
   window.__fawkesPiViewObserver=new MutationObserver(restore);
   window.__fawkesPiViewObserver.observe(root,{attributes:true,attributeFilter:['data-page','hidden'],subtree:true,childList:true});
   if(typeof ResizeObserver==='function'){window.__fawkesPiViewResize=new ResizeObserver(restore);window.__fawkesPiViewResize.observe(root);const history=document.getElementById('worker-conversation-history');if(history)window.__fawkesPiViewResize.observe(history);}
   const cancel=event=>{if(!event.isTrusted||!event.target.closest?.('#worker-reading,.page-scroll'))return;
    delete window.__fawkesPiRestoredView;window.__fawkesPiViewObserver?.disconnect();window.__fawkesPiViewResize?.disconnect();};
   document.addEventListener('pointerdown',cancel,{capture:true});document.addEventListener('wheel',cancel,{capture:true,passive:true});
   restore();}
 }
 return true;
 })()'''%(json.dumps(ORIGIN),json.dumps(self.waiting_url),self.matrix_source,self.gesture_source,json.dumps(self.waiting_url))
  return self.browser.evaluate(code)
 def checkpoint(self):
  try:
   value=self.browser.evaluate(capture_expression())
  except Exception as error:
   # Storage access/JSON failures surface as browser SetupError. Keep them
   # inside the save boundary: do not tear down Chromium or its live draft.
   raise SaveError('Live browser state could not be captured; keep this page open.') from error
  if value is not None:
   if value!=self.last:
    self.owner.save(value,self.thread_id);self.restore_hook();self.last=value
  return self.last
 def poll(self):
  request=self.browser.evaluate('''(() => {
   if(!((location.origin===%s&&['/','/dev-console'].includes(location.pathname))||location.href===%s))return null;
   return window.__fawkesIdleShutdown?.take()||null;
  })()'''%(json.dumps(ORIGIN),json.dumps(self.waiting_url)))
  if request is None:return None
  try:
   value=self.checkpoint() or self.owner.restore(self.thread_id)
   if value is None:value={'storage':{},'page':'unknown','scroll':{}}
   result=self.owner.shutdown(request['id'],value,self.thread_id)
  except (SaveError,OSError,ValueError,KeyError,TypeError):
   result={'state':'failed','message':'Could not save console state. Shutdown was not requested.'}
  try:self.browser.evaluate('window.__fawkesIdleShutdown?.result('+json.dumps(result['message'])+')')
  except Exception:
   # OS shutdown may already have closed Chromium. Preserve the recorded
   # operation outcome; a lost final display is not proof it was not issued.
   pass
  return result

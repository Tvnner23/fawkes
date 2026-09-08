import json,pathlib,subprocess,tempfile,unittest,sys
from unittest.mock import Mock,patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'deploy'))
from pi_shutdown_state import LocalShutdown,SaveError,THREAD
from pi_shutdown_browser import BrowserShutdown,capture_expression
ID='12345678-1234-4123-8123-123456789abc'
class State(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.run=Mock(return_value=subprocess.CompletedProcess([],0,b'',b''))
  self.s=LocalShutdown(pathlib.Path(self.tmp.name)/'private',runner=self.run,identity=lambda:'boot-one')
  self.value={'storage':{'fawkes-worker-page-v1':json.dumps({'draft':'unsent exact text'})},'page':'4','scroll':{'worker':123}}
 def test_save_reload_same_thread(self):
  self.s.save(self.value,THREAD);self.assertEqual(self.s.restore(THREAD),self.value)
  with self.assertRaises(SaveError):self.s.restore('other')
 def test_no_credentials_allowed(self):
  self.value['storage']['auth_token']='forbidden'
  with self.assertRaises(SaveError):self.s.save(self.value,THREAD)
 def test_one_fixed_command_after_save(self):
  self.assertEqual(self.s.shutdown(ID,self.value,THREAD)['state'],'requested')
  self.run.assert_called_once_with(['/usr/bin/sudo','-n','/usr/bin/systemctl','poweroff'],check=False,capture_output=True,timeout=10)
  with self.assertRaises(SaveError):self.s.shutdown(ID,self.value,THREAD)
  self.assertEqual(self.run.call_count,1)
 def test_save_failure_never_shutdown(self):
  with patch.object(self.s,'save',side_effect=SaveError('full')),self.assertRaises(SaveError):self.s.shutdown(ID,self.value,THREAD)
  self.run.assert_not_called()
 def test_ambiguous_no_retry(self):
  self.run.side_effect=subprocess.TimeoutExpired('fixed',10)
  self.assertEqual(self.s.shutdown(ID,self.value,THREAD)['state'],'unknown')
  with self.assertRaises(SaveError):self.s.shutdown('87654321-1234-4123-8123-123456789abc',self.value,THREAD)
  self.assertEqual(self.run.call_count,1)
 def test_failure_is_not_success(self):
  self.run.return_value=subprocess.CompletedProcess([],1,b'',b'permission denied')
  self.assertEqual(self.s.shutdown(ID,self.value,THREAD)['state'],'failed')
  self.assertEqual(self.s.restore(THREAD),self.value)
 def test_bounded_state(self):
  self.value['storage']['fawkes-worker-page-v1']='x'*200000
  with self.assertRaises(SaveError):self.s.save(self.value,THREAD)
 def test_result_save_failure_does_not_claim_no_request(self):
  real=self.s.durable
  def durable(path,value):
   if value.get('state')=='requested':raise SaveError('readback failed after command')
   return real(path,value)
  with patch.object(self.s,'durable',side_effect=durable):
   result=self.s.shutdown(ID,self.value,THREAD)
  self.assertEqual(result['state'],'unknown');self.assertIn('was requested',result['message'])
  self.assertEqual(self.run.call_count,1)
 def test_non_pi_never_runs_command(self):
  self.s.identity=Mock(side_effect=SaveError('not Pi'))
  with self.assertRaises(SaveError):self.s.shutdown(ID,self.value,THREAD)
  self.run.assert_not_called()
 def test_new_boot_preserves_prior_identity_and_allows_fresh_hold(self):
  self.s.shutdown(ID,self.value,THREAD)
  self.s.identity=lambda:'boot-two'
  with self.assertRaises(SaveError):self.s.shutdown(ID,self.value,THREAD)
  self.s.shutdown('87654321-1234-4123-8123-123456789abc',self.value,THREAD)
  self.assertEqual(self.run.call_count,2)
  self.assertEqual(len(list(self.s.requests.glob('*.json'))),2)
 def test_same_boot_second_new_hold_blocked(self):
  self.s.shutdown(ID,self.value,THREAD)
  with self.assertRaises(SaveError):self.s.shutdown('87654321-1234-4123-8123-123456789abc',self.value,THREAD)
  self.assertEqual(self.run.call_count,1)
 def test_request_record_write_failure_prevents_command(self):
  real=self.s.durable
  def fail(path,value):
   if path.parent==self.s.requests:raise OSError('disk full')
   return real(path,value)
  with patch.object(self.s,'durable',side_effect=fail),self.assertRaises(OSError):self.s.shutdown(ID,self.value,THREAD)
  self.run.assert_not_called()
 def test_another_owner_lock_refuses_execution(self):
  import fcntl
  with (self.s.root/'shutdown.lock').open('a') as f:
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   with self.assertRaises(BlockingIOError):self.s.shutdown(ID,self.value,THREAD)
  self.run.assert_not_called()
 def test_nonfinite_and_negative_scroll_rejected(self):
  for n in [float('nan'),float('inf'),-1,True]:
   self.value['scroll']['worker']=n
   with self.assertRaises((SaveError,ValueError)):self.s.save(self.value,THREAD)
 def test_private_modes_and_same_draft_after_new_owner(self):
  self.s.save(self.value,THREAD)
  self.assertEqual(self.s.saved.stat().st_mode&0o777,0o600)
  again=LocalShutdown(self.s.root,runner=self.run,identity=lambda:'boot-one')
  self.assertEqual(again.restore(THREAD),self.value)
 def test_browser_saves_latest_draft_before_exact_operation(self):
  class Browser:
   session='main'
   def call(self,*a):return {'identifier':'restore-one'}
   def evaluate(_,expression):
    if '.take()' in expression:return {'id':ID,'created':1}
    if 'const storage={}' in expression:return self.value
    return None
  bridge=BrowserShutdown(Browser(),self.s,THREAD,'file:///private/waiting.html','')
  self.assertEqual(bridge.poll()['state'],'requested')
  self.assertEqual(self.s.restore(THREAD),self.value)
 def test_offline_waiting_uses_saved_state_without_network(self):
  self.s.save(self.value,THREAD)
  browser=Mock();browser.session='main'
  browser.evaluate.side_effect=[{'id':ID},None,None]
  bridge=BrowserShutdown(browser,self.s,THREAD,'file:///private/waiting.html','')
  self.assertEqual(bridge.poll()['state'],'requested')
  self.assertEqual(self.s.restore(THREAD),self.value)
 def test_lost_display_after_shutdown_keeps_real_result(self):
  self.s.save(self.value,THREAD)
  browser=Mock();browser.session='main';browser.evaluate.side_effect=[{'id':ID},None,RuntimeError('browser closed by OS')]
  bridge=BrowserShutdown(browser,self.s,THREAD,'file:///private/waiting.html','')
  self.assertEqual(bridge.poll()['state'],'requested');self.assertEqual(self.run.call_count,1)
 def test_corrupt_saved_state_refuses_offline_shutdown(self):
  self.s.saved.write_text('{corrupt')
  browser=Mock();browser.session='main';browser.evaluate.side_effect=[{'id':ID},None,None]
  bridge=BrowserShutdown(browser,self.s,THREAD,'file:///private/waiting.html','')
  self.assertEqual(bridge.poll()['state'],'failed');self.run.assert_not_called()
 def test_restore_hook_has_exact_origin_and_no_action_submission(self):
  self.s.save(self.value,THREAD)
  browser=Mock();browser.session='main';browser.call.return_value={'identifier':'restore-one'}
  BrowserShutdown(browser,self.s,THREAD,'file:///private/waiting.html','').restore_hook()
  method,params,session=browser.call.call_args.args
  self.assertEqual(method,'Page.addScriptToEvaluateOnNewDocument');self.assertEqual(session,'main')
  self.assertIn('http://127.0.0.1:8791',params['source']);self.assertIn('unsent exact text',params['source'])
  for action in ['fetch(','.click(','.submit(','.requestSubmit(']:self.assertNotIn(action,params['source'])
 def test_restore_hook_failure_remains_retryable(self):
  browser=Mock();browser.session='main';browser.evaluate.return_value=self.value
  bridge=BrowserShutdown(browser,self.s,THREAD,'file:///private/waiting.html','')
  browser.call.side_effect=RuntimeError('temporary CDP failure')
  with self.assertRaises(RuntimeError):bridge.checkpoint()
  self.assertIsNone(bridge.last);self.assertEqual(self.s.restore(THREAD),self.value)
  browser.call.side_effect=None;browser.call.return_value={'identifier':'retry'}
  self.assertEqual(bridge.checkpoint(),self.value)
 def test_login_wait_services_same_reader_local_shutdown(self):
  import ast
  source=(pathlib.Path(__file__).resolve().parents[1]/'deploy/pi_console_supervisor.py').read_text()
  tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'local_shutdown_tick','responsive_wait'}]
  clock=Mock();clock.monotonic.side_effect=[0,0,1,2];clock.sleep=Mock()
  namespace={'time':clock,'status':Mock(),'SetupError':RuntimeError}
  exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-supervisor-functions','exec'),namespace)
  browser=Mock();browser.evaluate.side_effect=[False,False,True];shutdown=Mock();shutdown.poll.return_value=None
  namespace['responsive_wait'](browser,'actual-ready','timeout',timeout=25,shutdown=shutdown)
  self.assertEqual(shutdown.install.call_count,3);self.assertEqual(shutdown.poll.call_count,3)
  browser.wait_for.assert_not_called()
  shutdown.poll.return_value={'state':'requested'};browser.process.poll.return_value=0
  with self.assertRaises(SystemExit):namespace['local_shutdown_tick'](browser,shutdown)
  self.assertEqual(namespace['status'].call_args.args[0],'SHUTTING_DOWN')
 def test_valid_complete_storage_preserves_exact_pending_identities(self):
  uuid='12345678-1234-4123-8123-123456789abc';notice=json.dumps([THREAD,'turn-one','message-one','a'*64])
  values={'fawkes-worker-page-v1':{'draft':'unsent café','pendingReply':{'thread_id':THREAD,'reply_id':uuid,'text':'exact queued reply'},'pendingCopy':{'thread_id':THREAD,'message_id':'message-one','content_sha256':'a'*64,'idempotency_key':'worker-final-'+uuid}},
   'fawkes-native-worker-selection-v1':{'thread_id':THREAD,'request_key':'a'*64,'action_sha256':'b'*64,'choice_id':'c'*64,'submission_id':uuid},
   'fawkes-console-update-retry-v1':{'key':'console-browser-'+uuid,'campaign_id':'current-campaign'},
   'fawkes-worker-notice-baseline-v1':{'thread':THREAD,'key':notice},
   'fawkes-objective-notices-v1':[notice,json.dumps(['job','needs_you','b'*64]),json.dumps(['job','complete','event'])]}
  value={'storage':{k:json.dumps(v,ensure_ascii=False) for k,v in values.items()},'page':'4','scroll':{'worker':1400}}
  self.s.save(value,THREAD);self.assertEqual(self.s.restore(THREAD),value)
  self.assertEqual(self.s.shutdown(ID,value,THREAD)['state'],'requested')
 def test_malformed_stored_json_and_wrong_embedded_thread_never_dispatch(self):
  from pi_shutdown_state import KEYS
  cases=[(k,'{broken') for k in KEYS]
  cases += [('fawkes-worker-page-v1',json.dumps({'draft':'keep','pendingReply':{'thread_id':'different-worker','reply_id':ID,'text':'hello'}})),
   ('fawkes-worker-page-v1','{"draft":"first","draft":"ambiguous"}'),
   ('fawkes-worker-page-v1',json.dumps({'draft':'keep','pendingCopy':{'thread_id':'other','message_id':'m','content_sha256':'a'*64,'idempotency_key':'worker-final-'+ID}})),
   ('fawkes-worker-notice-baseline-v1',json.dumps({'thread':'other','key':None})),
   ('fawkes-native-worker-selection-v1',json.dumps({'thread_id':'other','request_key':'a'*64,'action_sha256':'b'*64,'choice_id':'c'*64,'submission_id':ID})),
   ('fawkes-objective-notices-v1',json.dumps([json.dumps(['other','turn','msg','a'*64])]))]
  self.s.save(self.value,THREAD);old=self.s.saved.read_bytes()
  for key,body in cases:
   bad={'storage':{key:body},'page':'4','scroll':{}}
   with self.subTest(key=key,body=body),self.assertRaises(SaveError):self.s.shutdown(ID,bad,THREAD)
   self.assertEqual(self.s.saved.read_bytes(),old)
  self.run.assert_not_called()
 def test_restore_revalidates_schema_and_thread_not_only_outer_record(self):
  self.s.save(self.value,THREAD);record=json.loads(self.s.saved.read_text())
  record['state']['storage']['fawkes-worker-page-v1']=json.dumps({'draft':'keep','pendingReply':{'thread_id':'other','reply_id':ID,'text':'hello'}})
  self.s.saved.write_text(json.dumps(record))
  with self.assertRaises(SaveError):self.s.restore(THREAD)
 def test_pre_navigation_recaptures_new_input_and_defers_hold_or_failed_save(self):
  import ast
  source=(pathlib.Path(__file__).resolve().parents[1]/'deploy/pi_console_supervisor.py').read_text();tree=ast.parse(source)
  functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'prepare_navigation','show_waiting'}]
  namespace={'local_shutdown_tick':Mock(),'status':Mock(),'SetupError':RuntimeError,'SaveError':SaveError}
  exec(compile(ast.Module(body=functions,type_ignores=[]),'actual-navigation-functions','exec'),namespace)
  browser=Mock();shutdown=Mock();shutdown.navigation_token=None;shutdown.begin_navigation.return_value=True;order=[]
  shutdown.checkpoint.side_effect=lambda:order.append('save latest input')
  browser.call.side_effect=lambda *a:order.append('navigate')
  self.assertTrue(namespace['show_waiting'](browser,'file:///local','matrix',shutdown));self.assertEqual(order,['save latest input','navigate'])
  browser.reset_mock();shutdown.begin_navigation.return_value=False
  self.assertFalse(namespace['show_waiting'](browser,'file:///local','matrix',shutdown));browser.call.assert_not_called()
  shutdown.begin_navigation.return_value=True;shutdown.checkpoint.side_effect=SaveError('disk full')
  self.assertFalse(namespace['show_waiting'](browser,'file:///local','matrix',shutdown));browser.call.assert_not_called()
 def test_async_history_restore_retains_intent_until_extent_and_survives_capture(self):
  browser=Mock();browser.session='main';bridge=BrowserShutdown(browser,self.s,THREAD,'file:///waiting','')
  bridge.install();code=browser.evaluate.call_args.args[0]
  javascript=r'''
const vm=require('vm'),assert=require('assert/strict'),fs=require('fs');const v=JSON.parse(fs.readFileSync(0,'utf8'));
let top=0,notify,resize;const root={dataset:{page:'0'}},worker={clientHeight:400,scrollHeight:400,get scrollTop(){return top},set scrollTop(n){top=Math.max(0,Math.min(n,this.scrollHeight-this.clientHeight))}},history={};
const win={__fawkesMatrix:{},FawkesIdleHold:{install(){}},__fawkesPiRestoredView:{page:'4',scroll:{worker:1400}}};
const doc={body:{},getElementById:id=>({'dev-console':root,'worker-reading':worker,'worker-conversation-history':history}[id]||null),querySelector:()=>worker,addEventListener(){}};
const context={window:win,document:doc,location:{origin:'http://127.0.0.1:8791',pathname:'/dev-console',href:'http://127.0.0.1:8791/dev-console'},localStorage:{getItem:()=>null},MutationObserver:class{constructor(f){notify=f}observe(){}disconnect(){this.stopped=true}},ResizeObserver:class{constructor(f){resize=f}observe(){}disconnect(){this.stopped=true}}};
vm.runInNewContext(v.install,context);root.dataset.page='4';notify();assert.equal(top,0);assert.ok(win.__fawkesPiRestoredView);
const captured=vm.runInNewContext(v.capture,context);assert.equal(captured.page,'4');assert.equal(captured.scroll.worker,1400);
worker.scrollHeight=2400;notify();assert.equal(top,1400);assert.equal(win.__fawkesPiRestoredView,undefined);assert.ok(win.__fawkesPiViewObserver.stopped);
console.log(JSON.stringify({deferred_capture:captured,restored:top}));'''
  result=subprocess.run(['node','-e',javascript],input=json.dumps({'install':code,'capture':capture_expression()}),capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['restored'],1400)
 def test_browser_capture_exception_is_save_failure_and_preserves_prior_state(self):
  import ast
  self.s.save(self.value,THREAD)
  pipe=pathlib.Path(__file__).resolve().parents[1]/'deploy/pi-console/browser_pipe.py'
  if not pipe.exists():
   pipe=pathlib.Path(__file__).resolve().parents[2]/'installer-inputs/parent/companion/browser_pipe.py'
  tree=ast.parse(pipe.read_text())
  error=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SetupError')
  cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PipeBrowser')
  fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='evaluate')
  ns={};exec(compile(ast.Module(body=[error,fn],type_ignores=[]),'actual-pipe-evaluate','exec'),ns)
  browser=Mock();browser.session='main'
  browser.call.return_value={'exceptionDetails':{'text':'Synthetic storage access/JSON exception'}}
  browser.evaluate.side_effect=lambda expression:ns['evaluate'](browser,expression)
  bridge=BrowserShutdown(browser,self.s,THREAD,'file:///waiting','')
  with self.assertRaises(SaveError):bridge.checkpoint()
  self.assertEqual(self.s.restore(THREAD),self.value);self.assertIsNone(bridge.last)
  browser.close.assert_not_called();browser.navigate.assert_not_called();self.run.assert_not_called()
  browser.evaluate.side_effect=None;browser.evaluate.return_value=self.value
  browser.call.return_value={'identifier':'restored'}
  self.assertEqual(bridge.checkpoint(),self.value)
 def test_pending_shutdown_capture_failure_never_dispatches_or_discards_page(self):
  browser=Mock();browser.session='main'
  browser.evaluate.side_effect=[{'id':ID},RuntimeError('synthetic Chromium SetupError'),True]
  self.s.save(self.value,THREAD)
  bridge=BrowserShutdown(browser,self.s,THREAD,'file:///waiting','')
  self.assertEqual(bridge.poll()['state'],'failed')
  self.run.assert_not_called();browser.close.assert_not_called()
  self.assertEqual(self.s.restore(THREAD),self.value)
 def test_exact_signin_and_summary_actions_wait_for_hold_and_checkpoint(self):
  import ast
  source=(pathlib.Path(__file__).resolve().parents[1]/'deploy/pi_console_supervisor.py').read_text()
  names={'prepare_navigation','guarded_navigation','open_console'}
  functions=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names]
  order=[];browser=Mock();browser.process.poll.return_value=None
  browser.navigate.side_effect=lambda p:order.append('root navigation')
  def evaluate(expr):
   if expr=='CONSOLE_READY':return False
   order.append(expr);return True
  browser.evaluate.side_effect=evaluate
  shutdown=Mock();shutdown.navigation_token=None;shutdown.begin_navigation.side_effect=[True,False,True,False,True]
  shutdown.select_summary.side_effect=lambda expression:browser.evaluate(expression)
  shutdown.checkpoint.side_effect=lambda:order.append('checkpoint')
  ns={'local_shutdown_tick':Mock(),'status':Mock(),'SetupError':RuntimeError,'SaveError':SaveError,
   'time':Mock(),'responsive_wait':Mock(),'LOGIN_READY':'LOGIN_READY','CONSOLE_READY':'CONSOLE_READY',
   'SUMMARY':'SUMMARY_NAV','sign_in_expression':lambda token:'SIGNIN_NAV'}
  exec(compile(ast.Module(body=functions,type_ignores=[]),'actual-guarded-open','exec'),ns)
  ns['open_console'](browser,'synthetic','MATRIX',shutdown)
  self.assertEqual(order,['checkpoint','root navigation','checkpoint','SIGNIN_NAV','checkpoint','SUMMARY_NAV','MATRIX'])
  self.assertEqual(ns['time'].sleep.call_count,2);self.assertEqual(ns['local_shutdown_tick'].call_count,5)
 def test_pointerdown_during_real_checkpoint_is_reserved_until_action(self):
  import ast
  root=pathlib.Path(__file__).resolve().parents[1]
  harness=(root/'tests/js/pi_console_idle_hold_harness.js').read_text()
  fixture=harness[harness.index('function fixture(){'):harness.index('\nlet f=fixture()')]
  js="const {install}=require("+json.dumps(str(root/'deploy/pi_console_idle_hold.js'))+");"+fixture+r'''
const f=fixture(),vm=require('vm'),root={dataset:{page:'4'}},page={hidden:true};let current='';
const summary={isConnected:true,disabled:false,closest:()=>null,getAttribute:k=>k==='aria-current'?current:null,click(){const e=f.fire('click',{target:summary,isTrusted:false});if(!e.prevented){root.dataset.page='0';current='page';page.hidden=false;}}};
f.doc.querySelector=q=>q==='#dev-console'?root:q.includes('.console-page')?page:null;
f.doc.querySelectorAll=q=>q.includes('button[data-page-target')?[summary]:q.includes('.console-page')?[page]:[];
const context={window:f.win,document:f.doc,location:{origin:'http://127.0.0.1:8791',pathname:'/dev-console'},localStorage:{getItem:()=>null}};
require('readline').createInterface({input:process.stdin}).on('line',line=>{try{const q=JSON.parse(line);let value=q.fire?f.fire(q.fire):vm.runInNewContext(q.expression,context);process.stdout.write(JSON.stringify({value:value===undefined?null:value})+'\n')}catch(e){process.stdout.write(JSON.stringify({error:String(e)})+'\n')}});
'''
  peer=subprocess.Popen(['node','-e',js],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  def rpc(value):
   peer.stdin.write(json.dumps(value)+'\n');peer.stdin.flush();r=json.loads(peer.stdout.readline())
   if 'error' in r:raise RuntimeError(r['error'])
   return r['value']
  browser=Mock();browser.session='main';browser.evaluate.side_effect=lambda expression:rpc({'expression':expression});browser.call.return_value={'identifier':'restore'}
  bridge=BrowserShutdown(browser,self.s,THREAD,'file:///waiting','')
  names={'prepare_navigation','guarded_navigation'};tree=ast.parse((root/'deploy/pi_console_supervisor.py').read_text())
  ns={'local_shutdown_tick':Mock(),'status':Mock(),'SetupError':RuntimeError,'SaveError':SaveError,'time':Mock()}
  exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'exact-navigation-race','exec'),ns)
  assignments={n.targets[0].id:n.value for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)}
  summary_control=ast.literal_eval(assignments['SUMMARY_CONTROL'])
  summary=eval(compile(ast.Expression(assignments['SUMMARY']),'actual-Summary-expression','eval'),{'CONSOLE_READY':'true','SUMMARY_CONTROL':summary_control})
  old_save=self.s.save;press=[];actions=[]
  def save(value,thread):
   press.append(rpc({'fire':'pointerdown'}));return old_save(value,thread)
  try:
   with patch.object(self.s,'save',side_effect=save):
    def action():
     actions.append(rpc({'expression':'[window.__fawkesIdleShutdown.holding,window.__fawkesIdleShutdown.navigationBlocked]'}))
     self.assertTrue(bridge.select_summary(summary))
     self.assertEqual(rpc({'expression':"document.querySelector('#dev-console').dataset.page"}),'0')
     self.assertFalse(rpc({'expression':"window.__fawkesIdleShutdown.selectSummary('wrong-token')"}))
    ns['guarded_navigation'](browser,bridge,action)
   self.assertTrue(press[0]['prevented']);self.assertEqual(actions,[[False,True]])
   self.assertIsNone(bridge.navigation_token);self.assertEqual(rpc({'expression':'window.__fawkesIdleShutdown.navigationBlocked'}),False)
   rpc({'fire':'pointerup'});self.assertTrue(rpc({'fire':'click'})['prevented']);self.run.assert_not_called()
  finally:
   peer.stdin.close();peer.wait(timeout=5);peer.stdout.close();peer.stderr.close()
 def test_navigation_timeout_stops_pending_load_before_releasing_controls(self):
  import ast
  root=pathlib.Path(__file__).resolve().parents[1];tree=ast.parse((root/'deploy/pi_console_supervisor.py').read_text())
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='guarded_navigation')
  ns={'prepare_navigation':lambda *a:True,'time':Mock(),'SetupError':RuntimeError};exec(compile(ast.Module(body=[fn],type_ignores=[]),'exact-timeout-navigation','exec'),ns)
  browser=Mock();browser.session='main';bridge=BrowserShutdown(browser,self.s,THREAD,'file:///waiting','');bridge.navigation_token=ID;order=[]
  browser.call.side_effect=lambda method,*a:order.append(method)
  browser.evaluate.side_effect=lambda expression:order.append('release')
  with self.assertRaises(RuntimeError):ns['guarded_navigation'](browser,bridge,lambda:(_ for _ in ()).throw(RuntimeError('timed out')))
  self.assertEqual(order,['Page.stopLoading','release']);self.assertIsNone(bridge.navigation_token)
  bridge.navigation_token=ID;browser.call.side_effect=RuntimeError('lost stop acknowledgement');browser.evaluate.reset_mock()
  with self.assertRaises(RuntimeError):bridge.abort_navigation()
  self.assertEqual(bridge.navigation_token,ID);browser.evaluate.assert_not_called()
 def test_summary_requires_exact_reserved_action(self):
  browser=Mock();bridge=BrowserShutdown(browser,self.s,THREAD,'file:///waiting','')
  with self.assertRaises(SaveError):bridge.select_summary('summary.click();')
  bridge.navigation_token=ID
  for expression in ['approval.click();','summary.click();summary.click();']:
   with self.assertRaises(SaveError):bridge.select_summary(expression)
  browser.evaluate.assert_not_called()
if __name__=='__main__':unittest.main()

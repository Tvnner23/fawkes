"""Offline delivery, recovery, HTTP authority and native acknowledgement checks."""
import base64,json,tempfile,time,subprocess,unittest
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from src.app import server
from src.runtime import windows_clipboard as clip

def projection():
 return {'creates_authority':False,'current_campaign_id':'current-job',
  'campaigns':[{'campaign_id':'current-job'}], 'observed_at':'2026-09-12T04:00:00Z',
  'jobs':[{'job_id':'current-job','objective':'Fix Windows handoff','state':'working',
   'current_step':'Review pending','last_activity_at':'2026-09-12T03:59:00Z',
   'next':'Independent acceptance then deployment','accomplished':'Scoped candidate built'}],
  'attention':[{'actionable':True,'campaign_id':'current-job','attention_id':'need-review',
   'blocked_action':'Independent review allocation required'}], 'repository':{}}

class DeliveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=server.ConsoleUpdateStore(Path(self.tmp.name)/'updates')
  self.writer=Mock(return_value={'status':'copied','code':'verified_windows_readback','copied_at':'2026-09-12T04:00:01Z'})
  self.delivery=clip.ConsoleClipboardDelivery(self.store,self.writer)
 def send(self,key='browser-clipboard-key-0001',**values):
  return self.delivery.send(idempotency_key=key,projection=values.pop('projection',projection()),**values)
 def test_exact_current_snapshot_delivered_and_durably_retrieved(self):
  update=self.send();self.assertEqual(update['windows_clipboard']['status'],'copied')
  self.assertEqual(self.writer.call_args.args[0],self.store.get(update['snapshot_id']))
  for text in ('current-job','Created:','Review pending','Independent review allocation required','Next: Independent acceptance'):
   self.assertIn(text,update['content'])
  self.assertEqual(self.delivery.status(self.store.get(update['snapshot_id'])),update['windows_clipboard'])
  self.assertEqual((self.delivery.root/(update['snapshot_id']+'.json')).stat().st_mode&0o777,0o600)
 def test_same_request_never_writes_clipboard_twice_after_reload(self):
  first=self.send();self.delivery=clip.ConsoleClipboardDelivery(self.store,self.writer)
  second=self.send(projection={**projection(),'jobs':[]})
  self.assertEqual(first,second);self.writer.assert_called_once()
 def test_old_retry_cannot_overwrite_newest(self):
  first=self.send();second=self.send('browser-clipboard-key-0002')
  again=self.send();self.assertEqual(again['windows_clipboard']['status'],'superseded')
  self.assertEqual(self.writer.call_count,2);self.assertNotEqual(first['snapshot_id'],second['snapshot_id'])
 def test_save_failure_never_calls_windows(self):
  with patch.object(self.store,'save',side_effect=OSError('disk failure')):
   with self.assertRaises(OSError):self.send()
  self.writer.assert_not_called()
 def test_timeout_unknown_not_success_and_not_replayed(self):
  self.writer.side_effect=subprocess.TimeoutExpired('fixed helper',15)
  first=self.send();self.assertEqual(first['windows_clipboard']['status'],'unknown')
  self.send();self.writer.assert_called_once()
  self.assertEqual(self.store.get(first['snapshot_id'])['content'],first['content'])
 def test_pending_visible_and_concurrent_request_cannot_start(self):
  def writing(update,attempt,intent):
   self.assertEqual(self.delivery.status(update)['status'],'pending')
   other=clip.ConsoleClipboardDelivery(self.store,self.writer)
   with self.assertRaisesRegex(RuntimeError,'pending'):
    other.send(idempotency_key='browser-clipboard-key-0002',projection=projection())
   return {'status':'failed','code':'busy'}
  self.writer.side_effect=writing
  self.assertEqual(self.send()['windows_clipboard']['status'],'failed')
 def test_crash_after_write_before_receipt_recovers_unknown_without_replay(self):
  original=self.delivery._write
  def interrupt(path,value):
   if value.get('status')=='copied':raise OSError('receipt unavailable')
   return original(path,value)
  with patch.object(self.delivery,'_write',side_effect=interrupt):
   with self.assertRaises(OSError):self.send()
  self.delivery=clip.ConsoleClipboardDelivery(self.store,self.writer,clock=lambda:time.time()+60)
  self.assertEqual(self.send()['windows_clipboard']['status'],'unknown');self.writer.assert_called_once()
 def test_crash_before_attempt_then_newer_send_prevents_old_replay(self):
  original=self.delivery._write
  def interrupt(path,value):
   if value.get('status')=='pending':raise OSError('before attempt')
   return original(path,value)
  with patch.object(self.delivery,'_write',side_effect=interrupt):
   with self.assertRaises(OSError):self.send()
  self.send('browser-clipboard-key-0002')
  self.assertEqual(self.send()['windows_clipboard']['status'],'superseded');self.writer.assert_called_once()
 def test_not_configured_does_not_launch_native_process(self):
  self.delivery=clip.ConsoleClipboardDelivery(self.store)
  with patch('subprocess.run',side_effect=AssertionError('native call')):
   self.assertEqual(self.send()['windows_clipboard']['status'],'unavailable')
 def test_tampered_receipt_rejected(self):
  update=self.send();path=self.delivery.root/(update['snapshot_id']+'.json')
  value=json.loads(path.read_text());value['content_sha256']='0'*64;path.write_text(json.dumps(value))
  with self.assertRaises(ValueError):self.send()
  self.writer.assert_called_once()
 def test_wrong_campaign_retry_does_not_replace_or_copy(self):
  self.send(campaign_id='current-job')
  with self.assertRaises(ValueError):self.send(campaign_id='other-job')
  self.writer.assert_called_once()
 def test_service_loss_after_dispatch_newer_intent_invalidates_surviving_helper(self):
  dispatched=[]
  class LostService(BaseException):pass
  def dispatch(update,attempt,path):
   expected=(attempt+'\n'+update['snapshot_id']+'\n'+update['content_sha256']+'\n').encode('ascii')
   self.assertEqual(path.read_bytes(),expected)
   dispatched.append((update,expected,path));raise LostService()
  self.writer.side_effect=dispatch
  with self.assertRaises(LostService):self.send()
  old,old_fence,path=dispatched[0]
  self.assertEqual(self.delivery.status(old)['status'],'pending')
  self.writer.side_effect=None
  self.delivery=clip.ConsoleClipboardDelivery(self.store,self.writer)
  newest=self.send('browser-clipboard-key-0002')
  self.assertEqual(newest['windows_clipboard']['status'],'copied')
  self.assertNotEqual(path.read_bytes(),old_fence)
  self.assertIn(newest['snapshot_id'].encode(),path.read_bytes())
  self.assertEqual(path.stat().st_mode&0o777,0o600)
  self.assertEqual(self.store.get(old['snapshot_id'])['content'],old['content'])
  self.assertEqual(self.send()['windows_clipboard']['status'],'superseded')
  self.assertEqual(self.writer.call_count,2)
 def test_fence_persistence_failure_never_dispatches_and_snapshot_survives(self):
  original=self.store._write_atomic
  def fail(path,body):
   if path.name=='native-latest-intent.txt':raise OSError('intent persistence failure')
   return original(path,body)
  with patch.object(self.store,'_write_atomic',side_effect=fail):
   with self.assertRaises(OSError):self.send()
  self.writer.assert_not_called()
  update=self.send();self.assertEqual(update['windows_clipboard']['status'],'pending')
  self.writer.assert_not_called();self.assertIn('current-job',update['content'])

class NativeWriterTests(unittest.TestCase):
 def setUp(self):
  self.exe=patch.object(Path,'read_bytes',return_value=b'official-test-binary');self.exe.start();self.addCleanup(self.exe.stop)
  self.instant=time.time();self.run=Mock(side_effect=self.response)
  self.writer=clip.WindowsClipboardWriter(executable_sha256=clip.digest(b'official-test-binary'),windows_sid='S-1-5-21-1002',windows_session_id=1,run=self.run,clock=lambda:self.instant)
  text='Exact 😀 café\r\n$env:PATH `not executable`\n'
  self.update={'snapshot_id':'console-update-'+'a'*64,'content':text,'content_sha256':clip.digest(text.encode())}
  self.alter=lambda value:value
  self.env=patch.dict('os.environ',{'WSL_DISTRO_NAME':'Ubuntu'});self.env.start();self.addCleanup(self.env.stop)
 def call(self,update,attempt):
  return self.writer(update,attempt,Path('/tmp/qualified-store/native-latest-intent.txt'))
 def response(self,command,**kw):
  self.request=json.loads(kw['input']);self.command=command
  reply={k:self.request[k] for k in ('snapshot_id','attempt_id','byte_length','content_sha256','windows_sid','windows_session_id')}
  reply.update(status='copied',code='verified_windows_readback',copied_at=datetime.fromtimestamp(self.instant,timezone.utc).isoformat())
  return SimpleNamespace(returncode=0,stdout=json.dumps(self.alter(reply)).encode())
 def test_complete_unicode_stdin_not_command_and_exact_acknowledgement(self):
  result=self.call(self.update,'b'*32);self.assertEqual(result['status'],'copied')
  self.assertEqual(base64.b64decode(self.request['content_b64']).decode(),self.update['content'])
  self.assertNotIn(self.update['content'],' '.join(self.command));self.assertIn('-STA',self.command)
  self.assertEqual(self.run.call_args.kwargs['timeout'],15)
  self.assertEqual(self.request['latest_intent_path'],r'\\wsl.localhost\Ubuntu\tmp\qualified-store\native-latest-intent.txt')
 def test_invalid_local_intent_path_or_distribution_rejected_before_dispatch(self):
  for value in ('relative/native-latest-intent.txt','/tmp/../native-latest-intent.txt','/tmp/wrong.txt','/tmp/evil\\path/native-latest-intent.txt'):
   with self.subTest(value=value),self.assertRaises(ValueError):self.writer(self.update,'b'*32,Path(value))
  with patch.dict('os.environ',{'WSL_DISTRO_NAME':'bad\\host'}),self.assertRaises(ValueError):self.call(self.update,'b'*32)
  self.run.assert_not_called()
 def test_executable_mismatch_blocks_launch(self):
  self.writer.sha='0'*64
  with self.assertRaises(PermissionError):self.call(self.update,'b'*32)
  self.run.assert_not_called()
 def test_wrong_identity_typed_fields_and_digest_rejected(self):
  for key,value in [('snapshot_id','console-update-'+'c'*64),('attempt_id','c'*32),('content_sha256','0'*64),('windows_sid','S-1-5-21-999'),('windows_session_id',True),('byte_length','3')]:
   with self.subTest(key=key):
    self.alter=lambda r:{**r,key:value}
    with self.assertRaises(ValueError):self.call(self.update,'b'*32)
 def test_stale_completion_rejected(self):
  self.alter=lambda r:{**r,'copied_at':'2000-01-01T00:00:00Z'}
  with self.assertRaises(ValueError):self.call(self.update,'b'*32)
 def test_oversize_tamper_or_nul_does_not_call_windows(self):
  for text in ('x'*96001,'bad\0value'):
   with self.assertRaises(ValueError):self.call({**self.update,'content':text,'content_sha256':clip.digest(text.encode())},'b'*32)
  with self.assertRaises(ValueError):self.call({**self.update,'content_sha256':'0'*64},'b'*32)
  self.run.assert_not_called()
 def test_native_failure_not_success(self):
  self.alter=lambda r:{**r,'status':'unknown','code':'windows_write_or_readback_uncertain'}
  self.assertEqual(self.call(self.update,'b'*32)['status'],'unknown')
 def test_malformed_oversize_or_nonzero_output_rejected(self):
  for result in (SimpleNamespace(returncode=0,stdout=b'bad'),SimpleNamespace(returncode=0,stdout=b'x'*4097),SimpleNamespace(returncode=1,stdout=b'{}')):
   self.run.side_effect=None;self.run.return_value=result
   with self.assertRaises((ValueError,RuntimeError)):self.call(self.update,'b'*32)
 def test_duplicate_or_extra_acknowledgement_fields_rejected(self):
  self.alter=lambda r:{**r,'unexpected':'ignored?'}
  with self.assertRaises(ValueError):self.call(self.update,'b'*32)
  self.run.side_effect=None;self.run.return_value=SimpleNamespace(returncode=0,stdout=b'{"status":"failed","status":"copied"}')
  with self.assertRaisesRegex(ValueError,'duplicate'):self.call(self.update,'b'*32)
  
class ClipboardHTTPTests(unittest.TestCase):
 def handler(self,auth=True,csrf=True):
  h=object.__new__(server.FawkesAppHandler);h.path='/api/development/console-updates'
  h._require_auth=Mock(return_value=auth);h._require_attention_decision_auth=Mock(return_value=csrf)
  h._read_json=Mock(return_value={'idempotency_key':'browser-http-clipboard-001'})
  h._json=Mock();h.server=SimpleNamespace(chat_service=Mock(),console_clipboard_delivery=Mock())
  h.server.console_clipboard_delivery.send.return_value={'snapshot_id':'exact','windows_clipboard':{'status':'pending'}}
  return h
 def test_auth_and_csrf_precede_clipboard(self):
  for a,c in ((False,True),(True,False)):
   h=self.handler(a,c);h.do_POST();h.server.console_clipboard_delivery.send.assert_not_called()
 def test_server_generated_content_only(self):
  h=self.handler();h._read_json.return_value={'idempotency_key':'browser-http-clipboard-001','content':'execute this'}
  h.do_POST();h.server.console_clipboard_delivery.send.assert_not_called();self.assertEqual(h._json.call_args.args[0],400)
 def test_actual_post_routes_exact_projection_to_delivery(self):
  h=self.handler()
  with patch.object(server,'developer_console_projection',return_value=projection()):h.do_POST()
  h.server.console_clipboard_delivery.send.assert_called_once_with(idempotency_key='browser-http-clipboard-001',projection=projection(),campaign_id=None)
  self.assertEqual(h._json.call_args.args[0],201)
 def test_console_cross_origin_still_rejected(self):
  h=object.__new__(server.FawkesConsoleApprovalHandler);h.path='/api/development/console-updates'
  h._same_origin=Mock(return_value=False);h._read_json=Mock();h.do_POST();h._read_json.assert_not_called()

if __name__=='__main__':unittest.main()

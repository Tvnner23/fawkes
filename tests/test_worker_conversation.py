"""Offline exact-message, same-thread and recovery tests. No provider/clipboard IO."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.app.server import ConsoleUpdateStore
from src.runtime.windows_clipboard import ConsoleClipboardDelivery
from src.runtime.worker_conversation import WorkerConversation, ConversationUnavailable, LocalWorkerProxy, canonical

THREAD='01a06f22-5b47-72c1-9b9c-b70157913436'
REPLY='11111111-2222-4333-8444-555555555555'
FINAL='Commands, unchanged:\r\n```powershell\n& "C:\\Users\\Tanner\\My File.ps1"\n```\nApprove once? — café 🐦\n'

def item(kind='agentMessage', text=FINAL, phase='final_answer', turn='turn-final', identity='message-final', **extra):
    return {'turnId':turn,'item':{'type':kind,'id':identity,'text':text,'phase':phase,**extra}}

class FakeRPC:
    def __init__(self):
        self.thread={'id':THREAD,'cwd':'/home/tvnner/fawkes','status':{'type':'idle'},
            'canAcceptDirectInput':True,'model':'gpt-6-astra','reasoningEffort':'xhigh','updatedAt':123}
        self.final=item();self.history=[self.final]
        self.turns=[{'id':'turn-final','status':'completed'}]
        self.queued=[];self.fail=False;self.wrong=False;self.calls=[]
    def __call__(self, method, params):
        self.calls.append((method,copy.deepcopy(params)))
        if params['threadId']!=THREAD: raise AssertionError('wrong Worker')
        if method=='thread/read':return {'thread':copy.deepcopy(self.thread)}
        if method=='thread/turns/list':return {'data':copy.deepcopy(self.turns)}
        if method=='thread/items/list':
            return {'data':copy.deepcopy([self.final] if params.get('turnId')=='turn-final' else self.history),'nextCursor':None}
        if method=='thread/queue/add':
            self.queued.append(copy.deepcopy(params))
            if self.fail:raise TimeoutError('synthetic lost acknowledgement')
            q={'id':'queue-1','clientUserMessageId':params['clientUserMessageId'],
                'input':[{**params['input'][0],'text_elements':[]}]}
            if self.wrong:q['input'][0]['text']='different'
            return {'queuedSubmission':q}
        raise AssertionError('unapproved method '+method)

class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=ConsoleUpdateStore(Path(self.temp.name)/'updates')
        self.rpc=FakeRPC();self.worker=self.make()
        self.projection={'current_campaign_id':'campaign-current','campaigns':[{'campaign_id':'campaign-current'}]}
    def make(self):
        return WorkerConversation(thread_id=THREAD,cwd='/home/tvnner/fawkes',rpc=self.rpc,store=self.store)
    def send(self,text='Hello from the Pi'):
        return self.worker.send_reply(thread_id=THREAD,reply_id=REPLY,text=text)
    def test_actual_complete_final_and_exact_bytes(self):
        value=self.worker.projection();self.assertEqual(value['latest_final']['text'],FINAL)
        self.assertEqual(value['latest_final']['content_sha256'],hashlib.sha256(FINAL.encode()).hexdigest())
        self.assertFalse(value['model_runtime_confirmed']);self.assertTrue(value['can_reply'])
    def test_streaming_final_does_not_replace_completed_answer(self):
        self.rpc.history=[item(text='unfinished',turn='turn-active')]
        self.rpc.turns.insert(0,{'id':'turn-active','status':'inProgress'})
        self.assertEqual(self.worker.projection()['latest_final']['text'],FINAL)
    def test_unknown_phase_is_public_but_reasoning_tools_and_system_are_not(self):
        self.rpc.history=[item('reasoning','PRIVATE'),item('commandExecution','PRIVATE'),item(phase=None),
                          item('hookPrompt','PRIVATE'),item(phase='commentary',text='Public progress')]
        for index,entry in enumerate(self.rpc.history):entry['item']['id']='unique-'+str(index)
        messages=self.worker.projection()['messages']
        self.assertEqual([x['text'] for x in messages],[FINAL,'Public progress'])
        self.assertIsNone(messages[0]['phase'])
    def test_missing_and_null_phase_never_become_a_final_answer(self):
        for missing in (False,True):
            self.rpc.final=item(phase=None)
            if missing:self.rpc.final['item'].pop('phase')
            self.rpc.history=[self.rpc.final]
            value=self.worker.projection()
            self.assertEqual(value['messages'][0]['text'],FINAL)
            self.assertIsNone(value['latest_final'])
    def test_unavailable_final_not_replaced_with_commentary(self):
        self.rpc.final=item(phase='commentary')
        self.assertIsNone(self.worker.projection()['latest_final'])
    def test_wrong_thread_or_cwd_rejected(self):
        for field,value in [('id','another'),('cwd','/tmp/other')]:
            with self.subTest(field=field):
                before=self.rpc.thread[field];self.rpc.thread[field]=value
                with self.assertRaises(ConversationUnavailable):self.worker.projection()
                self.rpc.thread[field]=before
    def test_unloaded_history_cannot_queue(self):
        self.rpc.thread.update(status={'type':'notLoaded'},canAcceptDirectInput=None)
        self.assertFalse(self.worker.projection()['can_reply'])
        with self.assertRaises(ConversationUnavailable):self.send()
        self.assertFalse(self.rpc.queued)
    def test_unsupported_direct_input_cannot_queue(self):
        self.rpc.thread['canAcceptDirectInput']=False
        with self.assertRaises(ConversationUnavailable):self.send()
    def test_queued_is_not_received_and_default_empty_text_elements_match(self):
        value=self.send();self.assertEqual(value['status'],'queued')
        self.assertNotIn('received_observed_at',value)
        self.assertEqual(self.rpc.queued[0]['input'],[{'type':'text','text':'Hello from the Pi'}])
        self.assertEqual(set(self.rpc.queued[0]),{'threadId','clientUserMessageId','input'})
    def test_exact_user_item_establishes_received_state(self):
        self.send()
        self.rpc.history.insert(0,item('userMessage',turn='turn-reply',identity='user-1',clientId=REPLY,
            content=[{'type':'text','text':'Hello from the Pi','text_elements':[]}]))
        value=self.make().reply_status(REPLY)
        self.assertEqual((value['status'],value['turn_id'],value['message_id']),('received','turn-reply','user-1'))
        self.assertEqual(self.make().reply_status(REPLY)['status'],'received')
    def test_older_receipt_is_resumed_boundedly_across_reload(self):
        self.send();rpc=self.rpc;original=rpc.__call__;pages=[]
        receipt=item('userMessage',turn='turn-old',identity='old-reply',clientId=REPLY,content=[{'type':'text','text':'Hello from the Pi'}])
        def paginated(method,params):
            if method!='thread/items/list':return original(method,params)
            cursor=params.get('cursor');pages.append(cursor)
            number=int(cursor or '0')
            return {'data':[receipt] if number==4 else [item('commandExecution',identity='tool-'+str(number))], 'nextCursor':None if number==4 else str(number+1)}
        self.rpc=paginated;self.worker=self.make()
        for expected in ('1','2','3','4'):
            start=len(pages);value=self.make().reply_status(REPLY)
            self.assertEqual(value['status'],'queued');self.assertEqual(value['reconcile_cursor'],expected)
            self.assertLessEqual(len(pages)-start,2)
        value=self.make().reply_status(REPLY)
        self.assertEqual((value['status'],value['turn_id']),('received','turn-old'))
        self.assertEqual(self.make().reply_status(REPLY)['status'],'received')
        self.assertEqual(len(rpc.queued),1)
    def test_new_head_receipt_is_seen_during_older_scan(self):
        self.send();path=self.worker.root/(REPLY+'.json');value=self.worker._read(path)
        self.worker._write(path,{k:v for k,v in {**value,'reconcile_cursor':'old-page'}.items() if k!='record_sha256'})
        self.rpc.history=[item('userMessage',clientId=REPLY,content=[{'type':'text','text':'Hello from the Pi'}])]
        self.assertEqual(self.worker.reply_status(REPLY)['status'],'received')
        self.assertFalse(any(p.get('cursor')=='old-page' for m,p in self.rpc.calls))
    def test_nonadvancing_receipt_cursor_is_not_success(self):
        self.send();path=self.worker.root/(REPLY+'.json');value=self.worker._read(path)
        self.worker._write(path,{k:v for k,v in {**value,'reconcile_cursor':'same'}.items() if k!='record_sha256'})
        original=self.rpc.__call__
        self.worker.rpc=lambda m,p: {'data':[],'nextCursor':'same'} if m=='thread/items/list' else original(m,p)
        value=self.worker.reply_status(REPLY)
        self.assertEqual(value['status'],'queued');self.assertEqual(value['observation'],'unavailable')
    def test_maximum_escaped_reply_survives_all_receipt_states(self):
        from src.runtime.worker_conversation import MAX_REPLY_RECORD
        for suffix in ('\n','\x01','\\','"'):
            with self.subTest(suffix=repr(suffix)),tempfile.TemporaryDirectory() as tmp:
                rpc=FakeRPC();worker=WorkerConversation(thread_id=THREAD,cwd='/home/tvnner/fawkes',rpc=rpc,store=ConsoleUpdateStore(Path(tmp)/'updates'))
                text='A'+suffix*15999
                value=worker.send_reply(thread_id=THREAD,reply_id=REPLY,text=text)
                self.assertEqual(value['status'],'queued')
                self.assertEqual(worker.reply_status(REPLY)['text'],text)
                rpc.history=[item('userMessage',clientId=REPLY,content=[{'type':'text','text':text}])]
                self.assertEqual(worker.reply_status(REPLY)['status'],'received')
                self.assertEqual(worker._read(worker.root/(REPLY+'.json'))['text'],text)
                self.assertLessEqual((worker.root/(REPLY+'.json')).stat().st_size,MAX_REPLY_RECORD)
    def test_lost_acknowledgement_is_not_replayed_after_reload(self):
        self.rpc.fail=True;self.assertEqual(self.send()['status'],'unknown')
        self.worker=self.make();self.assertEqual(self.send()['status'],'unknown')
        self.assertEqual(len(self.rpc.queued),1)
    def test_first_use_reply_directories_are_durable_before_queue(self):
        barriers=[];original=self.store._fsync_directory;rpc=self.rpc
        def sync(path):
            barriers.append(Path(path));original(path)
        def checked(method,params):
            if method=='thread/queue/add':
                for path in (self.worker.root.parent,self.worker.root):
                    self.assertIn(path,barriers);self.assertIn(path.parent,barriers)
                self.assertEqual(self.worker._read(self.worker.root/(REPLY+'.json'))['status'],'pending')
            return rpc(method,params)
        self.worker.rpc=checked
        with patch.object(self.store,'_fsync_directory',side_effect=sync):
            self.assertEqual(self.send()['status'],'queued')
    def test_interrupted_directory_publish_is_repaired_before_dispatch(self):
        self.store._prepare();self.worker.root.mkdir(parents=True)
        calls=[];original=self.store._fsync_directory
        def sync(path):calls.append(Path(path));original(path)
        with patch.object(self.store,'_fsync_directory',side_effect=sync):self.send()
        self.assertIn(self.store.root,calls);self.assertIn(self.worker.root.parent,calls)
        self.assertIn(self.worker.root,calls)
    def test_directory_sync_failure_prevents_queue_then_recovery_preserves_identity(self):
        self.store._prepare();original=self.store._fsync_directory
        def fail(path):
            if Path(path)==self.worker.root.parent:raise OSError('synthetic directory barrier failure')
            original(path)
        with patch.object(self.store,'_fsync_directory',side_effect=fail),self.assertRaises(OSError):self.send()
        self.assertFalse(self.rpc.queued)
        self.worker=self.make();self.assertEqual(self.send()['status'],'queued')
        self.worker=self.make();self.send();self.assertEqual(len(self.rpc.queued),1)
    def test_bad_acknowledgement_is_not_success(self):
        self.rpc.wrong=True;self.assertEqual(self.send()['status'],'unknown')
    def test_duplicate_identity_cannot_change_text_or_session(self):
        self.send()
        with self.assertRaises(ValueError):self.send('Changed')
        with self.assertRaises(ValueError):self.worker.send_reply(thread_id=REPLY,reply_id=REPLY,text='x')
        self.assertEqual(len(self.rpc.queued),1)
    def test_pending_crash_intent_is_not_resent(self):
        self.worker._prepare();path=self.worker.root/(REPLY+'.json')
        self.worker._write(path,{'thread_id':THREAD,'reply_id':REPLY,'text':'Hello from the Pi',
            'created_at':'2020-01-01T00:00:00+00:00','status':'pending'})
        self.assertEqual(self.send()['status'],'unknown');self.assertFalse(self.rpc.queued)
    def test_reply_record_tampering_rejected(self):
        self.send();path=self.worker.root/(REPLY+'.json');value=json.loads(path.read_text())
        value['text']='forged';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.worker.reply_status(REPLY)
    def test_same_client_id_wrong_text_cannot_claim_received(self):
        self.send();self.rpc.history=[item('userMessage',clientId=REPLY,content=[{'type':'text','text':'Wrong'}])]
        with self.assertRaises(ValueError):self.worker.reply_status(REPLY)
    def test_utf8_reply_bound_and_empty_input(self):
        for text in ('','   ','\0','🐦'*4001):
            with self.subTest(text_length=len(text)),self.assertRaises(ValueError):self.send(text)
        self.assertFalse(self.rpc.queued)
    def test_message_display_bound_never_truncates(self):
        self.rpc.final=item(text='x'*256001)
        with self.assertRaises(ConversationUnavailable):self.worker.projection()
    def test_expected_final_identity_revalidated(self):
        final=self.worker.projection()['latest_final']
        self.assertEqual(self.worker.exact_final(thread_id=THREAD,message_id=final['message_id'],content_sha256=final['content_sha256'])['text'],FINAL)
        self.rpc.final=item(text='new final')
        with self.assertRaises(ValueError):self.worker.exact_final(thread_id=THREAD,message_id=final['message_id'],content_sha256=final['content_sha256'])
    def test_exact_final_snapshot_and_windows_delivery_reuse(self):
        final={**self.worker.projection()['latest_final'],'thread_id':THREAD};writes=[]
        def writer(update,attempt,intent):
            writes.append(update['content']);self.assertTrue(intent.is_file())
            return {'status':'copied','code':'verified_windows_readback','copied_at':'2026-09-12T00:00:00+00:00'}
        delivery=ConsoleClipboardDelivery(self.store,writer)
        args={'idempotency_key':'final-test-request-123456789','projection':self.projection,'campaign_id':'campaign-current','final_message':final}
        value=delivery.send(**args);again=delivery.send(**args)
        self.assertEqual(value['content'],FINAL);self.assertEqual(writes,[FINAL])
        self.assertEqual(value['snapshot_id'],again['snapshot_id'])
        self.assertEqual(self.store.get(value['snapshot_id'])['content'].encode(),FINAL.encode())
        self.assertEqual(value['worker_message']['thread_id'],THREAD)
    def test_clipboard_failure_retains_exact_final(self):
        final={**self.worker.projection()['latest_final'],'thread_id':THREAD}
        def writer(*args):raise TimeoutError('synthetic')
        value=ConsoleClipboardDelivery(self.store,writer).send(idempotency_key='failure-request-123456789',
            projection=self.projection,campaign_id='campaign-current',final_message=final)
        self.assertEqual(value['windows_clipboard']['status'],'unknown')
        self.assertEqual(self.store.get(value['snapshot_id'])['content'],FINAL)
    def test_snapshot_key_cannot_be_rebound_to_new_final(self):
        final={**self.worker.projection()['latest_final'],'thread_id':THREAD}
        args={'idempotency_key':'bound-request-123456789','projection':self.projection,'campaign_id':'campaign-current'}
        self.store.save(**args,final_message=final)
        final={**final,'message_id':'different'}
        with self.assertRaises(ValueError):self.store.save(**args,final_message=final)
        with self.assertRaises(ValueError):self.store.save(**args)
    def test_full_message_beyond_clipboard_limit_rejected_not_summarized(self):
        self.rpc.final=item(text='x'*96001)
        final={**self.worker.projection()['latest_final'],'thread_id':THREAD}
        with self.assertRaises(ValueError):self.store.save(idempotency_key='oversize-request-123456789',projection=self.projection,final_message=final)
        self.assertFalse((self.store.root/'records').exists())
    def test_public_query_rejects_oversized_cursor(self):
        with self.assertRaises(ValueError):self.worker.projection('x'*4097)
    def test_transport_never_exposes_other_methods(self):
        proxy=LocalWorkerProxy(executable='/not/launched',socket_path='/not/opened',thread_id=THREAD,cwd='/home/tvnner/fawkes')
        for method in ('thread/start','thread/resume','turn/start','turn/steer','command/exec','item/commandExecution/requestApproval'):
            with self.subTest(method=method),self.assertRaises(PermissionError):proxy(method,{'threadId':THREAD})
        with self.assertRaises(PermissionError):proxy('thread/read',{'threadId':REPLY})

if __name__=='__main__':unittest.main()

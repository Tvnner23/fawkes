"""Real authenticated HTTP paths with synthetic session/clipboard peers."""
import http.client,json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src.app import server
from src.runtime.worker_conversation import WorkerConversation
from tests.test_worker_conversation import THREAD,REPLY,FINAL,FakeRPC,item

class WorkerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.store=server.ConsoleUpdateStore(root/'updates');self.rpc=FakeRPC()
        self.worker=WorkerConversation(thread_id=THREAD,cwd='/home/tvnner/fawkes',rpc=self.rpc,store=self.store)
        self.writes=[]
        def writer(update,*_):
            self.writes.append(update['content'])
            return {'status':'copied','code':'verified_windows_readback','copied_at':'2026-09-12T00:00:00Z'}
        self.http=server.FawkesAppServer(('127.0.0.1',0),chat_service=SimpleNamespace(),app_token='synthetic-test',
            app_session_store=server.BrowserSessionStore(root/'sessions'),console_update_store=self.store,
            console_clipboard_writer=writer,worker_conversation=self.worker)
        self.http.RequestHandlerClass=server.FawkesConsoleApprovalHandler
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.origin='http://127.0.0.1:'+str(self.http.server_port);self.cookie='';self.csrf=''
        projection={'current_campaign_id':'current','campaigns':[{'campaign_id':'current'}]}
        patcher=patch.object(server,'developer_console_projection',return_value=projection);patcher.start();self.addCleanup(patcher.stop)
    def close(self):self.http.shutdown();self.http.server_close();self.thread.join(timeout=2)
    def request(self,method,path,data=None,*,origin=None,csrf=True):
        c=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        headers={'Origin':origin or self.origin,'Content-Type':'application/json'}
        if self.cookie:headers['Cookie']=self.cookie
        if self.csrf and csrf:headers['X-Fawkes-CSRF-Token']=self.csrf
        c.request(method,path,None if data is None else (data if isinstance(data,str) else json.dumps(data)),headers)
        r=c.getresponse();body=r.read();status=r.status;h=dict(r.getheaders());c.close()
        return status,body,h
    def login(self):
        status,body,h=self.request('POST','/api/session',{'credential':'synthetic-test'})
        self.assertEqual(status,200);self.cookie=h['Set-Cookie'].split(';')[0];self.csrf=json.loads(body)['csrf_token']
    def test_auth_origin_and_csrf_before_reply(self):
        data={'thread_id':THREAD,'reply_id':REPLY,'text':'Hello'}
        self.assertEqual(self.request('POST','/api/development/worker/replies',data)[0],401)
        self.login()
        self.assertEqual(self.request('POST','/api/development/worker/replies',data,csrf=False)[0],403)
        self.assertEqual(self.request('POST','/api/development/worker/replies',data,origin='http://evil.test')[0],403)
        self.assertFalse(self.rpc.queued)
    def test_exact_final_copy_and_download_is_verbatim(self):
        self.login();status,body,_=self.request('GET','/api/development/worker')
        self.assertEqual(status,200);final=json.loads(body)['latest_final']
        data={'thread_id':THREAD,'message_id':final['message_id'],'content_sha256':final['content_sha256'],'idempotency_key':'worker-http-exact-123456789'}
        status,body,_=self.request('POST','/api/development/worker/clipboard',data)
        self.assertEqual(status,201,body);update=json.loads(body)
        self.assertEqual(update['content'],FINAL);self.assertEqual(self.writes,[FINAL])
        status,body,_=self.request('GET','/api/development/console-updates/'+update['snapshot_id']+'.txt')
        self.assertEqual(status,200);self.assertEqual(body,FINAL.encode())
    def test_browser_cannot_supply_final_body_or_change_worker(self):
        self.login();final=self.worker.projection()['latest_final']
        data={'thread_id':THREAD,'message_id':final['message_id'],'content_sha256':final['content_sha256'],'idempotency_key':'worker-http-forged-123456789','content':'injected'}
        self.assertEqual(self.request('POST','/api/development/worker/clipboard',data)[0],400)
        self.assertFalse(self.writes)
        self.assertEqual(self.request('POST','/api/development/worker/replies',{'thread_id':REPLY,'reply_id':REPLY,'text':'wrong thread'})[0],400)
        self.assertFalse(self.rpc.queued)
    def test_duplicate_json_fields_rejected(self):
        self.login()
        body='{"thread_id":"'+THREAD+'","reply_id":"'+REPLY+'","text":"first","text":"second"}'
        self.assertEqual(self.request('POST','/api/development/worker/replies',body)[0],400)
        self.assertFalse(self.rpc.queued)
    def test_reply_delivery_receipt_and_no_duplicate(self):
        self.login();data={'thread_id':THREAD,'reply_id':REPLY,'text':'Actual synthetic Pi text'}
        status,body,_=self.request('POST','/api/development/worker/replies',data)
        self.assertEqual(status,201);self.assertEqual(json.loads(body)['status'],'queued')
        self.rpc.history=[item('userMessage',clientId=REPLY,content=[{'type':'text','text':data['text']}])]
        status,body,_=self.request('GET','/api/development/worker/replies/'+REPLY)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],'received')
        self.request('POST','/api/development/worker/replies',data)
        self.assertEqual(len(self.rpc.queued),1)
    def test_disconnected_response_is_not_empty_history_or_sent(self):
        self.login();self.http.worker_conversation=None
        status,body,_=self.request('GET','/api/development/worker')
        self.assertEqual(status,503);self.assertEqual(json.loads(body)['error']['code'],'worker_not_connected')
    def test_worker_static_and_summary_entry_are_served(self):
        status,body,_=self.request('GET','/dev-console/worker.js');self.assertEqual(status,200)
        self.assertIn(b'FawkesWorkerConversation',body)

if __name__=='__main__':unittest.main()

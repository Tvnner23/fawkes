"""Authenticated console route against a synthetic native owner; no Codex call."""
import json,time,unittest
from src.runtime.worker_native_approvals import NativeApprovalRelay
from tests import test_worker_conversation_http as worker_http
from tests.test_worker_native_approvals import request
from tests.test_worker_conversation import THREAD,REPLY

class NativeHTTPTests(worker_http.WorkerHTTPTests):
    def setUp(self):
        super().setUp()
        self.native=NativeApprovalRelay(executable='/not/executed',socket_path='/not/opened',
            thread_id=THREAD,cwd='/tmp/fixture',store=self.store)
        self.native._prepare();self.addCleanup(self.native.close)
        self.native.epoch='http-fixture';self.native.connected=True;self.native.verified_at=time.time()
        self.native.observe(request());self.http.native_worker_approvals=self.native
    def data(self):
        r=next(iter(self.native.records.values()))
        return {'thread_id':THREAD,'request_key':r['request_key'],'action_sha256':r['action_sha256'],
            'choice_id':r['description']['choices'][0]['choice_id'],'submission_id':REPLY}
    def test_native_auth_csrf_origin_and_exact_fields(self):
        path='/api/development/worker/approvals/decision';data=self.data()
        self.assertEqual(self.request('POST',path,data)[0],401)
        self.assertEqual(self.request('GET','/api/development/worker/approvals')[0],401)
        self.login()
        self.assertEqual(self.request('POST',path,data,csrf=False)[0],403)
        self.assertEqual(self.request('POST',path,data,origin='https://wrong.example')[0],403)
        self.assertEqual(self.request('POST',path,{**data,'command':'injected'})[0],409)
        self.assertEqual(self.request('POST',path,{**data,'text':'yes'})[0],409)
        self.assertEqual(self.native.outgoing.qsize(),0)
    def test_native_receipt_only_queues_exact_offered_response(self):
        self.login();path='/api/development/worker/approvals/decision'
        status,body,_=self.request('POST',path,self.data());self.assertEqual(status,200,body)
        record=json.loads(body);self.assertEqual(record['selection']['state'],'recorded_not_sent')
        self.assertEqual(self.native.outgoing.qsize(),1);self.assertEqual(self.rpc.queued,[])
        status,body,_=self.request('POST',path,self.data());self.assertEqual(status,200,body)
        self.assertEqual(self.native.outgoing.qsize(),1)
        sent=[];self.native._send_selection(record['request_key'],sent.append)
        self.assertEqual(sent,[{'id':110,'result':{'decision':'accept'}}])
    def test_native_pc_resolution_and_unavailable_are_distinct_from_empty(self):
        self.login();self.native.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
        self.assertEqual(self.request('POST','/api/development/worker/approvals/decision',self.data())[0],409)
        status,body,_=self.request('GET','/api/development/worker/approvals');self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['pending_count'],0)
        self.native._disconnect('fixture');status,body,_=self.request('GET','/api/development/worker/approvals')
        self.assertFalse(json.loads(body)['connected'])
        self.http.native_worker_approvals=None
        self.assertEqual(self.request('GET','/api/development/worker/approvals')[0],503)
    def test_chat_yes_is_not_permission_and_native_js_is_served(self):
        self.login();self.request('POST','/api/development/worker/replies',{'thread_id':THREAD,'reply_id':REPLY,'text':'yes'})
        self.assertTrue(self.native.outgoing.empty());self.assertIsNone(next(iter(self.native.records.values()))['selection'])
        status,body,_=self.request('GET','/dev-console/worker-native.js');self.assertEqual(status,200)
        self.assertIn(b'FawkesNativeWorkerApprovals',body)

    def test_readonly_turn_cursor_routes_exactly_and_preserves_auth(self):
        from unittest.mock import patch
        self.assertEqual(self.request('GET','/api/development/worker?turn_cursor=older')[0],401)
        self.login()
        with patch.object(self.worker,'projection',return_value={'synthetic':True}) as project:
            status,_,_=self.request('GET','/api/development/worker?cursor=items&turn_cursor=turns')
            self.assertEqual(status,200);project.assert_called_once_with('items',turn_cursor='turns')
        self.assertEqual(self.request('GET','/api/development/worker?turn_cursor=')[0],400)
        self.assertEqual(self.request('GET','/api/development/worker?turn_cursor=one&turn_cursor=two')[0],400)
        self.assertEqual(self.request('GET','/api/development/worker/approvals?turn_cursor=older')[0],400)
        self.assertFalse(self.rpc.queued);self.assertTrue(self.native.outgoing.empty())

if __name__=='__main__':unittest.main()

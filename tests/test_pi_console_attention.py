import copy, http.client, json, os, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
from src.app.server import FawkesAppServer,FawkesConsoleApprovalHandler,BrowserSessionStore
from src.runtime.chat_service import ConsoleAttentionService
from src.runtime.codex_app_server import (CodexAppServerTransport, typed_approval,
    approval_response, bounded_decisions, PROTOCOL_VERSION, REVIEWER_PROTOCOL_VERSION,
    MANAGED_PROTOCOL_VERSION, exec_compatible_app_server_runner)
from src.runtime.development_attention import DevelopmentAttentionStore
from tests.test_codex_development_campaign import CampaignFixture

METHOD="item/commandExecution/requestApproval"

class LegacyActionMaterialTests(unittest.TestCase):
    """Pinned-schema action checks exercised through the real managed reader."""
    def valid(self, method):
        base={'conversationId':'t','callId':'action','reason':'Synthetic test only'}
        if method == 'execCommandApproval':
            return {**base,'command':['printf',''],'cwd':'/fixture','parsedCmd':[]}
        return {**base,'fileChanges':{'/fixture/empty.txt':{'type':'add','content':''},
            '/fixture/old.txt':{'type':'delete','content':''},
            '/fixture/edit.txt':{'type':'update','unified_diff':'-old\n+new\n','move_path':None}}}

    def run_request(self, method, params, choice='approve_once', mutate=False):
        from tests.test_codex_reviewer_client_compatibility import Process, START, ITEM, END
        from src.runtime import codex_app_server as app
        self.seen=[];self.claims=[]
        frames=copy.deepcopy(START)+[{'id':41,'method':method,'params':params}]
        if choice == 'approve_once':
            frames.append({'method':'serverRequest/resolved','params':{'threadId':'t','requestId':41}})
            frames.append({'method':'item/completed','params':{'threadId':'t','turnId':'u',
                'item':{'id':'action','type':'commandExecution' if method=='execCommandApproval' else 'fileChange',
                        'status':'completed'}}})
        frames+=copy.deepcopy([ITEM,END])
        self.process=Process(frames)
        def handler(request, **kwargs):
            self.seen.append(request)
            if mutate:
                action=request['exact_action']['action']
                if isinstance(action,list): action.append('CHANGED')
                else: action['/fixture/empty.txt']['content']='CHANGED'
            return {'choice':choice,'claim':lambda:self.claims.append('claim'),
                    'complete':lambda state:self.claims.append(state)}
        transport=app.CodexAppServerTransport(protocol_version=MANAGED_PROTOCOL_VERSION,
            timeout_seconds=2,popen=lambda *a,**k:self.process)
        with tempfile.TemporaryDirectory() as root, patch.object(transport,'qualify',return_value={'synthetic':True}), \
             patch.object(app.subprocess,'Popen',side_effect=AssertionError('Real process forbidden')):
            return transport.run(cwd=root,prompt='synthetic',output_schema={'type':'object'},
                output_path=Path(root)/'output.json',sandbox='workspace-write',campaign_id='c',
                invocation_id='i',worker={'worker_id':'fixture'},environment={},
                approval_handler=handler,allow_detached_continuation=False)

    def replies(self):
        return [json.loads(line) for line in self.process.stdin.getvalue().splitlines()
                if json.loads(line).get('id')==41]

    def test_reason_only_reproductions_block_approve_through_managed_transport(self):
        for method in ('execCommandApproval','applyPatchApproval'):
            with self.subTest(method=method):
                params={'conversationId':'t','callId':'action','reason':'Explanation is not an action.'}
                with self.assertRaisesRegex(OSError,'bounded decision'):self.run_request(method,params)
                self.assertNotIn('approve_once',self.seen[0]['protocol']['native_decision_choices'])
                self.assertIsNone(self.seen[0]['exact_action']['action'])
                self.assertEqual(self.replies(),[]);self.assertEqual(self.claims,[])

    def test_required_material_missing_or_wrong_type_fails_display_and_response(self):
        for method,keys in (('execCommandApproval',('command','cwd','parsedCmd')),
                            ('applyPatchApproval',('fileChanges',))):
            for key in keys:
                for value in ('MISSING',None,False,42):
                    with self.subTest(method=method,key=key,value=value):
                        params=self.valid(method)
                        if value=='MISSING':params.pop(key)
                        else:params[key]=value
                        self.assertNotIn('approve_once',bounded_decisions(method,params)[0])
                        with self.assertRaises(OSError):approval_response(method,'approve_once',params)
                        with self.assertRaises(OSError):self.run_request(method,params)
                        self.assertEqual(self.replies(),[])

    def test_nested_command_and_file_variants_are_checked(self):
        bad_commands=[[],[False],[''],['echo',1],'echo safe']
        for command in bad_commands:
            with self.subTest(command=command):
                p={**self.valid('execCommandApproval'),'command':command}
                self.assertNotIn('approve_once',bounded_decisions('execCommandApproval',p)[0])
        for parsed in ([{}],[{'type':'read','cmd':'x','name':'x'}],
            [{'type':'search','cmd':'x','query':False}],[{'type':'list_files','cmd':2}],
            [{'type':'unrecognized','cmd':'x'}],['x']):
            p={**self.valid('execCommandApproval'),'parsedCmd':parsed}
            with self.assertRaises(OSError):approval_response('execCommandApproval','approve_once',p)
        for changes in ({}, {'x':[]},{'':{'type':'add','content':''}},
            {'x':{'type':'add'}},{'x':{'type':'delete','content':False}},
            {'x':{'type':'update','unified_diff':False}},
            {'x':{'type':'update','unified_diff':'','move_path':7}}, {'x':{'type':'unknown'}}):
            with self.subTest(changes=changes):
                p={**self.valid('applyPatchApproval'),'fileChanges':changes}
                self.assertNotIn('approve_once',bounded_decisions('applyPatchApproval',p)[0])
                with self.assertRaises(OSError):approval_response('applyPatchApproval','approve_once',p)

    def test_valid_requests_approve_once_and_bind_actual_material(self):
        for method in ('execCommandApproval','applyPatchApproval'):
            with self.subTest(method=method):
                params=self.valid(method)
                params['changes']='Not the native action field'
                result=self.run_request(method,params)
                self.assertEqual(result.returncode,0)
                self.assertEqual(self.replies(),[{'id':41,'result':{'decision':'approved'}}])
                self.assertEqual(self.claims,['claim','completed'])
                action=params['command'] if method=='execCommandApproval' else params['fileChanges']
                self.assertEqual(self.seen[0]['exact_action']['action'],action)
                self.assertEqual(self.seen[0]['protocol']['thread_id'],'t')
                self.assertEqual(self.seen[0]['protocol']['turn_id'],'u')
                self.assertEqual(self.seen[0]['protocol']['item_id'],'action')
                if method=='applyPatchApproval':self.assertEqual(self.seen[0]['resources'],list(action))

    def test_denial_prevents_claim_for_valid_and_incomplete_legacy_requests(self):
        for method in ('execCommandApproval','applyPatchApproval'):
            for params in (self.valid(method),{'conversationId':'t','callId':'action','reason':'Only reason'}):
                with self.subTest(method=method,params=params):
                    self.run_request(method,params,'deny')
                    self.assertIn('denied',self.replies()[0]['result']['decision'])
                    self.assertEqual(self.claims,[])

    def test_cancel_returns_abort_and_stops_the_managed_turn(self):
        for method in ('execCommandApproval','applyPatchApproval'):
            with self.assertRaisesRegex(OSError,'cancelled by Tanner'):
                self.run_request(method,self.valid(method),'cancel_campaign')
            self.assertEqual(self.replies(),[{'id':41,'result':{'decision':'abort'}}])
            self.assertEqual(self.claims,[])

    def test_mutated_action_during_wait_is_rejected_before_reply(self):
        for method in ('execCommandApproval','applyPatchApproval'):
            with self.assertRaisesRegex(OSError,'changed during its decision wait'):
                self.run_request(method,self.valid(method),mutate=True)
            self.assertEqual(self.replies(),[]);self.assertEqual(self.claims,[])

    def test_optional_metadata_valid_variants_and_session_root_stay_bounded(self):
        p=self.valid('execCommandApproval')
        p['parsedCmd']=[{'type':'read','cmd':'x','name':'x','path':'/x'},
            {'type':'list_files','cmd':'x','path':None},
            {'type':'search','cmd':'x','path':None,'query':None},{'type':'unknown','cmd':'x'}]
        self.assertIn('approve_once',bounded_decisions('execCommandApproval',p)[0])
        for method in ('execCommandApproval','applyPatchApproval'):
            p=self.valid(method);p['reason']=False
            self.assertNotIn('approve_once',bounded_decisions(method,p)[0])
        for root in ('','/fixture',False,[]):
            p=self.valid('applyPatchApproval');p['grantRoot']=root
            self.assertNotIn('approve_once',bounded_decisions('applyPatchApproval',p)[0])

    def test_every_non_null_grant_root_is_blocked_through_managed_response(self):
        for root in ('', '/fixture', ' ', False, 0, [], {}):
            with self.subTest(root=root):
                p=self.valid('applyPatchApproval');p['grantRoot']=root
                self.assertNotIn('approve_once',bounded_decisions('applyPatchApproval',p)[0])
                with self.assertRaises(OSError):approval_response('applyPatchApproval','approve_once',p)
                with self.assertRaises(OSError):self.run_request('applyPatchApproval',p)
                self.assertEqual(self.replies(),[]);self.assertEqual(self.claims,[])
                self.run_request('applyPatchApproval',p,'deny')
                self.assertIn('denied',self.replies()[0]['result']['decision'])
                self.assertEqual(self.claims,[])

    def test_missing_and_null_grant_root_keep_exact_one_action_behavior(self):
        for include_null in (False,True):
            with self.subTest(include_null=include_null):
                p=self.valid('applyPatchApproval')
                if include_null:p['grantRoot']=None
                self.run_request('applyPatchApproval',p)
                self.assertEqual(self.replies(),[{'id':41,'result':{'decision':'approved'}}])
                self.assertEqual(self.claims,['claim','completed'])
                self.assertEqual(self.seen[0]['exact_action']['action'],p['fileChanges'])

class LocalTransport(CodexAppServerTransport):
    def qualify(self, environment):
        # Protocol fixture only; the installed executable has a separate real qualification.
        return {"protocol_version":PROTOCOL_VERSION,"synthetic":True}

class PiConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.fixture=CampaignFixture(self.root);self.campaign=self.fixture.campaign
        self.campaign.attention_store=DevelopmentAttentionStore(self.root/"attention")
        payload=self.fixture.payload("pi-local-fixture")
        payload["execution_budget_v01"]={"maximum_duration_seconds":600,"maximum_worker_turns":1,
            "maximum_reviewer_turns":1,"maximum_provider_turns":2,"maximum_cost_units":2,
            "maximum_correction_cycles":1,"maximum_iterations":1}
        record=self.campaign.create(payload,authenticated_rider=True,stepwise=True)
        self.campaign_id=record["campaign_id"];self.invocation_id="pi-fixture-worker-appserver"
        self.campaign._update(record,event_kind="fixture_owner_binding",event_detail={},
            active_builder_task_scope_id="pi-fixture-worker",status="builder_running")
        self.silence=patch("src.runtime.codex_development_campaign.retain_needs_tanner_notification",lambda *_a,**_k:None)
        self.silence.start();self.addCleanup(self.silence.stop)
        self.silence2=patch("src.runtime.codex_development_campaign.retain_campaign_terminal_notification",lambda *_a,**_k:None)
        self.silence2.start();self.addCleanup(self.silence2.stop)
        self.service=ConsoleAttentionService(self.campaign,repository=self.root)
        self.server=FawkesAppServer(("127.0.0.1",0),chat_service=self.service,
            app_token="synthetic-local-only",app_session_store=BrowserSessionStore(self.root/"sessions"))
        self.server.RequestHandlerClass=FawkesConsoleApprovalHandler
        self.origin="http://127.0.0.1:"+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_server)
        self.cookie="";self.csrf=""
    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)
    def request(self,path,body=None,*,auth=True,csrf=True,origin=True,method=None):
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={"Content-Type":"application/json"}
        if origin:headers["Origin"]=self.origin
        if auth and self.cookie:headers["Cookie"]=self.cookie
        if csrf and self.csrf:headers["X-Fawkes-CSRF-Token"]=self.csrf
        connection.request(method or ("POST" if body is not None else "GET"),path,
            json.dumps(body) if body is not None else None,headers)
        response=connection.getresponse();data=response.read();status=response.status
        cookie=response.getheader("Set-Cookie");connection.close()
        try:value=json.loads(data)
        except ValueError:value=data.decode()
        return status,value,cookie
    def login(self):
        code,value,cookie=self.request("/api/session",{"credential":"synthetic-local-only"})
        self.assertEqual(code,200);self.cookie=cookie.split(";")[0];self.csrf=value["csrf_token"]
    def binding(self, approval):
        approval["protocol"].update({"candidate_snapshot_id":"candidate-snapshot-fixture",
            "candidate_record_sha256":"a"*64,"mutation_digest_sha256":"b"*64,
            "managed_material_record_sha256":"a"*64,"authorized_scope_sha256":"c"*64})
        return approval
    def pending(self):
        approval=self.binding(typed_approval(METHOD,{"threadId":"fixture-thread","turnId":"fixture-turn",
            "itemId":"fixture-action","startedAtMs":1,"command":"fixture marker only","cwd":str(self.root),
            "availableDecisions":["accept","decline","cancel"]},campaign_id=self.campaign_id,
            invocation_id=self.invocation_id,worker={"worker_id":"fixture-worker","role":"builder"},process_id=os.getpid()))
        record=self.campaign.require_tanner(self.campaign_id,invocation_id=self.invocation_id,
            worker=approval["worker"],kind=approval["kind"],blocked_action=approval["blocked_action"],
            why_required=approval["why_required"],requested_authority=approval["requested_authority"],
            protocol_binding=approval["protocol"],expires_in_seconds=30,
            expiration_reason="Exact bounded synthetic process window.",
            expiration_effect="No fixture action after expiration.",can_request_again=False,work_lost=False)
        return self.campaign.attention_store.lifecycle(record["needs_tanner"]["attention_id"])["event"]
    def decision_path(self,event):
        return "/api/development/codex-campaigns/"+self.campaign_id+"/attention/"+event["attention_id"]+"/decision"
    def test_login_read_only_surface_and_csrf(self):
        code,html,_=self.request("/");self.assertEqual(code,200);self.assertIn('id="login"',html)
        self.assertIn("FAWKES MANAGED DEVELOPMENT CONSOLE",html)
        self.assertNotIn("Not deployed",html)
        self.assertEqual(self.request("/api/session",{"credential":"wrong"})[0],401)
        self.assertEqual(self.request("/api/development/dev-console")[0],401)
        self.login()
        self.assertEqual(self.request("/api/session/console-csrf",{})[1]["csrf_token"],self.csrf)
        self.assertEqual(self.request("/api/session/console-csrf",{},auth=False)[0],401)
        self.assertEqual(self.request("/api/session/console-csrf",{},origin=False)[0],403)
        for path in ("/api/chat","/api/development/codex-campaigns","/api/development/advance","/api/git"):
            self.assertEqual(self.request(path,{})[0],405)
        for path in ("/dev-console","/dev-console/console.js","/native-attention.js","/attention-binding.js"):
            self.assertEqual(self.request(path)[0],200)
        from tests.test_dev_console_projection import _repository_fixture
        with patch.object(self.service,"development_console_repository_projection",return_value=_repository_fixture()):
            status,projection,_=self.request("/api/development/dev-console")
        self.assertEqual(status,200,projection);self.assertFalse(projection["creates_authority"])
        event=self.pending();payload={"choice":"deny","identity":self.campaign.attention_store._authority_binding(event)}
        self.assertEqual(self.request(self.decision_path(event),payload,csrf=False)[0],403)
        self.assertEqual(self.request(self.decision_path(event),payload,auth=False)[0],403)
        self.assertEqual(self.request(self.decision_path(event),payload,origin=False)[0],403)
        self.assertEqual(self.request(self.decision_path(event),payload)[0],200)
        self.assertEqual(self.fixture.builder_payloads,[]);self.assertEqual(self.fixture.applications,[])
    def test_every_identity_mutation_omission_and_replay(self):
        self.login();event=self.pending();identity=self.campaign.attention_store._authority_binding(event)
        for key in identity:
            with self.subTest(key=key):
                omitted=dict(identity);omitted.pop(key)
                self.assertEqual(self.request(self.decision_path(event),{"choice":"approve_once","identity":omitted})[0],403)
                mutated={**identity,key:"neighbor"}
                self.assertEqual(self.request(self.decision_path(event),{"choice":"approve_once","identity":mutated})[0],403)
        response=self.request(self.decision_path(event),{"choice":"deny","identity":identity})
        self.assertEqual(response[0],200);self.assertFalse(response[1]["decision"]["creates_authority"])
        self.assertEqual(response[1]["decision"]["campaign_publication"]["state"],"published")
        self.assertNotEqual(self.request(self.decision_path(event),{"choice":"approve_once","identity":identity})[0],200)
    def test_two_clients_race_has_one_terminal_choice(self):
        self.login();event=self.pending();barrier=threading.Barrier(3);statuses=[]
        def submit(choice):
            barrier.wait()
            statuses.append(self.request(self.decision_path(event),{"choice":choice,
                "identity":self.campaign.attention_store._authority_binding(event)})[0])
        threads=[threading.Thread(target=submit,args=(choice,)) for choice in ("approve_once","deny")]
        for t in threads:t.start()
        barrier.wait()
        for t in threads:t.join(5)
        self.assertEqual(statuses.count(200),1)
        result=self.campaign.attention_store.lifecycle(event["attention_id"])
        if result["decision"]["choice"]=="approve_once":
            d=result["decision"]
            self.campaign.attention_store.consume_approve_once(d["decision_id"],attention_id=event["attention_id"],
                invocation_id=self.invocation_id,protocol_binding_sha256=event["protocol_binding_sha256"],
                approved_action_sha256=event["protocol_binding"]["approved_action_sha256"])
            self.campaign.attention_store.finish_live_action(d["decision_id"],status="failed")
    def _native_roundtrip(self,choice):
        self.login();completed=[];errors=[];child=[]
        def popen(_command,**kwargs):
            p=subprocess.Popen([sys.executable,str(Path(__file__).parent/"fixtures"/"pi_native_appserver_child.py"),str(self.root)],**kwargs)
            child.append(p);return p
        def handler(approval,**kwargs):
            return self.campaign._handle_typed_approval(self.binding(approval),**kwargs)
        def run():
            try:completed.append(LocalTransport(popen=popen,timeout_seconds=10,decision_timeout_seconds=20).run(
                cwd=self.root,prompt="LOCAL FIXTURE ONLY",output_schema={"type":"object"},
                output_path=self.root/"fixture-output.json",sandbox="workspace-write",
                campaign_id=self.campaign_id,invocation_id=self.invocation_id,
                worker={"worker_id":"fixture-worker","role":"builder"},environment=dict(os.environ),
                approval_handler=handler,progress_handler=self.campaign.record_managed_worker_activity))
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=run);thread.start()
        event=None
        for _ in range(300):
            items=self.campaign.attention_store.projection(pending_only=True)
            if items:
                event=self.campaign.attention_store.lifecycle(items[0]["attention_id"])["event"];break
            if errors:break
            threading.Event().wait(.01)
        self.assertIsNotNone(event,str(errors));self.assertFalse((self.root/"fixture-action-once").exists())
        self.assertEqual(self.campaign.managed_worker_activity_projection(self.campaign_id)[0]["state"],"waiting")
        status,response,_=self.request(self.decision_path(event),{"choice":choice,
            "identity":self.campaign.attention_store._authority_binding(event)})
        self.assertEqual(status,200,response);thread.join(8)
        self.assertFalse(thread.is_alive())
        if choice != "approve_once":
            self.assertFalse((self.root/"fixture-action-once").exists())
            result=self.campaign.attention_store.lifecycle(event["attention_id"])
            self.assertEqual(result["decision"]["choice"],choice)
            self.assertFalse(result["decision"]["creates_authority"])
            self.assertEqual(self.campaign.store.load(self.campaign_id)["status"],
                "cancelled" if choice=="cancel_campaign" else "failed_safe")
            if choice=="cancel_campaign":
                self.assertEqual(len(errors),1);self.assertEqual(errors[0].category,"campaign_cancelled")
            else:self.assertEqual(errors,[])
            return
        self.assertEqual(errors,[])
        self.assertEqual(len(completed),1);self.assertTrue((self.root/"fixture-action-once").is_file())
        lifecycle=self.campaign.attention_store.lifecycle(event["attention_id"])
        self.assertTrue(lifecycle["decision"]["consumed"])
        self.assertEqual(lifecycle["decision"]["campaign_publication"]["state"],"published")
        self.assertEqual(lifecycle["decision"]["lifecycle_state"],"completed")
        self.assertNotEqual(self.request(self.decision_path(event),{"choice":"approve_once",
            "identity":self.campaign.attention_store._authority_binding(event)})[0],200)
        activity=self.campaign.managed_worker_activity_projection(self.campaign_id)[0]
        self.assertEqual(activity["state"],"completed")
        self.assertEqual(len({e["event_id"] for e in activity["events"]}),len(activity["events"]))
        self.assertIn("Reading the harmless local fixture.",str(activity))
        self.assertNotIn("HIDDEN-MUST-NOT-PROJECT",str(activity))
        from src.runtime.codex_development_campaign import CodexDevelopmentCampaign
        restored=CodexDevelopmentCampaign(self.campaign.instance_id,root=self.root/"campaigns",
            runtime_state_root=self.root/"runtime")
        self.assertEqual(restored.managed_worker_activity_projection(self.campaign_id),[activity])
        self.assertEqual(self.fixture.builder_payloads,[]);self.assertEqual(self.fixture.applications,[])
    def test_real_stdio_transport_http_approve_once_activity_and_restart(self):
        self._native_roundtrip("approve_once")
    def test_real_stdio_deny_prevents_action(self):
        self._native_roundtrip("deny")
    def test_real_stdio_cancel_ends_exact_campaign(self):
        self._native_roundtrip("cancel_campaign")
    def test_expired_request_cannot_decide(self):
        from datetime import timedelta
        self.login();event=self.pending()
        class Future(datetime):
            @classmethod
            def now(cls,tz=None):return datetime.now(timezone.utc)+timedelta(seconds=90)
        with patch("src.runtime.development_attention.datetime",Future):
            status,value,_=self.request(self.decision_path(event),{"choice":"approve_once",
                "identity":self.campaign.attention_store._authority_binding(event)})
        self.assertNotEqual(status,200)
        self.assertIsNone(self.campaign.attention_store.lifecycle(event["attention_id"])["decision"])
    def test_unpublished_decision_cannot_be_consumed_and_closes(self):
        event=self.pending();store=self.campaign.attention_store
        result=store.decide(event["attention_id"],"approve_once",authenticated_rider=True,
            expected_identity=store._authority_binding(event))
        decision=result["decision"];self.assertFalse(decision["creates_authority"])
        with self.assertRaises(PermissionError):
            store.consume_approve_once(decision["decision_id"],attention_id=event["attention_id"],
                invocation_id=self.invocation_id,protocol_binding_sha256=event["protocol_binding_sha256"],
                approved_action_sha256=event["protocol_binding"]["approved_action_sha256"])
        closed=store.fail_unpublished_review_decision(decision["decision_id"],
            attention_id=event["attention_id"],campaign_id=self.campaign_id,reason="synthetic publication failure")
        self.assertEqual(closed["lifecycle_state"],"failed_safe");self.assertFalse(closed["creates_authority"])
    def test_activity_dedup_current_process_and_no_campaign_revision_mutation(self):
        record=self.campaign.store.load(self.campaign_id)
        event={"campaign_id":self.campaign_id,"invocation_id":self.invocation_id,"event_id":"fixture-event",
            "created_at":datetime.now(timezone.utc).isoformat(),"kind":"progress","state":"running",
            "public_message":"Reading source","worker":{"worker_id":"fixture-worker"},"process_id":os.getpid()}
        self.campaign.record_managed_worker_activity(event);self.campaign.record_managed_worker_activity(event)
        self.assertEqual(record,self.campaign.store.load(self.campaign_id))
        self.assertEqual(len(self.campaign.managed_worker_activity_projection(self.campaign_id)[0]["events"]),1)
        with self.assertRaises(PermissionError):self.campaign.record_managed_worker_activity({**event,"invocation_id":"neighbor-appserver"})
        with patch("src.runtime.development_attention._linux_process_identity",return_value=None):
            self.assertEqual(self.campaign.managed_worker_activity_projection(self.campaign_id)[0]["state"],"disconnected")
    def test_public_progress_redacts_complete_credentials_before_durable_retention(self):
        from src.runtime.codex_app_server import _safe
        samples=['Authorization: Bearer SYNTHETIC_REVIEW_MARKER',
            '{"token":"SYNTHETIC_REVIEW_MARKER"}',
            "password='SYNTHETIC_REVIEW_MARKER with spaces'",
            'API-key = "SYNTHETIC_REVIEW_MARKER\\\"quoted"',
            "Authorization: Basic SYNTHETIC_REVIEW_MARKER"]
        for index,text in enumerate(samples):
            self.assertNotIn('SYNTHETIC_REVIEW_MARKER',_safe(text))
            self.campaign.record_managed_worker_activity({"campaign_id":self.campaign_id,
                "invocation_id":self.invocation_id,"event_id":"redaction-"+str(index),
                "created_at":datetime.now(timezone.utc).isoformat(),"kind":"progress","state":"running",
                "public_message":text,"worker":{"worker_id":"fixture-worker"},"process_id":os.getpid()})
        records=list((self.campaign.store.root/'.managed-activity').glob('*.json'))
        self.assertTrue(records)
        for path in records:self.assertNotIn('SYNTHETIC_REVIEW_MARKER',path.read_text())
        self.assertNotIn('SYNTHETIC_REVIEW_MARKER',json.dumps(self.campaign.managed_worker_activity_projection(self.campaign_id)))
        self.assertEqual(_safe('Reading the authorized files.'),'Reading the authorized files.')
    def test_large_unicode_progress_keeps_attention_projection_bounded(self):
        from tests.test_dev_console_projection import _repository_fixture
        self.login()
        for index in range(64):
            self.campaign.record_managed_worker_activity({"campaign_id":self.campaign_id,
                "invocation_id":self.invocation_id,"event_id":"large-"+str(index),
                "created_at":datetime.now(timezone.utc).isoformat(),"kind":"progress","state":"running",
                "public_message":"Public progress "+chr(0x1f600)*2000,
                "worker":{"worker_id":"fixture-worker"},"process_id":os.getpid()})
        with patch.object(self.service,"development_console_repository_projection",return_value=_repository_fixture()):
            status,value,_=self.request("/api/development/dev-console")
        self.assertEqual(status,200,value)
        self.assertGreater(value["managed_activity_window"]["omitted_events"],0)
        self.assertLess(len(json.dumps(value).encode()),256000)
        retained=self.campaign.managed_worker_activity_projection(self.campaign_id)[0]["events"]
        self.assertEqual(len(retained),64)
        self.assertTrue(all(len(item["public_message"].encode())<=2048 for item in retained))

class InstalledProtocolSubsetTests(unittest.TestCase):
    def test_managed_worker_profile_is_explicit_and_not_the_reviewer_profile(self):
        self.assertNotEqual(MANAGED_PROTOCOL_VERSION, REVIEWER_PROTOCOL_VERSION)
        self.assertNotEqual(MANAGED_PROTOCOL_VERSION, PROTOCOL_VERSION)
        observed = {}
        class FixtureTransport:
            def __init__(self, **kwargs):
                observed["protocol_version"] = kwargs["protocol_version"]
            def run(self, **kwargs):
                observed["run"] = kwargs
                return subprocess.CompletedProcess([], 0, "{}", "")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema = root / "schema.json"; schema.write_text('{"type":"object"}')
            output = root / "output.json"
            runner = exec_compatible_app_server_runner(campaign_id="managed-campaign",
                invocation_id="managed-invocation", worker={"worker_id":"managed-worker"},
                approval_handler=lambda *_a, **_k: None)
            runner.bind_attention_context(lambda: {"candidate_snapshot_id":"candidate-snapshot-fixture"})
            command = ["codex", "exec", "--cd", str(root), "--sandbox", "workspace-write",
                "--output-schema", str(schema), "--output-last-message", str(output), "-"]
            with patch("src.runtime.codex_app_server.CodexAppServerTransport", FixtureTransport):
                result = runner(command, prompt="synthetic", environment={}, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(observed["protocol_version"], MANAGED_PROTOCOL_VERSION)
        self.assertEqual(observed["run"]["sandbox"], "workspace-write")
        self.assertEqual(observed["run"]["campaign_id"], "managed-campaign")

    def test_native_context_is_produced_from_actual_disposable_material(self):
        from tests.test_autonomy_production_transports import AutonomyProductionTransportTests,FakeWriteCodex
        from src.runtime.disposable_verifier import candidate_manifest
        from src.runtime.worker_exchange import _digest
        fixture=AutonomyProductionTransportTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        owner=self
        class ContextRunner(FakeWriteCodex):
            def bind_attention_context(self, reader):self.reader=reader
            def __call__(self,command,**kwargs):
                if command[-1:] == ["-"]:
                    self.before=self.reader()
                    execution=Path(command[command.index("--cd")+1])
                    owner.assertEqual(self.before["candidate_record_sha256"],_digest(candidate_manifest(execution)))
                    result=super().__call__(command,**kwargs)
                    self.after=self.reader()
                    owner.assertNotEqual(self.before["candidate_snapshot_id"],self.after["candidate_snapshot_id"])
                    owner.assertEqual(self.after["candidate_record_sha256"],_digest(candidate_manifest(execution)))
                    (execution/"outside-scope.txt").write_text("synthetic drift")
                    with owner.assertRaises(PermissionError):self.reader()
                    (execution/"outside-scope.txt").unlink()
                    return result
                return super().__call__(command,**kwargs)
        runner=ContextRunner(fixture.workspace)
        result=fixture.invoke(fake=runner,defer_authoritative_apply=True)
        self.assertEqual(result["status"],"delivered",result.get("failure_reason"))
        self.assertEqual((fixture.workspace/"src/allowed.py").read_text(),"before\n")
        self.assertEqual(runner.after["managed_scope"],fixture.scopes)
    def test_native_console_dom_boundaries(self):
        result=subprocess.run(["node","tests/js/pi_attention_harness.js"],
            cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("pi-native-attention-dom-ok",result.stdout)
    def test_profiles_stdin_undisclosed_file_changes_and_session_grants_never_become_once(self):
        for method,params in (("item/permissions/requestApproval",{}),("item/fileChange/requestApproval",{}),
            ("item/fileChange/requestApproval",{"grantRoot":"/somewhere"}),(METHOD,{"kind":"writeStdin","command":"input"}),
            (METHOD,{"command":"true","availableDecisions":["acceptForSession","cancel"]})):
            with self.subTest(method=method,params=params):
                self.assertNotIn("approve_once",bounded_decisions(method,params)[0])
                with self.assertRaises(OSError):approval_response(method,"approve_once",params)
        self.assertEqual(approval_response("item/permissions/requestApproval","deny",{}),{"permissions":{},"scope":"turn"})
        self.assertEqual(bounded_decisions("unknown",{})[0],[])

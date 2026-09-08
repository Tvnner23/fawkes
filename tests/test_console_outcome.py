import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from src.runtime.console_outcome import completed_objective, blocked_objective_identity
from src.runtime.autonomy_supervision import campaign_console_reporting
from src.app.server import _console_jobs, _console_reporting, _console_campaigns


def record():
    r={"campaign_id":"objective-one","status":"succeeded","objective":"Complete the requested fixture",
       "acceptance_condition_ids":["review","deployment","physical"],
       "acceptance_satisfied":["review","deployment","physical"],
       "recovery_references":[],"events":[], "record_sha256":"a"*64}
    r["events"]=[{"event_id":"closeout-one","kind":"console_objective_closed",
        "created_at":"2026-09-14T12:00:00+00:00","detail":{
        "scope":"whole_user_objective","campaign_id":r["campaign_id"],
        "objective_sha256":hashlib.sha256(r["objective"].encode()).hexdigest(),
        "remaining_authorized_work":False,"result":"The fixture outcome and all its gates were recorded.",
        "gates":[{"condition_id":c,"status":"satisfied","reference_id":"fixture-"+c,"sha256":"b"*64}
                 for c in r["acceptance_condition_ids"]]}}]
    return r


class OutcomeTests(unittest.TestCase):
    def test_explicit_complete_closeout_and_projection(self):
        r=record();before=copy.deepcopy(r)
        self.assertEqual(completed_objective(r)["gate_count"],3)
        reporting=_console_reporting(campaign_console_reporting(r))
        campaign={**r,"console_reporting":reporting,"activity":[]}
        job=_console_jobs([campaign],[])[0]
        self.assertEqual(job["objective_closeout"]["result"],r["events"][0]["detail"]["result"])
        self.assertIn("ready for your next task",job["next"])
        self.assertEqual(r,before)

    def test_later_descendant_material_invalidates_old_closeout_visible_and_hidden(self):
        for hidden in (False, True):
            for boundary in ('wrapper', 'event'):
                root,others,make=self.window_fixture()
                child=make('existing-child',created='2026-09-14T10:00:00Z',parents=[root['campaign_id']])
                if boundary=='wrapper':child['updated_at']='2026-09-14T13:00:00Z'
                else:child['live_activity']['activity']=[{'event_id':'later-result','kind':'builder_return_retained','created_at':'2026-09-14T13:00:00Z','detail':{}}]
                source={'campaigns':[root,*(others if hidden else []),child]};before=copy.deepcopy(source)
                jobs=_console_jobs(_console_campaigns(source),[])
                job=next(j for j in jobs if j['job_id']==root['campaign_id'])
                self.assertIsNone(job['objective_closeout']);self.assertNotIn('ready for your next task',job['next']);self.assertEqual(source,before)

    def test_descendant_material_unknown_and_fresh_explicit_closeout(self):
        root,others,make=self.window_fixture();child=make('child',parents=[root['campaign_id']])
        for value in (None,'bad-time','2026-09-14T13:00:00Z'):
            child['updated_at']=value
            job=_console_jobs(_console_campaigns({'campaigns':[root,child]}),[])[0]
            self.assertIsNone(job['objective_closeout'])
        fresh=record();fresh['events'][0]['created_at']='2026-09-14T14:00:00Z'
        root['console_reporting']=campaign_console_reporting(fresh)
        job=_console_jobs(_console_campaigns({'campaigns':[root,*others,child]}),[])[0]
        self.assertIsNotNone(job['objective_closeout'])

    def test_blocker_identity_full_material_event_and_reload(self):
        r=record();r['status']='tanner_escalation';r['needs_tanner']={'decision_needed':'x'*600+'one'}
        first=blocked_objective_identity(r)
        self.assertEqual(first,blocked_objective_identity(json.loads(json.dumps(r))))
        r['record_sha256']='c'*64;r['updated_at']='2026-09-14T13:00:00Z'
        self.assertEqual(first,blocked_objective_identity(r))
        r['events'].append({'event_id':'second-blocker','kind':'reviewer_blocked'})
        self.assertNotEqual(first,blocked_objective_identity(r))
        second=blocked_objective_identity(r);r['needs_tanner']['decision_needed']='x'*600+'two'
        self.assertNotEqual(second,blocked_objective_identity(r))
        projected=_console_reporting(campaign_console_reporting(r))
        self.assertEqual(projected['blocker_identity'],blocked_objective_identity(r))
        job=_console_jobs([{**r,'console_reporting':projected,'activity':[]}],[])[0]
        self.assertEqual(job['blocker_identity'],projected['blocker_identity'])

    def test_exact_attention_identity_survives_later_same_request_events(self):
        r=record();r['needs_tanner']={'attention_id':'attention-'+'a'*64,'decision_needed':'Same words'}
        first=blocked_objective_identity(r);r['events'].append({'event_id':'reminder','kind':'reminder'})
        self.assertEqual(first,blocked_objective_identity(r))
        r['needs_tanner']['attention_id']='attention-'+'b'*64
        self.assertNotEqual(first,blocked_objective_identity(r))
        r['needs_tanner']={'decision_needed':'Unidentified blocker'};r['events']=[]
        self.assertIsNone(blocked_objective_identity(r))

    def test_plain_success_final_turn_or_helper_is_not_whole_task_completion(self):
        for change in [{"events":[]},{"parent_campaign_id":"whole-job"},
                       {"recovery_references":[{"reference_type":"parent_campaign","reference_id":"whole-job"}]}]:
            with self.subTest(change=change):
                self.assertIsNone(completed_objective({**record(),**change}))

    def test_review_pending_failed_expired_waiting_not_complete(self):
        for status in ["failed_safe","expired","tanner_escalation","ready","builder_in_progress",
                       "awaiting_independent_review","reviewed_application_completed"]:
            with self.subTest(status=status):
                self.assertIsNone(completed_objective({**record(),"status":status}))
        self.assertIsNone(completed_objective({**record(),"needs_tanner":{"decision_needed":"Actual gate"}}))

    def test_incomplete_or_duplicate_gates_rejected(self):
        for kind in ["missing","duplicate","unverified","bad_digest","unsatisfied"]:
            r=record();g=r["events"][0]["detail"]["gates"]
            if kind=="missing":g.pop()
            if kind=="duplicate":g[2]=g[1].copy()
            if kind=="unverified":g[0]["status"]="unknown"
            if kind=="bad_digest":g[0]["sha256"]="not a digest"
            if kind=="unsatisfied":r["acceptance_satisfied"].pop()
            with self.subTest(kind=kind):self.assertIsNone(completed_objective(r))

    def test_wrong_scope_identity_objective_remaining_work_or_timestamp(self):
        for key,value in [("scope","review_child"),("campaign_id","another-objective"),
                          ("objective_sha256","c"*64),("remaining_authorized_work",True),
                          ("remaining_authorized_work",None)]:
            r=record();r["events"][0]["detail"][key]=value
            with self.subTest(key=key,value=value):self.assertIsNone(completed_objective(r))
        r=record();r["events"][0]["created_at"]="not a timestamp"
        self.assertIsNone(completed_objective(r))

    def test_later_lifecycle_invalidates_closeout_without_erasing_history(self):
        r=record();r["events"].append({"kind":"execution_resumed"})
        self.assertIsNone(completed_objective(r))
        self.assertEqual(len(r["events"]),2)

    def test_storage_roundtrip_and_unicode_bound(self):
        r=record();self.assertEqual(completed_objective(r),completed_objective(json.loads(json.dumps(r))))
        for value in ["🔥"*301,"\0"*201,"",None,[]]:
            r["events"][0]["detail"]["result"]=value
            with self.subTest(value_type=type(value).__name__):self.assertIsNone(completed_objective(r))

    def test_needs_you_keeps_actual_decision_separate(self):
        r=record();r["status"]="tanner_escalation";r["needs_tanner"]={"decision_needed":"Renew only the exact expired recovery ticket."}
        r["console_reporting"]=_console_reporting(campaign_console_reporting(r));r["activity"]=[]
        job=_console_jobs([r],[])[0]
        self.assertEqual(job["state"],"needs_you");self.assertIsNone(job["objective_closeout"])
        self.assertEqual(job["next"],r["needs_tanner"]["decision_needed"])

    def test_failed_terminal_campaign_keeps_explicit_required_decision(self):
        for status in ('failed_safe','expired','cancelled','denied','succeeded'):
            r=record();r['status']=status;r['needs_tanner']={'reason':'duration_expired','decision_needed':'Create a new exact request; the old failure remains closed.'}
            r['console_reporting']=_console_reporting(campaign_console_reporting(r));r['activity']=[]
            before=copy.deepcopy(r);job=_console_jobs([r],[])[0]
            self.assertEqual(job['state'],'needs_you');self.assertEqual(job['recorded_status'],status)
            self.assertTrue(job['historical']);self.assertEqual(job['next'],r['needs_tanner']['decision_needed'])
            self.assertIsNone(job['objective_closeout']);self.assertEqual(job['blocker_identity'],blocked_objective_identity(r))
            self.assertIn(status,job['current_step']);self.assertEqual(r,before)
        r['status']='failed_safe';r['needs_tanner']={'reason':'old failure','decision_needed':'  '}
        self.assertEqual(_console_jobs([r],[])[0]['state'],'failed')

    def test_new_or_open_child_cannot_be_superseded_by_root_closeout(self):
        for status,created in [("awaiting_independent_review","2026-09-14T11:00:00Z"),
                               ("succeeded","2026-09-14T13:00:00Z")]:
            r=record();r["console_reporting"]=_console_reporting(campaign_console_reporting(r));r["activity"]=[]
            child={**r,"campaign_id":"child","status":status,"created_at":created,
                   "console_reporting":{"parent_campaign_id":r["campaign_id"]}}
            jobs=_console_jobs([r,child],[])
            root=next(j for j in jobs if j["job_id"]==r["campaign_id"])
            self.assertIsNone(root["objective_closeout"])
            self.assertNotIn("ready for your next task",root["next"])

    def test_javascript_lifecycle_touch_and_focus_contract(self):
        root=Path(__file__).resolve().parents[1]
        p=subprocess.run(["node","tests/js/console_outcome_harness.js"],cwd=root,capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_legacy_child_lineage_survives_actual_presentation_shape(self):
        r=record();r['console_reporting']=_console_reporting(campaign_console_reporting(r));r['activity']=[]
        for status in ['historical_contract_unavailable','integrity_unavailable']:
            legacy={'campaign_id':'legacy-child','status':status,'objective':'Retained child',
                    'live_activity':{'campaign_id':'legacy-child','status':status,'objective':'Retained child',
                        'iteration':0,'maximum_iterations':1,'cancelled':False,'current_stage':'historical_evidence_only',
                        'builder':{},'reviewer':{},'needs_tanner':None,
                        'activity':[], 'recovery_references':[{'reference_type':'parent_campaign','reference_id':r['campaign_id']}]}}
            projected=_console_campaigns({'campaigns':[legacy]})
            jobs=_console_jobs([r,*projected],[])
            root=next(j for j in jobs if j['job_id']==r['campaign_id'])
            child=next(j for j in jobs if j['job_id']=='legacy-child')
            self.assertEqual(child['parent_campaign_id'],r['campaign_id'])
            self.assertEqual(child['state'],'unknown')
            self.assertIsNone(root['objective_closeout']);self.assertNotIn('ready for your next task',root['next'])

    def test_actionable_attention_precedes_recorded_success_and_closeout(self):
        for has_closeout in [False,True]:
            r=record()
            if not has_closeout:r['events']=[]
            r['needs_tanner']={'decision_needed':'Resolve the exact pending operation.'}
            # A retained closeout may predate new actionable Attention.
            clean={k:v for k,v in r.items() if k!='needs_tanner'}
            r['console_reporting']=_console_reporting(campaign_console_reporting(clean));r['activity']=[]
            job=_console_jobs([r],[{'campaign_id':r['campaign_id'],'actionable':True}])[0]
            self.assertEqual(job['state'],'needs_you')
            self.assertEqual(job['next'],r['needs_tanner']['decision_needed'])
            self.assertIsNone(job['objective_closeout'])
            del r['needs_tanner']
            job=_console_jobs([r],[{'campaign_id':r['campaign_id'],'actionable':True}])[0]
            self.assertIn('Attention request',job['next']);self.assertIsNone(job['objective_closeout'])

    def test_historical_child_with_new_actionable_request_blocks_root(self):
        r=record();r['console_reporting']=_console_reporting(campaign_console_reporting(r));r['activity']=[]
        child={**r,'campaign_id':'child','created_at':'2026-09-14T10:00:00Z',
               'console_reporting':{'parent_campaign_id':r['campaign_id']}}
        jobs=_console_jobs([r,child],[{'campaign_id':'child','actionable':True}])
        root=next(j for j in jobs if j['job_id']==r['campaign_id'])
        waiting=next(j for j in jobs if j['job_id']=='child')
        self.assertIsNone(root['objective_closeout']);self.assertEqual(waiting['state'],'needs_you')
        self.assertIn('Waiting for the recorded decision',waiting['current_step'])

    def window_fixture(self):
        root=record()
        def wrapper(identity,status='succeeded',created='2026-09-13T10:00:00Z',parents=()):
            return {'campaign_id':identity,'created_at':created,'updated_at':created,
                    'live_activity':{'campaign_id':identity,'status':status,'objective':identity,
                     'iteration':0,'maximum_iterations':1,'cancelled':False,'current_stage':'historical_evidence_only',
                     'builder':{},'reviewer':{},'needs_tanner':None,'activity':[],
                     'recovery_references':[{'reference_type':'parent_campaign','reference_id':p} for p in parents]}}
        first=wrapper(root['campaign_id'],created='2026-09-14T11:00:00Z')
        first['console_reporting']=campaign_console_reporting(root)
        return first,[wrapper('unrelated-'+str(i)) for i in range(31)],wrapper

    def test_hidden_legacy_child_blocks_completion_without_expanding_display(self):
        root,others,make=self.window_fixture()
        child=make('legacy-child','historical_contract_unavailable',None,[root['campaign_id']])
        source={'campaigns':[root,*others,child]};before=copy.deepcopy(source)
        projected=_console_campaigns(source)
        self.assertEqual(len(projected),32)
        job=next(j for j in _console_jobs(projected,[]) if j['job_id']==root['campaign_id'])
        self.assertEqual(job['state'],'unknown');self.assertIsNone(job['objective_closeout'])
        self.assertNotIn('ready for your next task',job['next']);self.assertEqual(source,before)
        self.assertLess(len(json.dumps(projected).encode()),512000)

    def test_unrelated_history_does_not_disable_supported_completion(self):
        root,others,make=self.window_fixture()
        projected=_console_campaigns({'campaigns':[root,*others,make('unrelated-extra')]})
        job=next(j for j in _console_jobs(projected,[]) if j['job_id']==root['campaign_id'])
        self.assertIsNotNone(job['objective_closeout']);self.assertEqual(job['state'],'done')

    def test_full_parent_references_and_hidden_descendant_chain_are_checked(self):
        root,others,make=self.window_fixture()
        middle=make('middle',parents=[root['campaign_id']])
        child=make('hidden-child','historical_contract_unavailable',None,['middle'])
        child['live_activity']['recovery_references'][:0]=[{'reference_type':'unrelated','reference_id':str(i)} for i in range(17)]
        projected=_console_campaigns({'campaigns':[root,*others,middle,child]})
        job=next(j for j in _console_jobs(projected,[]) if j['job_id']==root['campaign_id'])
        self.assertIsNone(job['objective_closeout'])

    def test_pending_attention_outside_display_window_invalidates_hidden_child(self):
        root,others,make=self.window_fixture();child=make('finished-child',parents=[root['campaign_id']])
        attention={'attention':[{'campaign_id':'elsewhere-'+str(i),'actionable':False} for i in range(80)]+[{'campaign_id':'finished-child','actionable':True}]}
        projected=_console_campaigns({'campaigns':[root,*others,child]},attention)
        job=next(j for j in _console_jobs(projected,[]) if j['job_id']==root['campaign_id'])
        self.assertIsNone(job['objective_closeout']);self.assertEqual(job['state'],'unknown')

    def test_unavailable_or_duplicate_lineage_cannot_prove_completion(self):
        root,others,make=self.window_fixture()
        bad=make('unknown-source');bad['live_activity']['recovery_references']={}
        for extra in [bad,copy.deepcopy(root),make('bad-integrity','integrity_unavailable')]:
            projected=_console_campaigns({'campaigns':[root,*others,extra]})
            job=next(j for j in _console_jobs(projected,[]) if j['job_id']==root['campaign_id'])
            self.assertIsNone(job['objective_closeout'])

if __name__=="__main__":unittest.main()

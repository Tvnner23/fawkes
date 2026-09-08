"""Selection, durable export and native-turn timing regressions (no provider)."""
import copy
import json
import tempfile
import unittest
import subprocess
from pathlib import Path
from src.runtime.console_observation import ordered_campaigns, primary_campaign_id, execution_turns
from src.app.server import _console_jobs, ConsoleUpdateStore
from tests.test_console_job_timing import record, projected


def transition(kind, second, state="running", turn="turn-one", event_id=None):
    return {"event_id": event_id or f"{turn}-{kind}-{second}", "kind": kind, "state": state,
        "created_at": f"2026-09-11T03:{second//60:02}:{second%60:02}+00:00",
        "thread_id": "thread-one", "turn_id": turn}


def observation(events, role="worker", state="completed", verified=None):
    return {"invocation_id": role+"-invocation", "role": role, "state": state,
        "timing_events": events, "verified_at": verified, "last_verified_at": events[-1].get("created_at")}


class ConsoleObservationTests(unittest.TestCase):
    def test_actual_javascript_observation_and_clock_paths(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','tests/js/console_observation_harness.js'],cwd=root,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_non_adjacent_old_trial_expiry_cannot_overtake_new_objective(self):
        rows=[]
        for identity,created,status,updated in [
            ("old-trial", "2026-09-11T01:00:00Z", "awaiting_independent_review", "2026-09-11T06:02:44Z"),
            ("repository-batch", "2026-09-11T03:00:00Z", "succeeded", "2026-09-11T03:50:27Z"),
            ("current-console", "2026-09-11T04:00:00Z", "failed_safe", "2026-09-11T05:08:13Z")]:
            source=record(status);source.update(campaign_id=identity,created_at=created,updated_at=updated)
            rows.append(projected(source))
        before=copy.deepcopy(rows)
        for state in ("succeeded","failed_safe","awaiting_independent_review","tanner_escalation"):
            rows[-1]["status"]=state
            self.assertEqual(primary_campaign_id(rows), "current-console")
            jobs=_console_jobs(rows,[])
            self.assertEqual(jobs[0]["job_id"],"current-console")
            self.assertTrue(jobs[0]["is_current_objective"])
            self.assertEqual({j["job_id"] for j in jobs},{"old-trial","repository-batch","current-console"})
        self.assertEqual(rows[:2],before[:2])

    def test_known_parent_not_child_completion_selects_parent(self):
        rows=[{"campaign_id":"parent","created_at":"2026-09-11T03:00:00Z"},
              {"campaign_id":"child","created_at":"2026-09-11T04:00:00Z",
               "console_reporting":{"parent_campaign_id":"parent"}}]
        self.assertEqual(primary_campaign_id(rows),"parent")
        rows[1]["console_reporting"]["parent_campaign_id"]="missing"
        self.assertEqual(primary_campaign_id(rows),"child")

    def test_worker_review_worker_turns_pause_and_resume_without_reset(self):
        events=[transition("turn_started",0),transition("permission_wait",10,"waiting"),
            transition("permission_wait",10,"waiting"),transition("permission_result",40),
            transition("final_result",65,"completed"),transition("turn_started",120,turn="turn-two"),
            transition("final_result",140,"completed",turn="turn-two")]
        review=[transition("turn_started",70,turn="review-one"),transition("final_result",110,"completed",turn="review-one")]
        values=[observation(events),observation(review,"reviewer")]
        before=copy.deepcopy(values)
        result=execution_turns(values,observed_at="2026-09-11T03:10:00Z")
        self.assertEqual([t["role"] for t in result],["worker","reviewer","worker"])
        self.assertEqual([t["active_seconds"] for t in result],[35,40,20])
        self.assertEqual([t["waiting_seconds"] for t in result],[30,0,0])
        self.assertEqual(result,execution_turns(json.loads(json.dumps(values)),observed_at="2026-09-12T03:10:00Z"))
        self.assertEqual(values,before)

    def test_zero_start_wait_freezes_and_process_loss_is_unknown(self):
        started=transition("turn_started",0)
        value=observation([started],state="running",verified=started["created_at"])
        turn=execution_turns([value],observed_at=started["created_at"])[0]
        self.assertEqual(turn["active_seconds"],0);self.assertTrue(turn["active_verified"])
        value["timing_events"].append(transition("permission_wait",10,"waiting"))
        value.update(state="waiting",verified_at="2026-09-11T03:02:00Z")
        turn=execution_turns([value],observed_at="2026-09-11T03:02:00Z")[0]
        self.assertEqual(turn["active_seconds"],10);self.assertEqual(turn["waiting_seconds"],110)
        self.assertFalse(turn["active_verified"])
        value.update(state="disconnected",verified_at=None)
        turn=execution_turns([value],observed_at="2026-09-11T03:20:00Z")[0]
        self.assertIsNone(turn["active_seconds"]);self.assertFalse(turn["active_verified"])

    def test_queued_or_missing_turn_begin_cannot_create_clock(self):
        self.assertEqual(execution_turns([],observed_at="2026-09-11T03:10:00Z"),[])
        unknown=execution_turns([observation([transition("final_result",20,"completed")])],observed_at="2026-09-11T03:10:00Z")[0]
        self.assertIsNone(unknown['started_at']);self.assertIsNone(unknown['active_seconds'])
        self.assertTrue(unknown['history_incomplete'])
        for key in ("thread_id","turn_id","created_at"):
            event=transition("turn_started",0);event.pop(key)
            values=execution_turns([observation([event])],observed_at="2026-09-11T03:10:00Z")
            if key=='created_at':
                self.assertEqual(len(values),1);self.assertIsNone(values[0]['active_seconds'])
                self.assertTrue(values[0]['duration_incomplete'])
            else:self.assertEqual(values,[])

    def test_transport_loss_detection_is_not_a_native_terminal_boundary(self):
        for close_state in ("disconnected", "failed"):
            events=[transition("turn_started",0),transition("permission_wait",10,"waiting"),
                transition("permission_result",40),transition("transport_closed",60,close_state)]
            value=observation(events,state=close_state)
            result=execution_turns([value],observed_at="2026-09-11T03:10:00Z")[0]
            self.assertIsNone(result["ended_at"])
            self.assertIsNone(result["active_seconds"])
            self.assertIsNone(result["waiting_seconds"])
            self.assertFalse(result["active_verified"])
            self.assertEqual([part["seconds"] for part in result["segments"]],[10,30])
            self.assertEqual(result,execution_turns([value],observed_at="2026-09-12T03:10:00Z")[0])

    def test_denial_resumes_same_turn_until_actual_terminal_event(self):
        events=[transition("turn_started",0),transition("permission_wait",10,"waiting"),
            transition("permission_result",40,"failed"),transition("final_result",65,"failed")]
        result=execution_turns([observation(events,state="failed")],observed_at="2026-09-11T03:10:00Z")[0]
        self.assertEqual(result["active_seconds"],35)
        self.assertEqual(result["waiting_seconds"],30)
        self.assertEqual(result["ended_at"],"2026-09-11T03:01:05+00:00")
        self.assertEqual(result["source_event_ids"],[event["event_id"] for event in events])
        live=observation(events[:-1],state="running",verified="2026-09-11T03:00:45Z")
        pending=execution_turns([live],observed_at="2026-09-11T03:00:45Z")[0]
        self.assertEqual(pending["active_seconds"],15)
        self.assertEqual(pending["waiting_seconds"],30)
        self.assertTrue(pending["active_verified"]);self.assertIsNone(pending["ended_at"])

    def test_each_retained_history_cap_marks_campaign_totals_incomplete(self):
        from src.runtime.autonomy_supervision import campaign_console_reporting
        events=[]
        for index in range(33):
            events.extend([transition("turn_started",index*12,turn=f"turn-{index}"),
                transition("final_result",index*12+10,"completed",turn=f"turn-{index}")])
        cases=[
            [observation(events)],
            [dict(observation(events[:2]),invocation_id=f"invocation-{index}") for index in range(17)],
            [dict(observation(events[:2]),timing_history_incomplete=True)],
        ]
        for values in cases:
            original=copy.deepcopy(values)
            report=campaign_console_reporting(record(),values,observed_at="2026-09-11T03:10:00Z")
            self.assertTrue(report["timing_history_incomplete"])
            self.assertTrue(all(turn["history_incomplete"] for turn in report["turns"]))
            self.assertLessEqual(len(report["turns"]),32)
            self.assertEqual(values,original)
        complete=campaign_console_reporting(record(),[observation(events[:64])],observed_at="2026-09-11T03:10:00Z")
        self.assertFalse(complete["timing_history_incomplete"])
        self.assertEqual(sum(turn["active_seconds"] for turn in complete["turns"]),320)

    def test_snapshot_retry_recovery_preserves_identity_and_campaign(self):
        projection={"creates_authority":False,"current_campaign_id":"current", "campaigns":[{"campaign_id":"current"},{"campaign_id":"old"}],
            "jobs":[{"job_id":"current","objective":"Current requested objective","accomplished":"Verified local fix; not deployed","state":"working"}]}
        with tempfile.TemporaryDirectory() as directory:
            store=ConsoleUpdateStore(directory)
            saved=store.save(idempotency_key="valid-retry-key-12345",projection=projection,campaign_id="current")
            for pointer in (Path(directory)/"idempotency").glob("*.txt"):pointer.unlink()
            changed=copy.deepcopy(projection);changed["jobs"][0]["objective"]="New text after response loss"
            restored=ConsoleUpdateStore(directory).save(idempotency_key="valid-retry-key-12345",projection=changed,campaign_id="current")
            self.assertEqual(saved,restored)
            self.assertEqual(saved["campaign_id"],"current")
            self.assertIn("Current objective campaign: current",saved["content"])
            with self.assertRaises(ValueError):store.save(idempotency_key="valid-retry-key-12345",projection=projection,campaign_id="old")
            with self.assertRaises(ValueError):store.save(idempotency_key="another-retry-key-12345",projection=projection,campaign_id="unknown")

    def test_missing_start_preserves_unknown_turn_and_invalidates_real_js_total(self):
        from src.runtime.autonomy_supervision import campaign_console_reporting
        from src.app.server import _console_reporting
        missing=[transition('final_result',20,'completed',turn='older-missing-start')]
        complete=[transition('turn_started',30,turn='later-complete'),
                  transition('final_result',40,'completed',turn='later-complete')]
        for values in ([observation(missing+complete)],
                       [observation(missing),dict(observation(complete),invocation_id='second')],
                       [observation(missing)]):
            with self.subTest(invocations=len(values),events=len(values[0]['timing_events'])):
                original=copy.deepcopy(values)
                report=campaign_console_reporting(record(),values,observed_at='2026-09-11T03:10:00Z')
                self.assertTrue(report['timing_history_incomplete'])
                unknown=next(t for t in report['turns'] if t['turn_id']=='older-missing-start')
                self.assertIsNone(unknown['started_at']);self.assertIsNone(unknown['active_seconds'])
                self.assertEqual(unknown['ended_at'],'2026-09-11T03:00:20+00:00')
                self.assertEqual(report['turns'],execution_turns(json.loads(json.dumps(values)),observed_at='2026-09-12T03:10:00Z'))
                wire=_console_reporting(report)
                js="const a=require('./tests/js/dev_console_projection_harness.js').consoleApi;const r=JSON.parse(require('fs').readFileSync(0,'utf8'));require('assert').strictEqual(a.roleClocks({reporting:r},'live',Date.parse('2026-09-11T03:10:00Z'))[0].total,null)"
                result=subprocess.run(['node','-e',js],input=json.dumps(wire),text=True,capture_output=True,cwd=Path(__file__).resolve().parents[1],timeout=20)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(values,original)


class TimingObservationLossTests(unittest.TestCase):
    """Actual reader + canonical observation writer, isolated synthetic stores."""
    def replay(self, losses=(), *, after_commit=False, deny=False, repeats=1):
        import contextlib, os
        from unittest.mock import patch
        from src.runtime import codex_app_server as app
        from src.runtime.codex_development_campaign import CodexDevelopmentCampaign
        from tests.test_codex_reviewer_client_compatibility import Process,START,ITEM,END,APPROVAL,RESOLVED
        frames=copy.deepcopy(START)
        for index in range(repeats):
            request=copy.deepcopy(APPROVAL);request['id']=7+index
            request['params']['itemId']='action-'+str(index)
            frames.append(request)
            if not deny:
                resolved=copy.deepcopy(RESOLVED);resolved['params']['requestId']=7+index
                frames.append(resolved)
                frames.append({'method':'item/completed','params':{'threadId':'t','turnId':'u',
                    'item':{'id':'action-'+str(index),'type':'commandExecution','status':'completed'}}})
        frames+=copy.deepcopy([ITEM,END]);process=Process(frames);process.pid=os.getpid()
        with tempfile.TemporaryDirectory() as directory:
            class Store:
                root=Path(directory)
                def protected(self, _):return contextlib.nullcontext()
                def load(self, _):return {'active_builder_task_scope_id':'fixture-scope',
                    'builder':{'worker_id':'fixture-worker'}}
            def owner():
                value=object.__new__(CodexDevelopmentCampaign);value.store=Store();return value
            seen=[];reloads=[];replacement=Path.replace
            def observe(event):
                event=copy.deepcopy(event)
                second={'starting':0,'turn_started':0,'permission_wait':10,
                        'permission_result':40,'final_result':50}.get(event['kind'],45)
                event['created_at']=f'2026-09-11T03:00:{second:02}+00:00'
                seen.append(event)
                def replace(path, target):
                    if event['kind'] in losses and str(target).endswith('fixture-scope-appserver.json'):
                        if after_commit:replacement(path,target)
                        raise OSError('Synthetic observation persistence or acknowledgement failure')
                    return replacement(path,target)
                with patch.object(Path,'replace',replace):
                    owner().record_managed_worker_activity(event)
                # Recreate the owner and reload the actual record after each save.
                path=Path(directory)/'.managed-activity/fixture-scope-appserver.json'
                reloads.append(json.loads(path.read_text()))
            transport=app.CodexAppServerTransport(protocol_version=app.MANAGED_PROTOCOL_VERSION,
                timeout_seconds=3,popen=lambda *a,**k:process)
            with patch.object(transport,'qualify',return_value={'synthetic':True}), \
                 patch.object(app.subprocess,'Popen',side_effect=AssertionError('No real process')):
                result=transport.run(cwd=directory,prompt='Synthetic timing regression',
                    output_schema={'type':'object'},output_path=Path(directory)/'output.json',
                    sandbox='workspace-write',campaign_id='fixture-campaign',invocation_id='fixture-scope-appserver',
                    worker={'worker_id':'fixture-worker'},environment={},allow_detached_continuation=False,
                    progress_handler=observe,approval_handler=lambda *a,**k:{'choice':'deny' if deny else 'approve_once',
                        'claim':lambda:None,'complete':lambda state:None})
            self.assertEqual(result.returncode,0);self.assertEqual(process.terminated,1)
            saved=json.loads((Path(directory)/'.managed-activity/fixture-scope-appserver.json').read_text())
            projection=owner().managed_worker_activity_projection('fixture-campaign')
            self.assertEqual(projection[0]['timing_events'],saved['timing_events'])
            before=copy.deepcopy(saved)
            owner().record_managed_worker_activity(seen[-1])
            self.assertEqual(json.loads((Path(directory)/'.managed-activity/fixture-scope-appserver.json').read_text()),before)
            replies=[json.loads(line) for line in process.stdin.getvalue().splitlines()]
            self.assertEqual(sum('result' in r for r in replies),repeats)
            return saved,projection,seen,reloads

    def project(self, observations):
        from src.runtime.autonomy_supervision import campaign_console_reporting
        from src.app.server import _console_reporting
        return _console_reporting(campaign_console_reporting(record(),observations,
            observed_at='2026-09-11T03:01:00Z'))

    def clocks(self, report):
        script="const a=require('./tests/js/dev_console_projection_harness.js').consoleApi;const r=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(a.roleClocks({reporting:a.normalizeConsoleReporting(r)},'live',Date.parse('2026-09-11T03:01:00Z'))))"
        result=subprocess.run(['node','-e',script],input=json.dumps(report),capture_output=True,text=True,
            cwd=Path(__file__).resolve().parents[1],timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_lost_pause_and_resume_are_unavailable_after_save_reload_and_recovery(self):
        for kind in ('permission_wait','permission_result'):
            for deny in (False,True):
                with self.subTest(kind=kind,deny=deny):
                    saved,observations,seen,reloads=self.replay([kind],deny=deny)
                    turns=execution_turns(observations,observed_at='2026-09-11T03:01:00Z')
                    turn=turns[0]
                    self.assertIsNone(turn['active_seconds']);self.assertIsNone(turn['waiting_seconds'])
                    self.assertTrue(turn['history_incomplete']);self.assertTrue(turn['duration_incomplete'])
                    self.assertFalse(turn['active_verified']);self.assertEqual(turn['ended_at'],'2026-09-11T03:00:50+00:00')
                    # Known prefix or suffix remains supported, never a guessed gap.
                    self.assertEqual(sum(s['seconds'] for s in turn['segments']),10)
                    self.assertEqual(turns,execution_turns(json.loads(json.dumps(observations)),observed_at='2026-09-12T03:01:00Z'))
                    report=self.project(observations);clocks=self.clocks(report)
                    self.assertTrue(report['timing_history_incomplete'])
                    self.assertEqual(report['timing_incomplete_roles'],['worker'])
                    self.assertIsNone(clocks[0]['seconds']);self.assertIsNone(clocks[0]['total'])
                    self.assertIn('timing unavailable',clocks[0]['label'])
                    self.assertTrue(any(e.get('timing_gap_before') for e in saved['timing_events']))
                    self.assertEqual(report,self.project(json.loads(json.dumps(observations))))

    def test_complete_or_committed_but_unacknowledged_evidence_stays_exact(self):
        for loss in ((),('permission_wait',),('permission_result',)):
            with self.subTest(loss=loss):
                saved,observations,_,_=self.replay(loss,after_commit=True)
                turn=execution_turns(observations,observed_at='2026-09-11T03:01:00Z')[0]
                self.assertEqual((turn['active_seconds'],turn['waiting_seconds']),(20,30))
                self.assertFalse(turn['history_incomplete']);self.assertFalse(turn['duration_incomplete'])
                self.assertFalse(any(e.get('timing_gap_before') for e in saved['timing_events']))
                self.assertEqual(self.clocks(self.project(observations))[0]['total'],20)

    def test_unaffected_turns_and_other_role_totals_remain_supported(self):
        _,values,_,_=self.replay(['permission_wait'])
        older=observation([transition('turn_started',0,turn='older'),transition('final_result',5,'completed',turn='older')])
        reviewer=observation([transition('turn_started',0,turn='reviewer'),transition('final_result',15,'completed',turn='reviewer')],'reviewer')
        report=self.project([older,*values,reviewer]);clocks=self.clocks(report)
        self.assertEqual(next(t['active_seconds'] for t in report['turns'] if t['turn_id']=='older'),5)
        self.assertIsNone(clocks[0]['total']);self.assertEqual(clocks[1]['total'],15)
        self.assertEqual(report['timing_incomplete_roles'],['worker'])

    def test_repeated_storage_failures_are_bounded_and_recovery_is_not_zero(self):
        saved,observations,seen,_=self.replay(['permission_wait','permission_result'],deny=True,repeats=20)
        self.assertTrue(any(e.get('timing_observation_loss_overflow') for e in seen))
        self.assertLessEqual(max(len(e.get('timing_observation_losses',[])) for e in seen),32)
        turn=execution_turns(observations,observed_at='2026-09-11T03:01:00Z')[0]
        self.assertIsNone(turn['active_seconds']);self.assertIsNone(turn['waiting_seconds'])
        self.assertTrue(turn['history_incomplete'])

    def test_live_recovery_does_not_accrue_unverified_time_or_claim_disconnection(self):
        _,_,_,reloads=self.replay(['permission_wait'])
        value=next(row for row in reloads if row['events'][-1]['kind']=='permission_result')
        value.update(verified_at='2026-09-11T03:00:45Z',last_verified_at=value['updated_at'])
        turn=execution_turns([value],observed_at='2026-09-11T03:00:46Z')[0]
        self.assertEqual(turn['state'],'running');self.assertFalse(turn['active_verified'])
        self.assertIsNone(turn['active_seconds']);self.assertTrue(turn['duration_incomplete'])
        value.update(state='disconnected',verified_at=None)
        lost=execution_turns([value],observed_at='2026-09-11T03:10:00Z')[0]
        self.assertEqual(lost['state'],'disconnected');self.assertIsNone(lost['active_seconds'])

    def test_non_timing_publication_failure_does_not_invalidate_complete_transitions(self):
        _,observations,_,_=self.replay(['starting'])
        turn=execution_turns(observations,observed_at='2026-09-11T03:01:00Z')[0]
        self.assertEqual((turn['active_seconds'],turn['waiting_seconds']),(20,30))
        self.assertFalse(turn['history_incomplete'])


class TimestampEvidenceTests(unittest.TestCase):
    def project(self,values,when):
        from src.runtime.autonomy_supervision import campaign_console_reporting
        from src.app.server import _console_reporting
        original=copy.deepcopy(values)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'retained-observation.json';path.write_text(json.dumps(values))
            restored=json.loads(path.read_text())
            report=campaign_console_reporting(record(),restored,observed_at=when)
            self.assertEqual(restored,original)
            wire=_console_reporting(report)
            script="const a=require('./tests/js/dev_console_projection_harness.js').consoleApi;const r=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(a.roleClocks({reporting:a.normalizeConsoleReporting(r.report)},'live',Date.parse(r.now))))"
            result=subprocess.run(['node','-e',script],input=json.dumps({'report':wire,'now':when}),text=True,
                capture_output=True,timeout=20,cwd=Path(__file__).resolve().parents[1])
            self.assertEqual(result.returncode,0,result.stderr)
            return report,json.loads(result.stdout)

    def test_reversed_pause_is_unknown_before_and_after_future_filter_boundary(self):
        events=[transition('turn_started',0),transition('permission_wait',40,'waiting'),
            transition('permission_result',20),transition('final_result',30,'completed')]
        summaries=[]
        for second in (35,60):
            report,clocks=self.project([observation(events)],transition('x',second)['created_at'])
            turn=report['turns'][0]
            self.assertIsNone(turn['active_seconds']);self.assertIsNone(turn['waiting_seconds'])
            self.assertTrue(turn['duration_incomplete']);self.assertTrue(turn['history_incomplete'])
            self.assertFalse(turn['active_verified']);self.assertIsNone(clocks[0]['total'])
            # No guessed segment bridges the discarded backwards-clock pause.
            self.assertEqual([s['seconds'] for s in turn['segments']],[10])
            summaries.append(turn)
        self.assertEqual(summaries[0],summaries[1])
        control=[transition('turn_started',0),transition('permission_wait',10,'waiting'),
            transition('permission_result',20),transition('final_result',30,'completed')]
        report,clocks=self.project([observation(control)],transition('x',60)['created_at'])
        self.assertEqual((report['turns'][0]['active_seconds'],report['turns'][0]['waiting_seconds']),(20,10))
        self.assertEqual(clocks[0]['total'],20)

    def test_unusable_transition_keeps_other_turns_role_and_segments_supported(self):
        for bad in (None,'not-a-timestamp',42,{},'2026-09-12T03:00:00Z'):
            with self.subTest(timestamp=bad):
                pause=transition('permission_wait',20,'waiting');pause['created_at']=bad
                events=[transition('turn_started',0,turn='older'),transition('final_result',5,'completed',turn='older'),
                    transition('turn_started',10),pause,transition('permission_result',30),transition('final_result',40,'completed'),
                    transition('turn_started',70,turn='later'),transition('final_result',90,'completed',turn='later')]
                reviewer=observation([transition('turn_started',0,turn='review'),transition('final_result',15,'completed',turn='review')],'reviewer')
                report,clocks=self.project([observation(events),reviewer],transition('x',150)['created_at'])
                by_id={t['turn_id']:t for t in report['turns']}
                self.assertEqual(by_id['older']['active_seconds'],5);self.assertEqual(by_id['later']['active_seconds'],20)
                self.assertEqual(by_id['review']['active_seconds'],15)
                self.assertIsNone(by_id['turn-one']['active_seconds'])
                self.assertEqual([s['seconds'] for s in by_id['turn-one']['segments']],[10])
                self.assertIsNone(clocks[0]['total']);self.assertEqual(clocks[1]['total'],15)

    def test_bound_turn_without_any_usable_timestamp_is_not_dropped_from_totals(self):
        unknown=transition('turn_started',0,turn='unknown');unknown['created_at']=None
        known=[transition('turn_started',0,turn='known'),transition('final_result',5,'completed',turn='known')]
        report,clocks=self.project([observation(known+[unknown])],transition('x',60)['created_at'])
        self.assertEqual(len(report['turns']),2)
        by_id={t['turn_id']:t for t in report['turns']}
        self.assertEqual(by_id['known']['active_seconds'],5)
        self.assertIsNone(by_id['unknown']['started_at']);self.assertIsNone(by_id['unknown']['active_seconds'])
        self.assertTrue(by_id['unknown']['duration_incomplete']);self.assertIsNone(clocks[0]['total'])


class NativeTimingLifecycleTests(unittest.TestCase):
    """Real reader, campaign/Attention decision owner and disk-backed observations."""
    def native_replay(self, *, role="worker", loss=(), choice="approve_once",
                      pause_second=10,decision_second=40,poll_second=40,canonical_wait_second=None):
        import os
        from datetime import datetime,timedelta,timezone
        from types import SimpleNamespace
        from unittest.mock import patch
        from src.runtime import codex_app_server as app
        from src.runtime import codex_development_campaign as module
        from src.runtime.autonomy_supervision import campaign_console_reporting
        from src.app.server import _console_reporting, _console_managed_activity
        from src.runtime.development_attention import DevelopmentAttentionStore
        from src.runtime.wsl_codex_reviewer import _review_attention_binding
        from tests.test_codex_development_campaign import CampaignFixture,CodexDevelopmentCampaignTests
        from tests.test_codex_reviewer_client_compatibility import Process,START,APPROVAL,RESOLVED,ITEM,END
        base=datetime.now(timezone.utc);second=[0]
        when=lambda n:(base+timedelta(seconds=n)).isoformat()
        frames=copy.deepcopy(START+[APPROVAL])
        if choice=='approve_once':
            frames+=copy.deepcopy([RESOLVED])
            frames.append({'method':'item/completed','params':{'threadId':'t','turnId':'u',
                'item':{'id':APPROVAL['params']['itemId'],'type':'commandExecution','status':'completed'}}})
        frames+=copy.deepcopy([ITEM,END]);process=Process(frames);process.pid=os.getpid()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture=CampaignFixture(root);campaign=fixture.campaign
            campaign.attention_store=DevelopmentAttentionStore(root/'attention')
            package=None;approval_binding=None
            if role=='reviewer':
                case=CodexDevelopmentCampaignTests();case.fixture=fixture;case.tmp=SimpleNamespace(name=directory)
                campaign,record_value,package,transport,worker=case._review_native_approval_fixture('native-review-timing')
                invocation='native-review-timing-invocation'
                retention=record_value['builder_runs'][-1]['candidate_retention_receipt']
                approval_binding=_review_attention_binding(package=package,transport_authority=transport,
                    campaign_id=record_value['campaign_id'],candidate_snapshot_id=retention['candidate_snapshot']['candidate_snapshot_id'],
                    reviewer=worker,reviewer_invocation_id=invocation)
            else:
                payload=fixture.payload('native-worker-timing')
                payload['execution_budget_v01']={'maximum_duration_seconds':600,'maximum_worker_turns':1,
                    'maximum_reviewer_turns':1,'maximum_provider_turns':2,'maximum_cost_units':2,
                    'maximum_correction_cycles':1,'maximum_iterations':1}
                record_value=campaign.create(payload,authenticated_rider=True,stepwise=True)
                record_value=campaign._update(record_value,event_kind='fixture-owner',status='builder_running',
                    active_builder_task_scope_id='native-worker-timing')
                worker=record_value['builder'];invocation='native-worker-timing-appserver'
            campaign_id=record_value['campaign_id'];polls={};seen=[];captured=[]
            original_replace=Path.replace
            def observe(event):
                event=copy.deepcopy(event)
                second[0]={'starting':0,'turn_started':0,'permission_wait':pause_second,
                           'permission_result':40,'final_result':50}.get(event['kind'],45)
                event['created_at']=when(second[0]);seen.append(event)
                def replace(path,target):
                    if event['kind'] in loss and str(target).endswith(invocation+'.json'):
                        raise OSError('Synthetic timing save failure')
                    return original_replace(path,target)
                with patch.object(Path,'replace',replace):
                    if role=='reviewer':campaign.record_managed_reviewer_activity(event,package_id=package['package_id'])
                    else:campaign.record_managed_worker_activity(event)
                captured.append(copy.deepcopy(campaign.managed_worker_activity_projection(campaign_id)))
            def poll(label):
                rows=campaign.managed_worker_activity_projection(campaign_id)
                # Recreate the canonical owner and reload both stores, without
                # rewriting a record or using the transport's in-memory marker.
                restored=module.CodexDevelopmentCampaign(fixture.instance_id,root=campaign.store.root.parent,
                    exchange=fixture.exchange,attention_store=campaign.attention_store,runtime_state_root=root/'runtime')
                # Store root is instance-qualified; constructor accepts its parent.
                self.assertEqual(rows,restored.managed_worker_activity_projection(campaign_id))
                wire=_console_reporting(campaign_console_reporting(campaign.store.load(campaign_id),rows,observed_at=when(second[0])))
                polls[label]={'observations':rows,'managed':_console_managed_activity(rows),'report':wire,'observed_at':when(second[0]),
                              'campaign_status':campaign.store.load(campaign_id)['status']}
            original_wait=campaign.attention_store.wait_for_decision
            def handle(approval,**kwargs):
                if canonical_wait_second is not None:second[0]=canonical_wait_second
                if role=='worker':
                    # The managed adapter supplies these frozen-material fields
                    # before entering the campaign owner. Synthetic material,
                    # not missing identity fields or weakened decision checks.
                    approval={**approval,'protocol':{**approval['protocol'],
                        'candidate_snapshot_id':'candidate-native-timing-fixture',
                        'candidate_record_sha256':'a'*64,'mutation_digest_sha256':'b'*64}}
                return campaign._handle_typed_approval(approval,**kwargs)
            def decide(attention_id,**kwargs):
                second[0]=poll_second;poll('pending')
                event=campaign.attention_store.get(attention_id)
                second[0]=decision_second
                campaign.decide_attention(campaign_id,attention_id,choice,authenticated_rider=True,
                    expected_identity=campaign.attention_store._authority_binding(event))
                second[0]=poll_second
                poll('decided_before_resume')
                return original_wait(attention_id,**kwargs)
            transport=app.CodexAppServerTransport(protocol_version=app.REVIEWER_PROTOCOL_VERSION if role=='reviewer' else app.MANAGED_PROTOCOL_VERSION,
                timeout_seconds=10,popen=lambda *a,**k:process)
            with patch.object(transport,'qualify',return_value={'synthetic':True}), \
                 patch.object(app.subprocess,'Popen',side_effect=AssertionError('No real process')), \
                 patch.object(module,'_now',side_effect=lambda:when(second[0])), \
                 patch.object(module,'retain_needs_tanner_notification',lambda *a,**k:None), \
                 patch.object(module,'retain_campaign_terminal_notification',lambda *a,**k:None), \
                 patch.object(campaign.attention_store,'wait_for_decision',side_effect=decide):
                result=None
                try:
                    result=transport.run(cwd=directory,prompt='Synthetic native timing only',output_schema={'type':'object'},
                        output_path=root/'output.json',sandbox='read-only' if role=='reviewer' else 'workspace-write',
                        campaign_id=campaign_id,invocation_id=invocation,worker=worker,environment={},
                        approval_binding=approval_binding,reviewer_invocation_id=invocation if role=='reviewer' else None,
                        allow_detached_continuation=False,progress_handler=observe,approval_handler=handle)
                except app.CodexAppServerError as exc:
                    self.assertEqual(choice,'cancel_campaign');self.assertEqual(exc.category,'campaign_cancelled')
                second[0]=60;poll('completed')
            # Evaluate each captured in-handler projection after restoring the
            # process guard. Only local Node runs; the native peer stays fake.
            for value in polls.values():
                script="const a=require('./tests/js/dev_console_projection_harness.js').consoleApi;const r=JSON.parse(require('fs').readFileSync(0,'utf8'));const c={campaign_id:'native-fixture',managed:r.managed,reporting:a.normalizeConsoleReporting(r.report)};const p={current_campaign_id:c.campaign_id,campaigns:[c]};const n=Date.parse(r.now);process.stdout.write(JSON.stringify({clocks:a.roleClocks(c,'live',n),combined:['worker','reviewer'].map(role=>a.combinedOperationStatus('managed-'+role,p,'live',n))}))"
                rendered=subprocess.run(['node','-e',script],input=json.dumps({'report':value['report'],'managed':value['managed'],'now':value['observed_at']}),
                    text=True,capture_output=True,timeout=20,cwd=Path(__file__).resolve().parents[1])
                self.assertEqual(rendered.returncode,0,rendered.stderr)
                value.update(json.loads(rendered.stdout))
                for index,clock in enumerate(value['clocks']):
                    if clock['label']=='Execution unknown':
                        # Process cancellation is a recorded outcome, not a
                        # claim that the missing native turn completed.
                        self.assertIn(value['combined'][index]['short'],('Execution unknown','Last failed'))
                        self.assertIn('execution unknown',value['combined'][index]['detail'].lower())
                    if clock['label']=='Executing':
                        self.assertEqual(value['combined'][index]['short'],'Executing')
            if choice=='cancel_campaign':
                self.assertIsNone(result);self.assertEqual(process.terminated,1)
            else:self.assertEqual(result.returncode,0)
            replies=[json.loads(line) for line in process.stdin.getvalue().splitlines()]
            self.assertEqual(sum('result' in item for item in replies),1)
            lifecycle=campaign.attention_store.lifecycle(campaign.store.load(campaign_id)['attention_event_ids'][-1])
            return polls,captured,seen,lifecycle

    def test_lost_pause_is_not_executing_while_actual_owner_waits(self):
        for role in ('worker','reviewer'):
            for choice in ('approve_once','deny','cancel_campaign'):
                with self.subTest(role=role,choice=choice):
                    polls,_,_,_=self.native_replay(role=role,loss=('permission_wait',),choice=choice)
                    turn=polls['pending']['report']['turns'][0]
                    self.assertEqual(turn['state'],'waiting')
                    self.assertIsNone(turn['active_seconds']);self.assertIsNone(turn['waiting_seconds'])
                    self.assertFalse(turn['active_verified']);self.assertTrue(turn['duration_incomplete'])
                    clock=next(c for c in polls['pending']['clocks'] if c['role']==role)
                    self.assertIsNone(clock['seconds']);self.assertIsNone(clock['total'])
                    self.assertNotIn('executing',clock['label'].lower())
                    self.assertIsNone(polls['completed']['report']['turns'][0]['active_seconds'])

    def test_bound_reviewer_pause_approve_deny_resume_and_terminal_stay_exact(self):
        for choice in ('approve_once','deny'):
            with self.subTest(choice=choice):
                polls,captured,seen,life=self.native_replay(role='reviewer',choice=choice)
                waiting=polls['pending']['report']['turns'][0]
                self.assertEqual((waiting['active_seconds'],waiting['waiting_seconds']),(10,30))
                # A saved decision is not yet the native resume boundary.
                self.assertIsNone(polls['decided_before_resume']['report']['turns'][0]['active_seconds'])
                resumed=next(rows[0] for rows in captured if rows[0]['events'][-1]['kind']=='permission_result')
                self.assertFalse(resumed['timing_state_unverified'])
                turn=polls['completed']['report']['turns'][0]
                self.assertEqual((turn['active_seconds'],turn['waiting_seconds']),(20,30))
                self.assertFalse(turn['duration_incomplete'])
                self.assertFalse(polls['completed']['report']['timing_history_incomplete'])
                self.assertFalse(any(e.get('timing_observation_losses') for e in seen))
                self.assertEqual(life['decision']['choice'],choice)
                if choice=='approve_once':self.assertTrue(life['decision']['consumed'])

    def test_lost_resume_cannot_keep_counting_canonical_decision_as_wait_time(self):
        for role in ('worker','reviewer'):
            polls,_,_,_=self.native_replay(role=role,loss=('permission_result',))
            self.assertIsNone(polls['decided_before_resume']['report']['turns'][0]['active_seconds'])
            self.assertIsNone(polls['completed']['report']['turns'][0]['active_seconds'])

    def test_cancel_records_cleanup_without_inventing_a_native_completion(self):
        for role in ('worker','reviewer'):
            polls,captured,seen,life=self.native_replay(role=role,choice='cancel_campaign')
            self.assertEqual(life['decision']['choice'],'cancel_campaign')
            self.assertEqual(polls['completed']['campaign_status'],'cancelled')
            self.assertEqual(captured[-1][0]['events'][-1]['kind'],'transport_closed')
            turn=polls['completed']['report']['turns'][0]
            self.assertFalse(turn['active_verified']);self.assertIsNone(turn['active_seconds'])
            self.assertFalse(any(e.get('timing_observation_losses') for e in seen))

    def test_reviewer_observations_require_exact_approved_or_closing_lineage(self):
        import os
        from types import SimpleNamespace
        from tests.test_codex_development_campaign import CampaignFixture,CodexDevelopmentCampaignTests
        with tempfile.TemporaryDirectory() as directory:
            fixture=CampaignFixture(Path(directory))
            case=CodexDevelopmentCampaignTests();case.fixture=fixture;case.tmp=SimpleNamespace(name=directory)
            owner,record,package,_,worker=case._review_native_approval_fixture('native-timing-scope')
            invocation='reviewer-exact-timing'
            active={'invocation_id':invocation,'review_package_id':package['package_id']}
            current=owner._update(record,event_kind='synthetic-approved-state',
                status='reviewer_native_action_approved',active_review_native_action=active)
            event={'campaign_id':record['campaign_id'],'invocation_id':invocation,
                'worker':worker,'process_id':os.getpid(),'event_id':'exact-resume',
                'created_at':current['updated_at'],'kind':'permission_result','state':'running',
                'thread_id':'t','turn_id':'u','public_message':'Synthetic approved resume'}
            owner.record_managed_reviewer_activity(event,package_id=package['package_id'])
            state_hash=owner.store.load(record['campaign_id'])['record_sha256']
            for overrides,pkg in (({'invocation_id':'neighbor'},package['package_id']),
                ({'worker':{'worker_id':'neighbor'}},package['package_id']),({},'neighbor-package')):
                with self.subTest(overrides=overrides,package=pkg),self.assertRaises(PermissionError):
                    owner.record_managed_reviewer_activity({**event,**overrides},package_id=pkg)
            self.assertEqual(owner.store.load(record['campaign_id'])['record_sha256'],state_hash)
            for state in ('cancelled','failed_safe'):
                current=owner._update(owner.store.load(record['campaign_id']),
                    event_kind='synthetic-unrelated-terminal',status=state,active_review_native_action=None)
                with self.subTest(state=state),self.assertRaises(PermissionError):
                    owner.record_managed_reviewer_activity({**event,'event_id':state},package_id=package['package_id'])

    def test_attention_crosscheck_is_bounded_exact_and_does_not_invent_time(self):
        from src.runtime.console_observation import unobserved_attention_transition
        from src.runtime.worker_exchange import _digest
        def canonical(value):
            value={**value,'state_revision':len(value['events'])+1}
            value['record_sha256']=_digest(value);return value
        def binding(value):
            return {'state_revision':value['state_revision'],'record_sha256':value['record_sha256'],
                'event_count':len(value['events']),'event_tail_sha256':_digest(value['events'][-1] if value['events'] else None)}
        observed={'invocation_id':'i','worker_id':'w','state':'running','updated_at':'2026-09-11T03:00:00Z'}
        observed['campaign_observation_binding']=binding(canonical({'status':'running','events':[]}))
        required={'kind':'tanner_attention_required','created_at':'2026-09-11T03:00:10Z',
            'detail':{'invocation_id':'i','worker_id':'w','attention_id':'a'}}
        record=canonical({'status':'tanner_escalation','needs_tanner':{'invocation_id':'i','worker_id':'w'},'events':[required]})
        self.assertEqual(unobserved_attention_transition(record,observed),(True,'waiting'))
        neighbor={**observed,'invocation_id':'other'}
        self.assertFalse(unobserved_attention_transition(record,neighbor)[0])
        saved_pause={**observed,'state':'waiting','updated_at':'2026-09-11T03:00:09Z'}
        self.assertFalse(unobserved_attention_transition(record,saved_pause)[0])
        decision={'kind':'tanner_attention_approve_once','created_at':'2026-09-11T03:00:20Z','detail':{'attention_id':'a'}}
        resolved=canonical({'status':'reviewer_native_action_approved','needs_tanner':None,'events':[required,decision]})
        self.assertTrue(unobserved_attention_transition(resolved,saved_pause)[0])
        self.assertFalse(unobserved_attention_transition(resolved,{**observed,'updated_at':'2026-09-11T03:00:21Z',
            'campaign_observation_binding':binding(resolved)})[0])
        truncated={**resolved,'events':[required]+[{'kind':'ordinary','created_at':'2026-09-11T03:00:30Z'}]*128}
        self.assertTrue(unobserved_attention_transition(truncated,observed)[0])
        for invalid in ({},None,{'event_count':True}, {**binding(resolved),'event_count':99},
                        {**binding(resolved),'event_tail_sha256':'0'*64},
                        {**binding(resolved),'record_sha256':'0'*64}):
            with self.subTest(binding=invalid):
                self.assertTrue(unobserved_attention_transition(resolved,{**saved_pause,'campaign_observation_binding':invalid})[0])

    def test_backward_canonical_decision_cannot_hide_a_missing_native_resume(self):
        for role in ('worker','reviewer'):
            for choice in ('approve_once','deny'):
                for poll_second in (45,50):
                    with self.subTest(role=role,choice=choice,poll=poll_second):
                        polls,_,_,_=self.native_replay(role=role,choice=choice,loss=('permission_result',),
                            pause_second=40,decision_second=20,poll_second=poll_second)
                        report=polls['decided_before_resume']['report'];turn=report['turns'][0]
                        self.assertIsNone(turn['active_seconds']);self.assertIsNone(turn['waiting_seconds'])
                        self.assertTrue(turn['duration_incomplete']);self.assertFalse(turn['active_verified'])
                        clock=next(c for c in polls['decided_before_resume']['clocks'] if c['role']==role)
                        self.assertIsNone(clock['total']);self.assertNotIn('Waiting for Tanner',clock['label'])
                        value=polls['decided_before_resume']
                        retained=execution_turns(value['observations'],observed_at=value['observed_at'])[0]
                        self.assertEqual([s['seconds'] for s in retained['segments']],[40])

    def test_backward_canonical_wait_and_decision_cannot_hide_failed_pause(self):
        for role in ('worker','reviewer'):
            with self.subTest(role=role):
                polls,_,_,_=self.native_replay(role=role,loss=('permission_wait','permission_result'),
                    canonical_wait_second=-5,decision_second=-10,poll_second=45)
                for key in ('pending','decided_before_resume','completed'):
                    self.assertIsNone(polls[key]['report']['turns'][0]['active_seconds'])
                    self.assertFalse(polls[key]['report']['turns'][0]['active_verified'])

    def test_canonical_clock_rollback_does_not_discard_complete_native_timing(self):
        for role in ('worker','reviewer'):
            with self.subTest(role=role):
                polls,captured,_,_=self.native_replay(role=role,decision_second=5)
                turn=polls['completed']['report']['turns'][0]
                self.assertEqual((turn['active_seconds'],turn['waiting_seconds']),(20,30))
                self.assertFalse(turn['duration_incomplete'])
                resumed=next(rows[0] for rows in captured if rows[0]['events'][-1]['kind']=='permission_result')
                self.assertFalse(resumed['timing_state_unverified'])


if __name__ == "__main__":unittest.main()

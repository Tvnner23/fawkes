import copy, hashlib, json, os, subprocess, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from src.runtime.historical_cleanup_session import HistoricalCleanupSession, _digest, _node
from src.runtime.git_commit_transaction import GitCommitTransaction
from src.runtime.worker_exchange import WorkerExchange
from src.runtime.windows_codex_reviewer import independent_review_acceptance_receipt


class HistoricalCleanupSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.repo=self.root/'repo';self.repo.mkdir()
        subprocess.run(['git','init','-q'],cwd=self.repo,check=True)
        subprocess.run(['git','config','user.email','test@example.invalid'],cwd=self.repo,check=True)
        subprocess.run(['git','config','user.name','Test'],cwd=self.repo,check=True)
        (self.repo/'a.py').write_text('old\n');(self.repo/'b.py').write_text('base\n')
        subprocess.run(['git','add','a.py','b.py'],cwd=self.repo,check=True);subprocess.run(['git','commit','-qm','base'],cwd=self.repo,check=True)
        self.head=subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,text=True,capture_output=True,check=True).stdout.strip()
        (self.repo/'a.py').write_text('new\n');(self.repo/'b.py').write_text('changed\n')
        status=subprocess.run(['git','status','--porcelain=v2','--untracked-files=all'],cwd=self.repo,capture_output=True,check=True).stdout
        self.status=hashlib.sha256(status).hexdigest();self.state=self.root/'state';self.state.mkdir()
        def item(name):
            body=(self.repo/name).read_bytes();return {'path':name,'node':{'state':'present','type':'regular','mode':0o644,'byte_length':len(body),'sha256':hashlib.sha256(body).hexdigest()}}
        self.inventory={'paths':[item('a.py'),item('b.py')]}
        self.validator=Mock(side_effect=self._validation)
        self.reviewer=Mock(side_effect=self._review)
        self.applied={}
        self.applier=Mock(side_effect=self._apply)
        self.commit_state=self.state/'git-transaction';self.commit_state.mkdir()
        self.committer=GitCommitTransaction(self.repo,self.commit_state)
        self.candidate_verifier=Mock(side_effect=self._verify)
        self.broad=Mock(return_value={'status':'passed'});self.attention=Mock(return_value={'request_id':'r','binding_sha256':'b'})
    def session(self,plans=None,clock=None):
        return HistoricalCleanupSession(repository=self.repo,state_root=self.state,inventory=self.inventory,
          plans=plans or [{'batch_id':'a','paths':['a.py'],'dependencies':[],'focused_tests':[['test','a']]}],
          expected_head=self.head,expected_status_sha256=self.status,validator=self.validator,reviewer=self.reviewer,
          applier=self.applier,committer=self.committer,broad_validator=self.broad,attention=self.attention,
          candidate_verifier=self.candidate_verifier,clock=clock)
    def _verify(self, plan, correction):
        value={key:copy.deepcopy(correction[key]) for key in ('candidate_generation','head','scope','nodes',
            'exact_diff','exact_diff_sha256','mutation_manifest_sha256','candidate_snapshot_id')}
        if value['candidate_generation']==0:
            actual=[]
            for item in value['nodes']:
                current=copy.deepcopy(item);current['frozen_postimage']=_node(self.repo/item['path']);actual.append(current)
            if actual != value['nodes']:
                value['nodes']=actual;value['mutation_manifest_sha256']=_digest(actual)
                value['candidate_snapshot_id']='candidate-snapshot-'+_digest({'head':value['head'],
                    'scope':value['scope'],'nodes':actual})
            if (self.repo/'neighbor.py').exists():value['scope']=[*value['scope'],'neighbor.py']
        value['verification_status']='exact_filesystem_match';value['record_sha256']=_digest(value);return value
    def _validation(self, plan, evidence):
        preimages=_digest([{'path':item['path'],'head_preimage':item['head_preimage'],
            'frozen_postimage':item['frozen_postimage']} for item in evidence['nodes']])
        return {'status':'passed','campaign_id':'campaign-a','builder_package_id':'builder-package-a',
            'review_package_id':'review-package-a','source_report_id':'source-report-a',
            'candidate_retention_receipt_sha256':'1'*64,
            'exact_change_evidence_sha256':evidence['exact_diff_sha256'],
            'authoritative_preimages_sha256':preimages,
            'acceptance_condition_ids':['exact','safe']}
    def _review(self, plan, evidence, validation):
        reviewer={'worker_id':'independent-reviewer','role':'reviewer'}
        package={'package_id':validation['review_package_id'],'source_report_id':validation['source_report_id'],
            'candidate_snapshot_id':evidence['candidate_snapshot_id'],'exact_diff_sha256':evidence['exact_diff_sha256'],
            'mutation_manifest_sha256':evidence['mutation_manifest_sha256'],
            'allowed_scope_sha256':evidence['scope_sha256'],
            'preimages_sha256':_digest([{'path':item['path'],'head_preimage':item['head_preimage'],
                'frozen_postimage':item['frozen_postimage']} for item in evidence['nodes']])}
        package['record_sha256']=_digest(package)
        report={'report_id':'report-a','sender':reviewer,'in_reply_to':{
            'package_id':package['package_id'],'source_report_id':validation['source_report_id']},
            'review_invocation_id':'invocation-a'};report['record_sha256']=_digest(report)
        delivery={'delivery_receipt_id':'delivery-a','package_id':package['package_id'],'status':'delivered'}
        delivery['record_sha256']=_digest(delivery)
        verification={'verification_receipt_id':'verification-a','package_id':package['package_id'],
            'source_report_id':validation['source_report_id'],'status':'accepted'}
        verification['record_sha256']=_digest(verification)
        receipt={'record_type':'codex_independent_review_acceptance_receipt','status':'accepted',
            'schema_version':2,'campaign_id':validation['campaign_id'],'package_id':validation['builder_package_id'],
            'review_package_id':package['package_id'],'candidate_snapshot_id':evidence['candidate_snapshot_id'],
            'review_package_sha256':package['record_sha256'],'source_report_id':validation['source_report_id'],
            'mutation_manifest_sha256':evidence['mutation_manifest_sha256'],
            'allowed_scope_sha256':evidence['scope_sha256'],
            'candidate_retention_receipt_sha256':validation['candidate_retention_receipt_sha256'],
            'exact_change_evidence_sha256':evidence['exact_diff_sha256'],
            'authoritative_preimages_sha256':package['preimages_sha256'],
            'acceptance_condition_ids_sha256':_digest(['exact','safe']),
            'review_report_id':report['report_id'],'review_report_sha256':report['record_sha256'],
            'review_invocation_id':'invocation-a','reviewer_worker_id':reviewer['worker_id'],
            'reviewer_role':reviewer['role'],'recipient':reviewer,'delivery_receipt_id':'delivery-a',
            'verification_receipt_id':'verification-a','verdict':'pass','creates_authority':False,
            'created_at':datetime.now(timezone.utc).isoformat(),
            'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()}
        receipt['replay_identity']=_digest({'package':package['record_sha256'],
            'candidate':evidence['candidate_snapshot_id'],'invocation':'invocation-a',
            'created_at':receipt['created_at']})
        receipt['record_sha256']=_digest({k:v for k,v in receipt.items() if k!='record_sha256'})
        return {'verdict':'accepted','acceptance_receipt':receipt,'review_report':report,
            'review_package':package,'delivery_receipt':delivery,'verification_receipt':verification}
    def _apply(self, plan, evidence, validation, review, *, operation_id, reconcile_only):
        if operation_id in self.applied:return self.applied[operation_id]
        if reconcile_only:return {'status':'not_applied'}
        result={'status':'applied','application_count':1,'operation_id':operation_id}
        self.applied[operation_id]=result;return result
    def test_truthful_provenance_and_exact_serialized_evidence(self):
        s=self.session();s.create('s');e=s.evidence('a')
        self.assertFalse(e['current_worker_authored']);self.assertEqual('unattributed_phase_0_9_work',e['historical_authorship'])
        self.assertIn('-old',e['exact_diff']);self.assertIn('+new',e['exact_diff']);self.assertEqual(e['record_sha256'],_digest({k:v for k,v in e.items() if k!='record_sha256'}))
    def test_dependency_selection_and_quarantine(self):
        s=self.session([{'batch_id':'blocked','paths':['a.py'],'dependencies':[],'quarantine_reason':'memory-store'},
          {'batch_id':'dependent','paths':['a.py'],'dependencies':['blocked']},{'batch_id':'independent','paths':['b.py'],'dependencies':[]}])
        r=s.create('s');self.assertEqual('independent',s.select(r));self.assertEqual('quarantined',r['batches']['blocked']['status'])
    def test_stale_postimage_and_baseline_rejected(self):
        s=self.session();s.create('s');(self.repo/'a.py').write_text('drift\n')
        with self.assertRaises(RuntimeError):s.evidence('a')
    def test_protected_paths_rejected(self):
        with self.assertRaises(PermissionError):self.session([{'batch_id':'x','paths':['.gitignore']}])
    def test_exactly_once_commit_and_review(self):
        s=self.session();s.create('s');r=s.run_next();self.assertEqual(1,r['accepted_batches'])
        self.assertEqual(1,len(self.applied));self.assertNotEqual(self.head,r['head']);self.assertIsNone(s.select(r))
        self.assertGreaterEqual(self.candidate_verifier.call_count,2)
    def test_rejected_review_never_applies(self):
        self.reviewer.side_effect=None;self.reviewer.return_value={'verdict':'rejected','creates_authority':False}
        s=self.session();s.create('s');r=s.run_next();self.assertEqual('failed',r['batches']['a']['status']);self.applier.assert_not_called()

    def test_generation_zero_drift_after_review_never_creates_apply_intent(self):
        mutations=(
            lambda: (self.repo/'a.py').write_text('changed after review\n'),
            lambda: (self.repo/'a.py').unlink(),
            lambda: ((self.repo/'a.py').unlink(),(self.repo/'a.py').symlink_to('b.py')),
            lambda: (self.repo/'a.py').chmod(0o755),
            lambda: (self.repo/'neighbor.py').write_text('unauthorized\n'),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.state.joinpath('session.json').unlink(missing_ok=True);self.applied.clear()
                target=self.repo/'a.py'
                if target.is_symlink() or target.exists():target.unlink()
                target.write_text('new\n');target.chmod(0o644)
                (self.repo/'neighbor.py').unlink(missing_ok=True)
                def drift(plan,evidence,validation):
                    result=self._review(plan,evidence,validation);mutate();return result
                self.reviewer.side_effect=drift;s=self.session();s.create('s');result=s.run_next()
                self.assertEqual('failed',result['batches']['a']['status']);self.assertFalse(self.applied)
                self.assertIsNone(result.get('transaction_intent'))
        self.reviewer.side_effect=self._review
    def test_two_cycle_exhaustion_requests_attention(self):
        self.reviewer.side_effect=None;self.reviewer.return_value={'verdict':'correction_required','creates_authority':False}
        s=self.session();r=s.create('s');r['batches']['a']['correction_cycles']=2;r['record_sha256']=_digest({k:v for k,v in r.items() if k!='record_sha256'});s.path.write_text(json.dumps(r))
        r=s.run_next();self.assertEqual('needs_tanner',r['batches']['a']['status']);self.attention.assert_called()
    def test_broad_scheduled_every_two_and_at_completion(self):
        plans=[{'batch_id':'a','paths':['a.py'],'dependencies':[]},{'batch_id':'b','paths':['b.py'],'dependencies':[]}]
        s=self.session(plans);s.create('s');s.run_next();s.run_next();self.assertGreaterEqual(self.broad.call_count,1)
    def test_mobile_attention_receipt_is_single_use(self):
        s=self.session();s.create('s');s.pause('ambiguity',{'x':1});s.resume({'request_id':'r','binding_sha256':'b','decision':'approve_once'})
        with self.assertRaises(PermissionError):s.resume({'request_id':'r','binding_sha256':'b','decision':'approve_once'})
    def test_restart_digest_and_revision(self):
        s=self.session();r=s.create('s');self.assertEqual(r,s.load());r=s.run_next();self.assertEqual(r,s.load())
        bad=json.loads(s.path.read_text());bad['revision']+=1;s.path.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):s.load()
    def test_runtime_state_external_and_no_repo_runtime(self):
        s=self.session();s.create('s');self.assertTrue(s.path.is_file());self.assertFalse((self.repo/'session.json').exists())

    def test_forged_neighbor_stale_and_replayed_review_receipts_fail_closed(self):
        for field,value in [('reviewer_worker_id','fawkes-development'),
                            ('candidate_snapshot_id','candidate-snapshot-neighbor'),
                            ('created_at','2000-01-01T00:00:00+00:00')]:
            with self.subTest(field=field):
                self.state.joinpath('session.json').unlink(missing_ok=True);self.applied.clear()
                original=self._review
                def altered(plan,evidence,validation,field=field,value=value):
                    result=original(plan,evidence,validation);result=copy.deepcopy(result)
                    result['acceptance_receipt'][field]=value
                    result['acceptance_receipt']['record_sha256']=_digest({k:v for k,v in result['acceptance_receipt'].items() if k!='record_sha256'})
                    return result
                self.reviewer.side_effect=altered
                result=self.session().create('s');result=self.session().run_next()
                self.assertEqual('failed',result['batches']['a']['status']);self.assertFalse(self.applied)
        self.reviewer.side_effect=self._review

    def test_crash_after_apply_is_reconciled_without_repeating_apply(self):
        s=self.session();s.create('s')
        real_write=s._write;calls={'count':0}
        def crash(record,**kwargs):
            value=real_write(record,**kwargs)
            if (record.get('transaction_intent') or {}).get('stage')=='apply_complete' and calls['count']==0:
                calls['count']+=1;raise KeyboardInterrupt('crash after apply')
            return value
        s._write=crash
        with self.assertRaises(KeyboardInterrupt):s.run_next()
        s._write=real_write;result=s.run_next()
        self.assertEqual('accepted',result['batches']['a']['status'],result)
        self.assertEqual(1,len(self.applied));self.assertNotEqual(self.head,result['head'])

    def test_crash_after_real_commit_is_reconciled_from_original_launch_binding(self):
        owner=self.committer
        class CrashAfterAdvance:
            def __init__(self):self.calls=0
            def prepare(self,**kwargs):return owner.prepare(**kwargs)
            def reconcile(self,prepared):return owner.reconcile(prepared)
            def advance(self,prepared):
                result=owner.advance(prepared);self.calls+=1
                raise KeyboardInterrupt('crash after atomic ref advancement')
        crashing=CrashAfterAdvance();s=self.session();s.committer=crashing;s.create('s')
        with self.assertRaises(KeyboardInterrupt):s.run_next()
        advanced=subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,text=True,
            capture_output=True,check=True).stdout.strip()
        self.assertNotEqual(self.head,advanced)
        restarted=self.session();restarted.committer=owner
        result=restarted.run_next()
        self.assertEqual('accepted',result['batches']['a']['status'],result)
        self.assertEqual(1,len(self.applied));self.assertEqual(1,crashing.calls)
        self.assertEqual(advanced,result['head']);self.assertIsNone(result['transaction_intent'])

    def test_expired_receipt_finalizes_only_an_already_advanced_exact_commit(self):
        owner=self.committer
        class CrashAfterAdvance:
            def prepare(self,**kwargs):return owner.prepare(**kwargs)
            def reconcile(self,prepared):return owner.reconcile(prepared)
            def advance(self,prepared):
                owner.advance(prepared);raise KeyboardInterrupt('crash after atomic ref advancement')
        s=self.session();s.committer=CrashAfterAdvance();s.create('s')
        with self.assertRaises(KeyboardInterrupt):s.run_next()
        advanced=subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,text=True,
            capture_output=True,check=True).stdout.strip()
        future=lambda:datetime.now(timezone.utc)+timedelta(days=2)
        restarted=self.session(clock=future);restarted.committer=owner;result=restarted.run_next()
        self.assertEqual('accepted',result['batches']['a']['status'],result)
        self.assertEqual(advanced,result['head']);self.assertEqual(1,len(self.applied))
        again=restarted.run_next()
        self.assertEqual(result['head'],again['head']);self.assertEqual(1,len(self.applied))
        self.assertFalse((again.get('attention') or {}).get('consumed',False))

    def test_expired_receipt_never_advances_a_prepared_but_uncommitted_ref(self):
        s=self.session();s.create('s');real_write=s._write
        def crash(record,**kwargs):
            value=real_write(record,**kwargs)
            if (record.get('transaction_intent') or {}).get('stage')=='commit_prepared':
                raise KeyboardInterrupt('crash before ref advancement')
            return value
        s._write=crash
        with self.assertRaises(KeyboardInterrupt):s.run_next()
        self.assertEqual(self.head,subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,
            text=True,capture_output=True,check=True).stdout.strip())
        future=lambda:datetime.now(timezone.utc)+timedelta(days=2)
        restarted=self.session(clock=future);result=restarted.run_next()
        self.assertEqual('needs_tanner',result['status']);self.assertEqual(self.head,
            subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,text=True,
                capture_output=True,check=True).stdout.strip())
        self.assertEqual(1,len(self.applied))

    def test_expiry_before_initial_mutation_blocks_every_side_effect(self):
        future=lambda:datetime.now(timezone.utc)+timedelta(days=2)
        s=self.session(clock=future);s.create('s');result=s.run_next()
        self.assertEqual('failed',result['batches']['a']['status'])
        self.assertEqual({},self.applied);self.assertIsNone(result.get('transaction_intent'))
        self.assertEqual(self.head,subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,
            text=True,capture_output=True,check=True).stdout.strip())

    def test_expired_commit_complete_finalizes_as_idempotent_bookkeeping_only(self):
        s=self.session();s.create('s');real_write=s._write;crashed={'value':False}
        def crash(record,**kwargs):
            value=real_write(record,**kwargs)
            if ((record.get('transaction_intent') or {}).get('stage')=='commit_complete'
                    and not crashed['value']):
                crashed['value']=True;raise KeyboardInterrupt('crash after durable commit completion')
            return value
        s._write=crash
        with self.assertRaises(KeyboardInterrupt):s.run_next()
        durable=s.load();self.assertEqual('commit_complete',durable['transaction_intent']['stage'])
        committed=durable['transaction_intent']['commit_receipt']['head']
        future=lambda:datetime.now(timezone.utc)+timedelta(days=2)
        restarted=self.session(clock=future);result=restarted.run_next()
        self.assertEqual('accepted',result['batches']['a']['status'],result)
        self.assertEqual(committed,result['head']);self.assertEqual(1,len(self.applied))
        self.assertEqual(1,int(subprocess.run(['git','rev-list','--count',f'{self.head}..HEAD'],
            cwd=self.repo,text=True,capture_output=True,check=True).stdout.strip()))
        again=restarted.run_next()
        self.assertEqual(result['head'],again['head']);self.assertEqual(1,len(self.applied))
        self.assertEqual(['session_completion'],[call.args[0] for call in self.attention.call_args_list])

    def test_expired_commit_complete_corruption_or_neighbor_fails_closed(self):
        for mutation in ('receipt','neighbor'):
            with self.subTest(mutation=mutation):
                self.tearDown();self.setUp();s=self.session();s.create('s');real_write=s._write
                def crash(record,**kwargs):
                    value=real_write(record,**kwargs)
                    if (record.get('transaction_intent') or {}).get('stage')=='commit_complete':
                        raise KeyboardInterrupt('crash after durable commit completion')
                    return value
                s._write=crash
                with self.assertRaises(KeyboardInterrupt):s.run_next()
                record=s.load()
                if mutation=='receipt':
                    record['transaction_intent']['commit_receipt']['operation_id']='neighbor-operation'
                    record['record_sha256']=_digest({k:v for k,v in record.items() if k!='record_sha256'})
                    s.path.write_text(json.dumps(record))
                else:
                    (self.repo/'neighbor.py').write_text('neighbor\n')
                    subprocess.run(['git','add','neighbor.py'],cwd=self.repo,check=True)
                    subprocess.run(['git','commit','-qm','neighbor'],cwd=self.repo,check=True)
                future=lambda:datetime.now(timezone.utc)+timedelta(days=2)
                restarted=self.session(clock=future);result=restarted.run_next()
                self.assertEqual('needs_tanner',result['status']);self.assertEqual(1,len(self.applied))

    def test_crash_after_commit_object_preparation_retries_same_object_and_advances_once(self):
        owner=self.committer;captured={}
        class CrashAfterPrepare:
            def prepare(self,**kwargs):
                captured['prepared']=owner.prepare(**kwargs)
                raise KeyboardInterrupt('crash after commit object preparation')
            def reconcile(self,prepared):return owner.reconcile(prepared)
            def advance(self,prepared):return owner.advance(prepared)
        s=self.session();s.committer=CrashAfterPrepare();s.create('s')
        with self.assertRaises(KeyboardInterrupt):s.run_next()
        self.assertEqual(self.head,subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,
            text=True,capture_output=True).stdout.strip())
        restarted=self.session();restarted.committer=owner;result=restarted.run_next()
        self.assertEqual('accepted',result['batches']['a']['status'])
        self.assertEqual(captured['prepared']['prepared_commit'],result['head'])
        self.assertEqual(1,len(self.applied))

    def test_commit_complete_neighboring_or_forged_repository_state_fails_closed(self):
        mutations=('head','parent','tree','diff','status','receipt')
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.tearDown();self.setUp();owner=self.committer
                class CrashAfterAdvance:
                    def prepare(self,**kwargs):return owner.prepare(**kwargs)
                    def reconcile(self,prepared):return owner.reconcile(prepared)
                    def advance(self,prepared):
                        owner.advance(prepared);raise KeyboardInterrupt('crash after ref')
                s=self.session();s.committer=CrashAfterAdvance();s.create('s')
                with self.assertRaises(KeyboardInterrupt):s.run_next()
                record=s.load();prepared=record['transaction_intent']['prepared_commit']
                if mutation=='head':
                    (self.repo/'neighbor.py').write_text('neighbor\n')
                    subprocess.run(['git','add','neighbor.py'],cwd=self.repo,check=True)
                    subprocess.run(['git','commit','-qm','neighbor'],cwd=self.repo,check=True)
                elif mutation=='status':(self.repo/'b.py').write_text('neighbor status\n')
                else:
                    field={'parent':'expected_parent_head','tree':'prepared_tree','diff':'prepared_diff_sha256',
                           'receipt':'operation_id'}[mutation]
                    prepared[field]='f'*64 if field!='operation_id' else 'neighbor-operation'
                    prepared['record_sha256']=_digest({k:v for k,v in prepared.items() if k!='record_sha256'})
                    record['record_sha256']=_digest({k:v for k,v in record.items() if k!='record_sha256'})
                    s.path.write_text(json.dumps(record))
                restarted=self.session();restarted.committer=owner
                result=restarted.run_next()
                self.assertEqual('needs_tanner',result['status'])

    def test_ambiguous_neighbor_reconciliation_needs_tanner(self):
        s=self.session();record=s.create('s');record['active_batch']='a';record['batches']['a']['status']='validating'
        record['transaction_intent']={'operation_id':'neighbor','batch_id':'other','stage':'apply_pending'}
        record['revision']+=1;s._write(record,expected_revision=record['revision']-1)
        result=s.run_next();self.assertEqual('needs_tanner',result['status']);self.assertFalse(self.applied)

    def test_neighboring_source_report_and_future_receipt_fail_closed(self):
        for mutation in ('source','future'):
            with self.subTest(mutation=mutation):
                self.state.joinpath('session.json').unlink(missing_ok=True);self.applied.clear()
                def altered(plan,evidence,validation,mutation=mutation):
                    result=copy.deepcopy(self._review(plan,evidence,validation))
                    if mutation=='source':result['review_package']['source_report_id']='source-report-neighbor'
                    else:
                        receipt=result['acceptance_receipt'];receipt['created_at']=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
                        receipt['expires_at']=(datetime.now(timezone.utc)+timedelta(minutes=35)).isoformat()
                        receipt['replay_identity']=_digest({'package':receipt['review_package_sha256'],
                            'candidate':receipt['candidate_snapshot_id'],'invocation':receipt['review_invocation_id'],
                            'created_at':receipt['created_at']})
                    target=result['review_package'] if mutation=='source' else result['acceptance_receipt']
                    target['record_sha256']=_digest({k:v for k,v in target.items() if k!='record_sha256'})
                    return result
                self.reviewer.side_effect=altered;s=self.session();s.create('s');result=s.run_next()
                self.assertEqual('failed',result['batches']['a']['status']);self.assertFalse(self.applied)
        self.reviewer.side_effect=self._review

    def test_write_ahead_durability_failure_prevents_external_side_effect(self):
        for failing_call in (1,2):
            with self.subTest(failing_call=failing_call):
                self.state.joinpath('session.json').unlink(missing_ok=True);self.applied.clear()
                calls={'n':0};real_fsync=os.fsync
                def fail(fd):
                    calls['n']+=1
                    if calls['n']==failing_call:raise OSError('durability boundary')
                    return real_fsync(fd)
                with unittest.mock.patch('os.fsync',side_effect=fail):
                    with self.assertRaises(OSError):self.session().create('s')
                self.assertFalse(self.applied);self.assertEqual(self.head,
                    subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,text=True,capture_output=True).stdout.strip())

    def test_apply_and_commit_intents_are_durable_before_each_side_effect(self):
        for failing_call,expected_applies in ((3,0),(4,0),(7,1),(8,1)):
            with self.subTest(failing_call=failing_call):
                self.state.joinpath('session.json').unlink(missing_ok=True);self.applied.clear()
                s=self.session();s.create('s');calls={'n':0};real_fsync=os.fsync
                def fail(fd):
                    calls['n']+=1
                    if calls['n']==failing_call:raise OSError('durability boundary')
                    return real_fsync(fd)
                with unittest.mock.patch('os.fsync',side_effect=fail):
                    with self.assertRaises(OSError):s.run_next()
                self.assertEqual(expected_applies,len(self.applied));self.assertEqual(self.head,
                    subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,text=True,capture_output=True).stdout.strip())

    def test_correction_generation_preserves_historical_provenance(self):
        self.reviewer.side_effect=None;calls={'n':0}
        def review(plan,evidence,validation):
            calls['n']+=1
            if calls['n']==1:return {'verdict':'correction_required'}
            return self._review(plan,evidence,validation)
        self.reviewer.side_effect=review
        def correct(plan,evidence,validation,verdict,correction_cycle):
            nodes=copy.deepcopy(evidence['nodes']);nodes[0]['frozen_postimage']['sha256']='2'*64
            diff='corrected exact diff\n';generation=evidence['candidate_generation']+1
            snapshot='candidate-snapshot-'+_digest({'head':self.head,'scope':evidence['scope'],
                'generation':generation,'nodes':nodes})
            return {'status':'corrected','candidate_generation':generation,'head':self.head,
                'scope':evidence['scope'],'nodes':nodes,'exact_diff':diff,
                'exact_diff_sha256':hashlib.sha256(diff.encode()).hexdigest(),
                'mutation_manifest_sha256':_digest(nodes),'candidate_snapshot_id':snapshot}
        s=HistoricalCleanupSession(repository=self.repo,state_root=self.state,inventory=self.inventory,
            plans=[{'batch_id':'a','paths':['a.py']}],expected_head=self.head,
            expected_status_sha256=self.status,validator=self.validator,reviewer=self.reviewer,
            applier=self.applier,committer=self.committer,broad_validator=self.broad,
            attention=self.attention,corrector=correct,candidate_verifier=self._verify)
        s.create('s');result=s.run_next();generation=result['batches']['a']['candidate_generations'][0]
        self.assertEqual(1,generation['generation']);self.assertEqual('accepted',result['batches']['a']['status'])
        self.assertTrue(generation['historical_provenance_sha256'])

    def test_end_to_end_consumes_genuine_worker_exchange_package_and_reviewer_acceptance(self):
        exchange=WorkerExchange('fawkes',root=self.root/'exchange')
        prepared={}
        coordinator={'worker_id':'fawkes-development','role':'coordination',
            'identity_status':'verified','charter_version':'1.0'}
        reviewer={'worker_id':'independent-reviewer','role':'reviewer',
            'identity_status':'rider_attested','charter_version':'1.0'}
        def authority(scope,sender,recipient=None):
            value={'decision':'authorized','instance_id':'fawkes','task_scope_id':scope,
                'sender_worker_id':sender,'authorization_reference':'historical-e2e',
                'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()}
            if recipient:value['recipient_worker_id']=recipient
            return value
        def validate(plan,evidence):
            exact_changes=[{'path':item['path'],'before_node_binding':{
                'head_preimage':item['head_preimage'],'frozen_postimage':item['frozen_postimage']}}
                for item in evidence['nodes']]
            retention={'record_type':'codex_candidate_retention_receipt',
                'status':'awaiting_independent_review','applied_paths':[],
                'candidate_snapshot_id':evidence['candidate_snapshot_id'],
                'exact_change_evidence_sha256':_digest(exact_changes),'creates_authority':False}
            retention['record_sha256']=_digest(retention)
            scope='historical-e2e-review'
            source=exchange.create_report(task_scope_id=scope,sender=coordinator,
                authority=authority(scope,coordinator['worker_id']),sections=[
                    {'section_id':'historical-evidence','title':'Historical evidence',
                     'content':json.dumps(evidence,sort_keys=True,separators=(',',':'))},
                    {'section_id':'exact-change-evidence','title':'Exact change evidence',
                     'content':json.dumps(exact_changes,sort_keys=True,separators=(',',':'))},
                    {'section_id':'candidate-retention-receipt','title':'Candidate retention',
                     'content':json.dumps(retention,sort_keys=True,separators=(',',':'))}],
                claims=[{'claim_id':'exact','area':'development','statement':'Exact historical candidate.',
                    'maturity':'in_development','change_class':'software_system'},
                    {'claim_id':'safe','area':'development','statement':'Guarded application only.',
                    'maturity':'in_development','change_class':'software_system'}])
            package=exchange.compose_package(report_id=source['report_id'],recipient=reviewer,
                authority=authority(scope,coordinator['worker_id'],reviewer['worker_id']),
                included_section_ids=['historical-evidence','exact-change-evidence',
                                      'candidate-retention-receipt'])
            prepared.update(source=source,package=package,retention=retention,
                            exact_changes=exact_changes,scope=scope)
            preimages=_digest([{'path':item['path'],'before_node_binding':item['before_node_binding']}
                for item in exact_changes])
            return {'status':'passed','campaign_id':'campaign-a','builder_package_id':'builder-package-a',
                'review_package_id':package['package_id'],'source_report_id':source['report_id'],
                'candidate_retention_receipt_sha256':retention['record_sha256'],
                'exact_change_evidence_sha256':_digest(exact_changes),
                'authoritative_preimages_sha256':preimages,
                'acceptance_condition_ids':['exact','safe']}
        def review(plan,evidence,validation):
            package=prepared['package'];scope=prepared['scope']
            transport=authority(scope,coordinator['worker_id'],reviewer['worker_id'])
            delivery=exchange.record_delivery(package_id=package['package_id'],authority=transport,
                adapter_id='historical-test-reviewer',adapter_version='1',status='delivered',
                delivery_reference='deterministic-e2e')
            verification=exchange.record_verification(package_id=package['package_id'],recipient=reviewer,
                authority=transport,status='accepted',checked_claim_ids=['exact','safe'],
                evidence_references=[{'reference_id':prepared['source']['report_id']}],
                method='deterministic canonical package validation',material_reliance=True,
                relied_source_section_ids=['historical-evidence','exact-change-evidence'])
            returned=exchange.create_return_report(source_package_id=package['package_id'],
                task_scope_id=scope,sender=reviewer,
                authority=authority(scope,reviewer['worker_id']),
                sections=[{'section_id':'verdict','title':'Verdict','content':'Accepted.'}])
            response={'review_status':'pass','recipient':reviewer,
                'acceptance_condition_ids_satisfied':['exact','safe']}
            receipt=independent_review_acceptance_receipt(response=response,campaign_id='campaign-a',
                package=package,candidate_snapshot_id=evidence['candidate_snapshot_id'],
                invocation_id='historical-e2e-invocation',reviewer=reviewer,return_report=returned,
                delivery_receipt_id=delivery['delivery_receipt_id'],
                verification_receipt_id=verification['verification_receipt_id'],transport_authority={
                    'builder_package_id':'builder-package-a',
                    'mutation_manifest_sha256':evidence['mutation_manifest_sha256'],
                    'allowed_scope_sha256':evidence['scope_sha256'],
                    'candidate_retention_receipt_sha256':prepared['retention']['record_sha256']})
            return {'verdict':'accepted','acceptance_receipt':receipt,'review_report':returned,
                'review_package':package,
                'delivery_receipt':delivery,
                'verification_receipt':verification}
        session=HistoricalCleanupSession(repository=self.repo,state_root=self.state,inventory=self.inventory,
            plans=[{'batch_id':'a','paths':['a.py']}],expected_head=self.head,
            expected_status_sha256=self.status,validator=validate,reviewer=review,
            applier=self.applier,committer=self.committer,broad_validator=self.broad,
            attention=self.attention,candidate_verifier=self.candidate_verifier)
        session.create('canonical-e2e');result=session.run_next()
        self.assertEqual('accepted',result['batches']['a']['status'],result)
        self.assertEqual(prepared['source']['report_id'],prepared['package']['source_report_id'])
        self.assertEqual(1,len(self.applied));self.assertNotEqual(self.head,result['head'])

if __name__=='__main__':unittest.main()

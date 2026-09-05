import hashlib, json, os, subprocess, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.runtime.git_commit_transaction import GitCommitTransaction
from src.runtime.codex_development_campaign import (
    DevelopmentCampaignStore, _ProtectedGitGuard, _PROTECTED_GIT_GUARD_SECRET,
)


class GitCommitTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=self.root/'repo';self.repo.mkdir()
        subprocess.run(['git','init','-q'],cwd=self.repo,check=True)
        subprocess.run(['git','config','user.email','test@example.invalid'],cwd=self.repo,check=True)
        subprocess.run(['git','config','user.name','Test'],cwd=self.repo,check=True)
        (self.repo/'a.py').write_text('old\n');(self.repo/'other.py').write_text('base\n')
        subprocess.run(['git','add','a.py','other.py'],cwd=self.repo,check=True)
        subprocess.run(['git','commit','-qm','base'],cwd=self.repo,check=True)
        self.parent=self.git('rev-parse','HEAD');(self.repo/'a.py').write_text('new\n')
        (self.repo/'other.py').write_text('unrelated dirty\n')
        self.state=self.root/'state';self.state.mkdir();self.owner=GitCommitTransaction(self.repo,self.state)
    def git(self,*args):return subprocess.run(['git',*args],cwd=self.repo,check=True,text=True,
        capture_output=True).stdout.strip()
    def prepared(self):return self.owner.prepare(operation_id='operation-a',
        expected_parent_head=self.parent,reviewed_tree_sha256='1'*64,scope=['a.py'],
        exact_diff_sha256='2'*64,mutation_manifest_sha256='3'*64,
        review_receipt_sha256='4'*64,message='Historical cleanup: a')
    def application_receipt(self, **changes):
        value={"schema_version":1,
          "record_type":"codex_post_review_authoritative_application_receipt",
          "status":"applied_verified_after_review","operation_id":"operation-a",
          "transaction_record_sha256":"5"*64,"application_count":1,
          "review_acceptance_receipt_sha256":"4"*64,
          "applied_paths":["a.py"],"binding":{"campaign_id":"campaign",
            "candidate_snapshot_id":"candidate-snapshot-"+"6"*64,
            "mutation_manifest_sha256":"3"*64,"review_package_id":"package",
            "review_acceptance_receipt_sha256":"4"*64,
            "authorized_scope_sha256":"7"*64,
            "expected_repository_head":self.parent},
          "creates_authority":False,"creates_continuing_authority":False}
        value["reviewed_commit_projection"]=self.owner.reviewed_application_projection(
          operation_id="operation-a",expected_parent_head=self.parent,scope=["a.py"],
          review_receipt_sha256="4"*64)
        value.update(changes);value["record_sha256"]=hashlib.sha256(json.dumps(value,
          sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest();return value
    def reviewed_prepared(self,receipt=None):
        receipt=receipt or self.application_receipt();projection=receipt["reviewed_commit_projection"]
        return self.owner.prepare_reviewed_application(terminal_application_receipt=receipt,
          operation_id='operation-a',expected_parent_head=self.parent,
          reviewed_tree_sha256=projection["expected_tree"],scope=['a.py'],
          exact_diff_sha256=projection["expected_diff_sha256"],
          mutation_manifest_sha256='3'*64,review_receipt_sha256='4'*64,
          message=projection["message"])
    def campaign_record(self,receipt,expires=None):
        immutable={"maximum_duration_seconds":3600,"maximum_worker_turns":2,
          "maximum_reviewer_turns":4,"maximum_provider_turns":6,"maximum_cost_units":6,
          "maximum_correction_cycles":2,"maximum_iterations":3,
          "created_at":datetime.now(timezone.utc).isoformat(),
          "expires_at":expires or (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
          "contract":"conservative-provider-reservation-failed-safe-v0.1"}
        budget={**immutable,"consumed_worker_turns":1,"consumed_reviewer_turns":2,
          "consumed_provider_turns":3,"consumed_cost_units":3,"consumed_correction_cycles":0,
          "provider_action":None,"provider_actions":[],"budget_sha256":hashlib.sha256(json.dumps(
          immutable,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()}
        value={"campaign_id":receipt["binding"]["campaign_id"],
          "status":"reviewed_application_completed","stepwise_v01":True,
          "state_revision":1,
          "execution_budget_v01":budget,"creates_authority":False,
          "creates_continuing_authority":False}
        value["record_sha256"]=hashlib.sha256(json.dumps(value,sort_keys=True,
          separators=(",",":"),ensure_ascii=False).encode()).hexdigest();return value
    def protected(self, campaign, operation_id="operation-a"):
        store=DevelopmentCampaignStore("fawkes",root=self.root/"campaign-store")
        store.load=lambda campaign_id: campaign
        handle=(self.state/"test-campaign-protection.lock").open("a+b")
        self.addCleanup(handle.close)
        guard=_ProtectedGitGuard(_PROTECTED_GIT_GUARD_SECRET,
          campaign_id=campaign["campaign_id"],record_sha256=campaign["record_sha256"],
          state_revision=campaign.get("state_revision",1),operation_id=operation_id,handle=handle)
        return {"campaign_store":store,"campaign_protection":guard}
    def test_prepare_creates_one_deterministic_object_without_advancing_ref_or_index(self):
        index_tree=self.git('write-tree');first=self.prepared();second=self.prepared()
        self.assertEqual(first['prepared_commit'],second['prepared_commit'])
        self.assertEqual(self.parent,self.git('rev-parse','HEAD'))
        self.assertEqual(index_tree,self.git('write-tree'))
        self.assertIn('other.py',self.git('status','--porcelain=v2','--untracked-files=all'))
    def test_safe_retry_and_exactly_one_compare_and_swap_commit(self):
        prepared=self.prepared();self.assertEqual('prepared',self.owner.reconcile(prepared)['status'])
        receipt=self.owner.advance(prepared);self.assertEqual('committed',receipt['status'])
        self.assertEqual(receipt,self.owner.advance(prepared));self.assertEqual(prepared['prepared_commit'],self.git('rev-parse','HEAD'))
        self.assertEqual(self.parent,self.git('rev-parse','HEAD^'))
    def test_neighboring_ref_and_forged_prepared_records_fail_closed(self):
        prepared=self.prepared();(self.repo/'neighbor.py').write_text('neighbor\n')
        subprocess.run(['git','add','neighbor.py'],cwd=self.repo,check=True);subprocess.run(['git','commit','-qm','neighbor'],cwd=self.repo,check=True)
        with self.assertRaises(RuntimeError):self.owner.advance(prepared)
        forged=json.loads(json.dumps(prepared));forged['prepared_commit']='f'*40
        with self.assertRaises(PermissionError):self.owner.reconcile(forged)
    def test_ref_advance_rejects_changed_normal_index(self):
        prepared=self.prepared();subprocess.run(['git','add','other.py'],cwd=self.repo,check=True)
        with self.assertRaises(RuntimeError):self.owner.advance(prepared)
    def test_reviewed_commit_requires_exact_terminal_application(self):
        with self.assertRaises(PermissionError):self.owner.prepare_reviewed_application(
          terminal_application_receipt={"verdict":"accepted"},operation_id='operation-a',
          expected_parent_head=self.parent,reviewed_tree_sha256='1'*64,scope=['a.py'],
          exact_diff_sha256='2'*64,mutation_manifest_sha256='3'*64,
          review_receipt_sha256='4'*64,message='bad')
    def test_reviewed_commit_rejects_unbound_tree_diff_and_metadata(self):
        receipt=self.application_receipt();projection=receipt["reviewed_commit_projection"]
        base={"terminal_application_receipt":receipt,"operation_id":"operation-a",
          "expected_parent_head":self.parent,"reviewed_tree_sha256":projection["expected_tree"],
          "scope":["a.py"],"exact_diff_sha256":projection["expected_diff_sha256"],
          "mutation_manifest_sha256":"3"*64,"review_receipt_sha256":"4"*64,
          "message":projection["message"]}
        for key,value in (("reviewed_tree_sha256","1"*40),("exact_diff_sha256","2"*64),
                          ("message","neighbor metadata")):
            with self.subTest(key=key),self.assertRaises(PermissionError):
                self.owner.prepare_reviewed_application(**{**base,key:value})
    def test_reviewed_application_commit_is_exactly_once(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        legacy=self.owner.advance_reviewed_application(prepared,receipt)
        self.assertEqual("failed_safe",legacy["status"])
        self.assertFalse(legacy["creates_continuing_authority"])
        with self.assertRaisesRegex(PermissionError,"canonical eligibility"):
            self.owner.advance(prepared)
        self.assertEqual(self.git('rev-list','--count',self.parent+'..HEAD'),'0')

    def eligible_receipt(self, receipt, *, expires=None, **changes):
        value={"schema_version":1,
          "record_type":"canonical_reviewed_application_git_eligibility_v01",
          "status":"available","campaign_id":"campaign",
          "application_operation_id":receipt["operation_id"],
          "application_transaction_sha256":receipt["transaction_record_sha256"],
          "review_acceptance_receipt_sha256":receipt["review_acceptance_receipt_sha256"],
          "commit_operation_id":receipt["operation_id"],
          "expected_parent_head":receipt["binding"]["expected_repository_head"],
          "scope_sha256":receipt["binding"]["authorized_scope_sha256"],
          "mutation_manifest_sha256":receipt["binding"]["mutation_manifest_sha256"],
          "expected_tree":receipt["reviewed_commit_projection"]["expected_tree"],
          "expected_diff_sha256":receipt["reviewed_commit_projection"]["expected_diff_sha256"],
          "expires_at":expires or (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
          "budget_sha256":"9"*64,"consumption_identity":"git-eligibility-test",
          "creates_authority":False,"creates_continuing_authority":False}
        value.update(changes);value["record_sha256"]=hashlib.sha256(json.dumps(value,
          sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        path=self.state/"eligibility.json";path.write_text(json.dumps(value))
        result={**receipt,"canonical_git_eligibility_reference":{
          "record_type":"canonical_git_eligibility_reference_v01","path":str(path.resolve()),
          "record_sha256":value["record_sha256"],"consumption_identity":value["consumption_identity"]}}
        result.pop("record_sha256",None);result["record_sha256"]=hashlib.sha256(json.dumps(result,
          sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest();return result

    def test_campaign_eligibility_is_checked_at_atomic_ref_boundary(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        campaign=self.campaign_record(receipt)
        with self.assertRaisesRegex(PermissionError,"canonical campaign protection"):
            self.owner.advance_campaign_reviewed_application(prepared,receipt)
        self.assertEqual(self.parent,self.git("rev-parse","HEAD"))
        committed=self.owner.advance_campaign_reviewed_application(prepared,receipt,**self.protected(campaign))
        self.assertEqual(committed["status"],"committed")
        self.assertFalse(committed["creates_continuing_authority"])
        self.assertEqual(self.owner.advance_campaign_reviewed_application(
            prepared,receipt,**self.protected(campaign)),committed)
        self.assertFalse(list(self.state.glob("*eligibility*.json")))

    def test_stale_campaign_revision_is_rejected_at_protected_cas_boundary(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        campaign=self.campaign_record(receipt);protected=self.protected(campaign)
        campaign["state_revision"]+=1;campaign.pop("record_sha256")
        campaign["record_sha256"]=hashlib.sha256(json.dumps(campaign,
          sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaisesRegex(PermissionError,"stale or mismatched"):
            self.owner.advance_campaign_reviewed_application(prepared,receipt,**protected)
        self.assertEqual(self.parent,self.git("rev-parse","HEAD"))

    def test_consumed_eligibility_cannot_authorize_neighboring_ref_advance(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        campaign=self.campaign_record(receipt)
        self.owner.advance_campaign_reviewed_application(prepared,receipt,**self.protected(campaign))
        neighboring={**prepared,"operation_id":"neighbor-operation"}
        neighboring.pop("record_sha256",None);neighboring["record_sha256"]=hashlib.sha256(
            json.dumps(neighboring,sort_keys=True,separators=(",",":"),
                ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(PermissionError):
            self.owner.advance_campaign_reviewed_application(neighboring,receipt,**self.protected(campaign))

    def test_expired_or_neighboring_campaign_eligibility_cannot_advance(self):
        receipt=self.application_receipt()
        prepared=self.reviewed_prepared(receipt)
        expired=self.campaign_record(receipt,
                    (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
        with self.assertRaises(PermissionError):
            self.owner.advance_campaign_reviewed_application(prepared,receipt,
                **self.protected(expired))
        self.assertEqual(self.parent,self.git('rev-parse','HEAD'))
        neighboring=self.application_receipt();neighbor_prepared=self.reviewed_prepared(neighboring)
        neighboring_campaign=self.campaign_record(neighboring)
        neighboring_campaign["campaign_id"]="neighbor"
        neighboring_campaign.pop("record_sha256",None)
        neighboring_campaign["record_sha256"]=hashlib.sha256(json.dumps(neighboring_campaign,
            sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(PermissionError):
            self.owner.advance_campaign_reviewed_application(neighbor_prepared,neighboring,
                **self.protected(neighboring_campaign))

    def test_clock_advance_inside_cas_lock_expires_eligibility_durably(self):
        receipt=self.application_receipt()
        prepared=self.reviewed_prepared(receipt)
        campaign=self.campaign_record(receipt)
        late=lambda: datetime.now(timezone.utc)+timedelta(hours=2)
        with self.assertRaisesRegex(PermissionError,"expired"):
            self.owner.advance_campaign_reviewed_application(prepared,receipt,
                clock=late,**self.protected(campaign))
        self.assertEqual(self.parent,self.git('rev-parse','HEAD'))
        self.assertFalse(list(self.state.glob("*eligibility*.json")))
        replay=self.owner.advance_campaign_reviewed_application(prepared,receipt,
            **self.protected(campaign))
        self.assertEqual(replay["status"],"failed_safe")
        self.assertEqual(replay["reason"],"pre_cas_restart_observe_only")

    def test_expiration_during_commit_preparation_is_rechecked_immediately_before_cas(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        expires=datetime.now(timezone.utc)+timedelta(minutes=5)
        campaign=self.campaign_record(receipt,expires.isoformat())
        crossed_preparation_boundary={"value":False};original=self.owner._run
        def preparation_barrier(args, **kwargs):
            result=original(args, **kwargs)
            if args and args[0] in {"rev-parse","status","write-tree","diff-tree"}:
                crossed_preparation_boundary["value"]=True
            return result
        def authoritative_clock():
            if crossed_preparation_boundary["value"]:
                return expires+timedelta(microseconds=1)
            return expires-timedelta(microseconds=1)
        self.owner._run=preparation_barrier
        with self.assertRaisesRegex(PermissionError,"expired"):
            self.owner.advance_campaign_reviewed_application(prepared,receipt,
                clock=authoritative_clock,**self.protected(campaign))
        self.assertTrue(crossed_preparation_boundary["value"])
        self.assertEqual(self.parent,self.git("rev-parse","HEAD"))

    def test_post_cas_crash_reconciles_by_observation_without_update_ref(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        campaign=self.campaign_record(receipt);original=self.owner._run
        def crash_after_cas(args, **kwargs):
            result=original(args, **kwargs)
            if args and args[0]=="update-ref":
                raise RuntimeError("injected crash after CAS")
            return result
        self.owner._run=crash_after_cas
        with self.assertRaisesRegex(RuntimeError,"injected crash"):
            self.owner.advance_campaign_reviewed_application(
                prepared,receipt,**self.protected(campaign))
        self.assertEqual(prepared["prepared_commit"],self.git("rev-parse","HEAD"))
        restarted=GitCommitTransaction(self.repo,self.state);calls=[]
        restarted_run=restarted._run
        def observe_only(args, **kwargs):
            if args and args[0]=="update-ref":calls.append(args)
            return restarted_run(args, **kwargs)
        restarted._run=observe_only
        terminal=restarted.reconcile_campaign_reviewed_application(
            operation_id=prepared["operation_id"],
            terminal_application_receipt=receipt,**self.protected(campaign))
        self.assertEqual("committed",terminal["status"]);self.assertEqual([],calls)
        self.assertFalse(terminal["creates_continuing_authority"])
        self.assertEqual(terminal,restarted.reconcile_campaign_reviewed_application(
            operation_id=prepared["operation_id"],
            terminal_application_receipt=receipt,**self.protected(campaign)))
        self.assertEqual([],calls)

    def test_reviewed_commit_rejects_neighbor_drift_after_terminal_receipt(self):
        receipt=self.application_receipt()
        (self.repo/'other.py').write_text('changed after terminal receipt\n')
        with self.assertRaisesRegex(PermissionError,'receipt-owned|projection drift'):
            self.reviewed_prepared(receipt)

    def test_reviewed_commit_rejects_untracked_mode_and_index_neighbor_drift(self):
        for kind in ('untracked','mode','index'):
            with self.subTest(kind=kind):
                receipt=self.application_receipt()
                if kind=='untracked':(self.repo/'new-neighbor.txt').write_text('new\n')
                elif kind=='mode':(self.repo/'other.py').chmod(0o755)
                else:subprocess.run(['git','add','other.py'],cwd=self.repo,check=True)
                with self.assertRaisesRegex(PermissionError,'receipt-owned|projection drift'):
                    self.reviewed_prepared(receipt)
                if (self.repo/'new-neighbor.txt').exists():(self.repo/'new-neighbor.txt').unlink()
                (self.repo/'other.py').chmod(0o644)
                subprocess.run(['git','reset','-q','HEAD','--','other.py'],cwd=self.repo,check=True)

    def test_reviewed_advance_rechecks_receipt_owned_neighbor_state(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        (self.repo/'other.py').write_text('changed after commit preparation\n')
        with self.assertRaisesRegex(PermissionError,'receipt-owned|campaign-owned synchronous route'):
            self.owner.advance_reviewed_application(prepared,receipt)
        self.assertEqual(self.parent,self.git('rev-parse','HEAD'))

    def test_protected_cas_revalidates_complete_in_scope_postimage_after_intent(self):
        mutations=(
          ("content",lambda path:path.write_text("post-preparation drift\n")),
          ("delete",lambda path:path.unlink()),
          ("mode",lambda path:path.chmod(0o755)),
          ("symlink",lambda path:(path.unlink(),os.symlink("other.py",path))),
        )
        for index,(kind,mutate) in enumerate(mutations):
            with self.subTest(kind=kind):
                if index:
                    self.tearDown();self.setUp()
                receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
                campaign=self.campaign_record(receipt);calls={"cas":0,"mutated":False}
                original_run=self.owner._run
                def count_cas(args,**kwargs):
                    if args and args[0]=="update-ref":calls["cas"]+=1
                    return original_run(args,**kwargs)
                self.owner._run=count_cas
                from src.runtime import git_commit_transaction as transaction_module
                original_write=transaction_module.write_durable_record
                def mutation_barrier(path,value,**kwargs):
                    original_write(path,value,**kwargs)
                    if (not calls["mutated"]
                            and value.get("record_type")=="reviewed_git_cas_intent_v01"
                            and value.get("status")=="cas_invocation_started"):
                        calls["mutated"]=True;mutate(self.repo/"a.py")
                with patch.object(transaction_module,"write_durable_record",mutation_barrier), \
                        self.assertRaisesRegex(PermissionError,"in-scope postimage"):
                    self.owner.advance_campaign_reviewed_application(
                        prepared,receipt,**self.protected(campaign))
                self.assertTrue(calls["mutated"])
                self.assertEqual(calls["cas"],0)
                self.assertEqual(self.parent,self.git("rev-parse","HEAD"))

    def test_valid_protected_cas_revalidation_still_advances_exactly_once(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        campaign=self.campaign_record(receipt);calls=[];original=self.owner._run
        def count_cas(args,**kwargs):
            if args and args[0]=="update-ref":calls.append(tuple(args))
            return original(args,**kwargs)
        self.owner._run=count_cas
        committed=self.owner.advance_campaign_reviewed_application(
            prepared,receipt,**self.protected(campaign))
        self.assertEqual(committed["status"],"committed")
        self.assertEqual(len(calls),1)
        self.assertEqual(prepared["prepared_commit"],self.git("rev-parse","HEAD"))
        self.assertFalse(committed["creates_continuing_authority"])
    def test_reviewed_commit_rejects_neighboring_or_tampered_receipt(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        neighbor=self.application_receipt(operation_id='neighbor')
        with self.assertRaises(PermissionError):
            self.owner.advance_reviewed_application(prepared,neighbor)
        tampered=dict(receipt);tampered['application_count']=2
        with self.assertRaises(PermissionError):
            self.owner.advance_reviewed_application(prepared,tampered)


if __name__=='__main__':unittest.main()

import hashlib, json, subprocess, tempfile, unittest
from pathlib import Path

from src.runtime.git_commit_transaction import GitCommitTransaction


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
        committed=self.owner.advance_reviewed_application(prepared,receipt)
        self.assertEqual(committed["status"],"committed")
        self.assertEqual(self.owner.advance_reviewed_application(prepared,receipt),committed)
        self.assertEqual(self.git('rev-list','--count',self.parent+'..HEAD'),'1')
    def test_reviewed_commit_rejects_neighboring_or_tampered_receipt(self):
        receipt=self.application_receipt();prepared=self.reviewed_prepared(receipt)
        neighbor=self.application_receipt(operation_id='neighbor')
        with self.assertRaises(PermissionError):
            self.owner.advance_reviewed_application(prepared,neighbor)
        tampered=dict(receipt);tampered['application_count']=2
        with self.assertRaises(PermissionError):
            self.owner.advance_reviewed_application(prepared,tampered)


if __name__=='__main__':unittest.main()

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


if __name__=='__main__':unittest.main()

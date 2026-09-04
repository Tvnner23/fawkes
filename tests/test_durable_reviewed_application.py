from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import hashlib, json, os, subprocess, tempfile, threading, unittest

from src.runtime.durable_reviewed_application import (
    DurableReviewedApplication, _node, unrelated_workspace_sha256,
)
from src.runtime.git_commit_transaction import GitCommitTransaction


def git(root,*args):
    return subprocess.run(["git",*args],cwd=root,text=True,capture_output=True,check=True).stdout.strip()


class DurableReviewedApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.repo=self.root/"repo";self.repo.mkdir();git(self.repo,"init","-q","-b","synthetic")
        git(self.repo,"config","user.name","Fixture");git(self.repo,"config","user.email","f@invalid")
        (self.repo/"a.bin").write_bytes(b"before-a\x00");(self.repo/"b.txt").write_text("before-b\n")
        git(self.repo,"add","a.bin","b.txt");git(self.repo,"commit","-qm","base")
        self.state=self.root/"state";self.now=datetime.now(timezone.utc)
        self.scope=["a.bin","b.txt"]
        self.binding={"campaign_id":"campaign","task_scope_id":"task",
          "worker_invocation_id":"worker-invocation","generation":1,
          "candidate_retention_receipt_sha256":"1"*64,
          "candidate_snapshot_id":"candidate-snapshot-"+"2"*64,
          "mutation_manifest_sha256":"3"*64,"review_package_id":"review-package",
          "review_package_sha256":"4"*64,"review_acceptance_receipt_sha256":"5"*64,
          "review_acceptance_record_type":"codex_independent_review_acceptance_receipt",
          "reviewer_worker_id":"independent-reviewer","review_invocation_id":"review-invocation",
          "authorized_scope_sha256":"6"*64,"expected_repository_head":git(self.repo,"rev-parse","HEAD"),
          "expected_repository_status_sha256":unrelated_workspace_sha256(self.repo,self.scope)}
        self.paths=[self.entry("a.bin",b"after-a\x00",0o644),self.entry("b.txt",b"after-b\n",0o644)]

    def tearDown(self):self.temp.cleanup()
    def entry(self,path,post,mode):
        target=self.repo/path;pre=_node(target);return {"path":path,"preimage":pre,
          "postimage":{"type":"regular","mode":mode,"byte_length":len(post),
                       "sha256":hashlib.sha256(post).hexdigest()},
          "preimage_body":target.read_bytes() if pre["type"]=="regular" else None,"postimage_body":post}
    def owner(self,**kwargs):return DurableReviewedApplication(self.repo,self.state,clock=lambda:self.now,**kwargs)
    def prepare(self,owner=None,operation="operation"):
        owner=owner or self.owner();return owner.prepare(operation_id=operation,binding=self.binding,
          paths=self.paths,review_expires_at=(self.now+timedelta(minutes=5)).isoformat())

    def test_crash_before_intent_persistence_mutates_nothing(self):
        bad=[{**self.paths[0],"postimage_body":b"wrong"}]
        with self.assertRaises(ValueError):self.owner().prepare(operation_id="bad",binding=self.binding,
            paths=bad,review_expires_at=(self.now+timedelta(minutes=5)).isoformat())
        self.assertEqual((self.repo/"a.bin").read_bytes(),b"before-a\x00")
        self.assertFalse((self.state/"bad"/"transaction.json").exists())

    def test_crash_after_intent_before_first_mutation(self):
        owner=self.owner(crash_hook=lambda point,path:(_ for _ in ()).throw(KeyboardInterrupt()) if point=="after_intent" else None)
        with self.assertRaises(KeyboardInterrupt):self.prepare(owner)
        resumed=self.owner();state=resumed.execute_or_resume("operation")
        self.assertEqual(state["state"],"completed");self.assertEqual(state["application_count"],1)

    def _fork_crash(self,crash_path):
        self.prepare();pid=os.fork()
        if pid==0:
            owner=self.owner(crash_hook=lambda point,path:os._exit(87) if point=="after_path" and path==crash_path else None)
            owner.execute_or_resume("operation");os._exit(88)
        _,status=os.waitpid(pid,0);self.assertEqual(os.waitstatus_to_exitcode(status),87)

    def test_process_death_after_each_path_reconciles_exactly(self):
        for path in self.scope:
            with self.subTest(path=path):
                self.tearDown();self.setUp();self._fork_crash(path)
                state=self.owner().reconcile("operation")
                expected="rolled_back" if path=="a.bin" else "completed"
                self.assertEqual(state["state"],expected)
                self.assertEqual(state["application_count"],1)

    def test_fully_unapplied_recovery_executes_once(self):
        self.prepare();state=self.owner().reconcile("operation")
        self.assertEqual((state["state"],state["application_count"]),("completed",1))

    def test_fully_applied_recovery_finalizes_without_writes(self):
        self.prepare()
        for item in self.paths:
            target=self.repo/item["path"];target.write_bytes(item["postimage_body"]);target.chmod(item["postimage"]["mode"])
        called=[];state=self.owner(replace=lambda a,b:called.append((a,b))).reconcile("operation")
        self.assertEqual(state["state"],"completed");self.assertEqual(called,[])

    def test_partial_exact_state_rolls_back_and_is_terminal(self):
        self.prepare();(self.repo/"a.bin").write_bytes(b"after-a\x00")
        state=self.owner().reconcile("operation");self.assertEqual(state["state"],"rolled_back")
        self.assertEqual((self.repo/"a.bin").read_bytes(),b"before-a\x00")
        self.assertEqual(self.owner().reconcile("operation")["revision"],state["revision"])

    def test_drifted_path_quarantines_without_overwrite(self):
        self.prepare();(self.repo/"a.bin").write_bytes(b"neighbor")
        state=self.owner().reconcile("operation");self.assertEqual(state["state"],"quarantined")
        self.assertEqual((self.repo/"a.bin").read_bytes(),b"neighbor")

    def test_candidate_material_drift_is_rejected(self):
        self.prepare();material=next((self.state/"operation"/"material").iterdir());material.write_bytes(b"tampered")
        with self.assertRaises(PermissionError):self.owner().execute_or_resume("operation")
        self.assertEqual((self.repo/"a.bin").read_bytes(),b"before-a\x00")

    def test_authoritative_preimage_drift_quarantines(self):
        self.prepare();(self.repo/"a.bin").write_bytes(b"drift")
        self.assertEqual(self.owner().execute_or_resume("operation")["state"],"quarantined")

    def test_neighboring_worktree_drift_quarantines(self):
        self.prepare();(self.repo/"neighbor.txt").write_text("drift")
        self.assertEqual(self.owner().execute_or_resume("operation")["state"],"quarantined")
        self.assertEqual((self.repo/"a.bin").read_bytes(),b"before-a\x00")

    def test_added_deleted_executable_empty_and_binary(self):
        added=self.entry("new.bin",b"\x00\xff",0o755);empty=self.entry("empty",b"",0o644)
        deleted=self.entry("b.txt",b"unused",0o644);deleted["postimage"]={"type":"missing"};deleted["postimage_body"]=None
        paths=sorted([added,empty,deleted],key=lambda item:item["path"]);scope=[x["path"] for x in paths]
        binding={**self.binding,"expected_repository_status_sha256":unrelated_workspace_sha256(self.repo,scope)}
        owner=self.owner();owner.prepare(operation_id="kinds",binding=binding,paths=paths,
            review_expires_at=(self.now+timedelta(minutes=5)).isoformat())
        state=owner.execute_or_resume("kinds");self.assertEqual(state["state"],"completed")
        self.assertEqual((self.repo/"new.bin").read_bytes(),b"\x00\xff");self.assertEqual((self.repo/"new.bin").stat().st_mode&0o777,0o755)
        self.assertEqual((self.repo/"empty").read_bytes(),b"");self.assertFalse((self.repo/"b.txt").exists())

    def test_symlink_directory_traversal_and_substitution_rejected(self):
        for path in ("../escape","/absolute"):
            with self.subTest(path=path):
                item={**self.paths[0],"path":path}
                with self.assertRaises(PermissionError):self.owner().prepare(operation_id="escape"+str(len(path)),binding=self.binding,
                    paths=[item],review_expires_at=(self.now+timedelta(minutes=5)).isoformat())
        self.prepare();(self.repo/"a.bin").unlink();(self.repo/"a.bin").symlink_to("b.txt")
        self.assertEqual(self.owner().reconcile("operation")["state"],"quarantined")
        self.tearDown();self.setUp();(self.repo/"link-parent").symlink_to(self.repo)
        item={**self.paths[0],"path":"link-parent/escape.bin"}
        with self.assertRaises(PermissionError):self.owner().prepare(operation_id="link-parent",binding=self.binding,
            paths=[item],review_expires_at=(self.now+timedelta(minutes=5)).isoformat())

    def test_partial_rollback_removes_created_parent_directories(self):
        first=self.entry("a-new/deep/a.bin",b"new",0o644);second=self.paths[1]
        paths=sorted([first,second],key=lambda item:item["path"]);scope=[x["path"] for x in paths]
        binding={**self.binding,"expected_repository_status_sha256":unrelated_workspace_sha256(self.repo,scope)}
        owner=self.owner();owner.prepare(operation_id="directories",binding=binding,paths=paths,
            review_expires_at=(self.now+timedelta(minutes=5)).isoformat())
        (self.repo/"a-new/deep").mkdir(parents=True);(self.repo/"a-new/deep/a.bin").write_bytes(b"new")
        state=owner.reconcile("directories");self.assertEqual(state["state"],"rolled_back")
        self.assertFalse((self.repo/"a-new").exists())

    def test_mode_preserved(self):
        self.paths=[self.entry("a.bin",b"after-a\x00",0o700)];self.scope=["a.bin"]
        self.binding["expected_repository_status_sha256"]=unrelated_workspace_sha256(self.repo,self.scope)
        self.prepare();self.owner().execute_or_resume("operation")
        self.assertEqual((self.repo/"a.bin").stat().st_mode&0o777,0o700)

    def test_intent_and_progress_tampering_rejected(self):
        self.prepare();path=self.state/"operation"/"transaction.json";record=json.loads(path.read_text());record["state"]="completed";path.write_text(json.dumps(record))
        with self.assertRaises(PermissionError):self.owner().reconcile("operation")

    def test_neighboring_bindings_and_bare_verdict_rejected(self):
        fields=("campaign_id","candidate_snapshot_id","review_package_id","worker_invocation_id","reviewer_worker_id")
        for index,field in enumerate(fields):
            with self.subTest(field=field):
                binding={**self.binding,field:"neighbor"}
                owner=self.owner();owner.prepare(operation_id=f"neighbor-{index}",binding=binding,paths=self.paths,
                    review_expires_at=(self.now+timedelta(minutes=5)).isoformat())
                binding[field]="changed"
                with self.assertRaises(PermissionError):owner.prepare(operation_id=f"neighbor-{index}",binding=binding,paths=self.paths,
                    review_expires_at=(self.now+timedelta(minutes=5)).isoformat())
        bare={"verdict":"accepted"}
        with self.assertRaises(PermissionError):self.owner().prepare(operation_id="bare",binding=bare,paths=self.paths,
            review_expires_at=(self.now+timedelta(minutes=5)).isoformat())

    def test_expired_before_side_effect_fails_safe(self):
        owner=self.owner();owner.prepare(operation_id="expired",binding=self.binding,paths=self.paths,
            review_expires_at=(self.now-timedelta(seconds=1)).isoformat())
        state=owner.execute_or_resume("expired");self.assertEqual(state["state"],"failed_safe")
        self.assertEqual(state["application_count"],0)

    def test_expiry_after_side_effect_allows_only_rollback_or_finalize(self):
        self.prepare();(self.repo/"a.bin").write_bytes(b"after-a\x00");self.now+=timedelta(hours=1)
        state=self.owner().reconcile("operation");self.assertEqual(state["state"],"rolled_back")
        self.assertEqual(state["application_count"],0)

    def test_concurrent_execute_is_exactly_once(self):
        self.prepare();results=[]
        threads=[threading.Thread(target=lambda:results.append(self.owner().execute_or_resume("operation"))) for _ in range(4)]
        [t.start() for t in threads];[t.join() for t in threads]
        self.assertEqual({x["state"] for x in results},{"completed"});self.assertEqual({x["application_count"] for x in results},{1})

    def test_terminal_completion_and_rollback_reconcile_idempotently(self):
        self.prepare();complete=self.owner().execute_or_resume("operation")
        self.assertEqual(self.owner().reconcile("operation"),complete)
        self.tearDown();self.setUp();self.prepare();(self.repo/"a.bin").write_bytes(b"after-a\x00")
        rolled=self.owner().reconcile("operation");self.assertEqual(self.owner().reconcile("operation"),rolled)

    def test_terminal_receipt_drives_one_git_commit_without_index_pollution(self):
        self.prepare();self.owner().execute_or_resume("operation");receipt=self.owner().terminal_receipt("operation")
        index_before=git(self.repo,"ls-files","--stage")
        git_state=self.root/"git-state";git_state.mkdir()
        tx=GitCommitTransaction(self.repo,git_state);parent=git(self.repo,"rev-parse","HEAD")
        prepared=tx.prepare(operation_id="commit-operation",expected_parent_head=parent,
            reviewed_tree_sha256="reviewed-tree",scope=self.scope,exact_diff_sha256="diff",
            mutation_manifest_sha256="mutation",review_receipt_sha256=receipt["record_sha256"],message="Reviewed change")
        first=tx.advance(prepared);second=tx.advance(prepared)
        self.assertEqual(first["head"],second["head"]);self.assertEqual(git(self.repo,"rev-list","--count",parent+"..HEAD"),"1")
        self.assertEqual(git(self.repo,"ls-files","--stage"),index_before)

    def test_no_success_receipt_for_failure_and_runtime_external(self):
        self.prepare();(self.repo/"a.bin").write_bytes(b"drift")
        self.owner().reconcile("operation")
        with self.assertRaises(RuntimeError):self.owner().terminal_receipt("operation")
        self.assertFalse((self.repo/"state").exists());self.assertFalse((self.repo/"application-transaction").exists())


if __name__=="__main__":unittest.main()

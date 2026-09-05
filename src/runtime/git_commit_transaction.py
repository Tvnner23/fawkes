"""Idempotent local Git commit preparation and compare-and-swap advancement."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import subprocess
import tempfile
import fcntl
from datetime import datetime, timezone

from src.runtime.durable_reviewed_application import unrelated_workspace_sha256, write_durable_record


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()


def _file_node(path):
    path=Path(path)
    if not path.exists(): return {"state":"absent"}
    body=path.read_bytes()
    return {"state":"present","byte_length":len(body),
            "sha256":hashlib.sha256(body).hexdigest(),"mode":path.stat().st_mode&0o7777}


class GitCommitTransaction:
    """Prepare one immutable commit object, then advance one local branch by CAS."""
    def __init__(self, repository, state_root):
        self.repository=Path(repository).resolve();self.state_root=Path(state_root).resolve()
        if not self.state_root.is_dir() or self.repository==self.state_root or self.repository in self.state_root.parents:
            raise ValueError("Git transaction state must be an existing external directory")
        git_dir=subprocess.run(["git","rev-parse","--git-dir"],cwd=self.repository,check=True,
            text=True,capture_output=True).stdout.strip()
        self.git_dir=(self.repository/git_dir).resolve() if not Path(git_dir).is_absolute() else Path(git_dir).resolve()

    def _run(self, args, *, env=None, text=False, input=None):
        return subprocess.run(["git",*args],cwd=self.repository,check=True,capture_output=True,
            text=text,input=input,env=env)

    def _head(self): return self._run(["rev-parse","HEAD"],text=True).stdout.strip()

    def _branch_ref(self):
        return self._run(["symbolic-ref","HEAD"],text=True).stdout.strip()

    def _reviewed_preparation_path(self, prepared_commit):
        return self.state_root/f"reviewed-{prepared_commit}.json"

    def _status_sha256(self):
        return hashlib.sha256(self._run(["status","--porcelain=v2","--untracked-files=all"]).stdout).hexdigest()

    def _unrelated_status_sha256(self, paths):
        exclusions=[f":(exclude,top,literal){path}" for path in paths]
        value=self._run(["status","--porcelain=v1","-z","--untracked-files=all","--",".",*exclusions]).stdout
        tokens=value.split(b"\0");nodes=[];index=0
        while index < len(tokens) and tokens[index]:
            entry=tokens[index];index+=1
            status=entry[:2].decode("ascii");raw=entry[3:]
            if status[0] in "RC" or status[1] in "RC":
                if index >= len(tokens) or not tokens[index]: raise RuntimeError("malformed Git status")
                original=tokens[index];index+=1
            else: original=None
            path=os.fsdecode(raw);node_path=self.repository/path
            if node_path.is_symlink():
                target=os.readlink(node_path).encode();node={"type":"symlink","mode":node_path.lstat().st_mode&0o7777,
                    "length":len(target),"sha256":hashlib.sha256(target).hexdigest()}
            elif node_path.is_file():
                body=node_path.read_bytes();node={"type":"regular","mode":node_path.stat().st_mode&0o7777,
                    "length":len(body),"sha256":hashlib.sha256(body).hexdigest()}
            elif node_path.is_dir():
                node={"type":"directory","mode":node_path.stat().st_mode&0o7777}
            else: node={"type":"absent"}
            nodes.append({"status":status,"path":path,"original":os.fsdecode(original) if original else None,
                          "node":node})
        return _digest(nodes)

    def _index_identity(self):
        tree=self._run(["write-tree"],text=True).stdout.strip()
        return {"tree":tree}

    def _neighboring_repository_state(self, paths):
        value={"schema_version":1,"record_type":"reviewed_application_neighboring_repository_state",
            "branch_ref":self._branch_ref(),"normal_index_node":self._index_identity(),
            "unrelated_status_sha256":self._unrelated_status_sha256(paths),
            "unrelated_workspace_sha256":unrelated_workspace_sha256(self.repository,paths),
            "creates_authority":False}
        value["record_sha256"]=_digest(value);return value

    def _validate_neighboring_repository_state(self, projection, paths):
        expected=projection.get("neighboring_repository_state")
        if (not isinstance(expected,dict)
                or expected.get("record_type")!="reviewed_application_neighboring_repository_state"
                or expected.get("record_sha256")!=_digest(
                    {key:value for key,value in expected.items() if key!="record_sha256"})):
            raise PermissionError("receipt-owned neighboring repository state is malformed")
        if self._neighboring_repository_state(paths)!=expected:
            raise PermissionError("receipt-owned neighboring repository state drift")
        return expected

    def _paths(self, scope):
        values=[]
        for raw in scope:
            path=PurePosixPath(raw)
            if (not isinstance(raw,str) or not raw or path.is_absolute()
                    or any(part in {"",".",".."} for part in path.parts)
                    or path.as_posix()!=raw):
                raise ValueError("normalized commit scope is required")
            values.append(raw)
        result=tuple(sorted(set(values)))
        if not result or len(result)!=len(values): raise ValueError("unique commit scope is required")
        return result

    def _validate_prepared(self, prepared):
        transaction_type = prepared.get("transaction_type") if isinstance(prepared,dict) else None
        if (not isinstance(prepared,dict)
                or prepared.get("record_type")!="git_commit_transaction_prepared"
                or prepared.get("status")!="prepared"
                or transaction_type not in {"generic_git_commit", "reviewed_application_commit"}
                or prepared.get("creates_authority") is not False
                or prepared.get("creates_continuing_authority") is not False
                or prepared.get("record_sha256")!=_digest(
                    {key:value for key,value in prepared.items() if key!="record_sha256"})):
            raise PermissionError("prepared Git transaction is malformed")
        return prepared

    def prepare(self, *, operation_id, expected_parent_head, reviewed_tree_sha256,
                scope, exact_diff_sha256, mutation_manifest_sha256,
                review_receipt_sha256, message):
        for name,value in (("operation_id",operation_id),("expected_parent_head",expected_parent_head),
                           ("reviewed_tree_sha256",reviewed_tree_sha256),
                           ("exact_diff_sha256",exact_diff_sha256),
                           ("mutation_manifest_sha256",mutation_manifest_sha256),
                           ("review_receipt_sha256",review_receipt_sha256),("message",message)):
            if not isinstance(value,str) or not value: raise ValueError(f"{name} is required")
        paths=self._paths(scope)
        if self._head()!=expected_parent_head: raise RuntimeError("Git parent HEAD changed before preparation")
        branch_ref=self._branch_ref();normal_index=self._index_identity()
        unrelated_status_sha256=self._unrelated_status_sha256(paths)
        descriptor,index_name=tempfile.mkstemp(prefix="cleanup-index-",dir=self.state_root)
        os.close(descriptor);os.unlink(index_name)
        environment={**os.environ,"GIT_INDEX_FILE":index_name}
        try:
            self._run(["read-tree",expected_parent_head],env=environment)
            self._run(["add","-A","--",*paths],env=environment)
            tree=self._run(["write-tree"],env=environment,text=True).stdout.strip()
        finally:
            Path(index_name).unlink(missing_ok=True)
        changed=tuple(sorted(filter(None,self._run(
            ["diff-tree","--no-commit-id","--name-only","-r",expected_parent_head,tree],
            text=True).stdout.splitlines())))
        if changed!=paths: raise RuntimeError("prepared Git tree changed outside or omitted reviewed scope")
        parent_date=self._run(["show","-s","--format=%aI",expected_parent_head],text=True).stdout.strip()
        commit_message=(message.rstrip()+"\n\nFawkes-Operation-ID: "+operation_id+
            "\nFawkes-Review-Receipt: "+review_receipt_sha256+"\n")
        commit_env={**os.environ,"GIT_AUTHOR_NAME":"Fawkes Cleanup",
            "GIT_AUTHOR_EMAIL":"fawkes-cleanup@localhost.invalid","GIT_AUTHOR_DATE":parent_date,
            "GIT_COMMITTER_NAME":"Fawkes Cleanup","GIT_COMMITTER_EMAIL":"fawkes-cleanup@localhost.invalid",
            "GIT_COMMITTER_DATE":parent_date}
        commit=self._run(["commit-tree",tree,"-p",expected_parent_head],env=commit_env,
                         text=True,input=commit_message).stdout.strip()
        content=self._run(["cat-file","commit",commit]).stdout
        commit_diff=self._run(["diff-tree","--binary","--no-ext-diff","--no-commit-id","-p",
            expected_parent_head,commit,"--",*paths]).stdout
        if self._index_identity()!=normal_index:
            raise RuntimeError("normal Git index changed during isolated commit preparation")
        prepared={"schema_version":1,"record_type":"git_commit_transaction_prepared",
            "status":"prepared","operation_id":operation_id,"expected_parent_head":expected_parent_head,
            "prepared_commit":commit,"prepared_tree":tree,
            "prepared_commit_content_sha256":hashlib.sha256(content).hexdigest(),
            "prepared_diff_sha256":hashlib.sha256(commit_diff).hexdigest(),
            "reviewed_tree_sha256":reviewed_tree_sha256,"scope":list(paths),
            "scope_sha256":_digest(list(paths)),"exact_diff_sha256":exact_diff_sha256,
            "mutation_manifest_sha256":mutation_manifest_sha256,
            "review_receipt_sha256":review_receipt_sha256,"commit_message":commit_message,
            "branch_ref":branch_ref,"normal_index_node":normal_index,
            "unrelated_status_sha256":unrelated_status_sha256,
            "transaction_type":"generic_git_commit","creates_authority":False,
            "creates_continuing_authority":False}
        prepared["record_sha256"]=_digest(prepared)
        return prepared

    def _reviewed_application(self, receipt):
        if (not isinstance(receipt,dict)
                or receipt.get("record_type")!="codex_post_review_authoritative_application_receipt"
                or receipt.get("status")!="applied_verified_after_review"
                or receipt.get("application_count")!=1
                or receipt.get("creates_authority") is not False
                or receipt.get("creates_continuing_authority") is not False
                or receipt.get("record_sha256")!=_digest(
                    {key:value for key,value in receipt.items() if key!="record_sha256"})):
            raise PermissionError("exact terminal reviewed-application receipt is required")
        binding=receipt.get("binding") or {}
        required=("campaign_id","candidate_snapshot_id","mutation_manifest_sha256",
                  "review_package_id","review_acceptance_receipt_sha256",
                  "authorized_scope_sha256","expected_repository_head")
        if any(binding.get(key) in (None,"") for key in required):
            raise PermissionError("terminal reviewed-application lineage is incomplete")
        projection=receipt.get("reviewed_commit_projection")
        if (not isinstance(projection,dict)
                or projection.get("record_type")!="reviewed_application_commit_projection"
                or projection.get("record_sha256")!=_digest(
                    {key:value for key,value in projection.items() if key!="record_sha256"})):
            raise PermissionError("reviewed application commit projection is malformed")
        return receipt

    def reviewed_application_projection(self, *, operation_id, expected_parent_head,
            scope, review_receipt_sha256):
        """Derive the sole Git tree, diff, and metadata allowed for an application."""
        for name,value in (("operation_id",operation_id),("expected_parent_head",expected_parent_head),
                           ("review_receipt_sha256",review_receipt_sha256)):
            if not isinstance(value,str) or not value:raise ValueError(f"{name} is required")
        paths=self._paths(scope)
        if self._head()!=expected_parent_head:raise RuntimeError("Git parent HEAD changed")
        normal_index=self._index_identity()
        neighboring_state=self._neighboring_repository_state(paths)
        descriptor,index_name=tempfile.mkstemp(prefix="reviewed-projection-index-",dir=self.state_root)
        os.close(descriptor);os.unlink(index_name);environment={**os.environ,"GIT_INDEX_FILE":index_name}
        try:
            self._run(["read-tree",expected_parent_head],env=environment)
            self._run(["add","-A","--",*paths],env=environment)
            tree=self._run(["write-tree"],env=environment,text=True).stdout.strip()
        finally:Path(index_name).unlink(missing_ok=True)
        changed=tuple(sorted(filter(None,self._run(["diff-tree","--no-commit-id","--name-only",
            "-r",expected_parent_head,tree],text=True).stdout.splitlines())))
        if changed!=paths:raise RuntimeError("reviewed projection changed outside or omitted scope")
        diff=self._run(["diff-tree","--binary","--no-ext-diff","--no-commit-id","-p",
            expected_parent_head,tree,"--",*paths]).stdout
        if self._index_identity()!=normal_index:raise RuntimeError("normal Git index changed")
        parent_date=self._run(["show","-s","--format=%aI",expected_parent_head],text=True).stdout.strip()
        message=f"Reviewed application {operation_id}"
        commit_message=(message+"\n\nFawkes-Operation-ID: "+operation_id+
            "\nFawkes-Review-Receipt: "+review_receipt_sha256+"\n")
        value={"schema_version":1,"record_type":"reviewed_application_commit_projection",
          "operation_id":operation_id,"expected_parent_head":expected_parent_head,
          "scope":list(paths),"scope_sha256":_digest(list(paths)),"expected_tree":tree,
          "expected_diff_sha256":hashlib.sha256(diff).hexdigest(),"message":message,
          "commit_message":commit_message,"author_name":"Fawkes Cleanup",
          "author_email":"fawkes-cleanup@localhost.invalid","author_date":parent_date,
          "committer_name":"Fawkes Cleanup","committer_email":"fawkes-cleanup@localhost.invalid",
          "committer_date":parent_date,"review_receipt_sha256":review_receipt_sha256,
          "neighboring_repository_state":neighboring_state,
          "creates_authority":False}
        value["record_sha256"]=_digest(value);return value

    def _validate_reviewed_workspace(self, receipt, prepared):
        """Recompute the complete reviewed tree from current in-scope postimages."""
        projection=receipt["reviewed_commit_projection"]
        observed=self.reviewed_application_projection(
            operation_id=prepared["operation_id"],
            expected_parent_head=prepared["expected_parent_head"],
            scope=prepared["scope"],
            review_receipt_sha256=prepared["review_receipt_sha256"])
        if observed!=projection:
            raise PermissionError(
                "reviewed commit projection drift: in-scope postimage or repository binding")
        return observed

    def prepare_reviewed_application(self, *, terminal_application_receipt,
            operation_id, expected_parent_head, reviewed_tree_sha256, scope,
            exact_diff_sha256, mutation_manifest_sha256, review_receipt_sha256, message):
        """Prepare a commit only for one exact completed canonical application."""
        receipt=self._reviewed_application(terminal_application_receipt)
        binding=receipt["binding"]
        projection=receipt["reviewed_commit_projection"]
        if (receipt.get("operation_id")!=operation_id
                or binding.get("expected_repository_head")!=expected_parent_head
                or binding.get("mutation_manifest_sha256")!=mutation_manifest_sha256
                or binding.get("review_acceptance_receipt_sha256")!=review_receipt_sha256
                or tuple(sorted(receipt.get("applied_paths") or ()))!=tuple(sorted(scope))
                or projection.get("expected_tree")!=reviewed_tree_sha256
                or projection.get("expected_diff_sha256")!=exact_diff_sha256
                or projection.get("message")!=message):
            raise PermissionError("reviewed application does not bind the exact commit")
        prepared_binding={"operation_id":operation_id,
            "expected_parent_head":expected_parent_head,"scope":list(self._paths(scope)),
            "review_receipt_sha256":review_receipt_sha256}
        self._validate_reviewed_workspace(receipt,prepared_binding)
        prepared=self.prepare(operation_id=operation_id,expected_parent_head=expected_parent_head,
            reviewed_tree_sha256=reviewed_tree_sha256,scope=scope,
            exact_diff_sha256=exact_diff_sha256,
            mutation_manifest_sha256=mutation_manifest_sha256,
            review_receipt_sha256=review_receipt_sha256,message=message)
        neighboring=self._validate_neighboring_repository_state(projection,
            self._paths(scope))
        if (prepared.get("normal_index_node")!=neighboring["normal_index_node"]
                or prepared.get("unrelated_status_sha256")!=
                    neighboring["unrelated_status_sha256"]
                or prepared.get("branch_ref")!=neighboring["branch_ref"]):
            raise PermissionError("commit preparation escaped receipt-owned repository state")
        prepared={**prepared,"terminal_application_receipt_sha256":receipt["record_sha256"],
            "application_operation_id":receipt["operation_id"],
            "application_candidate_snapshot_id":binding["candidate_snapshot_id"],
            "application_package_id":binding["review_package_id"],
            "reviewed_commit_projection_sha256":projection["record_sha256"],
            "transaction_type":"reviewed_application_commit","creates_authority":False,
            "creates_continuing_authority":False,"recovery_mode":"observe_only",
            "may_execute_after_restart":False}
        prepared.pop("record_sha256",None);prepared["record_sha256"]=_digest(prepared)
        marker={"schema_version":1,"record_type":"reviewed_git_preparation_marker",
            "prepared_commit":prepared["prepared_commit"],"operation_id":prepared["operation_id"],
            "terminal_application_receipt_sha256":receipt["record_sha256"],
            "prepared_record_sha256":prepared["record_sha256"],"creates_authority":False,
            "creates_continuing_authority":False}
        marker["record_sha256"]=_digest(marker)
        write_durable_record(self._reviewed_preparation_path(prepared["prepared_commit"]),marker)
        return prepared

    def reconcile_reviewed_application(self, prepared, terminal_application_receipt):
        receipt=self._reviewed_application(terminal_application_receipt)
        prepared=self._validate_prepared(prepared)
        marker=json.loads(self._reviewed_preparation_path(
            prepared["prepared_commit"]).read_text(encoding="utf-8"))
        if (marker.get("record_sha256") != _digest(
                {k:v for k,v in marker.items() if k!="record_sha256"})
                or marker.get("prepared_record_sha256") != prepared["record_sha256"]
                or marker.get("terminal_application_receipt_sha256") != receipt["record_sha256"]):
            raise PermissionError("canonical reviewed Git preparation is unavailable")
        if (prepared.get("terminal_application_receipt_sha256")!=receipt["record_sha256"]
                or prepared.get("application_operation_id")!=receipt["operation_id"]
                or prepared.get("application_candidate_snapshot_id")!=
                    receipt["binding"]["candidate_snapshot_id"]
                or prepared.get("application_package_id")!=receipt["binding"]["review_package_id"]):
            raise PermissionError("neighboring reviewed application commit binding")
        if prepared.get("reviewed_commit_projection_sha256")!=receipt[
                "reviewed_commit_projection"]["record_sha256"]:
            raise PermissionError("reviewed commit projection binding mismatch")
        self._validate_neighboring_repository_state(receipt["reviewed_commit_projection"],
            self._paths(prepared["scope"]))
        return self.reconcile(prepared)

    def advance_reviewed_application(self, prepared, terminal_application_receipt):
        """Legacy compatibility is read-only: classify, but never advance a ref."""
        state=self.reconcile_reviewed_application(prepared,terminal_application_receipt)
        if state.get("status")=="committed":
            return {**state,"legacy_reconciliation":True,
                "creates_authority":False,"creates_continuing_authority":False}
        value={"schema_version":1,"record_type":"legacy_reviewed_git_reconciliation",
            "status":"failed_safe","reason":"legacy_pre_cas_state_requires_tanner",
            "operation_id":prepared["operation_id"],"head":self._head(),
            "prepared_commit":prepared["prepared_commit"],"creates_authority":False,
            "creates_continuing_authority":False}
        value["record_sha256"]=_digest(value);return value

    def _protected_campaign(self, campaign_store, campaign_protection,
            receipt, operation_id):
        from src.runtime.codex_development_campaign import (
            DevelopmentCampaignStore, _ProtectedGitGuard,
        )
        if (type(campaign_store) is not DevelopmentCampaignStore
                or type(campaign_protection) is not _ProtectedGitGuard):
            raise PermissionError("canonical campaign protection is required")
        campaign=campaign_store.load(receipt["binding"]["campaign_id"])
        campaign_protection.validate(campaign_id=campaign["campaign_id"],
            record_sha256=campaign["record_sha256"],
            state_revision=campaign["state_revision"],operation_id=operation_id)
        budget=campaign.get("execution_budget_v01") or {}
        if campaign.get("campaign_id")!=receipt["binding"]["campaign_id"]:
            raise PermissionError("campaign identity is neighboring")
        if (campaign.get("status")!="reviewed_application_completed"
                or campaign.get("cancelled")
                or campaign.get("creates_authority") is not False
                or campaign.get("creates_continuing_authority") is not False
                or not campaign.get("stepwise_v01")
                or not budget.get("expires_at")):
            raise PermissionError("campaign is not currently eligible for reviewed Git")
        return campaign

    def advance_campaign_reviewed_application(self, prepared,
            terminal_application_receipt, *, campaign_store=None,
            campaign_protection=None, now=None, clock=None):
        """Perform one live CAS; a durable intent permits observation only on restart."""
        receipt=self._reviewed_application(terminal_application_receipt)
        prepared=self._validate_prepared(prepared)
        lock_path=self.state_root/f"{prepared['operation_id']}.campaign-eligibility.lock"
        intent_path=self.state_root/f"{prepared['operation_id']}.reviewed-cas-intent.json"
        terminal_path=self.state_root/f"{prepared['operation_id']}.reviewed-cas-terminal.json"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            try:
                campaign=self._protected_campaign(campaign_store,
                    campaign_protection,receipt,prepared["operation_id"])
                budget=campaign["execution_budget_v01"]
                state=self.reconcile_reviewed_application(prepared,receipt)
                if terminal_path.exists():
                    return self._load_reviewed_terminal(terminal_path, prepared, receipt, campaign)
                if intent_path.exists():
                    return self._observe_reviewed_intent(intent_path, terminal_path,
                        prepared, receipt, campaign, state)
                expires_at=budget.get("expires_at")
                intent={"schema_version":1,"record_type":"reviewed_git_cas_intent_v01",
                    "operation_id":prepared["operation_id"],"prepared_commit":prepared["prepared_commit"],
                    "expected_parent_head":prepared["expected_parent_head"],
                    "prepared_record_sha256":prepared["record_sha256"],
                    "prepared_record":prepared,"campaign_id":campaign["campaign_id"],
                    "campaign_record_sha256":campaign["record_sha256"],
                    "receipt_sha256":receipt["record_sha256"],
                    "review_receipt_sha256":prepared["review_receipt_sha256"],
                    "prepared_tree":prepared["prepared_tree"],
                    "prepared_diff_sha256":prepared["prepared_diff_sha256"],
                    "scope_sha256":prepared["scope_sha256"],
                    "prepared_commit_content_sha256":prepared["prepared_commit_content_sha256"],
                    "transaction_type":prepared["transaction_type"],
                    "expires_at":expires_at,"recovery_mode":"observe_only",
                    "may_execute_after_restart":False,"creates_authority":False,
                    "creates_continuing_authority":False}
                intent["status"]="cas_invocation_started"
                intent["record_sha256"]=_digest(intent);write_durable_record(intent_path,intent)
                # The worktree can change after application reconciliation and
                # commit-object preparation. Recompute the complete reviewed
                # projection while both canonical locks are held. Any content,
                # mode, type, deletion, scope, index, or neighboring drift
                # closes before the final clock sample and CAS.
                self._validate_reviewed_workspace(receipt,prepared)
                # Re-read the canonical campaign after every potentially lengthy
                # preparation/validation step.  The authoritative clock sample
                # below is deliberately adjacent to CAS while both the campaign
                # protection and this transaction lock remain held.
                campaign=self._protected_campaign(campaign_store,
                    campaign_protection,receipt,prepared["operation_id"])
                expires_at=campaign["execution_budget_v01"].get("expires_at")
                # ``now`` is retained only for call compatibility; it is not an
                # authority input.  Production always samples UTC here, while
                # deterministic tests may inject the canonical clock callable.
                final_pre_cas_at=(clock or (lambda: datetime.now(timezone.utc)))()
                if expires_at and final_pre_cas_at>=datetime.fromisoformat(expires_at):
                    intent={**intent,"status":"expired_without_ref_advancement",
                        "final_pre_cas_at":final_pre_cas_at.isoformat(),
                        "final_campaign_record_sha256":campaign["record_sha256"]}
                    intent.pop("record_sha256",None);intent["record_sha256"]=_digest(intent)
                    write_durable_record(intent_path,intent)
                    raise PermissionError("campaign eligibility expired before ref advancement")
                self._run(["update-ref",prepared["branch_ref"],prepared["prepared_commit"],
                           prepared["expected_parent_head"]])
                state=self.reconcile_reviewed_application(prepared,receipt)
                return self._persist_reviewed_terminal(terminal_path, state,
                    prepared, receipt, campaign, intent,
                    final_pre_cas_at=final_pre_cas_at)
            finally:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def _validate_reviewed_intent(self, intent, prepared, receipt, campaign):
        if (not isinstance(intent,dict)
                or intent.get("record_type")!="reviewed_git_cas_intent_v01"
                or intent.get("record_sha256")!=_digest(
                    {k:v for k,v in intent.items() if k!="record_sha256"})
                or intent.get("operation_id")!=prepared["operation_id"]
                or intent.get("prepared_record")!=prepared
                or intent.get("prepared_record_sha256")!=prepared["record_sha256"]
                or intent.get("prepared_commit")!=prepared["prepared_commit"]
                or intent.get("expected_parent_head")!=prepared["expected_parent_head"]
                or intent.get("prepared_tree")!=prepared["prepared_tree"]
                or intent.get("prepared_diff_sha256")!=prepared["prepared_diff_sha256"]
                or intent.get("scope_sha256")!=prepared["scope_sha256"]
                or intent.get("prepared_commit_content_sha256")!=prepared["prepared_commit_content_sha256"]
                or intent.get("transaction_type")!="reviewed_application_commit"
                or intent.get("campaign_id")!=campaign["campaign_id"]
                or intent.get("campaign_record_sha256")!=campaign["record_sha256"]
                or intent.get("receipt_sha256")!=receipt["record_sha256"]
                or intent.get("review_receipt_sha256")!=prepared["review_receipt_sha256"]
                or intent.get("recovery_mode")!="observe_only"
                or intent.get("may_execute_after_restart") is not False
                or intent.get("creates_authority") is not False
                or intent.get("creates_continuing_authority") is not False):
            raise PermissionError("reviewed CAS intent is malformed or neighboring")
        return intent

    def _persist_reviewed_terminal(self, path, state, prepared, receipt, campaign, intent,
            *, final_pre_cas_at=None):
        if state.get("status")!="committed":
            raise RuntimeError("reviewed Git transaction is not committed")
        value={**state,"record_type":"reviewed_git_commit_terminal_receipt_v01",
            "application_receipt_sha256":receipt["record_sha256"],
            "campaign_id":campaign["campaign_id"],
            "campaign_record_sha256":campaign["record_sha256"],
            "prepared_record_sha256":prepared["record_sha256"],
            "intent_record_sha256":intent["record_sha256"],
            "eligibility_expires_at":intent["expires_at"],
            "final_pre_cas_at":(final_pre_cas_at.isoformat()
                if final_pre_cas_at is not None else intent.get("final_pre_cas_at")),
            "creates_authority":False,"creates_continuing_authority":False}
        value.pop("record_sha256",None);value["record_sha256"]=_digest(value)
        write_durable_record(path,value)
        return value

    def _load_reviewed_terminal(self, path, prepared, receipt, campaign):
        value=json.loads(path.read_text(encoding="utf-8"))
        if (value.get("record_sha256")!=_digest(
                {k:v for k,v in value.items() if k!="record_sha256"})
                or value.get("status")!="committed"
                or value.get("operation_id")!=prepared["operation_id"]
                or value.get("head")!=prepared["prepared_commit"]
                or value.get("prepared_record_sha256")!=prepared["record_sha256"]
                or value.get("application_receipt_sha256")!=receipt["record_sha256"]
                or value.get("campaign_record_sha256")!=campaign["record_sha256"]
                or value.get("creates_authority") is not False
                or value.get("creates_continuing_authority") is not False):
            raise PermissionError("terminal reviewed Git receipt is malformed or neighboring")
        return value

    def _observe_reviewed_intent(self, intent_path, terminal_path,
            prepared, receipt, campaign, state):
        intent=self._validate_reviewed_intent(json.loads(
            intent_path.read_text(encoding="utf-8")),prepared,receipt,campaign)
        if state["status"]=="committed":
            return self._persist_reviewed_terminal(terminal_path,state,
                prepared,receipt,campaign,intent)
        return {"status":"failed_safe","reason":"pre_cas_restart_observe_only",
            "operation_id":prepared["operation_id"],"creates_authority":False,
            "creates_continuing_authority":False,"record_sha256":intent["record_sha256"]}

    def reconcile_campaign_reviewed_application(self, *, operation_id,
            terminal_application_receipt, campaign_store=None, campaign_protection=None):
        """Observe a durable reviewed-CAS intent; never initiates ref advancement."""
        if not isinstance(operation_id,str) or not operation_id:
            raise ValueError("operation_id is required")
        receipt=self._reviewed_application(terminal_application_receipt)
        campaign=self._protected_campaign(campaign_store,campaign_protection,
            receipt,operation_id)
        intent_path=self.state_root/f"{operation_id}.reviewed-cas-intent.json"
        terminal_path=self.state_root/f"{operation_id}.reviewed-cas-terminal.json"
        lock_path=self.state_root/f"{operation_id}.campaign-eligibility.lock"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            try:
                if not intent_path.exists():
                    raise FileNotFoundError("reviewed Git CAS intent is unavailable")
                raw=json.loads(intent_path.read_text(encoding="utf-8"))
                prepared=self._validate_prepared(raw.get("prepared_record"))
                if prepared.get("operation_id")!=operation_id:
                    raise PermissionError("reviewed Git operation identity mismatch")
                self._validate_reviewed_intent(raw,prepared,receipt,campaign)
                state=self.reconcile_reviewed_application(prepared,receipt)
                if terminal_path.exists():
                    return self._load_reviewed_terminal(terminal_path,prepared,receipt,campaign)
                return self._observe_reviewed_intent(intent_path,terminal_path,
                    prepared,receipt,campaign,state)
            finally:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def reconcile(self, prepared):
        prepared=self._validate_prepared(prepared);paths=self._paths(prepared["scope"])
        if (self._branch_ref()!=prepared["branch_ref"]
                or self._index_identity()!=prepared["normal_index_node"]
                or self._unrelated_status_sha256(paths)!=prepared["unrelated_status_sha256"]):
            raise RuntimeError("Git branch or normal index changed")
        content=self._run(["cat-file","commit",prepared["prepared_commit"]]).stdout
        tree=self._run(["rev-parse",f"{prepared['prepared_commit']}^{{tree}}"],text=True).stdout.strip()
        parent=self._run(["rev-parse",f"{prepared['prepared_commit']}^"],text=True).stdout.strip()
        changed=tuple(sorted(filter(None,self._run(["diff-tree","--no-commit-id","--name-only","-r",
            parent,prepared["prepared_commit"]],text=True).stdout.splitlines())))
        commit_diff=self._run(["diff-tree","--binary","--no-ext-diff","--no-commit-id","-p",
            parent,prepared["prepared_commit"],"--",*paths]).stdout
        if (parent!=prepared["expected_parent_head"] or tree!=prepared["prepared_tree"]
                or changed!=paths
                or hashlib.sha256(content).hexdigest()!=prepared["prepared_commit_content_sha256"]
                or hashlib.sha256(commit_diff).hexdigest()!=prepared["prepared_diff_sha256"]):
            raise RuntimeError("prepared Git commit identity is ambiguous")
        head=self._head()
        if head==prepared["expected_parent_head"]:
            return {"status":"prepared","operation_id":prepared["operation_id"],
                    "prepared_commit":prepared["prepared_commit"],"creates_authority":False}
        if head!=prepared["prepared_commit"]:
            raise RuntimeError("Git branch advanced to a neighboring commit")
        receipt={"schema_version":1,"record_type":"git_commit_transaction_receipt",
            "status":"committed","operation_id":prepared["operation_id"],
            "parent_head":parent,"head":head,"tree":tree,
            "commit_content_sha256":prepared["prepared_commit_content_sha256"],
            "committed_diff_sha256":prepared["prepared_diff_sha256"],"scope":list(paths),
            "scope_sha256":prepared["scope_sha256"],
            "reviewed_tree_sha256":prepared["reviewed_tree_sha256"],
            "exact_diff_sha256":prepared["exact_diff_sha256"],
            "mutation_manifest_sha256":prepared["mutation_manifest_sha256"],
            "review_receipt_sha256":prepared["review_receipt_sha256"],
            "status_sha256":self._status_sha256(),"normal_index_unchanged":True,
            "creates_authority":False}
        receipt["record_sha256"]=_digest(receipt)
        return receipt

    def advance(self, prepared):
        prepared=self._validate_prepared(prepared);state=self.reconcile(prepared)
        if (prepared["transaction_type"] != "generic_git_commit"
                or self._reviewed_preparation_path(prepared["prepared_commit"]).exists()):
            raise PermissionError("reviewed application commits require canonical eligibility consumption")
        if state["status"]=="committed": return state
        self._run(["update-ref",prepared["branch_ref"],prepared["prepared_commit"],
                   prepared["expected_parent_head"]])
        return self.reconcile(prepared)

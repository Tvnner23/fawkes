"""Durable orchestration for retrospective cleanup candidates.

This owner selects and checkpoints work.  It delegates validation, review,
correction, guarded application, commit, and Attention delivery to the already
qualified canonical owners supplied by the composition root.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import subprocess
import uuid

from src.runtime.evidence_eligibility import classify_reviewer_source_evidence

SCHEMA_VERSION = 2
MAX_ACCEPTED_BATCHES = 8
MAX_CORRECTIONS = 2
MAX_DURATION_SECONDS = 8 * 60 * 60
REVIEW_RECEIPT_LIFETIME_SECONDS = 60 * 60
REVIEW_CLOCK_SKEW_SECONDS = 30
PROTECTED_ROOTS = {".git", "Archive", "Memory", "Library", "conversations",
                   "continuity", "database", "backups", "Worker Exchange"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()


def _now(): return datetime.now(timezone.utc).isoformat()


def _path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("normalized repository-relative path is required")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("cleanup path escapes repository")
    if path.as_posix() == ".gitignore" or path.parts[0] in PROTECTED_ROOTS:
        raise PermissionError("protected cleanup path is excluded")
    return path.as_posix()


def _node(path):
    path = Path(path)
    if not path.exists() and not path.is_symlink(): return {"state": "absent"}
    mode = path.lstat().st_mode & 0o7777
    if path.is_symlink():
        body = os.readlink(path).encode()
        return {"state":"present","type":"symlink","mode":mode,
                "byte_length":len(body),"sha256":hashlib.sha256(body).hexdigest()}
    if path.is_dir(): return {"state":"present","type":"directory","mode":mode}
    body = path.read_bytes()
    return {"state":"present","type":"regular","mode":mode,
            "byte_length":len(body),"sha256":hashlib.sha256(body).hexdigest()}


def _validate_record(record):
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid historical cleanup session")
    claimed = record.get("record_sha256")
    if claimed != _digest({k:v for k,v in record.items() if k != "record_sha256"}):
        raise ValueError("historical cleanup session integrity mismatch")
    return record


def _required_digest(value, name):
    if not isinstance(value, str) or len(value) != 64:
        raise PermissionError(f"{name} must be a canonical digest")
    try: int(value, 16)
    except ValueError as exc: raise PermissionError(f"{name} must be a canonical digest") from exc
    return value


def _review_bindings(*, evidence, validation):
    nodes = [{"path": item["path"], "head_preimage": item["head_preimage"],
              "frozen_postimage": item["frozen_postimage"]}
             for item in evidence["nodes"]]
    conditions = validation.get("acceptance_condition_ids")
    if not isinstance(conditions, list) or not conditions or any(
            not isinstance(item, str) or not item for item in conditions):
        raise PermissionError("validation must declare acceptance conditions")
    return {
        "campaign_id": validation.get("campaign_id"),
        "package_id": validation.get("builder_package_id"),
        "review_package_id": validation.get("review_package_id"),
        "source_report_id": validation.get("source_report_id"),
        "candidate_snapshot_id": evidence["candidate_snapshot_id"],
        "exact_diff_sha256": evidence["exact_diff_sha256"],
        "exact_change_evidence_sha256": validation.get("exact_change_evidence_sha256"),
        "mutation_manifest_sha256": evidence["mutation_manifest_sha256"],
        "allowed_scope_sha256": evidence["scope_sha256"],
        "preimages_sha256": validation.get("authoritative_preimages_sha256"),
        "validation_sha256": _digest(validation),
        "acceptance_condition_ids_sha256": _digest(sorted(conditions)),
    }


def _validated_review_acceptance(review, *, evidence, validation, consumed,
                                 current_time=None, require_current_freshness=True):
    """Validate immutable Reviewer lineage; never derive acceptance locally."""
    if not isinstance(review, dict) or review.get("verdict") != "accepted":
        raise PermissionError("independent Reviewer acceptance is required")
    receipt = review.get("acceptance_receipt")
    report = review.get("review_report")
    package = review.get("review_package")
    delivery = review.get("delivery_receipt")
    verification = review.get("verification_receipt")
    if not all(isinstance(item, dict) for item in
               (receipt, report, package, delivery, verification)):
        raise PermissionError("complete immutable review evidence is required")
    for item in (receipt, report, package, delivery, verification):
        if item.get("record_sha256") != _digest(
                {key: value for key, value in item.items() if key != "record_sha256"}):
            raise PermissionError("review evidence digest mismatch")
    expected = _review_bindings(evidence=evidence, validation=validation)
    reviewer = {"worker_id": receipt.get("reviewer_worker_id"),
                "role": receipt.get("reviewer_role")}
    recipient = receipt.get("recipient")
    if (receipt.get("record_type") != "codex_independent_review_acceptance_receipt"
            or receipt.get("status") != "accepted"
            or receipt.get("creates_authority") is not False
            or reviewer.get("role") != "reviewer"
            or not isinstance(reviewer.get("worker_id"), str)
            or reviewer.get("worker_id") in {"", "fawkes-development", "codex-repository-wsl-fawkes"}
            or not isinstance(recipient,dict)
            or recipient.get("worker_id") != reviewer["worker_id"]
            or recipient.get("role") != reviewer["role"]
            or any(receipt.get(key) != value for key, value in expected.items()
                   if key in {"campaign_id","package_id","review_package_id",
                              "candidate_snapshot_id","mutation_manifest_sha256",
                              "allowed_scope_sha256","acceptance_condition_ids_sha256"})
            or receipt.get("candidate_retention_receipt_sha256") !=
                validation.get("candidate_retention_receipt_sha256")
            or receipt.get("exact_change_evidence_sha256") != expected["exact_change_evidence_sha256"]
            or receipt.get("authoritative_preimages_sha256") != expected["preimages_sha256"]
            or report.get("report_id") != receipt.get("review_report_id")
            or report.get("record_sha256") != receipt.get("review_report_sha256")
            or not isinstance(report.get("sender"),dict)
            or any(report["sender"].get(key)!=recipient.get(key) for key in
                   ("worker_id","role","identity_status","charter_version"))
            or (report.get("in_reply_to") or {}).get("package_id") != package.get("package_id")
            or package.get("package_id") != expected["review_package_id"]
            or receipt.get("review_package_sha256") != package.get("record_sha256")
            or receipt.get("source_report_id") != expected["source_report_id"]
            or package.get("source_report_id") != expected["source_report_id"]
            or (report.get("in_reply_to") or {}).get("source_report_id") != expected["source_report_id"]
            or delivery.get("delivery_receipt_id") != receipt.get("delivery_receipt_id")
            or delivery.get("package_id") != package.get("package_id")
            or delivery.get("status") != "delivered"
            or verification.get("verification_receipt_id") != receipt.get("verification_receipt_id")
            or verification.get("package_id") != package.get("package_id")
            or verification.get("source_report_id") != expected["source_report_id"]
            or verification.get("status") != "accepted"
            or not isinstance(receipt.get("review_invocation_id"),str)
            or not receipt.get("review_invocation_id")):
        raise PermissionError("independent review lineage mismatch")
    for name in ("record_sha256", "review_report_sha256", "mutation_manifest_sha256",
                 "allowed_scope_sha256", "acceptance_condition_ids_sha256",
                 "candidate_retention_receipt_sha256"):
        _required_digest(receipt.get(name), name)
    try:
        issued_at = datetime.fromisoformat(receipt.get("created_at"))
        expires_at = datetime.fromisoformat(receipt.get("expires_at"))
    except (TypeError, ValueError) as exc: raise PermissionError("review freshness is malformed") from exc
    now=current_time or datetime.now(timezone.utc);skew=timedelta(seconds=REVIEW_CLOCK_SKEW_SECONDS)
    if (issued_at.tzinfo is None or expires_at.tzinfo is None
            or issued_at > now+skew or expires_at <= issued_at
            or expires_at-issued_at > timedelta(seconds=REVIEW_RECEIPT_LIFETIME_SECONDS)
            or (require_current_freshness and now-skew >= expires_at)):
        raise PermissionError("review acceptance is stale")
    replay_key = receipt.get("replay_identity")
    if (not isinstance(replay_key, str) or not replay_key
            or replay_key != _digest({"package": receipt.get("review_package_sha256"),
                                      "candidate": receipt.get("candidate_snapshot_id"),
                                      "invocation": receipt.get("review_invocation_id"),
                                      "created_at": receipt.get("created_at")})
            or replay_key in consumed):
        raise PermissionError("review acceptance is stale or replayed")
    return receipt


class HistoricalCleanupSession:
    """One bounded, restart-safe retrospective cleanup session."""
    def __init__(self, *, repository, state_root, inventory, plans, expected_head,
                 expected_status_sha256, validator, reviewer, applier, committer,
                 broad_validator, attention, corrector=None, candidate_verifier=None,
                 clock=None):
        self.repository = Path(repository).resolve()
        self.state_root = Path(state_root).resolve()
        if self.repository == self.state_root or self.repository in self.state_root.parents:
            raise ValueError("cleanup session state must be external")
        if not self.state_root.exists() or not self.state_root.is_dir():
            raise ValueError("external cleanup session state root must exist")
        self.inventory = inventory
        self.expected_head = expected_head
        self.expected_status_sha256 = expected_status_sha256
        self.validator, self.reviewer = validator, reviewer
        self.applier, self.committer = applier, committer
        self.broad_validator, self.attention = broad_validator, attention
        self.corrector = corrector
        self.candidate_verifier = candidate_verifier
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.plans = self._plans(plans)
        self.path = self.state_root / "session.json"

    def _plans(self, plans):
        result = {}
        for raw in plans:
            batch_id = raw.get("batch_id")
            if not isinstance(batch_id, str) or not batch_id or batch_id in result:
                raise ValueError("unique batch identity is required")
            paths = tuple(sorted(_path(value) for value in raw.get("paths", ())))
            if not paths: raise ValueError("batch scope is required")
            result[batch_id] = {"batch_id":batch_id,"paths":paths,
                "dependencies":tuple(sorted(raw.get("dependencies", ()))),
                "focused_tests":tuple(tuple(command) for command in raw.get("focused_tests", ())),
                "quarantine_reason":raw.get("quarantine_reason")}
        for plan in result.values():
            if any(dep not in result or dep == plan["batch_id"] for dep in plan["dependencies"]):
                raise ValueError("batch dependency is invalid")
        return result

    def _write(self, record, *, expected_revision=None):
        if expected_revision is not None and self.path.exists():
            current = self.load()
            if current["revision"] != expected_revision:
                raise RuntimeError("cleanup session revision changed")
        value = {**record,"updated_at":_now()}
        value.pop("record_sha256",None); value["record_sha256"]=_digest(value)
        temporary=self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        payload=(json.dumps(value,indent=2)+"\n").encode()
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(descriptor,"wb",closefd=False) as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        os.replace(temporary,self.path)
        directory=os.open(self.path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
        try: os.fsync(directory)
        finally: os.close(directory)
        return value

    def load(self): return _validate_record(json.loads(self.path.read_text()))

    def create(self, session_id):
        if self.path.exists(): return self.load()
        self._baseline_guard()
        now=datetime.now(timezone.utc)
        batches={key:{"status":"quarantined" if value["quarantine_reason"] else "pending",
            "correction_cycles":0,"terminal_records":[],"quarantine_reason":value["quarantine_reason"]}
            for key,value in self.plans.items()}
        return self._write({"schema_version":SCHEMA_VERSION,"record_type":"historical_cleanup_session",
            "session_id":session_id,"head":self.expected_head,
            "status_sha256":self.expected_status_sha256,"started_at":now.isoformat(),
            "deadline":(now+timedelta(seconds=MAX_DURATION_SECONDS)).isoformat(),
            "maximum_accepted_batches":MAX_ACCEPTED_BATCHES,"maximum_corrections_per_batch":MAX_CORRECTIONS,
            "accepted_batches":0,"broad_regressions":0,"active_batch":None,
            "status":"running","revision":1,"batches":batches,"creates_authority":False,
            "creates_continuing_authority":False})

    def _baseline_guard(self):
        head=subprocess.run(["git","rev-parse","HEAD"],cwd=self.repository,check=True,
            text=True,capture_output=True).stdout.strip()
        status=subprocess.run(["git","status","--porcelain=v2","--untracked-files=all"],
            cwd=self.repository,check=True,capture_output=True).stdout
        if head != self.expected_head or hashlib.sha256(status).hexdigest()!=self.expected_status_sha256:
            raise RuntimeError("cleanup authoritative baseline drifted")

    def select(self, record=None):
        record=record or self.load()
        if record["status"] != "running" or record["active_batch"] is not None: return None
        if record["accepted_batches"] >= MAX_ACCEPTED_BATCHES or datetime.now(timezone.utc)>=datetime.fromisoformat(record["deadline"]):
            return None
        for batch_id in sorted(self.plans):
            state=record["batches"][batch_id]
            if state["status"] != "pending": continue
            dependencies=self.plans[batch_id]["dependencies"]
            if all(record["batches"][item]["status"]=="accepted" for item in dependencies): return batch_id
            if any(record["batches"][item]["status"] in {"quarantined","failed","needs_tanner"} for item in dependencies):
                continue
        return None

    def evidence(self, batch_id):
        self._baseline_guard(); plan=self.plans[batch_id]
        inventory={item["path"]:item for item in self.inventory["paths"]}
        entries=[]; diff_parts=[]
        import subprocess
        for relative in plan["paths"]:
            if relative not in inventory: raise ValueError("batch path missing frozen inventory")
            expected=inventory[relative]["node"]; actual=_node(self.repository/relative)
            if actual != expected: raise RuntimeError("frozen historical postimage drifted")
            shown=subprocess.run(["git","show",f"{self.expected_head}:{relative}"],cwd=self.repository,
                capture_output=True)
            before=shown.stdout if shown.returncode==0 else None
            after=(self.repository/relative).read_bytes() if actual.get("type")=="regular" else None
            eligibility=classify_reviewer_source_evidence(path=relative,before=before,after=after)
            if not eligibility["disclosure_allowed"]: raise PermissionError("historical evidence is ineligible")
            entries.append({"path":relative,"head_preimage":None if before is None else {
                "sha256":hashlib.sha256(before).hexdigest(),"byte_length":len(before)},
                "frozen_postimage":expected,"eligibility_receipt":eligibility})
        diff=subprocess.run(["git","diff","--binary","--no-ext-diff",self.expected_head,"--",*plan["paths"]],
            cwd=self.repository,check=True,capture_output=True).stdout
        value={"schema_version":1,"record_type":"historical_cleanup_candidate_evidence",
            "historical_authorship":"unattributed_phase_0_9_work","current_worker_authored":False,
            "candidate_generation":0,
            "head":self.expected_head,"batch_id":batch_id,"scope":list(plan["paths"]),
            "scope_sha256":_digest(list(plan["paths"])),"inventory_sha256":_digest(self.inventory),
            "nodes":entries,"exact_diff":diff.decode("utf-8"),"exact_diff_sha256":hashlib.sha256(diff).hexdigest(),
            "creates_authority":False}
        value["mutation_manifest_sha256"]=_digest(entries)
        value["candidate_snapshot_id"]="candidate-snapshot-"+_digest({
            "head":self.expected_head,"scope":value["scope"],"nodes":entries})
        value["record_sha256"]=_digest(value); return value

    def _corrected_generation(self, batch_id, previous, correction):
        """Validate a Worker-produced generation without rewriting historical intake."""
        if not callable(self.candidate_verifier):
            raise PermissionError("canonical candidate verifier is required")
        verified=self.candidate_verifier(self.plans[batch_id],correction)
        if (not isinstance(verified,dict)
                or verified.get("record_sha256") != _digest(
                    {key:value for key,value in verified.items() if key!="record_sha256"})
                or verified.get("verification_status")!="exact_filesystem_match"):
            raise PermissionError("canonical candidate verification failed")
        generation=verified.get("candidate_generation")
        nodes=verified.get("nodes");scope=verified.get("scope")
        exact_diff=verified.get("exact_diff")
        if (correction.get("status")!="corrected"
                or generation != previous["candidate_generation"]+1
                or scope != previous["scope"]
                or verified.get("head") != self.expected_head
                or not isinstance(nodes,list)
                or sorted(item.get("path") for item in nodes) != list(self.plans[batch_id]["paths"])
                or not isinstance(exact_diff,str)):
            raise PermissionError("corrected candidate generation is incomplete or mismatched")
        diff_sha=hashlib.sha256(exact_diff.encode()).hexdigest()
        mutation_sha=_digest(nodes)
        snapshot="candidate-snapshot-"+_digest({"head":self.expected_head,"scope":scope,
            "generation":generation,"nodes":nodes})
        if (verified.get("exact_diff_sha256")!=diff_sha
                or verified.get("mutation_manifest_sha256")!=mutation_sha
                or verified.get("candidate_snapshot_id")!=snapshot
                or any(correction.get(key)!=verified.get(key) for key in
                    ("candidate_snapshot_id","exact_diff_sha256","mutation_manifest_sha256"))):
            raise PermissionError("corrected candidate generation identity mismatch")
        value={"schema_version":1,"record_type":"historical_cleanup_corrected_candidate_evidence",
            "historical_authorship":previous["historical_authorship"],"current_worker_authored":True,
            "historical_provenance_sha256":previous.get("historical_provenance_sha256",
                previous["record_sha256"]),"parent_candidate_snapshot_id":previous["candidate_snapshot_id"],
            "candidate_generation":generation,"head":self.expected_head,"batch_id":batch_id,
            "scope":scope,"scope_sha256":previous["scope_sha256"],"inventory_sha256":previous["inventory_sha256"],
            "nodes":nodes,"exact_diff":exact_diff,"exact_diff_sha256":diff_sha,
            "mutation_manifest_sha256":mutation_sha,"candidate_snapshot_id":snapshot,
            "creates_authority":False}
        value["record_sha256"]=_digest(value);return value

    def _verify_current_candidate(self, plan, evidence):
        """Reverify the reviewed generation from its actual frozen filesystem."""
        if not callable(self.candidate_verifier):
            raise PermissionError("canonical candidate verifier is required")
        verified=self.candidate_verifier(plan,{"status":"candidate_recheck",**evidence})
        if (not isinstance(verified,dict)
                or verified.get("record_sha256") != _digest(
                    {key:value for key,value in verified.items() if key!="record_sha256"})
                or verified.get("verification_status")!="exact_filesystem_match"):
            raise PermissionError("canonical candidate recheck failed")
        required=("candidate_generation","head","scope","nodes","exact_diff",
            "exact_diff_sha256","mutation_manifest_sha256","candidate_snapshot_id")
        if any(verified.get(key)!=evidence.get(key) for key in required):
            raise PermissionError("reviewed candidate filesystem changed")
        return verified

    def run_next(self):
        record=self.load(); batch_id=self.select(record)
        if record.get("transaction_intent"):
            return self._reconcile_transaction(record)
        if batch_id is None: return self.finish_if_bounded(record)
        revision=record["revision"]; record["revision"]+=1; record["active_batch"]=batch_id
        record["batches"][batch_id]["status"]="validating"; record=self._write(record,expected_revision=revision)
        evidence=self.evidence(batch_id)
        validation=self.validator(self.plans[batch_id],evidence)
        if not isinstance(validation,dict) or validation.get("status")!="passed":
            return self._terminal_batch(record,batch_id,"failed",{"validation":validation})
        verdict=self.reviewer(self.plans[batch_id],evidence,validation)
        while verdict.get("verdict")=="correction_required":
            state=record["batches"][batch_id]
            if state["correction_cycles"]>=MAX_CORRECTIONS:
                self.attention("correction_scope_exhausted",batch_id,evidence)
                return self._terminal_batch(record,batch_id,"needs_tanner",{"review":verdict})
            if not callable(self.corrector):
                self.attention("correction_worker_unavailable",batch_id,evidence)
                return self._terminal_batch(record,batch_id,"needs_tanner",{"review":verdict})
            correction=self.corrector(self.plans[batch_id],evidence,validation,verdict,
                correction_cycle=state["correction_cycles"]+1)
            try: corrected=self._corrected_generation(batch_id,evidence,correction)
            except (AttributeError,PermissionError,TypeError,ValueError):
                return self._terminal_batch(record,batch_id,"failed",{"correction":correction})
            state["correction_cycles"]+=1
            revision=record["revision"];record["revision"]+=1
            state.setdefault("candidate_generations",[]).append({
                "generation":corrected["candidate_generation"],
                "candidate_snapshot_id":corrected["candidate_snapshot_id"],
                "record_sha256":corrected["record_sha256"],
                "historical_provenance_sha256":corrected["historical_provenance_sha256"]})
            record=self._write(record,expected_revision=revision)
            evidence=corrected
            validation=self.validator(self.plans[batch_id],evidence)
            if validation.get("status")!="passed":
                return self._terminal_batch(record,batch_id,"failed",{"validation":validation})
            verdict=self.reviewer(self.plans[batch_id],evidence,validation)
        try:
            receipt=_validated_review_acceptance(verdict,evidence=evidence,validation=validation,
                consumed=set(record.get("consumed_review_replay_keys",())),current_time=self.clock())
            self._baseline_guard()
            self._verify_current_candidate(self.plans[batch_id],evidence)
        except (PermissionError,RuntimeError) as exc:
            return self._terminal_batch(record,batch_id,"failed",{"review_failure":type(exc).__name__})
        operation_id="cleanup-transaction-"+_digest({"session":record["session_id"],
            "batch":batch_id,"candidate":evidence["candidate_snapshot_id"],
            "review":receipt["record_sha256"]})
        revision=record["revision"];record["revision"]+=1
        record["transaction_intent"]={"operation_id":operation_id,"stage":"apply_pending",
            "batch_id":batch_id,"evidence":evidence,"validation":validation,
            "review":verdict,"review_receipt_sha256":receipt["record_sha256"],
            "review_replay_key":receipt["replay_identity"],"creates_authority":False}
        record=self._write(record,expected_revision=revision)
        return self._reconcile_transaction(record)

    def _reconcile_transaction(self, record):
        intent=record.get("transaction_intent") or {}; batch_id=intent.get("batch_id")
        if batch_id not in self.plans or record.get("active_batch") != batch_id:
            return self.pause("ambiguous_transaction_recovery",{"operation_id":intent.get("operation_id")})
        operation_id=intent.get("operation_id")
        if not isinstance(operation_id,str) or not operation_id:
            return self.pause("ambiguous_transaction_recovery",{"stage":intent.get("stage")})
        plan=self.plans[batch_id]; evidence=intent["evidence"]; validation=intent["validation"]
        review=intent["review"]
        stage=intent.get("stage")
        reconciled_commit=None; completed_before_restart=False
        if stage=="commit_complete":
            try:
                reconciled=self.committer.reconcile(intent.get("prepared_commit"))
                if reconciled!=intent.get("commit_receipt"):
                    raise RuntimeError("durable commit receipt does not match canonical reconciliation")
                applied=intent.get("apply_receipt") or {}
                if (applied.get("status")!="applied" or applied.get("application_count")!=1
                        or applied.get("operation_id")!=operation_id):
                    raise RuntimeError("completed commit lacks exact one-shot application evidence")
                reconciled_commit=reconciled;completed_before_restart=True
            except Exception:
                return self.pause("ambiguous_transaction_recovery",{"operation_id":operation_id,
                    "stage":"commit_complete"})
        elif stage=="commit_prepared":
            try:
                reconciled_commit=self.committer.reconcile(intent.get("prepared_commit"))
                completed_before_restart=reconciled_commit.get("status")=="committed"
                applied=intent.get("apply_receipt") or {}
                if (completed_before_restart and (applied.get("status")!="applied"
                        or applied.get("application_count")!=1
                        or applied.get("operation_id")!=operation_id)):
                    raise RuntimeError("completed commit lacks exact one-shot application evidence")
            except Exception:
                return self.pause("ambiguous_transaction_recovery",{"operation_id":operation_id,
                    "stage":"commit_prepared"})
        else:
            try:
                self._baseline_guard()
                self._verify_current_candidate(plan,evidence)
            except Exception:
                return self.pause("candidate_changed_before_application",{"operation_id":operation_id})
        try:
            receipt=_validated_review_acceptance(review,evidence=evidence,validation=validation,
                consumed=set(record.get("consumed_review_replay_keys",()))-{intent["review_replay_key"]},
                current_time=self.clock(),require_current_freshness=not completed_before_restart)
        except PermissionError:
            return self.pause("ambiguous_transaction_recovery",{"operation_id":operation_id})
        if stage=="apply_pending":
            applied=self.applier(plan,evidence,validation,review,operation_id=operation_id,reconcile_only=True)
            if applied.get("status")=="not_applied":
                applied=self.applier(plan,evidence,validation,review,operation_id=operation_id,reconcile_only=False)
            if (applied.get("status")!="applied" or applied.get("application_count")!=1
                    or applied.get("operation_id")!=operation_id):
                return self.pause("ambiguous_transaction_recovery",{"operation_id":operation_id,"stage":stage})
            revision=record["revision"];record["revision"]+=1;intent["stage"]="apply_complete"
            intent["apply_receipt"]={**applied};record=self._write(record,expected_revision=revision)
            stage="apply_complete"
        if stage in {"apply_complete","commit_pending","commit_prepared"}:
            if stage=="apply_complete":
                revision=record["revision"];record["revision"]+=1;intent["stage"]="commit_pending"
                record=self._write(record,expected_revision=revision)
                stage="commit_pending"
            if stage=="commit_pending":
                try:
                    prepared=self.committer.prepare(operation_id=operation_id,
                        expected_parent_head=record["head"],
                        reviewed_tree_sha256=evidence["candidate_snapshot_id"],scope=plan["paths"],
                        exact_diff_sha256=evidence["exact_diff_sha256"],
                        mutation_manifest_sha256=evidence["mutation_manifest_sha256"],
                        review_receipt_sha256=receipt["record_sha256"],
                        message="Historical cleanup: "+batch_id)
                except Exception:
                    return self.pause("ambiguous_transaction_recovery",{"operation_id":operation_id,
                        "stage":"commit_pending"})
                revision=record["revision"];record["revision"]+=1;intent["stage"]="commit_prepared"
                intent["prepared_commit"]=prepared;record=self._write(record,expected_revision=revision)
            prepared=intent.get("prepared_commit")
            try:
                committed=reconciled_commit or self.committer.reconcile(prepared)
                if committed.get("status")=="prepared": committed=self.committer.advance(prepared)
            except Exception:
                return self.pause("ambiguous_transaction_recovery",{"operation_id":operation_id,
                    "stage":"commit_prepared"})
            if (committed.get("record_type")!="git_commit_transaction_receipt"
                    or committed.get("status")!="committed"
                    or committed.get("operation_id")!=operation_id
                    or committed.get("review_receipt_sha256")!=receipt["record_sha256"]
                    or committed.get("reviewed_tree_sha256")!=evidence["candidate_snapshot_id"]
                    or committed.get("exact_diff_sha256")!=evidence["exact_diff_sha256"]
                    or committed.get("mutation_manifest_sha256")!=evidence["mutation_manifest_sha256"]):
                return self.pause("ambiguous_transaction_recovery",{"operation_id":operation_id,
                    "stage":"commit_prepared"})
            revision=record["revision"];record["revision"]+=1;intent["stage"]="commit_complete"
            intent["commit_receipt"]={**committed};record=self._write(record,expected_revision=revision)
        committed=intent["commit_receipt"];applied=intent["apply_receipt"]
        self.expected_head=committed["head"];self.expected_status_sha256=committed["status_sha256"]
        record["head"]=self.expected_head;record["status_sha256"]=self.expected_status_sha256
        record.setdefault("consumed_review_replay_keys",[]).append(intent["review_replay_key"])
        record["transaction_intent"]=None
        record=self._terminal_batch(record,batch_id,"accepted",{"validation":validation,
            "review_receipt_sha256":receipt["record_sha256"],"apply":applied,"commit":committed})
        if record["accepted_batches"]%2==0:
            broad=self.broad_validator(record)
            if broad.get("status")!="passed":
                self.attention("terminal_failure",batch_id,broad)
                record["status"]="failed"; record["revision"]+=1
                return self._write(record,expected_revision=record["revision"]-1)
            record["broad_regressions"]+=1; record["revision"]+=1
            record=self._write(record,expected_revision=record["revision"]-1)
        return record

    def _terminal_batch(self,record,batch_id,status,evidence):
        revision=record["revision"]; record["revision"]+=1; record["active_batch"]=None
        record["batches"][batch_id]["status"]=status
        terminal={"terminal_id":"cleanup-batch-terminal-"+_digest({"batch":batch_id,"revision":revision}),
            "batch_id":batch_id,"status":status,"evidence_sha256":_digest(evidence),
            "created_at":_now(),"creates_authority":False}
        record["batches"][batch_id]["terminal_records"].append(terminal)
        if status=="accepted": record["accepted_batches"]+=1
        return self._write(record,expected_revision=revision)

    def pause(self, reason, evidence):
        record=self.load(); revision=record["revision"]; record["revision"]+=1
        request=self.attention(reason,record.get("active_batch"),evidence)
        record["status"]="needs_tanner"; record["attention"]={"request_id":request["request_id"],
            "binding_sha256":request["binding_sha256"],"consumed":False}
        return self._write(record,expected_revision=revision)

    def resume(self, receipt):
        record=self.load(); expected=record.get("attention") or {}
        if (record["status"]!="needs_tanner" or expected.get("consumed")
                or receipt.get("request_id")!=expected.get("request_id")
                or receipt.get("binding_sha256")!=expected.get("binding_sha256")
                or receipt.get("decision") not in {"approve_once","deny"}):
            raise PermissionError("Mobile Attention receipt is stale, mismatched, or replayed")
        revision=record["revision"]; record["revision"]+=1; expected["consumed"]=True
        record["status"]="running" if receipt["decision"]=="approve_once" else "failed"
        return self._write(record,expected_revision=revision)

    def finish_if_bounded(self,record=None):
        record=record or self.load()
        pending=[key for key,value in record["batches"].items() if value["status"]=="pending"]
        bounded=(record["accepted_batches"]>=MAX_ACCEPTED_BATCHES
                 or datetime.now(timezone.utc)>=datetime.fromisoformat(record["deadline"]))
        if pending and not bounded: return record
        broad=self.broad_validator(record)
        if broad.get("status")!="passed": return self.pause("terminal_failure",broad)
        revision=record["revision"];record["revision"]+=1;record["status"]="completed"
        record["broad_regressions"]+=1
        final=self._write(record,expected_revision=revision)
        self.attention("session_completion",None,{"record_sha256":final["record_sha256"]})
        return final

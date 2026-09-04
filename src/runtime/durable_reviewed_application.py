"""Durable, restart-reconcilable execution of one already-reviewed file application."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import fcntl, hashlib, json, os, stat, tempfile, uuid
import subprocess


TERMINAL = {"completed", "rolled_back", "failed_safe", "quarantined"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def write_durable_record(path, value, *, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, mode)
        body=(json.dumps(value, sort_keys=True, indent=2)+"\n").encode()
        os.write(descriptor, body); os.fsync(descriptor); os.close(descriptor); descriptor=-1
        os.replace(temporary, path); _fsync_directory(path.parent)
        if json.loads(path.read_text()) != value: raise RuntimeError("durable record read-back mismatch")
    finally:
        if descriptor >= 0: os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _node(path):
    try: value=path.lstat()
    except FileNotFoundError: return {"type":"missing"}
    if stat.S_ISLNK(value.st_mode): return {"type":"symlink","target":os.readlink(path)}
    if stat.S_ISDIR(value.st_mode): return {"type":"directory","mode":value.st_mode & 0o777}
    if not stat.S_ISREG(value.st_mode): return {"type":"other","mode":value.st_mode & 0o777}
    body=path.read_bytes()
    return {"type":"regular","mode":value.st_mode & 0o777,"byte_length":len(body),
            "sha256":hashlib.sha256(body).hexdigest()}


def unrelated_workspace_sha256(repository, scope):
    repository=Path(repository).resolve(); excluded=set(scope);nodes=[]
    for path in sorted(repository.rglob("*")):
        relative=path.relative_to(repository).as_posix()
        if relative==".git" or relative.startswith(".git/") or relative in excluded:
            continue
        if any(item.startswith(relative+"/") for item in excluded) and path.is_dir():
            continue
        nodes.append({"path":relative,"node":_node(path)})
    return _digest(nodes)


class DurableReviewedApplication:
    """Own one exact reviewed mutation from durable intent through terminal receipt.

    Recovery policy: a recognized partial pre/post set is rolled back exactly and
    terminated. An already complete postimage set is finalized without rewriting.
    """

    def __init__(self, repository, state_root, *, replace=os.replace, crash_hook=None, clock=None):
        self.repository=Path(repository).resolve(); self.state_root=Path(state_root).resolve()
        if self.repository == self.state_root or self.repository in self.state_root.parents:
            raise ValueError("application transaction state must be outside the repository")
        self.state_root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.state_root,0o700)
        self.replace=replace;self.crash_hook=crash_hook or (lambda point,path=None:None)
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _directory(self, operation_id):
        if not isinstance(operation_id,str) or not operation_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in operation_id):
            raise ValueError("operation identity is malformed")
        return self.state_root/operation_id

    @contextmanager
    def _lock(self, operation_id):
        directory=self._directory(operation_id);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        handle=(directory/"operation.lock").open("a+b");os.chmod(directory/"operation.lock",0o600)
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(handle.fileno(),fcntl.LOCK_UN);handle.close()

    def _load(self, operation_id):
        record=json.loads((self._directory(operation_id)/"transaction.json").read_text())
        claimed=record.get("record_sha256")
        if claimed != _digest({k:v for k,v in record.items() if k!="record_sha256"}):
            raise PermissionError("application transaction integrity mismatch")
        if record.get("operation_id")!=operation_id or record.get("repository_root")!=str(self.repository):
            raise PermissionError("application transaction identity mismatch")
        return record

    def _write(self, record, *, expected_revision):
        path=self._directory(record["operation_id"])/"transaction.json"
        if path.exists():
            current=self._load(record["operation_id"])
            if current["revision"] != expected_revision: raise RuntimeError("application transaction revision changed")
        elif expected_revision is not None: raise RuntimeError("application transaction disappeared")
        value={**record,"revision":0 if expected_revision is None else expected_revision+1}
        value.pop("record_sha256",None);value["record_sha256"]=_digest(value)
        write_durable_record(path,value)
        if self._load(value["operation_id"])!=value: raise RuntimeError("application transaction durability failure")
        return value

    def _target(self, relative):
        pure=PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts: raise PermissionError("application path escapes root")
        target=self.repository.joinpath(*pure.parts)
        parent=self.repository
        for component in pure.parts[:-1]:
            parent=parent/component
            if parent.is_symlink(): raise PermissionError("application parent is a symlink")
            if parent.exists() and not parent.is_dir(): raise PermissionError("application parent is not a directory")
        return target

    def _material(self, operation_id, name, body):
        path=self._directory(operation_id)/"material"/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if path.exists():
            retained=path.read_bytes()
            if retained!=body:raise PermissionError("neighboring rollback/application material")
            return {"relative_path":str(path.relative_to(self._directory(operation_id))),
                    "sha256":hashlib.sha256(body).hexdigest(),"byte_length":len(body)}
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try: os.write(descriptor,body);os.fsync(descriptor)
        finally: os.close(descriptor)
        _fsync_directory(path.parent)
        return {"relative_path":str(path.relative_to(self._directory(operation_id))),
                "sha256":hashlib.sha256(body).hexdigest(),"byte_length":len(body)}

    def prepare(self, *, operation_id, binding, paths, review_expires_at):
        required=("campaign_id","task_scope_id","worker_invocation_id","generation",
          "candidate_retention_receipt_sha256","candidate_snapshot_id","mutation_manifest_sha256",
          "review_package_id","review_package_sha256","review_acceptance_receipt_sha256",
          "reviewer_worker_id","review_invocation_id","authorized_scope_sha256",
          "expected_repository_head","expected_repository_status_sha256")
        if not isinstance(binding,dict) or any(binding.get(key) in (None,"") for key in required):
            raise PermissionError("complete canonical application binding is required")
        if binding.get("review_acceptance_record_type")!="codex_independent_review_acceptance_receipt":
            raise PermissionError("canonical Reviewer acceptance is required")
        if not paths or sorted(item["path"] for item in paths)!=[item["path"] for item in paths]:
            raise ValueError("exact ordered application paths are required")
        directory=self._directory(operation_id)
        with self._lock(operation_id):
            transaction=directory/"transaction.json"
            if transaction.exists():
                existing=self._load(operation_id)
                if existing.get("binding")!=binding: raise PermissionError("neighboring operation binding")
                return existing
            entries=[];created_directories=set()
            for index,item in enumerate(paths):
                relative=item["path"];target=self._target(relative)
                parent=target.parent
                while parent!=self.repository and not parent.exists():
                    created_directories.add(parent.relative_to(self.repository).as_posix());parent=parent.parent
                if item["preimage"]["type"] not in {"regular","missing"} or item["postimage"]["type"] not in {"regular","missing"}:
                    raise PermissionError("only exact regular-file transitions are supported")
                pre_body=item.get("preimage_body");post_body=item.get("postimage_body")
                material={}
                for label,node,body in (("preimage",item["preimage"],pre_body),("postimage",item["postimage"],post_body)):
                    if node["type"]=="regular":
                        if not isinstance(body,bytes) or hashlib.sha256(body).hexdigest()!=node["sha256"] or len(body)!=node["byte_length"]:
                            raise ValueError(f"{label} material mismatch")
                        material[label]=self._material(operation_id,f"{index}-{label}.bin",body)
                    elif body is not None: raise ValueError(f"missing {label} cannot have material")
                entries.append({"path":relative,"preimage":item["preimage"],"postimage":item["postimage"],
                                "material":material,"progress":"pending"})
            record={"schema_version":1,"record_type":"durable_reviewed_application_transaction",
              "operation_id":operation_id,"repository_root":str(self.repository),"state":"prepared",
              "binding":binding,"paths":entries,"review_expires_at":review_expires_at,
              "created_directories":sorted(created_directories,key=lambda item:(item.count("/"),item)),
              "recovery_policy":"rollback_exact_partial_finalize_exact_complete",
              "application_count":0,"created_at":self.clock().isoformat(),
              "creates_continuing_authority":False}
            value=self._write(record,expected_revision=None);self.crash_hook("after_intent",None);return value

    def _body(self, record, entry, label):
        reference=entry["material"].get(label)
        if reference is None:return None
        path=self._directory(record["operation_id"])/reference["relative_path"]
        body=path.read_bytes()
        if len(body)!=reference["byte_length"] or hashlib.sha256(body).hexdigest()!=reference["sha256"]:
            raise PermissionError("rollback/application material integrity mismatch")
        return body

    def _classification(self, record):
        values=[]
        for entry in record["paths"]:
            actual=_node(self._target(entry["path"]))
            values.append("preimage" if actual==entry["preimage"] else
                          "postimage" if actual==entry["postimage"] else "drifted")
        return values

    def _replace(self, target, node, body):
        if node["type"]=="missing":
            target.unlink(missing_ok=True);_fsync_directory(target.parent);return
        target.parent.mkdir(parents=True,exist_ok=True)
        descriptor,name=tempfile.mkstemp(prefix=".fawkes-durable-apply-",dir=target.parent)
        temporary=Path(name)
        try:
            os.write(descriptor,body);os.fchmod(descriptor,node["mode"]);os.fsync(descriptor);os.close(descriptor);descriptor=-1
            self.replace(temporary,target);_fsync_directory(target.parent)
        finally:
            if descriptor>=0:os.close(descriptor)
            temporary.unlink(missing_ok=True)
        if _node(target)!=node: raise RuntimeError("durable application postimage mismatch")

    def _transition(self, record, state, **changes):
        return self._write({**record,"state":state,**changes},expected_revision=record["revision"])

    def execute_or_resume(self, operation_id):
        with self._lock(operation_id):
            record=self._load(operation_id)
            if record["state"] in TERMINAL:return record
            scope=[item["path"] for item in record["paths"]]
            expected_head=record["binding"]["expected_repository_head"]
            if not expected_head.startswith("workspace-snapshot:"):
                observed=subprocess.run(["git","rev-parse","HEAD"],cwd=self.repository,
                    text=True,capture_output=True,check=False).stdout.strip()
                if observed!=expected_head:
                    return self._transition(record,"quarantined",failure_reason="repository_head_drift")
            if unrelated_workspace_sha256(self.repository,scope)!=record["binding"]["expected_repository_status_sha256"]:
                return self._transition(record,"quarantined",failure_reason="neighboring_workspace_drift")
            classes=self._classification(record)
            if "drifted" in classes:
                return self._transition(record,"quarantined",classification=classes,
                    failure_reason="unclassifiable_filesystem_state")
            if all(item=="postimage" for item in classes):
                record=self._transition(record,"applied",classification=classes,
                    application_count=max(1,record["application_count"]))
                record=self._transition(record,"finalizing")
                return self._transition(record,"completed",completed_at=self.clock().isoformat())
            if any(item=="postimage" for item in classes):
                record=self._transition(record,"rolling_back",classification=classes)
                try:
                    for entry,classification in reversed(list(zip(record["paths"],classes))):
                        if classification=="postimage":
                            self._replace(self._target(entry["path"]),entry["preimage"],self._body(record,entry,"preimage"))
                    for relative in reversed(record.get("created_directories",[])):
                        directory=self.repository/relative
                        if directory.exists():directory.rmdir();_fsync_directory(directory.parent)
                except Exception as exc:
                    return self._transition(record,"quarantined",
                        failure_reason="rollback_failed:"+type(exc).__name__)
                if not all(item=="preimage" for item in self._classification(record)):
                    return self._transition(record,"quarantined",failure_reason="rollback_verification_failed")
                return self._transition(record,"rolled_back",rolled_back_at=self.clock().isoformat())
            if record["state"]=="rolling_back":
                return self._transition(record,"rolled_back",rolled_back_at=self.clock().isoformat())
            expires=datetime.fromisoformat(record["review_expires_at"])
            if self.clock()>=expires:
                return self._transition(record,"failed_safe",failure_reason="review_expired_before_side_effect")
            # Authenticate every durable body before the first side effect. A later
            # per-path read repeats this check to close replacement-time races.
            for entry in record["paths"]:
                self._body(record,entry,"preimage")
                self._body(record,entry,"postimage")
            record=self._transition(record,"applying",application_count=record["application_count"]+1)
            for index,entry in enumerate(record["paths"]):
                if _node(self._target(entry["path"]))!=entry["preimage"]:
                    return self._transition(record,"quarantined",failure_reason="preimage_drift")
                paths=list(record["paths"]);paths[index]={**entry,"progress":"mutating"}
                record=self._transition(record,"applying",paths=paths)
                self.crash_hook("before_path",entry["path"])
                self._replace(self._target(entry["path"]),entry["postimage"],self._body(record,entry,"postimage"))
                self.crash_hook("after_path",entry["path"])
                paths=list(record["paths"]);paths[index]={**paths[index],"progress":"completed"}
                record=self._transition(record,"applying",paths=paths)
            classes=self._classification(record)
            if not all(item=="postimage" for item in classes):
                return self._transition(record,"quarantined",classification=classes,
                                        failure_reason="post_apply_classification_failed")
            record=self._transition(record,"applied",classification=classes)
            record=self._transition(record,"finalizing")
            return self._transition(record,"completed",completed_at=self.clock().isoformat())

    def reconcile(self, operation_id):
        return self.execute_or_resume(operation_id)

    def terminal_receipt(self, operation_id):
        record=self._load(operation_id)
        if record["state"]!="completed": raise RuntimeError("successful application receipt is unavailable")
        receipt={"schema_version":1,"record_type":"codex_post_review_authoritative_application_receipt",
          "status":"applied_verified_after_review","operation_id":operation_id,
          "transaction_record_sha256":record["record_sha256"],"application_count":record["application_count"],
          "applied_paths":[item["path"] for item in record["paths"]],"binding":record["binding"],
          "creates_continuing_authority":False}
        receipt["record_sha256"]=_digest(receipt);return receipt

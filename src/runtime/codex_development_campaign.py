"""One bounded Fawkes-coordinated CODEX (REPO) builder/reviewer campaign.

This is durable coordination state over Development and Worker Exchange. It is
not a scheduler, worker registry, authority source, or general orchestrator.
"""

from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from pathlib import Path
import fcntl
import hashlib
import json
import os
import subprocess
import threading
import uuid

from src.library.artifacts import require_id
from src.runtime.codex_development_handoff import (
    CODEX_REPO_WORKER_REFERENCE, run_codex_development_handoff,
)
from src.runtime.disposable_verifier import DisposableVerifierWorkspace
from src.runtime.worker_exchange import WorkerExchange, _digest, body_free_references
from src.runtime.autonomy_supervision import (
    campaign_activity_projection, retain_campaign_terminal_notification,
    retain_needs_tanner_notification,
)
from src.runtime.development_attention import DevelopmentAttentionStore
from src.runtime.codex_worker_adapter import (
    DEFAULT_TIMEOUT_SECONDS, _runtime_state_root, minimal_subprocess_environment,
)


ROOT = Path(os.environ.get(
    "FAWKES_DEVELOPMENT_ROOT", Path(__file__).resolve().parent.parent.parent
)).resolve()
CAMPAIGN_ROOT = ROOT / "database" / "development_campaigns"
CAMPAIGN_SCHEMA_VERSION = 1
CAMPAIGN_CONTRACT_VERSION = "codex-builder-review-campaign-v0.2-wsl-default-reviewer"
MAX_ITERATIONS = 3
REVIEW_STATUSES = {
    "pass", "pass_with_caveats", "correction_required",
    "insufficient_evidence", "blocked",
}
TERMINAL_STATUSES = {"succeeded", "cancelled", "failed_safe", "tanner_escalation"}
STEPWISE_ACTIVE_CAMPAIGN_STATUSES = frozenset({
    "ready", "builder_in_progress", "awaiting_independent_review",
    "reviewer_native_action_approved", "review_accepted_application_pending",
    "reviewed_application_completed", "correction_pending",
})
STEPWISE_PAUSED_CAMPAIGN_STATUSES = frozenset({
    "tanner_escalation", "ready_for_bounded_continuation",
})
STEPWISE_TERMINAL_CAMPAIGN_STATUSES = frozenset({
    "succeeded", "cancelled", "failed_safe",
})
BUILDER_MODES = {"read_only", "repository_write"}
WINDOWS_REVIEWER_ROLE = "windows_software_architecture_review"
WINDOWS_REVIEWER_WORKER_ID = "windows-codex-software-review"
FORMAL_REVIEW_ROLE = "formal_independent_software_review"
DEFAULT_REVIEWER_ROLE = "wsl_read_only_code_health_review"
DEFAULT_REVIEWER_WORKER_ID = "wsl-codex-read-only-review"
DEFAULT_REVIEWER_BINDING_ASSURANCE = {
    "campaign": "wsl-default-formal-reviewer-binding-assurance-v1",
    "candidate_snapshot_id": "candidate-snapshot-194476eab4b84b49ed83053daaf48e884291e37241da552e56cee6663c3514fb",
    "candidate_record_sha256": "216d8374ec4821106fa66de64a39bd1b5be6ea8dcebd01ff3ef8084487d7c827",
    "hard_invariants": "8/8", "real_production_review_path": "pass",
    "independent_verdict": "pass", "tanner_preauthorized_promotion": True,
    "promoted": True,
}
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_PROTECTED_LOCAL = threading.local()
_PROTECTED_GIT_GUARD_SECRET = object()


class _ProtectedGitGuard:
    """Ephemeral proof that the campaign serialization boundary is held."""
    __slots__ = ("campaign_id", "record_sha256", "state_revision", "operation_id",
                 "_handle", "_thread", "_active")

    def __init__(self, secret, *, campaign_id, record_sha256, state_revision,
                 operation_id, handle):
        if secret is not _PROTECTED_GIT_GUARD_SECRET:
            raise PermissionError("canonical campaign protection is required")
        self.campaign_id=campaign_id;self.record_sha256=record_sha256
        self.state_revision=state_revision;self.operation_id=operation_id
        self._handle=handle;self._thread=threading.get_ident();self._active=True

    def validate(self, *, campaign_id, record_sha256, state_revision, operation_id):
        if (not self._active or self._handle.closed
                or self._thread!=threading.get_ident()
                or self.campaign_id!=campaign_id
                or self.record_sha256!=record_sha256
                or self.state_revision!=state_revision
                or self.operation_id!=operation_id):
            raise PermissionError("canonical campaign protection is stale or mismatched")

    def close(self): self._active=False

CAMPAIGN_ACCEPTANCE_CONTRACT = {
    "contract_version": CAMPAIGN_CONTRACT_VERSION,
    "campaign_type": "one_codex_repo_builder_one_independent_reviewer",
    "hard_limits": {
        "maximum_builder_iterations": MAX_ITERATIONS,
        "builder_worker_id": CODEX_REPO_WORKER_REFERENCE["worker_id"],
        "reviewer_role": FORMAL_REVIEW_ROLE,
        "default_reviewer_worker_id": DEFAULT_REVIEWER_WORKER_ID,
        "automatic_promotion": False,
        "worker_discovery": False,
        "purchases": False,
        "credential_changes": False,
        "destructive_operations": False,
        "scope_expansion": False,
    },
    "completion_requires": (
        "all_predeclared_acceptance_conditions_satisfied",
        "independent_review_sufficient",
        "exact_builder_and_reviewer_evidence_retained",
        "no_required_tanner_decision",
    ),
    "restart_rule": "in_progress_is_never_blindly_replayed",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def stepwise_campaign_status_disposition(status):
    """Classify one established campaign status without inventing an outcome."""
    if status in STEPWISE_ACTIVE_CAMPAIGN_STATUSES:
        return "active"
    if status in STEPWISE_PAUSED_CAMPAIGN_STATUSES:
        return "paused"
    if status in STEPWISE_TERMINAL_CAMPAIGN_STATUSES:
        return "terminal"
    raise PermissionError("canonical stepwise campaign status is unknown")


def stepwise_campaign_budget_limits(record):
    """Return the immutable limits authenticated by a canonical campaign budget."""
    if not isinstance(record, dict) or record.get("stepwise_v01") is not True:
        raise PermissionError("a canonical stepwise campaign is required")
    budget = record.get("execution_budget_v01")
    maximum_keys = (
        "maximum_duration_seconds", "maximum_worker_turns",
        "maximum_reviewer_turns", "maximum_provider_turns",
        "maximum_cost_units", "maximum_correction_cycles",
        "maximum_iterations",
    )
    if (not isinstance(budget, dict)
            or any(type(budget.get(key)) is not int or budget[key] <= 0
                   for key in maximum_keys)
            or budget.get("contract") !=
                "conservative-provider-reservation-failed-safe-v0.1"):
        raise PermissionError("canonical stepwise campaign budget is malformed")
    immutable = {key: budget.get(key) for key in maximum_keys}
    immutable.update({
        "created_at": budget.get("created_at"),
        "expires_at": budget.get("expires_at"),
        "contract": budget.get("contract"),
    })
    try:
        created = datetime.fromisoformat(immutable["created_at"])
        expires = datetime.fromisoformat(immutable["expires_at"])
    except (TypeError, ValueError) as exc:
        raise PermissionError("canonical stepwise campaign budget time is malformed") from exc
    if (created.tzinfo is None or expires.tzinfo is None
            or expires - created != timedelta(
                seconds=budget["maximum_duration_seconds"])
            or budget.get("budget_sha256") != _digest(immutable)):
        raise PermissionError("canonical stepwise campaign budget binding is invalid")
    return {
        "seconds": budget["maximum_duration_seconds"],
        "provider_turns": budget["maximum_provider_turns"],
        "correction_cycles": budget["maximum_correction_cycles"],
        "cost_units": budget["maximum_cost_units"],
        "iterations": budget["maximum_iterations"],
    }


def _lock(path):
    key = str(Path(path).resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _text(value, label, *, maximum=32_000):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > maximum:
        raise ValueError(f"bounded {label} is required")
    return value.strip()


def _ids(values, label, *, maximum=16):
    if not isinstance(values, list) or not values or len(values) > maximum:
        raise ValueError(f"one to {maximum} {label} values are required")
    result = [require_id(value, label) for value in values]
    if len(set(result)) != len(result):
        raise ValueError(f"{label} values must be unique")
    return result


def _scopes(values):
    if not isinstance(values, list) or not values or len(values) > 24:
        raise ValueError("one to 24 allowed scope values are required")
    result = []
    for value in values:
        if (not isinstance(value, str) or not value.strip() or len(value.encode()) > 512
                or any(ord(character) < 32 for character in value)
                or value.startswith("/") or ".." in Path(value).parts):
            raise ValueError("allowed scope must be a bounded relative path or descriptive domain")
        result.append(value.strip())
    if len(set(result)) != len(result):
        raise ValueError("allowed scope values must be unique")
    return result


def _source_sections(values):
    if not isinstance(values, list) or len(values) > 6:
        raise ValueError("zero to six campaign source sections are allowed")
    sections = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("campaign source sections must be objects")
        content = _text(item.get("content"), "source content", maximum=64_000)
        sections.append({"section_id": require_id(item.get("section_id"), "section_id"),
                         "title": _text(item.get("title") or item.get("section_id"), "source title", maximum=512),
                         "content": content})
    if len({item["section_id"] for item in sections}) != len(sections):
        raise ValueError("campaign source section identities must be unique")
    return sections


def _validation_commands(values):
    if values in (None, []):
        return []
    if not isinstance(values, list) or len(values) > 4:
        raise ValueError("zero to four rider-authorized validation commands are allowed")
    normalized = []
    for command in values:
        if not isinstance(command, list) or not command or len(command) > 16:
            raise ValueError("validation command must be a bounded argv list")
        argv = [_text(item, "validation command argument", maximum=512) for item in command]
        if argv[0] not in {".venv/bin/python", "python3"} or "-m" not in argv:
            raise ValueError("validation command must use an explicit Python module invocation")
        if any(item in {"pip", "install"} for item in argv):
            raise PermissionError("validation commands cannot install software")
        normalized.append(argv)
    return normalized


def _validation_contract(payload, commands, *, campaign_id, allowed_scope):
    policy = payload.get("validation_policy", "required")
    if policy not in {"required", "intentionally_not_applicable"}:
        raise ValueError("validation_policy must be required or intentionally_not_applicable")
    if policy == "required" and not commands:
        raise ValueError("required campaign validation commands cannot be empty")
    if policy == "intentionally_not_applicable" and commands:
        raise ValueError("not-applicable validation cannot include commands")
    reason = payload.get("validation_not_applicable_reason_code")
    if policy == "intentionally_not_applicable" and reason not in {
            "no_deterministic_validation_applicable"}:
        raise ValueError("not-applicable validation requires a permitted reason code")
    declaration = {"policy_version": "development-campaign-validation-v2",
        "status": policy, "campaign_id": campaign_id,
        "allowed_scope_sha256": _digest(allowed_scope),
        "validation_plan_sha256": _digest(commands),
        "reason_code": reason if policy == "intentionally_not_applicable" else None,
        "creates_authority": False}
    declaration["record_sha256"] = hashlib.sha256(json.dumps(
        declaration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return policy, declaration


def _cleanup_python_cache(scopes, *, root=ROOT):
    """Remove only reproducible bytecode beside explicitly allowed source paths."""
    removed = []
    directories = {Path(scope).parent for scope in scopes if Path(scope).suffix == ".py"}
    for directory in sorted(directories):
        cache = (Path(root) / directory / "__pycache__").resolve()
        try:
            cache.relative_to(Path(root).resolve())
        except ValueError as exc:
            raise PermissionError("cache cleanup escaped the repository") from exc
        if not cache.is_dir():
            continue
        unexpected = [path for path in cache.iterdir()
                      if not path.is_file() or path.suffix not in {".pyc", ".pyo"}]
        if unexpected:
            raise RuntimeError("Python cache contains non-bytecode material and cannot be cleaned")
        for path in sorted(cache.iterdir()):
            data = path.read_bytes()
            removed.append({"path": path.relative_to(root).as_posix(),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "byte_length": len(data), "disposable_python_bytecode": True})
            path.unlink()
        try:
            cache.rmdir()
        except OSError:
            raise RuntimeError("Python cache cleanup did not leave an empty directory")
    return removed


class DevelopmentCampaignStore:
    """Atomic current-state record; worker evidence remains in Worker Exchange."""

    def __init__(self, instance_id, *, root=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.root = (Path(root) if root is not None else CAMPAIGN_ROOT) / self.instance_id

    def path(self, campaign_id):
        return self.root / f"{require_id(campaign_id, 'campaign_id')}.json"

    def protection_path(self, campaign_id):
        return self.root / ".protected" / f"{require_id(campaign_id, 'campaign_id')}.lock"

    @contextmanager
    def protected(self, campaign_id):
        """Process-safe serialization for protected Git and terminal cancellation."""
        path=self.protection_path(campaign_id);path.parent.mkdir(parents=True,exist_ok=True)
        key=str(path.resolve());held=getattr(_PROTECTED_LOCAL,"held",{})
        if key in held:
            handle,count=held[key];held[key]=(handle,count+1)
            try: yield handle
            finally:
                handle,count=held[key];held[key]=(handle,count-1)
            return
        with _lock(path):
            with path.open("a+b") as handle:
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
                held=dict(held);held[key]=(handle,1);_PROTECTED_LOCAL.held=held
                try: yield handle
                finally:
                    held.pop(key,None);_PROTECTED_LOCAL.held=held
                    fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def list(self):
        if not self.root.exists():
            return []
        records = [self.load(path.stem) for path in self.root.glob("*.json")]
        return sorted(records, key=lambda item: item["updated_at"], reverse=True)

    @staticmethod
    def _validate(record, *, instance_id):
        if (not isinstance(record, dict) or record.get("schema_version") != CAMPAIGN_SCHEMA_VERSION
                or record.get("record_type") != "codex_development_campaign"
                or record.get("instance_id") != instance_id
                or record.get("contract_version") != CAMPAIGN_CONTRACT_VERSION):
            raise ValueError("invalid Development campaign record")
        claimed = record.get("record_sha256")
        if claimed != _digest({key: value for key, value in record.items() if key != "record_sha256"}):
            raise ValueError("Development campaign integrity mismatch")
        if record.get("maximum_iterations") != MAX_ITERATIONS:
            raise ValueError("Development campaign iteration boundary changed")
        return record

    def load(self, campaign_id):
        path = self.path(campaign_id)
        if not path.exists():
            raise KeyError("Development campaign not found")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Development campaign is unreadable") from exc
        return self._validate(record, instance_id=self.instance_id)

    def write(self, record, *, expected_revision=None):
        path = self.path(record["campaign_id"])
        with self.protected(record["campaign_id"]), _lock(path):
            current = self.load(record["campaign_id"]) if path.exists() else None
            if current is not None and expected_revision is None:
                raise RuntimeError("Development campaign identity already exists")
            if expected_revision is not None and (current or {}).get("state_revision") != expected_revision:
                raise RuntimeError("Development campaign changed concurrently")
            if current is None and expected_revision is not None:
                raise RuntimeError("Development campaign does not exist")
            value = {key: item for key, item in record.items() if key != "record_sha256"}
            value["record_sha256"] = _digest(value)
            self._validate(value, instance_id=self.instance_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
                stream.flush(); os.fsync(stream.fileno())
            temporary.replace(path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return value


class CodexDevelopmentCampaign:
    """Deterministic coordinator for one fixed builder and reviewer slot."""

    def __init__(self, instance_id, *, root=None, exchange=None, builder_runner=None,
                 builder_modes=None, attention_store=None, runtime_state_root=None,
                 worker_timeout_seconds=DEFAULT_TIMEOUT_SECONDS, candidate_applier=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.store = DevelopmentCampaignStore(instance_id, root=root)
        self.supervision_root = (Path(root).parent / "component_supervision"
                                 if root is not None else None)
        self.exchange = exchange or WorkerExchange(instance_id)
        self.builder_runner = builder_runner or self._run_promoted_builder
        self.candidate_applier = candidate_applier or self._apply_reviewed_builder_candidate
        self.builder_modes = set(builder_modes or {"read_only", "repository_write"})
        self.attention_store = attention_store or DevelopmentAttentionStore()
        self.runtime_state_root = _runtime_state_root(runtime_state_root, workspace=ROOT)
        self.git_transaction_state_root = (self.runtime_state_root / "campaign-git-transactions"
                                           if self.runtime_state_root is not None else None)
        self.worker_timeout_seconds = int(worker_timeout_seconds)
        if self.worker_timeout_seconds <= 0:
            raise ValueError("worker timeout must be positive")
        if not self.builder_modes <= BUILDER_MODES:
            raise ValueError("invalid builder execution mode")

    def _run_promoted_builder(self, payload):
        return run_codex_development_handoff(instance_id=self.instance_id, payload=payload,
            authenticated_rider=True, exchange=self.exchange,
            approval_handler=self._handle_typed_approval,
            worker_timeout_seconds=self.worker_timeout_seconds,
            runtime_state_root=self.runtime_state_root,
            provider_reservation_owner=self if payload.get("stepwise_v01") else None,
            progress_handler=self.record_managed_worker_activity)

    def record_managed_worker_activity(self, event):
        """Bounded observational sidecar, never campaign state or authority.

        Do not bump the campaign revision while its synchronous builder is
        executing. The campaign lock still orders publication with cancellation.
        """
        from src.runtime.development_attention import _linux_process_identity
        campaign_id = require_id(event.get("campaign_id"), "campaign_id")
        invocation_id = require_id(event.get("invocation_id"), "invocation_id")
        with self.store.protected(campaign_id):
            campaign = self.store.load(campaign_id)
            scope = campaign.get("active_builder_task_scope_id")
            if not scope or invocation_id != scope + "-appserver":
                raise PermissionError("activity is not bound to the active managed Worker")
            if event.get("state") not in {"running", "waiting", "completed", "failed", "disconnected"}:
                raise ValueError("unknown managed Worker observation")
            path = self.store.root / ".managed-activity" / (invocation_id + ".json")
            old = json.loads(path.read_text()) if path.exists() else {}
            if old and old.get("record_sha256") != _digest({k:v for k,v in old.items() if k != "record_sha256"}):
                raise ValueError("managed activity record integrity mismatch")
            events = old.get("events", [])
            if any(item["event_id"] == event["event_id"] for item in events): return
            from src.runtime.codex_app_server import _safe
            public = {key: event[key] for key in ("event_id", "created_at", "kind", "state")}
            message = _safe(event.get("public_message"))
            encoded = message.encode("utf-8")
            public["public_message"] = (encoded[:1900].decode("utf-8", errors="ignore") + " [truncated]"
                                        if len(encoded) > 1900 else message)
            value = {"campaign_id": campaign_id, "invocation_id": invocation_id,
                "worker_id": event["worker"]["worker_id"], "process_id": event["process_id"],
                "process_identity": _linux_process_identity(event["process_id"]),
                "events": [*events, public][-64:], "state": event["state"],
                "updated_at": event["created_at"], "creates_authority": False,
                "creates_continuing_authority": False}
            value["record_sha256"] = _digest(value)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
            temporary.replace(path)

    def managed_worker_activity_projection(self, campaign_id):
        from src.runtime.development_attention import _linux_process_identity
        values = []
        root = self.store.root / ".managed-activity"
        if not root.exists(): return []
        for path in root.glob('*.json'):
            value = json.loads(path.read_text())
            if value.get("campaign_id") != campaign_id: continue
            if value.get("record_sha256") != _digest({k:v for k,v in value.items() if k != "record_sha256"}):
                raise ValueError("managed activity record integrity mismatch")
            state = value["state"]
            if state in {"running", "waiting"} and (not value.get("process_identity") or
                    _linux_process_identity(value["process_id"]) != value["process_identity"]):
                state = "disconnected"
            values.append({k:value[k] for k in ("invocation_id", "worker_id", "events", "updated_at")}
                          | {"state": state, "creates_authority": False})
        return sorted(values, key=lambda x:x["updated_at"], reverse=True)[:8]

    @staticmethod
    def _budget_from_payload(payload, created):
        supplied = payload.get("execution_budget_v01")
        if supplied is None:
            return None
        keys = {"maximum_duration_seconds", "maximum_worker_turns",
                "maximum_reviewer_turns", "maximum_provider_turns",
                "maximum_cost_units", "maximum_correction_cycles",
                "maximum_iterations"}
        if set(supplied) != keys or any(type(supplied[k]) is not int or supplied[k] <= 0
                                        for k in keys):
            raise ValueError("an exact positive v0.1 execution budget is required")
        if supplied["maximum_correction_cycles"] > 2:
            raise ValueError("v0.1 correction budget exceeds the canonical bound")
        if supplied["maximum_iterations"] > MAX_ITERATIONS:
            raise ValueError("v0.1 iteration budget exceeds the campaign bound")
        expires = datetime.fromisoformat(created) + timedelta(
            seconds=supplied["maximum_duration_seconds"])
        immutable = {**supplied, "created_at": created, "expires_at": expires.isoformat(),
            "contract": "conservative-provider-reservation-failed-safe-v0.1"}
        value = {**immutable,
                 "consumed_worker_turns": 0, "consumed_reviewer_turns": 0,
                 "consumed_provider_turns": 0, "consumed_cost_units": 0,
                 "consumed_correction_cycles": 0, "provider_action": None,
                 "provider_actions": []}
        value["budget_sha256"] = _digest(immutable)
        return value

    def _provider_ambiguity(self, record):
        budget = dict(record["execution_budget_v01"])
        action = budget.get("provider_action")
        if not isinstance(action, dict) or action.get("status") not in {
                "provider_action_reserved", "provider_action_in_flight"}:
            return None
        kind = action["operation_type"]
        budget["consumed_provider_turns"] += action["maximum_reserved_provider_turns"]
        budget["consumed_cost_units"] += action["maximum_reserved_cost_units"]
        budget["consumed_" + kind + "_turns"] += action["maximum_reserved_provider_turns"]
        budget["provider_action"] = {**action, "status": "ambiguous_provider_completion",
                                     "closed_at": _now()}
        return self._update(record, event_kind="ambiguous_provider_completion",
            event_detail={"operation_id": action["operation_id"], "operation_type": kind},
            status="failed_safe", execution_budget_v01=budget,
            needs_tanner={"urgency": "urgent_blocking_flow",
                "reason": "ambiguous_provider_completion",
                "decision_needed": "cancel, inspect body-free evidence, or create a new exact request"})

    def _reserve_provider(self, record, *, operation_type, package_id, package_sha256,
                          invocation_id, task_scope_id, turns, cost):
        budget = dict(record.get("execution_budget_v01") or {})
        if not budget:
            raise PermissionError("stepwise provider action requires a durable campaign budget")
        if budget.get("provider_action") is not None:
            raise RuntimeError("a provider action is already reserved")
        now = datetime.now(timezone.utc)
        exhausted = None
        if now >= datetime.fromisoformat(budget["expires_at"]):
            exhausted = "maximum_duration_seconds"
        elif (budget["consumed_" + operation_type + "_turns"] + turns >
                budget["maximum_" + operation_type + "_turns"]):
            exhausted = "maximum_" + operation_type + "_turns"
        elif budget["consumed_provider_turns"] + turns > budget["maximum_provider_turns"]:
            exhausted = "maximum_provider_turns"
        elif budget["consumed_cost_units"] + cost > budget["maximum_cost_units"]:
            exhausted = "maximum_cost_units"
        if exhausted is not None:
            self._update(record, event_kind="provider_budget_exhausted",
                event_detail={"exhausted_limit":exhausted,"requested_turns":turns,
                    "requested_cost_units":cost}, status="failed_safe",
                needs_tanner={"urgency":"urgent_blocking_flow",
                    "reason":"provider_budget_exhausted","exhausted_limit":exhausted,
                    "decision_needed":"create a new exact request"})
            raise RuntimeError("campaign provider budget is exhausted: " + exhausted)
        action = {"operation_id": "provider-action-" + _digest({
                "campaign_id": record["campaign_id"], "package_id": package_id,
                "invocation_id": invocation_id, "operation_type": operation_type,
                "iteration": record["iteration"], "budget_sha256": budget["budget_sha256"]}),
            "campaign_id": record["campaign_id"], "task_scope_id": task_scope_id,
            "package_id": package_id, "package_sha256": package_sha256,
            "scope_sha256": _digest(record["allowed_scope"]),
            "invocation_id": invocation_id, "operation_type": operation_type,
            "maximum_reserved_provider_turns": turns,
            "maximum_reserved_cost_units": cost, "iteration": record["iteration"],
            "correction_cycle": max(0, record["iteration"] - 1),
            "started_at": _now(), "expires_at": budget["expires_at"],
            "budget_sha256": budget["budget_sha256"],
            "status": "provider_action_reserved"}
        action["record_sha256"] = _digest(action)
        budget["provider_action"] = action
        return self._update(record, event_kind="provider_action_reserved",
            event_detail={"operation_id": action["operation_id"], "operation_type": operation_type},
            execution_budget_v01=budget)

    def reserve_worker_provider_action(self, *, campaign_id, task_scope_id, package_id,
                                       package_sha256, invocation_id):
        record = self.store.load(campaign_id)
        package = self.exchange._load("packages", require_id(package_id, "package_id"))
        if record.get("status") != "builder_in_progress" or task_scope_id != record.get(
                "active_builder_task_scope_id") or package.get("task_scope_id") != task_scope_id or package.get(
                "record_sha256") != package_sha256:
            raise PermissionError("Worker reservation is not eligible")
        return self._reserve_provider(record, operation_type="worker", package_id=package_id,
            package_sha256=package_sha256, invocation_id=invocation_id,
            task_scope_id=task_scope_id, turns=1, cost=1)

    def _consume_provider_reservation(self, campaign_id, result_identity=None):
        record = self.store.load(campaign_id); budget = dict(record["execution_budget_v01"])
        action = budget.get("provider_action") or {}
        if action.get("status") != "provider_action_reserved":
            raise PermissionError("exact provider reservation is unavailable")
        kind = action["operation_type"]
        budget["consumed_provider_turns"] += action["maximum_reserved_provider_turns"]
        budget["consumed_cost_units"] += action["maximum_reserved_cost_units"]
        budget["consumed_" + kind + "_turns"] += action["maximum_reserved_provider_turns"]
        completed = {**action, "status": "provider_result_checkpointed",
            "result_identity": result_identity, "closed_at": _now()}
        budget["provider_actions"] = [*budget.get("provider_actions", []), completed]
        budget["provider_action"] = None
        return self._update(record, event_kind="provider_result_checkpointed",
            event_detail={"operation_id": action["operation_id"]}, execution_budget_v01=budget)

    def _close_failed_provider_reservation(self, campaign_id, *, failure_code,
                                           completion_class="ambiguous_provider_completion"):
        """Conservatively consume and close one failed provider reservation."""
        record = self.store.load(campaign_id)
        budget = dict(record.get("execution_budget_v01") or {})
        action = budget.get("provider_action")
        if not isinstance(action, dict) or action.get("status") not in {
                "provider_action_reserved", "provider_action_in_flight"}:
            raise PermissionError("exact provider reservation is unavailable for failure closure")
        kind = action["operation_type"]
        reserved_turns = action["maximum_reserved_provider_turns"]
        reserved_cost = action["maximum_reserved_cost_units"]
        budget["consumed_provider_turns"] += reserved_turns
        budget["consumed_cost_units"] += reserved_cost
        budget["consumed_" + kind + "_turns"] += reserved_turns
        closed = {**action, "status": completion_class, "failure_code": failure_code,
            "closed_at": _now(), "reserved_turns_consumed": reserved_turns,
            "reserved_cost_units_consumed": reserved_cost,
            "automatic_retry_permitted": False}
        closed["record_sha256"] = _digest(
            {key: value for key, value in closed.items() if key != "record_sha256"})
        budget["provider_actions"] = [*budget.get("provider_actions", []), closed]
        budget["provider_action"] = None
        return self._update(record, event_kind="provider_reservation_failed_closed",
            event_detail={"operation_id": action["operation_id"],
                "operation_type": kind, "failure_code": failure_code,
                "completion_class": completion_class},
            status="failed_safe", execution_budget_v01=budget,
            needs_tanner={"urgency": "urgent_blocking_flow",
                "reason": "ambiguous_provider_completion",
                "failure_code": failure_code,
                "decision_needed": "cancel, inspect body-free evidence, or create a new exact request"})

    def _apply_reviewed_builder_candidate(self, *, package_id, campaign_id,
                                          review_report_id, review_acceptance_receipt):
        from src.runtime.codex_write_builder_adapter import CodexWriteBuilderAdapter
        return CodexWriteBuilderAdapter(self.exchange, workspace=ROOT,
            runtime_state_root=self.runtime_state_root,
            timeout_seconds=self.worker_timeout_seconds).apply_reviewed_candidate_once(
                package_id=package_id, campaign_id=campaign_id,
                review_report_id=review_report_id,
                review_acceptance_receipt=review_acceptance_receipt)

    def _canonical_application_adapter(self):
        """Resolve the canonical owner without accepting caller-supplied validation logic."""
        from src.runtime.codex_write_builder_adapter import CodexWriteBuilderAdapter
        owner = getattr(self.candidate_applier, "__self__", None)
        function = getattr(self.candidate_applier, "__func__", None)
        if (isinstance(owner, CodexWriteBuilderAdapter)
                and function is CodexWriteBuilderAdapter.apply_reviewed_candidate_once):
            return owner
        if (owner is self
                and function is CodexDevelopmentCampaign._apply_reviewed_builder_candidate):
            return CodexWriteBuilderAdapter(self.exchange, workspace=ROOT,
                runtime_state_root=self.runtime_state_root,
                timeout_seconds=self.worker_timeout_seconds)
        raise PermissionError("campaign application owner is not canonically reconcilable")

    def reconcile_completed_application(self, campaign_id):
        """Retrieve one exact terminal application without replaying its authority."""
        record = self.store.load(campaign_id)
        if record.get("status") != "succeeded":
            raise RuntimeError("campaign application is not terminally successful")
        reviews = record.get("reviews") or []
        if not reviews:
            raise PermissionError("campaign has no accepted independent review")
        review = reviews[-1]
        receipt = review.get("review_acceptance_receipt")
        application = record.get("application_evidence")
        if (review.get("status") not in {"pass", "pass_with_caveats"}
                or not isinstance(receipt, dict)
                or receipt.get("record_sha256") != _digest(
                    {key: value for key, value in receipt.items() if key != "record_sha256"})
                or receipt.get("campaign_id") != campaign_id
                or not isinstance(application, dict)
                or application.get("status") != "applied_verified_after_review"
                or application.get("application_count") != 1
                or application.get("operation_id") !=
                    review.get("reviewed_application_operation_id")
                or application.get("review_report_id") != review.get("review_report_id")
                or application.get("review_acceptance_receipt_sha256") !=
                    receipt.get("record_sha256")):
            raise PermissionError("campaign terminal application lineage is incomplete")
        runs = record.get("builder_runs") or []
        if not runs:
            raise PermissionError("campaign has no retained candidate")
        run = runs[-1]
        if (receipt.get("package_id") != run.get("package_id")
                or receipt.get("review_report_id") != review.get("review_report_id")
                or receipt.get("review_package_id") != review.get("review_package_id")
                or receipt.get("candidate_snapshot_id") !=
                    (run.get("candidate_snapshot") or {}).get("candidate_snapshot_id")
                or receipt.get("mutation_manifest_sha256") !=
                    (run.get("candidate_retention_receipt") or {}).get(
                        "mutation_manifest_sha256")
                or receipt.get("allowed_scope_sha256") != _digest(record["allowed_scope"])):
            raise PermissionError("campaign acceptance receipt is neighboring or mismatched")
        adapter = self._canonical_application_adapter()
        return adapter.reconcile_reviewed_candidate_application(
            operation_id=application["operation_id"], package_id=run["package_id"],
            campaign_id=campaign_id, review_report_id=review["review_report_id"],
            review_acceptance_receipt=receipt)

    def _complete_pending_reviewed_application(self, record):
        """Apply once or reconcile an exact application completed before checkpointing."""
        if record.get("status") != "review_accepted_application_pending":
            raise RuntimeError("campaign has no pending reviewed application")
        review = (record.get("reviews") or [])[-1]
        receipt = review.get("review_acceptance_receipt")
        run = (record.get("builder_runs") or [])[-1]
        try:
            adapter = self._canonical_application_adapter()
        except Exception as exc:
            return self._update(record, event_kind="reviewed_candidate_apply_failed",
                status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                "reason":"reviewed_candidate_apply_failed", "failure_code":type(exc).__name__,
                "decision_needed":"inspect retained candidate and apply failure evidence"})
        try:
            self.candidate_applier(
                package_id=run["package_id"], campaign_id=record["campaign_id"],
                review_report_id=review["review_report_id"],
                review_acceptance_receipt=receipt)
        except Exception:
            # A process may have completed the durable application before the
            # campaign checkpoint. Only canonical reconciliation can classify it.
            pass
        try:
            application = adapter.reconcile_reviewed_candidate_application(
                operation_id=review["reviewed_application_operation_id"],
                package_id=run["package_id"], campaign_id=record["campaign_id"],
                review_report_id=review["review_report_id"],
                review_acceptance_receipt=receipt)
        except Exception as exc:
            return self._update(record, event_kind="reviewed_candidate_apply_failed",
                status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                "reason":"reviewed_candidate_apply_failed", "failure_code":type(exc).__name__,
                "decision_needed":"inspect retained candidate and apply failure evidence"})
        if record.get("stepwise_v01"):
            return self._update(record, event_kind="reviewed_application_completed",
                status="reviewed_application_completed", needs_tanner=None,
                application_evidence=application, git_commit_evidence=None,
                creates_authority=False, creates_continuing_authority=False)
        event = ("campaign_succeeded_with_nonblocking_caveats"
                 if review["status"] == "pass_with_caveats" else "campaign_succeeded")
        return self._update(record, event_kind=event, status="succeeded",
            needs_tanner=None, application_evidence=application,
            git_commit_evidence=None,creates_authority=False,
            creates_continuing_authority=False)

    def _complete_pending_reviewed_git_locked(self, record, guard):
        """Perform or observe the sole reviewed Git stage after application checkpointing."""
        if record.get("status") != "reviewed_application_completed":
            raise RuntimeError("campaign has no completed reviewed application")
        application = record.get("application_evidence")
        review = (record.get("reviews") or [])[-1]
        if (not isinstance(application, dict)
                or application.get("status") != "applied_verified_after_review"
                or application.get("application_count") != 1
                or application.get("operation_id") != review.get("reviewed_application_operation_id")):
            raise PermissionError("exact terminal reviewed application is required")
        try:
            from src.runtime.git_commit_transaction import GitCommitTransaction
            adapter = self._canonical_application_adapter()
            projection = application["reviewed_commit_projection"]
            if self.git_transaction_state_root is None:
                raise RuntimeError("canonical Git transaction state root is unavailable")
            owner = GitCommitTransaction(adapter.workspace, self.git_transaction_state_root)
            try:
                committed = owner.reconcile_campaign_reviewed_application(
                    operation_id=application["operation_id"],
                    terminal_application_receipt=application,
                    campaign_store=self.store, campaign_protection=guard)
            except FileNotFoundError:
                committed = None
            if committed is not None:
                if committed.get("status") != "committed":
                    return self._update(record, event_kind="reviewed_git_failed_safe",
                        status="failed_safe", git_commit_evidence=committed,
                        needs_tanner={"urgency":"urgent_blocking_flow",
                            "reason":committed.get("reason", "reviewed_git_failed_safe"),
                            "decision_needed":"inspect exact Git transaction evidence"},
                        creates_authority=False, creates_continuing_authority=False)
            else:
                budget = record.get("execution_budget_v01") or {}
                if (record.get("stepwise_v01")
                        and datetime.now(timezone.utc) >=
                            datetime.fromisoformat(budget["expires_at"])):
                    return self._update(record,
                        event_kind="campaign_expired_before_git",
                        status="failed_safe", git_commit_evidence=None,
                        needs_tanner={"urgency":"urgent_blocking_flow",
                            "reason":"campaign_duration_expired",
                            "decision_needed":"create a new exact request"},
                        creates_authority=False,
                        creates_continuing_authority=False)
                prepared = owner.prepare_reviewed_application(
                    terminal_application_receipt=application,
                    operation_id=application["operation_id"],
                    expected_parent_head=application["binding"]["expected_repository_head"],
                    reviewed_tree_sha256=projection["expected_tree"],
                    scope=application["applied_paths"],
                    exact_diff_sha256=projection["expected_diff_sha256"],
                    mutation_manifest_sha256=application["binding"]["mutation_manifest_sha256"],
                    review_receipt_sha256=application["review_acceptance_receipt_sha256"],
                    message=projection["message"])
                committed = owner.advance_campaign_reviewed_application(
                    prepared, application, campaign_store=self.store,
                    campaign_protection=guard)
            if committed.get("status") != "committed":
                return self._update(record, event_kind="reviewed_git_failed_safe",
                    status="failed_safe", git_commit_evidence=committed,
                    needs_tanner={"urgency":"urgent_blocking_flow",
                        "reason":committed.get("reason", "reviewed_git_failed_safe"),
                        "decision_needed":"inspect exact Git transaction evidence"},
                    creates_authority=False, creates_continuing_authority=False)
        except Exception as exc:
            # A CAS may have completed before the transport surfaced an
            # exception.  While campaign protection is still held, observation
            # of the canonical intent is the only permissible recovery action.
            try:
                recovered = owner.reconcile_campaign_reviewed_application(
                    operation_id=application["operation_id"],
                    terminal_application_receipt=application,
                    campaign_store=self.store, campaign_protection=guard)
            except Exception:
                recovered = None
            if recovered is not None and recovered.get("status") == "committed":
                committed = recovered
            else:
                return self._update(record, event_kind="reviewed_git_failed_safe",
                    status="failed_safe", git_commit_evidence=recovered,
                    needs_tanner={"urgency":"urgent_blocking_flow",
                    "reason":((recovered or {}).get("reason") or "reviewed_git_failed_safe"),
                    "failure_code":type(exc).__name__,
                    "decision_needed":"inspect exact Git transaction evidence"},
                    creates_authority=False, creates_continuing_authority=False)
        event = ("campaign_succeeded_with_nonblocking_caveats"
                 if review["status"] == "pass_with_caveats" else "campaign_succeeded")
        return self._update(record, event_kind=event, status="succeeded",
            needs_tanner=None, git_commit_evidence=committed,
            creates_authority=False, creates_continuing_authority=False)

    def _complete_pending_reviewed_git(self, record):
        """Linearize the reviewed Git stage against cancellation and terminal mutation."""
        with self.store.protected(record["campaign_id"]) as handle:
            current=self.store.load(record["campaign_id"])
            if (current.get("record_sha256")!=record.get("record_sha256")
                    or current.get("state_revision")!=record.get("state_revision")
                    or current.get("status")!="reviewed_application_completed"
                    or current.get("cancelled")):
                raise PermissionError("campaign changed before protected Git stage")
            operation_id=current["application_evidence"]["operation_id"]
            guard=_ProtectedGitGuard(_PROTECTED_GIT_GUARD_SECRET,
                campaign_id=current["campaign_id"],record_sha256=current["record_sha256"],
                state_revision=current["state_revision"],operation_id=operation_id,handle=handle)
            try:
                return self._complete_pending_reviewed_git_locked(current,guard)
            finally:
                guard.close()

    def _handle_typed_approval(self, approval, *, timeout_seconds, process_alive=None):
        """Project one exact typed request into the accepted Rider boundary."""
        paused = self.require_tanner(
            approval["campaign_id"], invocation_id=approval["invocation_id"],
            worker=approval["worker"], kind=approval["kind"],
            blocked_action=approval["blocked_action"],
            why_required=approval["why_required"],
            requested_authority=approval["requested_authority"],
            resources=approval["resources"], reversible=approval["reversible"],
            provider_code=approval["provider_code"],
            protocol_binding=approval["protocol"], expires_in_seconds=timeout_seconds,
            expiration_reason=("This exact typed request is bound to a frozen candidate and one "
                               "app-server invocation; indefinite reuse would become stale authority."),
            expiration_effect=("The exact request and any unconsumed grant become invalid and the "
                               "blocked action remains unperformed."),
            can_request_again=True, work_lost=False)
        attention_id = paused["needs_tanner"]["attention_id"]
        try:
            result = self.attention_store.wait_for_decision(
                attention_id, timeout_seconds=timeout_seconds, process_alive=process_alive,
                reminder_handler=lambda _event: retain_needs_tanner_notification(
                    self.store.load(approval["campaign_id"])))
        except (PermissionError, TimeoutError):
            current = self.store.load(approval["campaign_id"])
            if ((current.get("needs_tanner") or {}).get("attention_id") == attention_id
                    and current.get("status") == "tanner_escalation"):
                self._update(current, event_kind="tanner_attention_failed_safe",
                    event_detail={"attention_id": attention_id,
                                  "invocation_id": approval["invocation_id"]},
                    status="failed_safe", needs_tanner={
                        "reason": "attention_unavailable_or_expired",
                        "attention_id": attention_id,
                        "invocation_id": approval["invocation_id"],
                        "decision_needed": "create a new exact request",
                    }, creates_authority=False,
                    creates_continuing_authority=False)
            raise
        decision = result["decision"]
        if (decision.get("choice") == "approve_once"
                and approval["protocol"].get("managed_material_record_sha256")):
            with self.store.protected(approval["campaign_id"]):
                current = self.store.load(approval["campaign_id"])
                retained = self.attention_store.lifecycle(attention_id).get("decision") or {}
                if (current.get("status") != "ready_for_bounded_continuation"
                        or (retained.get("campaign_publication") or {}).get("state") != "published"
                        or retained.get("decision_id") != decision.get("decision_id")):
                    raise PermissionError("managed Worker decision publication is incomplete")
        if (decision.get("choice") == "approve_once"
                and approval["protocol"].get(
                    "approval_binding_kind") == "independent_review_provider"):
            # DevelopmentAttentionStore.decide wakes its waiter after the exact
            # decision is durable.  Do not return that decision to the paused
            # process until the campaign has published the matching live-action
            # state under its own serialization boundary.
            with self.store.protected(approval["campaign_id"]):
                current = self.store.load(approval["campaign_id"])
                active = current.get("active_review_native_action") or {}
                if (current.get("status") != "reviewer_native_action_approved"
                        or active.get("attention_id") != attention_id
                        or active.get("decision_id") != decision.get("decision_id")
                        or active.get("invocation_id") != approval["invocation_id"]
                        or active.get("review_package_id") !=
                            approval["protocol"].get("review_package_id")):
                    raise PermissionError(
                        "Reviewer native-action publication is stale or mismatched")
        is_review_action = (approval["protocol"].get(
            "approval_binding_kind") == "independent_review_provider")

        def close_failed_review_action(reason):
            if not is_review_action:
                return
            try:
                lifecycle = self.attention_store.lifecycle(attention_id)
                retained = lifecycle.get("decision") or {}
                if retained.get("consumed") is not True:
                    self.attention_store.consume_approve_once(
                        decision["decision_id"], attention_id=attention_id,
                        invocation_id=approval["invocation_id"],
                        protocol_binding_sha256=result["event"].get(
                            "protocol_binding_sha256"),
                        approved_action_sha256=approval["protocol"].get(
                            "approved_action_sha256"),
                        expected_binding=self.attention_store._authority_binding(
                            result["event"]))
                self.attention_store.finish_live_action(
                    decision["decision_id"], status="failed")
            except (PermissionError, RuntimeError, TimeoutError):
                # An already invalid or expired decision cannot authorize an
                # action.  The campaign must still close failed-safe below.
                pass
            self._fail_review_native_action(
                approval["campaign_id"], attention_id,
                decision["decision_id"], approval["invocation_id"],
                reason=reason)

        def claim(continuation_id=None):
            try:
                return self.attention_store.consume_approve_once(
                    decision["decision_id"], attention_id=attention_id,
                    invocation_id=approval["invocation_id"],
                    protocol_binding_sha256=result["event"].get("protocol_binding_sha256"),
                    approved_action_sha256=approval["protocol"]["approved_action_sha256"],
                    continuation_id=continuation_id)
            except (PermissionError, RuntimeError, TimeoutError):
                retained = (self.attention_store.lifecycle(attention_id).get(
                    "decision") or {})
                # A rejected duplicate claim is only replay evidence.  The
                # already-claimed original action retains responsibility for
                # reporting its own exact terminal result.
                if retained.get("consumed") is not True:
                    close_failed_review_action(
                        "reviewer_native_action_claim_failed")
                raise
        def reserve(continuation_id):
            try:
                return self.attention_store.reserve_detached_continuation(
                    decision["decision_id"], attention_id=attention_id,
                    invocation_id=approval["invocation_id"],
                    protocol_binding_sha256=result["event"].get("protocol_binding_sha256"),
                    continuation_id=continuation_id)
            except (PermissionError, RuntimeError, TimeoutError):
                close_failed_review_action("reviewer_native_action_transport_lost")
                raise
        def finish(continuation_id, status):
            completed = self.attention_store.finish_detached_continuation(
                decision["decision_id"], continuation_id, status=status)
            if approval["protocol"].get(
                    "approval_binding_kind") == "independent_review_provider":
                self._finish_review_native_action(
                    approval["campaign_id"], attention_id,
                    decision["decision_id"], approval["invocation_id"],
                    action_status="completed" if status == "completed" else "failed")
            return completed
        def complete(status):
            completed = self.attention_store.finish_live_action(
                decision["decision_id"], status=status)
            if approval["protocol"].get(
                    "approval_binding_kind") == "independent_review_provider":
                self._finish_review_native_action(
                    approval["campaign_id"], attention_id,
                    decision["decision_id"], approval["invocation_id"],
                    action_status=status)
            return completed
        return {"choice": decision["choice"], "attention_id": attention_id,
                "decision_id": decision["decision_id"], "claim": claim,
                "reserve": reserve, "finish": finish, "complete": complete}

    def _finish_review_native_action(self, campaign_id, attention_id, decision_id,
                                     invocation_id, *, action_status):
        """Close one live Reviewer action and restore its exact provider state."""
        if action_status not in {"completed", "failed"}:
            raise ValueError("invalid Reviewer native-action status")
        with self.store.protected(campaign_id):
            current = self.store.load(campaign_id)
            active = current.get("active_review_native_action") or {}
            lifecycle = self.attention_store.lifecycle(attention_id)
            decision = lifecycle.get("decision") or {}
            expected_lifecycle = "completed" if action_status == "completed" else "failed_safe"
            prior_completion = next((item for item in reversed(current.get("events", []))
                if item.get("kind") == "reviewer_native_action_completed"
                and item.get("detail", {}).get("attention_id") == attention_id
                and item.get("detail", {}).get("decision_id") == decision_id
                and item.get("detail", {}).get("invocation_id") == invocation_id
                and item.get("detail", {}).get("action_status") == action_status), None)
            if (current.get("status") == "awaiting_independent_review"
                    and not active and prior_completion is not None
                    and decision.get("decision_id") == decision_id
                    and decision.get("invocation_id") == invocation_id
                    and decision.get("consumed") is True
                    and decision.get("lifecycle_state") == expected_lifecycle):
                return current
            if (current.get("status") != "reviewer_native_action_approved"
                    or active.get("attention_id") != attention_id
                    or active.get("decision_id") != decision_id
                    or active.get("invocation_id") != invocation_id
                    or active.get("resume_status") != "awaiting_independent_review"
                    or decision.get("decision_id") != decision_id
                    or decision.get("invocation_id") != invocation_id
                    or decision.get("consumed") is not True
                    or decision.get("lifecycle_state") != expected_lifecycle):
                raise PermissionError(
                    "Reviewer native-action completion is stale or mismatched")
            return self._update(current,
                event_kind="reviewer_native_action_completed",
                event_detail={"attention_id": attention_id,
                              "decision_id": decision_id,
                              "invocation_id": invocation_id,
                              "action_status": action_status},
                status="awaiting_independent_review",
                active_review_native_action=None,
                creates_authority=False,
                creates_continuing_authority=False)

    def _fail_review_native_action(self, campaign_id, attention_id, decision_id,
                                   invocation_id, *, reason):
        """Close an unresumable Reviewer action without retry or authority."""
        with self.store.protected(campaign_id):
            current = self.store.load(campaign_id)
            active = current.get("active_review_native_action") or {}
            if current.get("status") == "failed_safe":
                return current
            if (current.get("status") != "reviewer_native_action_approved"
                    or active.get("attention_id") != attention_id
                    or active.get("decision_id") != decision_id
                    or active.get("invocation_id") != invocation_id):
                raise PermissionError(
                    "Reviewer native-action failure is stale or mismatched")
            return self._update(current,
                event_kind="reviewer_native_action_failed_safe",
                event_detail={"attention_id": attention_id,
                              "decision_id": decision_id,
                              "invocation_id": invocation_id,
                              "reason": reason},
                status="failed_safe",
                active_review_native_action=None,
                needs_tanner={
                    "reason": reason,
                    "attention_id": attention_id,
                    "invocation_id": invocation_id,
                    "decision_needed": "inspect evidence or create a new exact request",
                },
                creates_authority=False,
                creates_continuing_authority=False)

    @staticmethod
    def _validated_worker_attention_binding(record, attention, transport_result):
        """Bind a returned Worker Attention request to coordinator-owned lineage."""
        if not isinstance(attention, dict) or not isinstance(transport_result, dict):
            raise PermissionError("Worker Attention lineage is missing")
        protocol = attention.get("protocol")
        snapshot = transport_result.get("candidate_snapshot")
        if not isinstance(protocol, dict) or not isinstance(snapshot, dict):
            raise PermissionError("Worker Attention lineage is incomplete")
        invocation_id = transport_result.get("invocation_id")
        expected = {
            "candidate_snapshot_id": snapshot.get("candidate_snapshot_id"),
            "candidate_record_sha256": snapshot.get("record_sha256"),
            "mutation_digest_sha256": transport_result.get("workspace_changes_sha256"),
            "authorized_scope_sha256": _digest(record["allowed_scope"]),
        }
        required_protocol = ("version", "method", "item_id", "approved_action_sha256",
                             *expected)
        if (not isinstance(invocation_id, str) or not invocation_id
                or attention.get("invocation_id") != invocation_id
                or attention.get("campaign_id") != record["campaign_id"]
                or any(not isinstance(protocol.get(key), str) or not protocol[key]
                       for key in required_protocol)
                or any(protocol.get(key) != value for key, value in expected.items())
                or protocol.get("method") != attention.get("provider_code")):
            raise PermissionError("Worker Attention lineage is missing or mismatched")
        exact_action = attention.get("exact_action")
        if (not isinstance(exact_action, dict)
                or protocol["approved_action_sha256"] != _digest(exact_action)
                or exact_action.get("method") != protocol["method"]):
            raise PermissionError("Worker Attention action identity is missing or mismatched")
        return {**protocol, **expected}

    def _validated_review_attention_binding(self, record, binding, worker, invocation_id):
        """Validate a Reviewer Attention tuple against canonical campaign records."""
        if not isinstance(binding, dict):
            raise PermissionError("Reviewer Attention lineage is missing")
        review_request = next((item for item in reversed(record.get("review_requests", []))
                               if item.get("iteration") == record.get("iteration")), None)
        run = record.get("builder_runs", [])[-1] if record.get("builder_runs") else {}
        retention = run.get("candidate_retention_receipt") or {}
        snapshot = retention.get("candidate_snapshot") or run.get("candidate_snapshot") or {}
        package_id = (review_request or {}).get("package_id")
        try:
            package = self.exchange._load("packages", package_id)
        except Exception as exc:
            raise PermissionError("Reviewer Attention package is unavailable") from exc
        canonical = {
            "approval_binding_kind": "independent_review_provider",
            "campaign_id": record["campaign_id"],
            "review_package_id": package_id,
            "review_package_record_sha256": package.get("record_sha256"),
            "candidate_snapshot_id": snapshot.get("candidate_snapshot_id"),
            "candidate_record_sha256": snapshot.get("record_sha256"),
            "mutation_digest_sha256": retention.get("mutation_manifest_sha256"),
            "exact_change_evidence_sha256": retention.get(
                "exact_change_evidence_sha256"),
            "authorized_scope_sha256": retention.get("allowed_scope_sha256"),
            "reviewer_worker_id": worker.get("worker_id"),
            "reviewer_identity_sha256": _digest(worker),
            "reviewer_invocation_id": invocation_id,
        }
        if (record.get("status") != "awaiting_independent_review"
                or package.get("recipient", {}).get("worker_id") != worker.get("worker_id")
                or package.get("recipient", {}).get("role") != worker.get("role")
                or any(not isinstance(canonical.get(key), str) or not canonical[key]
                       for key in canonical)
                or any(binding.get(key) != value for key, value in canonical.items())
                or binding.get("recipient_sha256") != canonical["reviewer_identity_sha256"]
                or binding.get("approval_binding_sha256") != _digest(canonical)):
            raise PermissionError("Reviewer Attention lineage is missing or mismatched")
        return binding

    @staticmethod
    def _event(kind, detail=None):
        value = {"event_id": f"campaign-event-{uuid.uuid4()}", "kind": kind,
                 "created_at": _now(), "detail": detail or {}}
        value["event_sha256"] = _digest(value)
        return value

    def _update(self, record, *, event_kind, event_detail=None, **changes):
        current_revision = record["state_revision"]
        updated = {**record, **changes, "state_revision": current_revision + 1,
                   "updated_at": _now(), "events": [*record["events"], self._event(event_kind, event_detail)]}
        retained = self.store.write(updated, expected_revision=current_revision)
        retain_needs_tanner_notification(retained)
        retain_campaign_terminal_notification(retained)
        needs = retained.get("needs_tanner")
        if needs and needs != record.get("needs_tanner"):
            from src.runtime.component_supervision import ComponentReceiptStore
            component = ("worker" if "builder" in event_kind else
                         "reviewer" if "review" in event_kind else "development_coordinator")
            ComponentReceiptStore(self.supervision_root).failure(
                component=component, stage=event_kind,
                category=str(needs.get("reason") or "needs_tanner"),
                provider_code=needs.get("failure_code"),
                service_state="needs_tanner", notify=True,
            )
        return retained

    def create(self, payload, *, authenticated_rider, stepwise=False):
        if authenticated_rider is not True:
            raise PermissionError("authenticated rider authority is required")
        if not isinstance(payload, dict) or payload.get("explicitly_authorized") is not True:
            raise PermissionError("explicit campaign authorization is required")
        if payload.get("instance_id") not in {None, self.instance_id}:
            raise PermissionError("Development campaign belongs to another Phoenix")
        if payload.get("target_builder") != "codex_repo":
            raise ValueError("campaign builder must be explicit CODEX (REPO)")
        mode = payload.get("objective_mode")
        if mode not in BUILDER_MODES:
            raise ValueError("objective_mode must be read_only or repository_write")
        campaign_id = require_id(payload.get("campaign_id") or f"codex-campaign-{uuid.uuid4()}", "campaign_id")
        objective = _text(payload.get("objective"), "campaign objective")
        conditions = _ids(payload.get("acceptance_condition_ids"), "acceptance_condition_id")
        condition_text = payload.get("acceptance_conditions")
        if not isinstance(condition_text, dict) or set(condition_text) != set(conditions):
            raise ValueError("each acceptance condition requires exact text")
        condition_text = {item: _text(condition_text[item], "acceptance condition", maximum=8_000)
                          for item in conditions}
        allowed_scope = _scopes(payload.get("allowed_scope"))
        recovery = payload.get("recovery_references")
        if not isinstance(recovery, list) or not recovery:
            raise ValueError("at least one recovery reference is required")
        recovery = body_free_references(recovery)
        authorization_reference = require_id(payload.get("rider_authorization_reference"),
                                             "rider_authorization_reference")
        validation_commands = _validation_commands(payload.get("validation_commands", []))
        validation_policy, validation_declaration = _validation_contract(
            payload, validation_commands, campaign_id=campaign_id, allowed_scope=allowed_scope)
        created = _now()
        budget = self._budget_from_payload(payload, created)
        if stepwise and budget is None:
            raise ValueError("stepwise campaign requires execution_budget_v01")
        if stepwise and self.git_transaction_state_root is None:
            raise ValueError("stepwise campaign requires an exact external Git transaction state root")
        if stepwise:
            self.git_transaction_state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        record = {
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "record_type": "codex_development_campaign",
            "contract_version": CAMPAIGN_CONTRACT_VERSION,
            "campaign_id": campaign_id,
            "instance_id": self.instance_id,
            "objective": objective,
            "objective_sha256": hashlib.sha256(objective.encode()).hexdigest(),
            "objective_mode": mode,
            "acceptance_condition_ids": conditions,
            "acceptance_conditions": condition_text,
            "allowed_scope": allowed_scope,
            "source_sections": _source_sections(payload.get("source_sections", [])),
            "validation_commands": validation_commands,
            "validation_policy": validation_policy,
            "validation_declaration": validation_declaration,
            "rider_authorization_reference": authorization_reference,
            "recovery_references": recovery,
            "builder": {**CODEX_REPO_WORKER_REFERENCE, "target": "codex_repo",
                        "execution_mode_required": mode, "identified_is_authorized": False},
            "reviewer_requirement": {"functional_role": FORMAL_REVIEW_ROLE,
                "role": DEFAULT_REVIEWER_ROLE, "worker_id": DEFAULT_REVIEWER_WORKER_ID,
                "transport_binding": "wsl-codex-exec-exact-review-v0.1", "must_differ_from_builder": True,
                "identity_is_authority": False},
            "maximum_iterations": MAX_ITERATIONS,
            "iteration": 0,
            "status": "ready",
            "active_builder_task_scope_id": None,
            "builder_runs": [],
            "reviews": [],
            "review_requests": [],
            "review_transport_attempts": [],
            "cache_lifecycle_events": [],
            "acceptance_satisfied": [],
            "needs_tanner": None,
            "attention_event_ids": [],
            "cancelled": False,
            "automatic_promotion": False,
            "creates_authority": False,
            "state_revision": 1,
            "created_at": created,
            "stepwise_v01": bool(stepwise),
            "execution_budget_v01": budget,
            "updated_at": created,
            "events": [self._event("campaign_created", {"authorization_reference": authorization_reference})],
        }
        record = self.store.write(record)
        return record if stepwise else self._start_builder(record, correction=None)

    def require_tanner(self, campaign_id, *, invocation_id, worker, kind,
                       blocked_action, why_required, requested_authority,
                       resources=(), reversible=None, provider_code=None,
                       protocol_binding=None, expires_in_seconds=None,
                       expiration_reason=None, expiration_effect=None,
                       can_request_again=None, work_lost=None):
        """Pause one exact campaign action at the durable Rider boundary."""
        record = self.store.load(campaign_id)
        if record["cancelled"] or record["status"] in {"succeeded", "cancelled"}:
            raise RuntimeError("terminal campaign cannot request new authority")
        binding = dict(protocol_binding or {})
        if binding.get("managed_material_record_sha256"):
            budget = record.get("execution_budget_v01") or {}
            if budget:
                remaining = (datetime.fromisoformat(budget["expires_at"]) - datetime.now(timezone.utc)).total_seconds()
                if remaining < 1:
                    raise PermissionError("managed campaign duration has expired")
                expires_in_seconds = min(int(remaining), int(expires_in_seconds or remaining))
        binding.setdefault("rider_id", "tanner")
        if binding.get("approval_binding_kind") == "independent_review_provider":
            self._validated_review_attention_binding(
                record, binding, worker, invocation_id)
        else:
            binding.setdefault("recipient_sha256", _digest(worker))
            binding.setdefault("authorized_scope_sha256", _digest(record["allowed_scope"]))
        event = self.attention_store.create(
            campaign_id=campaign_id, invocation_id=invocation_id, worker=worker,
            kind=kind, blocked_action=blocked_action, why_required=why_required,
            requested_authority=requested_authority, resources=resources,
            reversible=reversible, provider_code=provider_code,
            protocol_binding=binding, expires_in_seconds=expires_in_seconds,
            expiration_reason=expiration_reason, expiration_effect=expiration_effect,
            can_request_again=can_request_again, work_lost=work_lost)
        needs = {"urgency": "urgent_blocking_flow", "reason": kind,
                 "plain_reason": event["why_required"],
                 "decision_needed": "Approve this exact action once, deny it, or cancel the campaign",
                 "attention_id": event["attention_id"], "invocation_id": invocation_id,
                 "detail_url": event["detail_url"],
                 "urgency": event["urgency"], "expires_at": event["expires_at"],
                 "expiration_reason": event["expiration_reason"],
                 "expiration_effect": event["expiration_effect"],
                 "can_request_again": event["can_request_again"], "work_lost": event["work_lost"],
                 "worker_id": worker["worker_id"], "requested_authority": event["requested_authority"]}
        if binding.get("approval_binding_kind") == "independent_review_provider":
            needs["resume_status"] = record["status"]
            needs["reviewer_invocation_id"] = binding["reviewer_invocation_id"]
            needs["review_package_id"] = binding["review_package_id"]
        return self._update(record, event_kind="tanner_attention_required",
            event_detail={"attention_id": event["attention_id"], "invocation_id": invocation_id,
                          "worker_id": worker["worker_id"], "kind": kind},
            status="tanner_escalation", needs_tanner=needs,
            attention_event_ids=[*record.get("attention_event_ids", []), event["attention_id"]])

    def decide_attention(self, campaign_id, attention_id, choice, *, authenticated_rider,
                         expected_identity=None):
        # Keep the campaign lock from exact decision persistence through state
        # publication.  The Attention waiter may wake, but cannot return an
        # approval to its paused action until this publication is visible.
        with self.store.protected(campaign_id):
            record = self.store.load(campaign_id)
            needs = record.get("needs_tanner") or {}
            if needs.get("attention_id") != attention_id:
                raise PermissionError("attention decision is not bound to this campaign state")
            result = self.attention_store.decide(
                attention_id, choice, authenticated_rider=authenticated_rider,
                expected_identity=expected_identity)
            if choice == "cancel_campaign":
                if record["status"] == "succeeded":
                    raise RuntimeError("completed campaign cannot be cancelled")
                updated = self._update(record,
                    event_kind="rider_cancelled_campaign", status="cancelled",
                    cancelled=True, needs_tanner=None,
                    active_builder_task_scope_id=None,
                    active_review_native_action=None,
                    creates_authority=False,
                    creates_continuing_authority=False)
                return {"campaign": updated, **result}
            # Approval is retained as one consumable grant. It does not
            # automatically resume a process or broaden campaign scope.
            review_action = (choice == "approve_once"
                and needs.get("resume_status") == "awaiting_independent_review"
                and isinstance(result.get("event"), dict)
                and (result["event"].get("protocol_binding") or {}).get(
                    "approval_binding_kind") == "independent_review_provider")
            active_review_action = ({
                "attention_id": attention_id,
                "decision_id": result["decision"]["decision_id"],
                "invocation_id": needs.get("reviewer_invocation_id"),
                "review_package_id": needs.get("review_package_id"),
                "resume_status": needs.get("resume_status"),
                "creates_authority": False,
                "creates_continuing_authority": False,
            } if review_action else None)
            review_bound = self.attention_store.requires_campaign_publication(result.get("event", {}))
            try:
                updated = self._update(record, event_kind=f"tanner_attention_{choice}",
                    event_detail={"attention_id": attention_id,
                                  "decision_id": result["decision"]["decision_id"]},
                    status=("reviewer_native_action_approved" if review_action else
                            "ready_for_bounded_continuation" if choice == "approve_once" else
                            "failed_safe"),
                    needs_tanner=None,
                    active_review_native_action=active_review_action,
                    creates_authority=False,
                    creates_continuing_authority=False)
            except Exception:
                if review_bound:
                    self.attention_store.fail_unpublished_review_decision(
                        result["decision"]["decision_id"], attention_id=attention_id,
                        campaign_id=campaign_id,
                        reason="campaign_decision_publication_failed")
                    current = self.store.load(campaign_id)
                    if current.get("status") == "tanner_escalation":
                        try:
                            self._update(current,
                                event_kind="attention_decision_publication_failed_safe",
                                event_detail={"attention_id": attention_id,
                                    "decision_id": result["decision"]["decision_id"]},
                                status="failed_safe", active_review_native_action=None,
                                needs_tanner={"reason":
                                    "attention_decision_publication_interrupted",
                                    "attention_id": attention_id,
                                    "invocation_id": result["event"]["invocation_id"],
                                    "decision_needed":
                                        "inspect evidence or create a new exact request"},
                                creates_authority=False,
                                creates_continuing_authority=False)
                        except Exception:
                            pass
                raise
            if review_bound:
                result = {**result, "decision":
                    self.attention_store.publish_review_decision(
                        result["decision"]["decision_id"], attention_id=attention_id,
                        campaign_id=campaign_id,
                        campaign_record_sha256=updated["record_sha256"],
                        campaign_state_revision=updated["state_revision"])}
            return {"campaign": updated, **result}

    def reconcile_attention_decision(self, campaign_id):
        """Reconcile one exact pending or decided Reviewer Attention lifecycle."""
        with self.store.protected(campaign_id):
            record = self.store.load(campaign_id)
            needs = record.get("needs_tanner") or {}
            attention_id = needs.get("attention_id")
            if record.get("status") != "tanner_escalation" or not attention_id:
                return record
            lifecycle = self.attention_store.lifecycle(attention_id)
            event = lifecycle["event"]
            decision = lifecycle.get("decision") or {}
            if not decision:
                binding = event.get("protocol_binding") or {}
                if binding.get("approval_binding_kind") != "independent_review_provider":
                    return record
                if (needs.get("resume_status") != "awaiting_independent_review"
                        or needs.get("reviewer_invocation_id") !=
                            event.get("invocation_id")
                        or needs.get("review_package_id") !=
                            binding.get("review_package_id")):
                    raise PermissionError(
                        "pending Reviewer Attention campaign lineage is mismatched")
                self._validated_review_attention_binding(
                    {**record, "status": needs["resume_status"]}, binding,
                    event.get("reviewer_identity") or {}, event["invocation_id"])
                if event.get("state") == "needs_tanner" and event.get("actionable"):
                    return record
                if event.get("state") == "needs_tanner":
                    event = self.attention_store.fail_unavailable_pending_review(
                        attention_id, campaign_id=campaign_id,
                        invocation_id=event["invocation_id"])
                if event.get("state") not in {"expired", "failed_safe"}:
                    raise PermissionError(
                        "pending Reviewer Attention state is not reconcilable")
                reason = ("attention_unavailable_or_expired"
                          if event.get("state") == "expired" else
                          "reviewer_native_action_transport_lost")
                return self._update(record,
                    event_kind="reviewer_attention_reconciled_failed_safe",
                    event_detail={"attention_id": attention_id,
                                  "invocation_id": event["invocation_id"],
                                  "attention_state": event["state"]},
                    status="failed_safe", active_review_native_action=None,
                    needs_tanner={"reason": reason,
                        "attention_id": attention_id,
                        "invocation_id": event["invocation_id"],
                        "decision_needed":
                            "inspect evidence or create a new exact request"},
                    creates_authority=False,
                    creates_continuing_authority=False)
            publication = decision.get("campaign_publication") or {}
            if (event.get("campaign_id") != campaign_id
                    or decision.get("campaign_id") != campaign_id
                    or decision.get("attention_id") != attention_id
                    or publication.get("state") not in {"pending", "failed_safe"}):
                raise PermissionError(
                    "interrupted Attention decision publication is mismatched")
            if publication.get("state") == "pending":
                self.attention_store.fail_unpublished_review_decision(
                    decision["decision_id"], attention_id=attention_id,
                    campaign_id=campaign_id,
                    reason="campaign_decision_publication_interrupted")
            return self._update(record,
                event_kind="attention_decision_publication_reconciled_failed_safe",
                event_detail={"attention_id": attention_id,
                              "decision_id": decision["decision_id"]},
                status="failed_safe", active_review_native_action=None,
                needs_tanner={"reason": "attention_decision_publication_interrupted",
                    "attention_id": attention_id,
                    "invocation_id": event["invocation_id"],
                    "decision_needed": "inspect evidence or create a new exact request"},
                creates_authority=False, creates_continuing_authority=False)

    def reconcile_review_native_action(self, campaign_id):
        """Project an exact terminal Reviewer action into canonical campaign state."""
        with self.store.protected(campaign_id):
            record = self.store.load(campaign_id)
            if record.get("status") != "reviewer_native_action_approved":
                return record
            active = record.get("active_review_native_action") or {}
            attention_id = active.get("attention_id")
            if not attention_id:
                raise PermissionError("active Reviewer action lineage is unavailable")
            lifecycle = self.attention_store.lifecycle(attention_id)
            decision = lifecycle.get("decision") or {}
            if (decision.get("decision_id") != active.get("decision_id")
                    or decision.get("invocation_id") != active.get("invocation_id")):
                raise PermissionError("active Reviewer action lineage is mismatched")
            state = decision.get("lifecycle_state")
            if state not in {"completed", "failed_safe"}:
                return self._fail_review_native_action(
                    campaign_id, attention_id, active["decision_id"],
                    active["invocation_id"],
                    reason="reviewer_native_action_completion_ambiguous")
            return self._finish_review_native_action(
                campaign_id, attention_id, active["decision_id"],
                active["invocation_id"],
                action_status="completed" if state == "completed" else "failed")

    def resume_reserved_continuation(self, campaign_id, attention_id, decision_id,
                                     continuation_id, *, recovery_runner):
        with _lock(self.store.root / f"{campaign_id}.json"):
            return self._resume_reserved_continuation(
                campaign_id, attention_id, decision_id, continuation_id,
                recovery_runner=recovery_runner)

    def _resume_reserved_continuation(self, campaign_id, attention_id, decision_id,
                                      continuation_id, *, recovery_runner):
        """Canonical post-restart entrypoint for one already-reserved continuation.

        Recovery code is supplied by the canonical campaign runtime; persisted
        data can select no callable and therefore creates no execution authority.
        """
        record = self.store.load(campaign_id)
        event = self.attention_store.get(attention_id)
        expected = self.attention_store._authority_binding(event)
        decision = self.attention_store.lifecycle(attention_id).get("decision") or {}
        continuation = decision.get("continuation") or {}
        review_action = ((event.get("protocol_binding") or {}).get(
            "approval_binding_kind") == "independent_review_provider")
        if (review_action and record.get("status") in {
                "reviewer_native_action_approved", "awaiting_independent_review"}):
            active = record.get("active_review_native_action") or {}
            action_status = ("completed" if continuation.get("state") == "completed"
                             else "failed" if continuation.get("state") == "failed"
                             else None)
            if (event.get("campaign_id") != campaign_id
                    or decision.get("decision_id") != decision_id
                    or decision.get("invocation_id") != event.get("invocation_id")
                    or continuation.get("continuation_id") != continuation_id
                    or continuation.get("authority_binding") != expected
                    or action_status is None
                    or (record.get("status") == "reviewer_native_action_approved"
                        and (active.get("attention_id") != attention_id
                             or active.get("decision_id") != decision_id
                             or active.get("invocation_id") != event.get("invocation_id")))):
                raise PermissionError(
                    "terminal Reviewer continuation is stale or mismatched")
            updated = self._finish_review_native_action(
                campaign_id, attention_id, decision_id, event["invocation_id"],
                action_status=action_status)
            return {"campaign": updated, "decision": decision,
                    "consumption": decision}
        if (event.get("campaign_id") != campaign_id
                or record.get("status") != "ready_for_bounded_continuation"
                or not callable(recovery_runner)):
            raise PermissionError("campaign is not eligible for bounded recovery")
        if (decision.get("decision_id") != decision_id
                or continuation.get("continuation_id") != continuation_id
                or continuation.get("state") not in {
                    "reserved", "executing", "outcome_recorded", "completed", "failed"}
                or continuation.get("authority_binding") != expected):
            raise PermissionError("reserved continuation binding is missing or mismatched")
        if continuation.get("state") in {"completed", "failed"}:
            status = continuation["state"]
            current = self.store.load(campaign_id)
            updated = self._update(current, event_kind="bounded_continuation_" + status,
                event_detail={"attention_id": attention_id, "decision_id": decision_id,
                              "continuation_id": continuation_id, "recovered_projection": True},
                status="ready" if status == "completed" else "failed_safe", needs_tanner=None)
            return {"campaign": updated, "decision": decision, "consumption": decision}
        if (event.get("expires_at")
                and datetime.fromisoformat(event["expires_at"]) <= datetime.now(timezone.utc)):
            raise PermissionError("reserved continuation authority has expired")
        if decision.get("consumed"):
            if (decision.get("consumed_by_continuation_id") != continuation_id
                    or decision.get("lifecycle_state") != "resumed"):
                raise PermissionError("continuation consumption is stale or belongs to a neighbor")
            consumed = decision
        else:
            consumed = self.attention_store.consume_approve_once(
                decision_id, attention_id=attention_id, invocation_id=event["invocation_id"],
                protocol_binding_sha256=event["protocol_binding_sha256"],
                approved_action_sha256=(event.get("protocol_binding") or {}).get(
                    "approved_action_sha256"), continuation_id=continuation_id,
                expected_binding=expected)
        idempotency_id = _digest({"campaign_id": campaign_id, "attention_id": attention_id,
            "decision_id": decision_id, "continuation_id": continuation_id,
            "candidate_snapshot_id": expected["candidate_snapshot_id"],
            "mutation_digest_sha256": expected["mutation_digest_sha256"],
            "authorized_scope_sha256": expected["authorized_scope_sha256"]})
        claimed, execute = self.attention_store.begin_recovery_execution(
            decision_id, continuation_id)
        if execute:
            try:
                outcome = recovery_runner(
                    (event.get("protocol_binding") or {})["recovery_evidence"],
                    idempotency_id=idempotency_id)
                if (not isinstance(outcome, dict)
                        or outcome.get("idempotency_id") != idempotency_id
                        or outcome.get("status") not in {"completed", "failed"}):
                    raise ValueError("recovery owner returned an unbound idempotency result")
                status = outcome["status"]
            except Exception:
                status = "failed"
            claimed = self.attention_store.record_recovery_outcome(
                decision_id, continuation_id, status=status)
        else:
            status = (claimed.get("continuation") or {}).get("outcome_status", "failed")
        finished = self.attention_store.finish_detached_continuation(
            decision_id, continuation_id, status=status)
        current = self.store.load(campaign_id)
        updated = self._update(current, event_kind="bounded_continuation_" + status,
            event_detail={"attention_id": attention_id, "decision_id": decision_id,
                          "continuation_id": continuation_id},
            status="ready" if status == "completed" else "failed_safe", needs_tanner=None)
        return {"campaign": updated, "decision": finished, "consumption": consumed}

    def _builder_task(self, record, iteration, correction):
        lines = [
            "Execute only this Tanner-authorized bounded Development campaign.",
            f"Campaign: {record['campaign_id']}",
            f"Iteration: {iteration} of {record['maximum_iterations']}",
            f"Objective (exact): {record['objective']}",
            "Allowed scope: " + ", ".join(record["allowed_scope"]),
            "Acceptance conditions:",
        ]
        lines.extend(f"- {item}: {record['acceptance_conditions'][item]}"
                     for item in record["acceptance_condition_ids"])
        lines.extend([
            "Forbidden: purchases, credential changes, destructive operations, promotion, scope expansion, unrelated work, or new workers.",
            "Preserve exact evidence and report changed artifacts, tests, caveats, blockers, and recovery implications.",
        ])
        if correction:
            lines.append("Correction is limited to the independently reported defects referenced in the exact review sections supplied with this task.")
            lines.extend(f"- {item['defect_id']}: acceptance={item['acceptance_condition_id']} evidence={item['evidence_reference']}"
                         for item in correction["defects"])
        return _text("\n".join(lines), "builder task")

    def _start_builder(self, record, correction):
        if record["cancelled"] or record["status"] in TERMINAL_STATUSES:
            return record
        next_iteration = record["iteration"] + 1
        if next_iteration > MAX_ITERATIONS:
            return self._update(record, event_kind="iteration_limit_reached", status="tanner_escalation",
                needs_tanner={"urgency": "urgent_blocking_flow", "reason": "maximum_iterations_reached",
                              "decision_needed": "change scope, stop, or authorize a new campaign"})
        if record["objective_mode"] not in self.builder_modes:
            return self._update(record, event_kind="builder_transport_unavailable", status="tanner_escalation",
                needs_tanner={"urgency": "urgent_blocking_flow", "reason": "builder_write_transport_unavailable",
                    "decision_needed": "qualify and authorize a bounded repository-write CODEX (REPO) execution boundary",
                    "existing_adapter_scope": "ephemeral_read_only"})
        task_scope_id = f"{record['campaign_id']}-builder-{next_iteration}"
        task = self._builder_task(record, next_iteration, correction)
        source_sections = list(record["source_sections"])
        evidence_references = []
        if correction:
            review_report = self.exchange._load("reports", correction["review_report_id"])
            for index, section in enumerate(review_report["sections"][:6]):
                source_sections.append({"section_id": f"review-{next_iteration}-{index+1}",
                    "title": f"Exact independent review: {section['title']}", "content": section["content"]})
            source_sections = source_sections[-6:]
            evidence_references.append({"reference_type": "worker_exchange_report",
                "reference_id": review_report["report_id"], "sha256": review_report["record_sha256"]})
        cache_before = _cleanup_python_cache(record["allowed_scope"])
        record = self._update(record, event_kind="builder_invocation_started",
            event_detail={"iteration": next_iteration, "task_scope_id": task_scope_id,
                          "python_cache_entries_removed": len(cache_before)},
            status="builder_in_progress", iteration=next_iteration,
            active_builder_task_scope_id=task_scope_id, needs_tanner=None,
            cache_lifecycle_events=[*record.get("cache_lifecycle_events", []), {
                "iteration": next_iteration, "stage": "before_builder", "removed": cache_before,
                "prevention": "PYTHONDONTWRITEBYTECODE=1", "created_at": _now()}])
        payload = {"instance_id": self.instance_id, "target_worker": "codex_repo",
            "task_scope_id": task_scope_id, "rider_request_id": f"{record['campaign_id']}-builder-{next_iteration}",
            "explicitly_authorized": True, "task": task, "source_sections": source_sections,
            "claims": [{"claim_id": f"acceptance-{item}", "area": "development",
                "statement": record["acceptance_conditions"][item], "maturity": "in_development",
                "change_class": "software_system"} for item in record["acceptance_condition_ids"]],
            "evidence_references": evidence_references,
            "contract_references": [{"contract_id": CAMPAIGN_CONTRACT_VERSION, "version": "0.1"}],
            "recovery_references": record["recovery_references"],
            "execution_mode": record["objective_mode"], "campaign_id": record["campaign_id"],
            "iteration": next_iteration, "allowed_scope": record["allowed_scope"],
            "acceptance_condition_ids": record["acceptance_condition_ids"],
            "stepwise_v01": bool(record.get("stepwise_v01"))}
        try:
            result = self.builder_runner(payload)
        except Exception as exc:
            result = {"presentation": {"status": "failed", "failure": {
                "code": type(exc).__name__, "detail": str(exc)}, "return_report_id": None},
                "transport_result": {"status": "failed"}}
        if record.get("stepwise_v01"):
            current = self.store.load(record["campaign_id"])
            if current["status"] == "failed_safe":
                return current
            checkpointed = self._consume_provider_reservation(record["campaign_id"], {
                "package_id": result.get("package_id") if isinstance(result, dict) else None,
                "source_report_id": result.get("source_report_id") if isinstance(result, dict) else None,
                "return_report_id": ((result.get("presentation") or {}).get("return_report_id")
                                     if isinstance(result, dict) else None)})
            record = checkpointed
        cache_after = _cleanup_python_cache(record["allowed_scope"])
        current = self.store.load(record["campaign_id"])
        presentation = result.get("presentation") if isinstance(result, dict) else None
        transport_result = result.get("transport_result") if isinstance(result, dict) else None
        candidate_workspace = ((transport_result or {}).get("candidate_workspace")
                               if isinstance(transport_result, dict) else None)
        validation = (self._run_validation(record["validation_commands"], cwd=candidate_workspace)
                      if candidate_workspace and record["validation_policy"] == "required" else [])
        if (candidate_workspace and record["validation_policy"] == "intentionally_not_applicable"
                and isinstance(transport_result, dict)):
            snapshot = transport_result.get("candidate_snapshot") or {}
            na = {"schema_version": 1, "record_type": "candidate_validation_not_applicable_receipt",
                "status": "intentionally_not_applicable", "campaign_id": record["campaign_id"],
                "candidate_snapshot_id": snapshot.get("candidate_snapshot_id"),
                "candidate_record_sha256": snapshot.get("record_sha256"),
                "allowed_scope_sha256": _digest(record["allowed_scope"]),
                "validation_plan_sha256": _digest(record["validation_commands"]),
                "validation_declaration_sha256": record["validation_declaration"]["record_sha256"],
                "reason_code": record["validation_declaration"].get("reason_code"),
                "classification_source": "canonical_campaign_validator",
                "creates_authority": False}
            na["record_sha256"] = _digest(na); validation = [na]
        validation_passed = ((record["validation_policy"] == "required" and bool(validation)
                              and all(item.get("exit_status") == 0 for item in validation))
                             or (record["validation_policy"] == "intentionally_not_applicable"
                                 and len(validation) == 1
                                 and validation[0].get("record_type") ==
                                     "candidate_validation_not_applicable_receipt"
                                 and validation[0].get("candidate_snapshot_id") ==
                                     ((transport_result or {}).get("candidate_snapshot") or {}).get(
                                         "candidate_snapshot_id")
                                 and record["validation_declaration"].get("status") ==
                                     "intentionally_not_applicable"))
        retention_receipt = None
        application = ((transport_result or {}).get("application_evidence")
                       if isinstance(transport_result, dict) else None)
        if (validation_passed and isinstance(application, dict)
                and application.get("record_type") == "codex_candidate_retention_intent"
                and application.get("status") == "awaiting_independent_review"
                and application.get("applied_paths") == []):
            retention_receipt = {"schema_version": 1,
                "record_type": "codex_candidate_retention_receipt",
                "status": "awaiting_independent_review", "applied_paths": [],
                "campaign_id": record["campaign_id"],
                "package_id": (transport_result or {}).get("package_id"),
                "iteration": next_iteration,
                "worker_invocation_id": (transport_result or {}).get("invocation_id"),
                "allowed_scope_sha256": _digest(record["allowed_scope"]),
                "mutation_manifest_sha256": (transport_result or {}).get("workspace_changes_sha256"),
                "exact_change_evidence_sha256": (transport_result or {}).get(
                    "exact_change_evidence_sha256"),
                "candidate_snapshot": (transport_result or {}).get("candidate_snapshot"),
                "validation_policy": record["validation_policy"],
                "validation_declaration_sha256": record["validation_declaration"]["record_sha256"],
                "validation_evidence_sha256": _digest(validation),
                "recovery_references_sha256": _digest(record["recovery_references"]),
                "retention_intent_sha256": application.get("application_record_sha256"),
                "creates_authority": False, "created_at": _now()}
            retention_receipt["record_sha256"] = _digest(retention_receipt)
        run = {"iteration": next_iteration, "task_scope_id": task_scope_id,
            "source_report_id": result.get("source_report_id") if isinstance(result, dict) else None,
            "package_id": result.get("package_id") if isinstance(result, dict) else None,
            "return_report_id": (presentation or {}).get("return_report_id"),
            "status": (presentation or {}).get("status", "failed"),
            "verification_status": (presentation or {}).get("verification_status", "unverified"),
            "failure": ((presentation or {}).get("failure")
                        if isinstance((presentation or {}).get("failure"), dict) else None),
            "transport_result_reference": ({"adapter_id": transport_result.get("adapter_id"),
                "invocation_id": transport_result.get("invocation_id"),
                "record_sha256": transport_result.get("record_sha256"),
                "workspace_changes_sha256": transport_result.get("workspace_changes_sha256")}
                if isinstance(transport_result, dict) else None),
            "candidate_workspace": candidate_workspace,
            "candidate_snapshot": ((transport_result or {}).get("candidate_snapshot")
                                   if isinstance(transport_result, dict) else None),
            "validation_evidence": validation,
            "validation_declaration": record["validation_declaration"],
            "candidate_retention_receipt": retention_receipt,
            "cache_cleanup": {"removed": cache_after, "absence_verified": not cache_after or all(
                not (ROOT / item["path"]).exists() for item in cache_after)},
            "completed_at": _now()}
        runs = [*current["builder_runs"], run]
        cache_events = [*current.get("cache_lifecycle_events", []), {
            "iteration": next_iteration, "stage": "after_builder", "removed": cache_after,
            "absence_verified": run["cache_cleanup"]["absence_verified"], "created_at": _now()}]
        if current["cancelled"]:
            return self._update(current, event_kind="builder_return_retained_after_cancel",
                                builder_runs=runs, active_builder_task_scope_id=None)
        evidence_valid = False
        if (run["status"] == "completed" and run["return_report_id"] and run["package_id"]
                and run["source_report_id"] and candidate_workspace and validation_passed):
            try:
                returned = self.exchange._load("reports", run["return_report_id"])
                package = self.exchange._load("packages", run["package_id"])
                source = self.exchange._load("reports", run["source_report_id"])
                evidence_valid = (returned.get("in_reply_to", {}).get("package_id") == package["package_id"]
                    and package["source_report_id"] == source["report_id"]
                    and package["task_scope_id"] == task_scope_id
                    and returned["task_scope_id"] == task_scope_id
                    and returned["sender"]["worker_id"] == CODEX_REPO_WORKER_REFERENCE["worker_id"])
            except (KeyError, PermissionError, ValueError):
                evidence_valid = False
        if not evidence_valid:
            failure_code = (run.get("failure") or {}).get("code")
            attention = (presentation or {}).get("attention_request")
            if failure_code == "native_approval_required" and isinstance(attention, dict):
                try:
                    protocol_binding = self._validated_worker_attention_binding(
                        current, attention, transport_result)
                except PermissionError:
                    return self._update(current, event_kind="builder_attention_rejected",
                        status="failed_safe", builder_runs=runs,
                        active_builder_task_scope_id=None,
                        cache_lifecycle_events=cache_events,
                        needs_tanner={"urgency": "urgent_blocking_flow",
                            "reason": "builder_attention_lineage_invalid",
                            "failure_code": "attention_lineage_mismatch",
                            "decision_needed": "inspect bound Worker Attention evidence"})
                current = self._update(current, event_kind="builder_return_requires_tanner",
                    builder_runs=runs, active_builder_task_scope_id=None,
                    cache_lifecycle_events=cache_events)
                return self.require_tanner(current["campaign_id"],
                    invocation_id=attention["invocation_id"], worker=current["builder"],
                    kind="native_codex_approval_required",
                    blocked_action=attention["blocked_action"],
                    why_required=attention["why_required"],
                    requested_authority=attention["requested_authority"],
                    resources=attention.get("resources", ()),
                    reversible=attention.get("reversible"),
                    provider_code=attention.get("provider_code"),
                    protocol_binding=protocol_binding)
            return self._update(current, event_kind="builder_failed_safe", status="failed_safe",
                builder_runs=runs, active_builder_task_scope_id=None,
                cache_lifecycle_events=cache_events,
                needs_tanner={"urgency": "urgent_blocking_flow", "reason": "builder_transport_or_return_failed",
                              "failure_code": failure_code,
                              "decision_needed": "inspect failure evidence or use manual fallback"})
        return self._update(current, event_kind="builder_return_retained", status="awaiting_independent_review",
            builder_runs=runs, active_builder_task_scope_id=None, cache_lifecycle_events=cache_events,
            event_detail={"iteration": next_iteration, "return_report_id": run["return_report_id"]})

    def _run_validation(self, commands, *, cwd=ROOT):
        evidence = []
        cwd = Path(cwd).resolve()
        environment = minimal_subprocess_environment(
            runtime_state_root=self.runtime_state_root, workspace=cwd,
            PYTHONDONTWRITEBYTECODE="1")
        for argv in commands:
            resolved_argv = list(argv)
            if resolved_argv[0] == ".venv/bin/python":
                resolved_argv[0] = str(ROOT / ".venv/bin/python")
            completed = subprocess.run(resolved_argv, cwd=cwd, env=environment, capture_output=True,
                                       text=True, encoding="utf-8", errors="replace",
                                       timeout=180, check=False)
            stdout, stderr = completed.stdout or "", completed.stderr or ""
            if len(stdout.encode()) > 128_000 or len(stderr.encode()) > 128_000:
                raise RuntimeError("validation evidence exceeds bounded output limit")
            evidence.append({"argv": argv, "exit_status": completed.returncode,
                "stdout": stdout, "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                "stderr": stderr, "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
                "bytecode_prevention": True})
        return evidence

    def consume_review(self, campaign_id, review, *, reviewer, transport_verified):
        record = self.store.load(campaign_id)
        if record["status"] != "awaiting_independent_review" or record["cancelled"]:
            raise RuntimeError("campaign is not awaiting an independent review")
        if transport_verified is not True:
            raise PermissionError("verified reviewer transport evidence is required")
        if not isinstance(reviewer, dict):
            raise ValueError("reviewer reference is required")
        reviewer_id = require_id(reviewer.get("worker_id"), "reviewer_worker_id")
        if reviewer_id == CODEX_REPO_WORKER_REFERENCE["worker_id"]:
            raise PermissionError("builder cannot serve as independent reviewer")
        requirement = record["reviewer_requirement"]
        if (reviewer_id != requirement["worker_id"]
                or reviewer.get("role") != requirement["role"]
                or reviewer.get("identity_status") not in {"verified", "rider_attested"}):
            raise PermissionError("reviewer does not satisfy the campaign reviewer binding")
        if not isinstance(review, dict) or review.get("status") not in REVIEW_STATUSES:
            raise ValueError("invalid independent review status")
        report = self.exchange._load("reports", require_id(review.get("review_report_id"), "review_report_id"))
        if report["sender"]["worker_id"] != reviewer_id:
            raise PermissionError("review report sender does not match reviewer")
        in_reply_to = report.get("in_reply_to") or {}
        package_id = require_id(in_reply_to.get("package_id"), "review_package_id")
        package = self.exchange._load("packages", package_id)
        review_source = self.exchange._load("reports", package["source_report_id"])
        builder_return_id = record["builder_runs"][-1]["return_report_id"]
        builder_return = self.exchange._load("reports", builder_return_id)
        expected_builder_reference = {"reference_type": "worker_exchange_report",
            "reference_id": builder_return_id, "sha256": builder_return["record_sha256"]}
        if expected_builder_reference not in review_source.get("evidence_references", []):
            raise PermissionError("review target is not bound to the current exact builder return")
        delivery = self.exchange._load("delivery_receipts",
            require_id(review.get("delivery_receipt_id"), "delivery_receipt_id"))
        verification = self.exchange._load("verification_receipts",
            require_id(review.get("verification_receipt_id"), "verification_receipt_id"))
        if (package["recipient"]["worker_id"] != reviewer_id
                or delivery["package_id"] != package_id or delivery["status"] != "delivered"
                or verification["package_id"] != package_id
                or verification["recipient"]["worker_id"] != reviewer_id):
            raise PermissionError("review transport lineage is incomplete or mismatched")
        satisfied_raw = review.get("acceptance_condition_ids_satisfied")
        if not isinstance(satisfied_raw, list) or len(satisfied_raw) != len(set(satisfied_raw)):
            raise ValueError("satisfied acceptance conditions must be a unique list")
        satisfied = list(satisfied_raw)
        if any(item not in record["acceptance_condition_ids"] for item in satisfied):
            raise ValueError("review references an unknown acceptance condition")
        violated_raw = review.get("violated_acceptance_condition_ids")
        if not isinstance(violated_raw, list) or len(violated_raw) != len(set(violated_raw)):
            raise ValueError("violated acceptance conditions must be a unique list")
        violated = list(violated_raw)
        if any(item not in record["acceptance_condition_ids"] for item in violated):
            raise ValueError("review violates an unknown acceptance condition")
        defects = review.get("defects", [])
        if not isinstance(defects, list) or len(defects) > 12:
            raise ValueError("review defects are invalid")
        normalized_defects = []
        for item in defects:
            if not isinstance(item, dict):
                raise ValueError("review defects must be objects")
            condition = require_id(item.get("acceptance_condition_id"), "acceptance_condition_id")
            if condition not in record["acceptance_condition_ids"]:
                raise ValueError("review defect is outside campaign acceptance")
            normalized_defects.append({"defect_id": require_id(item.get("defect_id"), "defect_id"),
                "acceptance_condition_id": condition,
                "evidence_reference": require_id(item.get("evidence_reference"), "evidence_reference")})
        status = review["status"]
        if set(satisfied) & set(violated):
            raise ValueError("acceptance condition matrix is contradictory")
        if status in {"pass", "pass_with_caveats"} and (violated or normalized_defects):
            raise ValueError("accepted review cannot contain violated or blocking defects")
        if status == "correction_required" and not normalized_defects:
            raise ValueError("correction_required needs scoped defects")
        if status == "correction_required" and (
                {item["acceptance_condition_id"] for item in normalized_defects} - set(violated)):
            raise ValueError("correction defect is not bound to a violated condition")
        all_satisfied = set(satisfied) == set(record["acceptance_condition_ids"])
        acceptance_receipt = review.get("review_acceptance_receipt")
        if status in {"pass", "pass_with_caveats"} and all_satisfied and not violated:
            builder_run = record["builder_runs"][-1]
            retention = builder_run.get("candidate_retention_receipt") or {}
            expected = {"record_type": "codex_independent_review_acceptance_receipt",
                "status": "accepted", "campaign_id": campaign_id,
                "package_id": builder_run["package_id"], "review_report_id": report["report_id"],
                "review_report_sha256": report["record_sha256"],
                "review_package_id": package_id, "reviewer_worker_id": reviewer_id,
                "review_package_sha256": package["record_sha256"],
                "source_report_id": package["source_report_id"],
                "review_invocation_id": require_id(
                    review.get("invocation_id"), "review_invocation_id"),
                "reviewer_role": reviewer["role"],
                "recipient": review.get("recipient"),
                "candidate_snapshot_id": (retention.get("candidate_snapshot") or {}).get(
                    "candidate_snapshot_id"),
                "mutation_manifest_sha256": retention.get("mutation_manifest_sha256"),
                "allowed_scope_sha256": retention.get("allowed_scope_sha256"),
                "candidate_retention_receipt_sha256": retention.get("record_sha256"),
                "acceptance_condition_ids_sha256": _digest(sorted(satisfied)),
                "delivery_receipt_id": delivery["delivery_receipt_id"],
                "verification_receipt_id": verification["verification_receipt_id"],
                "verdict": status,
                "creates_authority": False}
            if (not isinstance(acceptance_receipt, dict)
                    or acceptance_receipt.get("record_sha256") != _digest(
                        {k:v for k,v in acceptance_receipt.items() if k != "record_sha256"})
                    or any(acceptance_receipt.get(k) != v for k,v in expected.items())):
                raise PermissionError("validated Reviewer-authored acceptance receipt is required")
        review_record = {"iteration": record["iteration"], "status": status,
            "reviewer": {"worker_id": reviewer_id, "role": reviewer["role"],
                         "identity_status": reviewer["identity_status"]},
            "review_report_id": report["report_id"], "review_report_sha256": report["record_sha256"],
            "review_package_id": package_id,
            "delivery_receipt_id": delivery["delivery_receipt_id"],
            "verification_receipt_id": verification["verification_receipt_id"],
            "acceptance_condition_ids_satisfied": satisfied,
            "violated_acceptance_condition_ids": violated, "defects": normalized_defects,
            "transport_verified": True, "creates_authority": False, "received_at": _now()}
        if status in {"pass", "pass_with_caveats"} and all_satisfied and not violated:
            review_record["review_acceptance_receipt"] = acceptance_receipt
            review_record["reviewed_application_operation_id"] = (
                "reviewed-application-" + _digest({"package_id": record["builder_runs"][-1]["package_id"],
                    "campaign_id": campaign_id,
                    "review_receipt": acceptance_receipt["record_sha256"]}))
        reviews = [*record["reviews"], review_record]
        accepted = status in {"pass", "pass_with_caveats"} and all_satisfied and not violated
        record = self._update(record, event_kind="independent_review_retained",
            event_detail={"iteration": record["iteration"], "status": status,
                          "review_report_id": report["report_id"]},
            reviews=reviews, acceptance_satisfied=satisfied,
            reviewer_requirement={**record["reviewer_requirement"], "worker_id": reviewer_id,
                                  "transport_binding": "verified_for_recorded_review"},
            **({"status": "review_accepted_application_pending"} if accepted else {}))
        if accepted and not record.get("stepwise_v01"):
            return self._complete_pending_reviewed_application(record)
        if accepted:
            return record
        if status == "blocked":
            return self._update(record, event_kind="reviewer_blocked", status="tanner_escalation",
                needs_tanner={"urgency": "urgent_blocking_flow", "reason": "independent_reviewer_blocked",
                              "decision_needed": "resolve blocker or stop campaign"})
        if status == "insufficient_evidence" and review.get("correctable_within_scope") is not True:
            return self._update(record, event_kind="review_evidence_insufficient", status="tanner_escalation",
                needs_tanner={"urgency": "urgent_blocking_flow", "reason": "insufficient_evidence_not_correctable_in_scope",
                              "decision_needed": "expand evidence scope or stop campaign"})
        if not normalized_defects:
            return self._update(record, event_kind="review_cannot_generate_bounded_correction",
                status="tanner_escalation", needs_tanner={"urgency": "urgent_blocking_flow",
                "reason": "review_requires_correction_without_scoped_defects",
                "decision_needed": "request a scoped review or stop campaign"})
        if record.get("stepwise_v01"):
            return self._update(record, event_kind="correction_transition_pending",
                status="correction_pending", pending_correction=review_record)
        return self._start_builder(record, correction=review_record)

    def run_wsl_review(self, campaign_id, *, adapter=None):
        """Review through the promoted default WSL formal-review binding."""
        record = self.store.load(campaign_id)
        if record["status"] != "awaiting_independent_review" or record["cancelled"]:
            raise RuntimeError("campaign is not awaiting independent review")
        from src.runtime.wsl_codex_reviewer import (
            WSL_REVIEWER_REFERENCE, WslCodexReviewAdapter, prepare_wsl_review_package,
        )
        candidate_root = Path(record["builder_runs"][-1]["candidate_workspace"]).resolve()
        with DisposableVerifierWorkspace(candidate_root) as snapshot:
            retained_snapshot = record["builder_runs"][-1].get("candidate_snapshot") or {}
            if any(snapshot.provenance.get(key) != retained_snapshot.get(key) for key in
                   ("candidate_snapshot_id", "file_count", "total_byte_length")):
                raise PermissionError("builder candidate changed before independent review")
            prepared = prepare_wsl_review_package(exchange=self.exchange, campaign_record=record,
                candidate_snapshot=snapshot.provenance, workspace=ROOT)
            logical = {"iteration": record["iteration"], "package_id": prepared["package_id"],
                "source_report_id": prepared["source_report_id"],
                "builder_return_report_id": record["builder_runs"][-1]["return_report_id"],
                "candidate_snapshot_id": snapshot.provenance["candidate_snapshot_id"]}
            existing = next((item for item in record.get("review_requests", [])
                             if item["iteration"] == record["iteration"]), None)
            if existing is not None and existing != logical:
                raise RuntimeError("logical review request changed during recovery")
            if existing is None:
                record = self._update(record, event_kind="logical_review_request_prepared",
                    event_detail=logical, review_requests=[*record.get("review_requests", []), logical])
            if record.get("stepwise_v01"):
                record = self._reserve_provider(self.store.load(campaign_id),
                    operation_type="reviewer", package_id=prepared["package_id"],
                    package_sha256=self.exchange._load("packages", prepared["package_id"])["record_sha256"],
                    invocation_id=f"{campaign_id}-review-{record['iteration']}",
                    task_scope_id=self.exchange._load("packages", prepared["package_id"])["task_scope_id"],
                    turns=2, cost=2)
            adapter = adapter or WslCodexReviewAdapter(self.exchange)
            builder_return_id = record["builder_runs"][-1]["return_report_id"]
            try:
                result = adapter.deliver_production_once(package_id=prepared["package_id"],
                    transport_authority=prepared["transport_authority"],
                    return_authority=prepared["return_authority"], campaign_id=campaign_id,
                    builder_return_report_id=builder_return_id,
                    candidate_snapshot_id=snapshot.provenance["candidate_snapshot_id"],
                    candidate_snapshot_root=snapshot.root,
                    approval_handler=self._handle_typed_approval)
                snapshot.verify_source_unchanged()
            except Exception as exc:
                current = (self._close_failed_provider_reservation(campaign_id,
                    failure_code=type(exc).__name__) if record.get("stepwise_v01")
                    else self.store.load(campaign_id))
                attempt = {"iteration": record["iteration"], "package_id": prepared["package_id"],
                    "invocation_id": None, "status": "transport_exception",
                    "consumed": bool(record.get("stepwise_v01")),
                    "actual_process_invocation": None, "failure_code": type(exc).__name__, "created_at": _now()}
                return self._update(current, event_kind="wsl_review_transport_exception",
                    event_detail={"failure_code": type(exc).__name__}, status="failed_safe",
                    review_transport_attempts=[*current.get("review_transport_attempts", []), attempt],
                    needs_tanner={"urgency": "urgent_blocking_flow", "reason": "wsl_review_transport_failed",
                                  "decision_needed": "inspect exact failure evidence or stop campaign"})
        if record.get("stepwise_v01"):
            record = self._consume_provider_reservation(campaign_id, {
                "package_id": prepared["package_id"], "invocation_id": result.get("invocation_id"),
                "return_report_id": result.get("return_report_id")})
        current = self.store.load(campaign_id)
        attempt = {"iteration": record["iteration"], "package_id": prepared["package_id"],
            "invocation_id": result.get("invocation_id"), "status": result.get("status"), "consumed": False,
            "actual_process_invocation": not result.get("idempotent_replay", False),
            "idempotent_result_reused": bool(result.get("idempotent_replay")), "created_at": _now()}
        current = self._update(current, event_kind="wsl_review_transport_attempt_retained",
            event_detail={"iteration": record["iteration"], "status": result.get("status")},
            review_transport_attempts=[*current.get("review_transport_attempts", []), attempt])
        if result.get("status") != "delivered":
            return self._update(current, event_kind="wsl_review_failed_safe", status="failed_safe",
                needs_tanner={"urgency": "urgent_blocking_flow", "reason": "wsl_review_transport_failed",
                              "decision_needed": "inspect exact failure evidence or stop campaign"})
        defects = []
        for item in result["defects"]:
            evidence_reference = require_id(item.get("evidence_reference"), "evidence_reference")
            defects.append({**item, "evidence_reference": evidence_reference})
        review = {"status": result["review_status"], "review_report_id": result["return_report_id"],
            "invocation_id": result["invocation_id"], "recipient": result["recipient"],
            "delivery_receipt_id": result["delivery_receipt_id"],
            "verification_receipt_id": result["verification_receipt_id"],
            "acceptance_condition_ids_satisfied": result["acceptance_condition_ids_satisfied"],
            "violated_acceptance_condition_ids": result["violated_acceptance_condition_ids"],
            "defects": defects, "correctable_within_scope": result["correctable_within_scope"],
            "review_acceptance_receipt": result.get("review_acceptance_receipt")}
        consumed = self.consume_review(campaign_id, review, reviewer=WSL_REVIEWER_REFERENCE,
                                       transport_verified=True)
        attempts = list(consumed.get("review_transport_attempts", []))
        attempts[-1] = {**attempts[-1], "consumed": True, "review_report_id": result["return_report_id"]}
        return self._update(consumed, event_kind="wsl_review_attempt_consumed",
                            review_transport_attempts=attempts)

    def run_windows_review(self, campaign_id, *, adapter=None):
        """Review the current builder return through the one promoted Windows route."""
        record = self.store.load(campaign_id)
        if record["status"] != "awaiting_independent_review" or record["cancelled"]:
            raise RuntimeError("campaign is not awaiting independent review")
        from src.runtime.windows_codex_reviewer import (
            WINDOWS_CODEX_WORKER_REFERENCE, WINDOWS_REVIEW_SNAPSHOT_PARENT, WindowsCodexReviewAdapter,
            prepare_windows_review_package,
        )
        with DisposableVerifierWorkspace(ROOT, parent=WINDOWS_REVIEW_SNAPSHOT_PARENT) as snapshot:
            prepared = prepare_windows_review_package(exchange=self.exchange, campaign_record=record,
                candidate_snapshot=snapshot.provenance, workspace=ROOT)
            logical = {"iteration": record["iteration"], "package_id": prepared["package_id"],
                "source_report_id": prepared["source_report_id"],
                "builder_return_report_id": record["builder_runs"][-1]["return_report_id"],
                "candidate_snapshot_id": snapshot.provenance["candidate_snapshot_id"]}
            existing = next((item for item in record.get("review_requests", [])
                             if item["iteration"] == record["iteration"]), None)
            if existing is not None and existing != logical:
                raise RuntimeError("logical review request changed during recovery")
            if existing is None:
                record = self._update(record, event_kind="logical_review_request_prepared",
                    event_detail=logical, review_requests=[*record.get("review_requests", []), logical])
            adapter = adapter or WindowsCodexReviewAdapter(self.exchange)
            builder_return_id = record["builder_runs"][-1]["return_report_id"]
            try:
                result = adapter.deliver_production_once(package_id=prepared["package_id"],
                    transport_authority=prepared["transport_authority"],
                    return_authority=prepared["return_authority"], campaign_id=campaign_id,
                    builder_return_report_id=builder_return_id,
                    candidate_snapshot_id=snapshot.provenance["candidate_snapshot_id"],
                    candidate_snapshot_root=snapshot.root)
            except Exception as exc:
                current = self.store.load(campaign_id)
                attempt = {"iteration": record["iteration"], "package_id": prepared["package_id"],
                    "invocation_id": None, "status": "transport_exception", "consumed": False,
                    "actual_process_invocation": False, "failure_code": type(exc).__name__,
                    "created_at": _now()}
                return self._update(current, event_kind="windows_review_transport_exception",
                    event_detail={"failure_code": type(exc).__name__}, status="failed_safe",
                    review_transport_attempts=[*current.get("review_transport_attempts", []), attempt],
                    needs_tanner={"urgency": "urgent_blocking_flow",
                        "reason": "windows_review_transport_failed",
                        "decision_needed": "inspect exact failure evidence or stop campaign"})
            snapshot.verify_source_unchanged()
        current = self.store.load(campaign_id)
        attempt = {"iteration": record["iteration"], "package_id": prepared["package_id"],
            "invocation_id": result.get("invocation_id"), "status": result.get("status"),
            "consumed": False, "actual_process_invocation": not result.get("idempotent_replay", False),
            "idempotent_result_reused": bool(result.get("idempotent_replay")), "created_at": _now()}
        current = self._update(current, event_kind="windows_review_transport_attempt_retained",
            event_detail={"iteration": record["iteration"], "status": result.get("status")},
            review_transport_attempts=[*current.get("review_transport_attempts", []), attempt])
        if result.get("status") != "delivered":
            return self._update(current, event_kind="windows_review_failed_safe",
                status="failed_safe", needs_tanner={"urgency": "urgent_blocking_flow",
                    "reason": "windows_review_transport_failed",
                    "decision_needed": "inspect exact failure evidence or stop campaign"})
        # The transport result preserves the reviewer's exact free-form defect
        # citation. Campaign state needs a canonical evidence identity, so an
        # unstructured citation resolves to the immutable return report that
        # contains the exact review instead of being treated as a new ID.
        defects = []
        for item in result["defects"]:
            evidence_reference = item.get("evidence_reference")
            try:
                evidence_reference = require_id(evidence_reference, "evidence_reference")
            except ValueError:
                evidence_reference = result["return_report_id"]
            defects.append({**item, "evidence_reference": evidence_reference})
        review = {"status": result["review_status"], "review_report_id": result["return_report_id"],
            "invocation_id": result["invocation_id"], "recipient": result["recipient"],
            "delivery_receipt_id": result["delivery_receipt_id"],
            "verification_receipt_id": result["verification_receipt_id"],
            "acceptance_condition_ids_satisfied": result["acceptance_condition_ids_satisfied"],
            "violated_acceptance_condition_ids": result["violated_acceptance_condition_ids"],
            "defects": defects, "correctable_within_scope": result["correctable_within_scope"],
            "review_acceptance_receipt": result.get("review_acceptance_receipt")}
        consumed = self.consume_review(campaign_id, review, reviewer=WINDOWS_CODEX_WORKER_REFERENCE,
                                       transport_verified=True)
        attempts = list(consumed.get("review_transport_attempts", []))
        attempts[-1] = {**attempts[-1], "consumed": True,
                        "review_report_id": result["return_report_id"]}
        return self._update(consumed, event_kind="windows_review_attempt_consumed",
                            review_transport_attempts=attempts)

    def advance_once(self, campaign_id, *, reviewer_adapter=None):
        """Perform at most one canonical transition or external action."""
        record = self.store.load(campaign_id)
        if (record.get("status") == "tanner_escalation"
                and (record.get("needs_tanner") or {}).get("attention_id")):
            return self.reconcile_attention_decision(campaign_id)
        if record.get("status") == "reviewer_native_action_approved":
            return self.reconcile_review_native_action(campaign_id)
        if record.get("stepwise_v01"):
            ambiguous = self._provider_ambiguity(record)
            if ambiguous is not None:
                return ambiguous
            if record.get("status") == "builder_in_progress":
                # The durable builder state is written before the downstream
                # handoff creates its exact provider reservation. A restart in
                # that narrow window proves no canonical result and authorizes
                # no retry; close safely instead of stalling the state machine.
                return self._update(record,
                    event_kind="provider_reservation_missing_after_restart",
                    event_detail={"provider_contact_proven": False},
                    status="failed_safe", needs_tanner={
                        "urgency":"urgent_blocking_flow",
                        "reason":"ambiguous_provider_completion",
                        "provider_contact_proven":False,
                        "decision_needed":"cancel, inspect body-free evidence, or create a new exact request"},
                    creates_authority=False, creates_continuing_authority=False)
            budget = record["execution_budget_v01"]
            expired = datetime.now(timezone.utc) >= datetime.fromisoformat(budget["expires_at"])
            if record["status"] in {"ready", "correction_pending"}:
                if expired:
                    return self._update(record, event_kind="campaign_duration_expired",
                        status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                        "reason":"campaign_duration_expired", "decision_needed":"create a new exact request"})
                if (record["status"] == "correction_pending"
                        and budget["consumed_correction_cycles"] >=
                            budget["maximum_correction_cycles"]):
                    return self._update(record, event_kind="correction_budget_exhausted",
                        status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                        "reason":"correction_budget_exhausted", "decision_needed":"create a new exact request"})
                if record["iteration"] >= budget["maximum_iterations"]:
                    return self._update(record, event_kind="iteration_budget_exhausted",
                        status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                        "reason":"maximum_iterations_reached", "decision_needed":"create a new exact request"})
                correction = record.get("pending_correction") if record["status"] == "correction_pending" else None
                if correction:
                    revised = dict(budget); revised["consumed_correction_cycles"] += 1
                    record = self._update(record, event_kind="correction_budget_consumed",
                        execution_budget_v01=revised); budget = revised
                return self._start_builder(record, correction)
            if record["status"] == "awaiting_independent_review":
                if expired:
                    return self._update(record, event_kind="campaign_duration_expired",
                        status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                        "reason":"campaign_duration_expired", "decision_needed":"create a new exact request"})
                try:
                    return self.run_wsl_review(campaign_id, adapter=reviewer_adapter)
                except RuntimeError:
                    failed = self.store.load(campaign_id)
                    if (failed.get("status") == "failed_safe"
                            and (failed.get("needs_tanner") or {}).get("reason") ==
                                "provider_budget_exhausted"):
                        return failed
                    raise
            if record["status"] == "review_accepted_application_pending":
                if expired:
                    return self._update(record, event_kind="campaign_expired_before_application",
                        status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                        "reason":"campaign_duration_expired", "decision_needed":"create a new exact request"})
                return self._complete_pending_reviewed_application(record)
            if record["status"] == "reviewed_application_completed":
                return self._complete_pending_reviewed_git(record)
            return record
        if record["status"] == "awaiting_independent_review":
            return self.run_wsl_review(campaign_id, adapter=reviewer_adapter)
        if record["status"] == "review_accepted_application_pending":
            return self._complete_pending_reviewed_application(record)
        if record["status"] == "reviewed_application_completed":
            return self._complete_pending_reviewed_git(record)
        return record

    def run_to_terminal(self, campaign_id, *, reviewer_adapter=None):
        """Compatibility loop over canonical stepwise advancement."""
        record = self.store.load(campaign_id)
        remaining_steps = ((record["execution_budget_v01"]["maximum_iterations"] * 4) + 4
                           if record.get("stepwise_v01") else (MAX_ITERATIONS * 4) + 4)
        while record["status"] in STEPWISE_ACTIVE_CAMPAIGN_STATUSES:
            if remaining_steps <= 0:
                return self._update(record, event_kind="stepwise_progress_exhausted",
                    status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                    "reason":"stepwise_progress_exhausted",
                    "decision_needed":"inspect canonical campaign evidence"})
            prior_revision = record["state_revision"]
            record = self.advance_once(campaign_id, reviewer_adapter=reviewer_adapter)
            remaining_steps -= 1
            if (record["status"] in STEPWISE_ACTIVE_CAMPAIGN_STATUSES
                    and record["state_revision"] <= prior_revision):
                return self._update(record, event_kind="stepwise_progress_stalled",
                    status="failed_safe", needs_tanner={"urgency":"urgent_blocking_flow",
                    "reason":"stepwise_progress_stalled",
                    "decision_needed":"inspect canonical campaign evidence"})
        return record

    def cancel(self, campaign_id, *, authenticated_rider):
        if authenticated_rider is not True:
            raise PermissionError("authenticated rider authority is required")
        with self.store.protected(campaign_id):
            record = self.store.load(campaign_id)
            if record["status"] == "cancelled":
                return record
            if record["status"] == "succeeded":
                raise RuntimeError("completed campaign cannot be cancelled")
            return self._update(record, event_kind="rider_cancelled_campaign", status="cancelled",
                cancelled=True, needs_tanner=None, active_builder_task_scope_id=None,
                creates_authority=False, creates_continuing_authority=False)

    def presentation(self, campaign_id):
        record = self.store.load(campaign_id)
        attempts = record.get("review_transport_attempts", [])
        observations = {"builder_invocations": len(record["builder_runs"]),
            "logical_reviews": len(record["reviews"]),
            "review_transport_attempts": len(attempts),
            "reviewer_process_invocations": sum(1 for item in attempts if item.get("actual_process_invocation")),
            "correction_count": sum(1 for item in record["reviews"]
                                    if item["status"] == "correction_required"),
            "reviewer_defect_count": sum(len(item["defects"]) for item in record["reviews"]),
            "source_section_count": len(record["source_sections"]),
            "tanner_escalation_required": bool(record["needs_tanner"]),
            "observations_are_not_policy_or_authority": True}
        return {"schema_version": 1, "presentation_type": "codex_development_campaign",
            "campaign_id": record["campaign_id"], "objective": record["objective"],
            "status": record["status"], "iteration": record["iteration"],
            "maximum_iterations": record["maximum_iterations"], "builder": record["builder"],
            "reviewer": record["reviewer_requirement"], "last_builder_run": record["builder_runs"][-1] if record["builder_runs"] else None,
            "last_review": record["reviews"][-1] if record["reviews"] else None,
            "acceptance_condition_ids": record["acceptance_condition_ids"],
            "acceptance_satisfied": record["acceptance_satisfied"],
            "needs_tanner": record["needs_tanner"], "cancelled": record["cancelled"],
            "notification_signals": {
                "immediate_human_review": bool(record["needs_tanner"]),
                "periodic_progress_interval_seconds": 10_800,
                "periodic_progress_pauses_campaign": False,
                "rider_inactivity_source_required": True,
            },
            "operational_learning_observations": observations,
            "live_activity": campaign_activity_projection(record),
            "managed_worker_activity": self.managed_worker_activity_projection(campaign_id),
            "automatic_promotion": False, "derived_from_campaign_record": True,
            "exact_worker_evidence_remains_in_exchange": True, "creates_authority": False}

    def list_presentations(self):
        """Project current campaigns while retaining typed legacy-contract visibility."""
        presentations = []
        if not self.store.root.exists():
            return presentations
        for path in sorted(self.store.root.glob("*.json"), reverse=True):
            try:
                presentations.append(self.presentation(path.stem))
            except ValueError:
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    claimed = record.get("record_sha256")
                    integrity = claimed == _digest({key: value for key, value in record.items()
                                                    if key != "record_sha256"})
                except (OSError, json.JSONDecodeError):
                    integrity = False; record = {}
                presentations.append({"schema_version": 1,
                    "presentation_type": "codex_development_campaign_legacy",
                    "campaign_id": record.get("campaign_id", path.stem),
                    "objective": record.get("objective", "Historical campaign"),
                    "status": "historical_contract_unavailable" if integrity else "integrity_unavailable",
                    "iteration": record.get("iteration", 0),
                    "maximum_iterations": record.get("maximum_iterations", MAX_ITERATIONS),
                    "live_activity": {"campaign_id": record.get("campaign_id", path.stem),
                        "objective": record.get("objective", "Historical campaign"),
                        "status": "historical_contract_unavailable" if integrity else "integrity_unavailable",
                        "current_stage": "historical_evidence_only", "iteration": record.get("iteration", 0),
                        "maximum_iterations": record.get("maximum_iterations", MAX_ITERATIONS),
                        "builder": record.get("builder", {}), "reviewer": record.get("reviewer_requirement", {}),
                        "needs_tanner": None, "cancelled": bool(record.get("cancelled")),
                        "recovery_references": record.get("recovery_references", []), "activity": [],
                        "exact_worker_bodies_remain_in_worker_exchange": True,
                        "hidden_chain_of_thought_exposed": False, "creates_authority": False}})
        return presentations

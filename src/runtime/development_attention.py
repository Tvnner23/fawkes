"""Durable, zero-authority Rider attention and exact-action decisions."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import uuid
import threading
import time
import fcntl
from contextlib import contextmanager
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


ROOT = Path(os.environ.get(
    "FAWKES_DEVELOPMENT_ROOT", Path(__file__).resolve().parent.parent.parent
)).resolve()
ATTENTION_ROOT = ROOT / "database" / "development_attention"
RUNTIME_STATE_ROOT_ENV = "FAWKES_RUNTIME_STATE_ROOT"
CHOICES = {"approve_once", "deny", "cancel_campaign"}
QUALIFICATION_CHOICES = {"approve_once", "deny"}
SUPPORTED_RECOVERY_METHODS = {"item/commandExecution/requestApproval", "execCommandApproval"}
ATTENTION_BASE_URL_ENV = "FAWKES_ATTENTION_BASE_URL"
REMOTE_AUTHENTICATED_ENV = "FAWKES_ATTENTION_REMOTE_AUTHENTICATED"
CONSUMER_LEASE_SECONDS = 5
_DECISION_CONDITION = threading.Condition()
_SECRET = re.compile(r"(?i)(authorization|token|api[_ -]?key|webhook|password|secret)\s*[:=]\s*\S+")


class AttentionConsumerUnavailable(RuntimeError):
    """The exact typed request has no verifiably live or resumable consumer."""

    code = "attention_consumer_unavailable"


def _linux_process_identity(process_id):
    """Return a boot-scoped process-start identity, never PID alone."""
    try:
        pid = int(process_id)
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        # Fields after the final ')' begin at proc field 3; starttime is field 22.
        start_ticks = stat.rsplit(")", 1)[1].split()[19]
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except (OSError, ValueError, IndexError):
        return None
    return _digest({"boot_id": boot_id, "process_id": pid, "start_ticks": start_ticks})


def _validated_configured_root(value, *, leaf=None):
    try:
        configured = Path(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("configured Development Attention root is malformed") from exc
    if not configured.is_absolute():
        raise ValueError("configured Development Attention root must be absolute")
    selected = configured.resolve(strict=False)
    if leaf is not None:
        selected = selected / leaf
    repository = Path(__file__).resolve().parents[2]
    if selected == repository or repository in selected.parents:
        raise ValueError("configured Development Attention root must be outside the repository")
    existing = selected
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if ((selected.exists() and not selected.is_dir())
            or not existing.is_dir()
            or not os.access(existing, os.W_OK | os.X_OK)):
        raise ValueError("configured Development Attention root is unusable")
    return selected


def resolve_attention_root(root=None, *, environment=None):
    """Resolve one store root without changing the historical unconfigured default."""
    if root is not None:
        return _validated_configured_root(root)
    values = os.environ if environment is None else environment
    runtime_root = values.get(RUNTIME_STATE_ROOT_ENV)
    if runtime_root:
        return _validated_configured_root(runtime_root, leaf="development_attention")
    return ATTENTION_ROOT


@contextmanager
def _decision_lock(path):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as descriptor:
        fcntl.flock(descriptor.fileno(), fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(descriptor.fileno(), fcntl.LOCK_UN)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json_atomic(path, value):
    """Durably replace one record; callers retain an explicit cross-record state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def sanitize_action(value):
    text = "".join(character for character in str(value or "")[:2_000] if character.isprintable())
    text = re.sub(r"(?:https?|wss?)://\S+", "<redacted-endpoint>", text)
    return _SECRET.sub(lambda match: match.group(1) + "=<redacted>", text) or "unspecified protected action"


def canonical_attention_detail_url(attention_id, *, environment=None):
    """Build one credential-free decision URL under the authenticated app boundary."""
    if not re.fullmatch(r"attention-[a-f0-9]{64}", str(attention_id or "")):
        raise ValueError("invalid attention identity")
    values = os.environ if environment is None else environment
    base = str(values.get(ATTENTION_BASE_URL_ENV) or "http://localhost:8787").strip()
    parsed = urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("attention base URL must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("attention base URL must be an origin without a path")
    loopback = (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "http" and not loopback:
        raise ValueError("remote attention base URL requires HTTPS")
    if parsed.scheme == "https" and not loopback:
        if str(values.get(REMOTE_AUTHENTICATED_ENV, "")).lower() != "true":
            raise ValueError("remote attention base URL must declare its authenticated boundary")
    elif parsed.scheme not in {"http", "https"}:
        raise ValueError("attention base URL must use HTTP loopback or authenticated HTTPS")
    origin = urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))
    return origin + "?" + urlencode({
        "view": "developer", "section": "attention", "attention": attention_id})


def validate_attention_detail_url(detail_url, attention_id):
    parsed = urlsplit(str(detail_url or ""))
    query = parse_qs(parsed.query, strict_parsing=True)
    if query != {"view": ["developer"], "section": ["attention"],
                 "attention": [attention_id]}:
        raise ValueError("attention detail URL is not bound to the exact request")
    environment = {ATTENTION_BASE_URL_ENV: urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, "", ""))}
    if parsed.scheme == "https":
        environment[REMOTE_AUTHENTICATED_ENV] = "true"
    expected = canonical_attention_detail_url(attention_id, environment=environment)
    if expected != detail_url:
        raise ValueError("attention detail URL is not canonical")
    return detail_url


def native_approval_from_jsonl(stdout, stderr=""):
    """Recognize only typed Codex events or documented noninteractive process failures.

    Arbitrary agent prose is deliberately ignored.
    """
    for line in str(stdout or "").splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        event_type = event.get("type")
        if event_type not in {"approval.requested", "item.approval_requested", "tool.approval_required"}:
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        return {
            "origin": "codex_native_event", "provider_code": event_type,
            "blocked_action": sanitize_action(item.get("command") or item.get("action")),
            "why_required": sanitize_action(item.get("reason") or "Codex requested native approval"),
            "requested_authority": sanitize_action(item.get("permission") or "one protected operation"),
            "resources": [sanitize_action(value) for value in item.get("resources", [])[:16]],
            "reversible": item.get("reversible") if isinstance(item.get("reversible"), bool) else None,
        }
    # Codex 0.151.0 exec does not emit an approval event in the tested ephemeral
    # path. Only stable CLI-originated stderr diagnostics are accepted here.
    stable = str(stderr or "")
    match = re.search(r"(?im)^codex(?: exec)?: approval required(?: \(([^)]+)\))?\s*$", stable)
    if match:
        return {"origin": "codex_noninteractive_exit", "provider_code": match.group(1),
                "blocked_action": "Codex protected operation", "why_required": "native approval required",
                "requested_authority": "one protected operation", "resources": [], "reversible": None}
    return None


class DevelopmentAttentionStore:
    def __init__(self, root=None, *, environment=None, consumer_probe=None):
        self.environment = os.environ if environment is None else environment
        self.root = resolve_attention_root(root, environment=self.environment)
        self.events = self.root / "events"
        self.decisions = self.root / "decisions"
        self.transactions = self.root / "transactions"
        self.consumer_probe = consumer_probe or _linux_process_identity

    def _recover_transactions(self):
        """Roll durable multi-record intents forward to their one coherent state."""
        if not self.transactions.exists():
            return
        for transaction_path in sorted(self.transactions.glob("*.json")):
            with _decision_lock(transaction_path):
                try:
                    transaction = json.loads(transaction_path.read_text(encoding="utf-8"))
                    for write in transaction["writes"]:
                        target = self.root / write["relative_path"]
                        if self.root not in target.resolve(strict=False).parents:
                            raise ValueError("transaction target escapes Attention root")
                        _write_json_atomic(target, write["value"])
                    transaction_path.unlink(missing_ok=True)
                except FileNotFoundError:
                    continue

    def _write_transaction(self, transaction_id, writes):
        transaction_path = self.transactions / f"{transaction_id}.json"
        transaction = {"schema_version": 1, "record_type": "development_attention_transaction",
            "transaction_id": transaction_id, "writes": [
                {"relative_path": str(Path(path).relative_to(self.root)), "value": value}
                for path, value in writes]}
        _write_json_atomic(transaction_path, transaction)
        for path, value in writes:
            _write_json_atomic(path, value)
        transaction_path.unlink(missing_ok=True)

    def _new_consumer_binding(self, event_binding, binding_sha, created, *, owner_identity):
        # Typed app-server requests supply their exact child PID. Other bounded
        # producers are owned by the creating process and receive the same
        # boot/start-time protection instead of an unverifiable "live" flag.
        process_id = event_binding.get("process_id", os.getpid())
        process_identity = self.consumer_probe(process_id)
        if process_identity is None:
            return None
        return {
            "process_id": process_id,
            "process_start_identity": process_identity,
            "protocol_binding_sha256": binding_sha,
            "owner_identity_sha256": _digest(owner_identity),
            "registered_at": created.isoformat(),
            "lease_expires_at": (created + timedelta(seconds=CONSUMER_LEASE_SECONDS)).isoformat(),
        }

    def _effective_consumer(self, event, *, now=None):
        stored = event.get("consumer_state")
        if stored == "durably_resumable":
            return "durably_resumable", True, None
        if stored != "live":
            return "unavailable", False, "consumer_not_live"
        binding = event.get("consumer_binding")
        if not isinstance(binding, dict):
            return "unavailable", False, "consumer_binding_missing"
        if binding.get("protocol_binding_sha256") != event.get("protocol_binding_sha256"):
            return "unavailable", False, "consumer_binding_mismatch"
        owner_identity = {"campaign_id": event.get("campaign_id"),
            "invocation_id": event.get("invocation_id"),
            "attention_id": event.get("attention_id"),
            "protocol_binding_sha256": event.get("protocol_binding_sha256")}
        if binding.get("owner_identity_sha256") != _digest(owner_identity):
            return "unavailable", False, "consumer_owner_identity_mismatch"
        current = datetime.now(timezone.utc) if now is None else now
        try:
            lease_expires = datetime.fromisoformat(binding["lease_expires_at"])
        except (KeyError, TypeError, ValueError):
            return "unavailable", False, "consumer_lease_invalid"
        if lease_expires <= current:
            return "unavailable", False, "consumer_lease_expired"
        observed = self.consumer_probe(binding.get("process_id"))
        if not observed or observed != binding.get("process_start_identity"):
            return "unavailable", False, "consumer_process_identity_mismatch"
        return "live", True, None

    def _project_actionability(self, event):
        effective, actionable, reason = self._effective_consumer(event)
        return {**event, "stored_consumer_state": event.get("consumer_state"),
                "consumer_state": effective, "actionable": actionable,
                "consumer_unavailable_reason": reason}

    @staticmethod
    def _authority_binding(event):
        """The body-free immutable tuple carried by every authority transition."""
        protocol = event.get("protocol_binding") or {}
        return {
            "attention_id": event.get("attention_id"),
            "campaign_id": event.get("campaign_id"),
            "invocation_id": event.get("invocation_id"),
            "rider_id": protocol.get("rider_id", "tanner"),
            "recipient_sha256": protocol.get("recipient_sha256"),
            "approval_binding_kind": protocol.get("approval_binding_kind"),
            "approval_binding_sha256": protocol.get("approval_binding_sha256"),
            "review_package_id": protocol.get("review_package_id"),
            "review_package_record_sha256": protocol.get("review_package_record_sha256"),
            "reviewer_worker_id": protocol.get("reviewer_worker_id"),
            "reviewer_identity_sha256": protocol.get("reviewer_identity_sha256"),
            "reviewer_invocation_id": protocol.get("reviewer_invocation_id"),
            "candidate_snapshot_id": protocol.get("candidate_snapshot_id"),
            "candidate_record_sha256": protocol.get("candidate_record_sha256"),
            "mutation_digest_sha256": (protocol.get("mutation_digest_sha256")
                                       or protocol.get("workspace_changes_sha256")),
            "exact_change_evidence_sha256": protocol.get(
                "exact_change_evidence_sha256"),
            "authorized_scope_sha256": (protocol.get("authorized_scope_sha256")
                                         or protocol.get("allowed_scope_sha256")),
            "method": protocol.get("method"), "item_id": protocol.get("item_id"),
            "action_digest": protocol.get("approved_action_sha256"),
            "protocol_binding_sha256": event.get("protocol_binding_sha256"),
            "expires_at": event.get("expires_at"),
            "decision_nonce": event.get("decision_nonce"),
        }

    @staticmethod
    def _complete_recovery_evidence(event):
        protocol = event.get("protocol_binding") or {}
        recovery = protocol.get("recovery_evidence")
        if protocol.get("method") not in SUPPORTED_RECOVERY_METHODS or not isinstance(recovery, dict):
            return False
        required = {"recovery_id", "payload_sha256", "candidate_snapshot_id",
                    "mutation_digest_sha256", "authorized_scope_sha256",
                    "protocol_binding_sha256"}
        if any(not isinstance(recovery.get(key), str) or not recovery[key] for key in required):
            return False
        binding = DevelopmentAttentionStore._authority_binding(event)
        return (recovery["candidate_snapshot_id"] == binding["candidate_snapshot_id"]
                and recovery["mutation_digest_sha256"] == binding["mutation_digest_sha256"]
                and recovery["authorized_scope_sha256"] == binding["authorized_scope_sha256"]
                and recovery["protocol_binding_sha256"] == _digest({
                    key: value for key, value in protocol.items()
                    if key != "recovery_evidence"}))

    def _renew_consumer_lease(self, attention_id):
        path = self.events / f"{attention_id}.json"
        with _decision_lock(path):
            event = json.loads(path.read_text(encoding="utf-8"))
            binding = event.get("consumer_binding")
            if event.get("consumer_state") != "live" or not isinstance(binding, dict):
                return event
            observed = self.consumer_probe(binding.get("process_id"))
            if not observed or observed != binding.get("process_start_identity"):
                return event
            event = {**event, "consumer_binding": {**binding,
                "lease_expires_at": (datetime.now(timezone.utc) + timedelta(
                    seconds=CONSUMER_LEASE_SECONDS)).isoformat()}}
            event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
            _write_json_atomic(path, event)
            return event

    def create(self, *, campaign_id, invocation_id, worker, kind, blocked_action,
               why_required, requested_authority, resources=(), reversible=None,
               provider_code=None, expires_in_seconds=None, detail_url=None,
               protocol_binding=None, expiration_reason=None,
               expiration_effect=None, can_request_again=None, work_lost=None,
               qualification_instruction=None):
        binding = dict(protocol_binding or {})
        binding_sha = _digest(binding) if binding else None
        logical = {"campaign_id": campaign_id, "invocation_id": invocation_id,
                   "worker_id": worker["worker_id"], "kind": kind,
                   "blocked_action": sanitize_action(blocked_action),
                   "requested_authority": sanitize_action(requested_authority),
                   "protocol_binding_sha256": binding_sha}
        logical_id = "attention-" + _digest(logical)
        path = self.events / f"{logical_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        created = datetime.now(timezone.utc)
        decision_nonce = _digest({"attention_id": logical_id,
            "created_at": created.isoformat(), "entropy": uuid.uuid4().hex})
        canonical_detail = canonical_attention_detail_url(
            logical_id, environment=self.environment)
        if detail_url is not None and detail_url != canonical_detail:
            raise ValueError("supplied attention detail URL conflicts with canonical route")
        if expires_in_seconds is not None and not all((expiration_reason, expiration_effect,
                                                       can_request_again is not None,
                                                       work_lost is not None)):
            raise ValueError("expiring attention requires a complete justification")
        qualification = None
        if qualification_instruction is not None:
            if (not isinstance(qualification_instruction, dict)
                    or qualification_instruction.get("choice") not in QUALIFICATION_CHOICES
                    or not isinstance(qualification_instruction.get("label"), str)
                    or not qualification_instruction["label"].strip()):
                raise ValueError("qualification instruction must have a bounded label and exact choice")
            qualification = {
                "choice": qualification_instruction["choice"],
                "label": sanitize_action(qualification_instruction["label"]),
                "creates_authority": False,
            }
        owner_identity = {"campaign_id": campaign_id, "invocation_id": invocation_id,
            "attention_id": logical_id, "protocol_binding_sha256": binding_sha}
        consumer_binding = self._new_consumer_binding(
            binding, binding_sha, created, owner_identity=owner_identity)
        event = {"schema_version": 2, "record_type": "development_attention_event",
            "attention_id": logical_id, "logical_identity_sha256": _digest(logical),
            "campaign_id": campaign_id, "invocation_id": invocation_id,
            "worker": {"worker_id": worker["worker_id"], "role": worker.get("role"),
                       "creates_authority": False}, "kind": kind, "state": "needs_tanner",
            "blocked_action": sanitize_action(blocked_action),
            "why_required": sanitize_action(why_required),
            "resources": [sanitize_action(value) for value in list(resources)[:16]],
            "requested_authority": sanitize_action(requested_authority),
            "reversible": reversible, "choices": sorted(CHOICES),
            "provider_code": sanitize_action(provider_code) if provider_code else None,
            "protocol_binding": binding or None,
            "protocol_binding_sha256": binding_sha,
            "decision_nonce": decision_nonce,
            "created_at": created.isoformat(),
            "expires_at": ((created + timedelta(seconds=expires_in_seconds)).isoformat()
                           if expires_in_seconds is not None else None),
            "urgency": "urgent_expiring" if expires_in_seconds is not None else "normal",
            "expiration_reason": sanitize_action(expiration_reason) if expiration_reason else None,
            "expiration_effect": sanitize_action(expiration_effect) if expiration_effect else None,
            "can_request_again": can_request_again,
            "work_lost": work_lost,
            "qualification_instruction": qualification,
            "consumer_state": "live" if consumer_binding else "unavailable",
            "consumer_binding": consumer_binding,
            "approval_outcome": "awaiting_decision",
            "detail_url": canonical_detail,
            "decision_id": None, "acknowledged": False,
            "creates_authority": False, "creates_continuing_authority": False}
        # The UI receives this server-owned digest as an external anchor for
        # the exact authority tuple it displayed. It is not itself authority.
        event["authority_binding_sha256"] = _digest(self._authority_binding(event))
        event["record_sha256"] = _digest(event)
        self.events.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, event)
        return event

    def set_qualification_instruction(self, attention_id, *, campaign_id, invocation_id,
                                      choice, label, expected_action_digest):
        """Attach non-authoritative synthetic-test presentation metadata.

        This can repair a pending qualification display without replacing its
        identity, protocol binding, consumer, or authority state.
        """
        if choice not in QUALIFICATION_CHOICES or not str(label or "").strip():
            raise ValueError("invalid qualification instruction")
        path = self.events / f"{attention_id}.json"
        with _decision_lock(path):
            event = json.loads(path.read_text(encoding="utf-8"))
            binding = event.get("protocol_binding") or {}
            if (event.get("state") != "needs_tanner" or event.get("decision_id") is not None
                    or event.get("campaign_id") != campaign_id
                    or event.get("invocation_id") != invocation_id
                    or binding.get("approved_action_sha256") != expected_action_digest):
                raise PermissionError("qualification annotation identity/state mismatch")
            instruction = {"choice": choice, "label": sanitize_action(label),
                           "creates_authority": False}
            existing = event.get("qualification_instruction")
            if existing is not None and existing != instruction:
                raise PermissionError("qualification instruction is immutable once set")
            event = {**event, "qualification_instruction": instruction}
            event.pop("record_sha256", None)
            event["record_sha256"] = _digest(event)
            _write_json_atomic(path, event)
            return event

    def list(self, *, pending_only=False):
        if not self.events.exists():
            return []
        records = [self._project_actionability(self.refresh_expiration(path.stem))
                   for path in self.events.glob("*.json")]
        if pending_only:
            records = [item for item in records if item["state"] == "needs_tanner"
                       and item["actionable"]]
        return sorted(records, key=lambda item: item["created_at"], reverse=True)

    def get(self, attention_id):
        return self._project_actionability(self._read_event(attention_id))

    def _read_event(self, attention_id):
        return json.loads((self.events / f"{attention_id}.json").read_text(encoding="utf-8"))

    def refresh_expiration(self, attention_id, *, now=None):
        path = self.events / f"{attention_id}.json"
        with _decision_lock(path):
            event = json.loads(path.read_text(encoding="utf-8"))
            current = datetime.now(timezone.utc) if now is None else now
            if (event.get("state") == "needs_tanner" and event.get("expires_at")
                    and datetime.fromisoformat(event["expires_at"]) <= current):
                event = {**event, "state": "expired", "approval_outcome": "expired",
                         "expired_at": current.isoformat(), "creates_authority": False}
                event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
                _write_json_atomic(path, event)
            return event

    def lifecycle(self, attention_id):
        """Return the event plus its exact decision/consumption outcome for presentation."""
        self._recover_transactions()
        event = self._project_actionability(self.refresh_expiration(attention_id))
        decision = None
        if event.get("decision_id"):
            path = self.decisions / f"{event['decision_id']}.json"
            if path.exists():
                decision = json.loads(path.read_text(encoding="utf-8"))
        return {"event": event, "decision": decision}

    def decide(self, attention_id, choice, *, authenticated_rider, expected_identity=None):
        if authenticated_rider is not True:
            raise PermissionError("authenticated Rider decision required")
        if choice not in CHOICES:
            raise ValueError("decision must be approve_once, deny, or cancel_campaign")
        event_path = self.events / f"{attention_id}.json"
        with _decision_lock(event_path):
            event = json.loads(event_path.read_text(encoding="utf-8"))
            if event.get("record_sha256") != _digest(
                    {key: value for key, value in event.items() if key != "record_sha256"}):
                raise PermissionError("attention event integrity is invalid")
            canonical = self._authority_binding(event)
            required = ("attention_id", "campaign_id", "invocation_id", "rider_id",
                "recipient_sha256", "candidate_snapshot_id", "candidate_record_sha256",
                "mutation_digest_sha256", "authorized_scope_sha256", "method",
                "action_digest", "protocol_binding_sha256")
            if canonical.get("approval_binding_kind") == "independent_review_provider":
                required = (*required, "approval_binding_kind", "approval_binding_sha256",
                    "review_package_id", "review_package_record_sha256",
                    "reviewer_worker_id", "reviewer_identity_sha256",
                    "reviewer_invocation_id", "exact_change_evidence_sha256",
                    "expires_at", "decision_nonce")
            if (not isinstance(expected_identity, dict)
                    or any(not isinstance(expected_identity.get(key), str)
                           or not expected_identity[key] for key in required)):
                raise PermissionError("decision identity tuple is required and incomplete")
            if expected_identity != canonical:
                raise PermissionError("decision identity tuple does not match the canonical pending request")
            if event["state"] != "needs_tanner":
                raise RuntimeError("attention event is no longer awaiting Tanner")
            if event.get("expires_at") and datetime.fromisoformat(event["expires_at"]) <= datetime.now(timezone.utc):
                event = {**event, "state": "expired", "approval_outcome": "expired",
                         "expired_at": _now(), "creates_authority": False}
                event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
                _write_json_atomic(event_path, event)
                raise RuntimeError("attention request is stale")
            _effective, actionable, _reason = self._effective_consumer(event)
            if not actionable:
                raise AttentionConsumerUnavailable(
                    "exact action is no longer live or durably resumable")
            decision = {"schema_version": 1, "record_type": "development_attention_decision",
            "decision_id": f"attention-decision-{uuid.uuid4()}", "attention_id": attention_id,
            "campaign_id": event["campaign_id"], "invocation_id": event["invocation_id"],
            "choice": choice, "bounded_action_sha256": hashlib.sha256(
                event["blocked_action"].encode()).hexdigest(),
            "protocol_binding_sha256": event.get("protocol_binding_sha256"),
            "one_time": choice == "approve_once", "consumed": False,
            "creates_authority": choice == "approve_once",
            "lifecycle_state": ("recorded_pending_consumption" if choice == "approve_once"
                                else "completed"),
            "creates_continuing_authority": False, "decided_by": "authenticated_tanner",
            "decided_at": _now()}
            decision["authority_binding"] = self._authority_binding(event)
            decision["authority_binding_sha256"] = _digest(decision["authority_binding"])
            decision["record_sha256"] = _digest(decision)
            # The decision is written first. If interruption occurs before the event
            # projection, it remains a recoverable, explicitly unconsumed grant.
            decision_path = self.decisions / f"{decision['decision_id']}.json"
            _write_json_atomic(decision_path, decision)
            event = {**event, "state": "approved_once" if choice == "approve_once" else choice,
                 "decision_id": decision["decision_id"], "acknowledged": True,
                 "decided_at": decision["decided_at"],
                 "approval_outcome": decision["lifecycle_state"]}
            event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
            try:
                _write_json_atomic(event_path, event)
            except Exception:
                # A failed projection cannot leave a visible or consumable grant.
                decision_path.unlink(missing_ok=True)
                raise
        with _DECISION_CONDITION:
            _DECISION_CONDITION.notify_all()
        return {"event": event, "decision": decision}

    def mark_process_detached(self, attention_id):
        path = self.events / f"{attention_id}.json"
        with _decision_lock(path):
            event = json.loads(path.read_text(encoding="utf-8"))
            if event.get("process_state") == "detached":
                return event
            resumable = self._complete_recovery_evidence(event)
            event = {**event, "process_state": "detached",
                     "consumer_state": "durably_resumable" if resumable else "unavailable",
                     "process_detached_at": _now()}
            event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
            _write_json_atomic(path, event)
            return event

    def cancel_unresolved_qualification(self, attention_id, *, authorization_reference):
        """Close an explicitly cancelled synthetic request without fabricating a Rider decision."""
        if not isinstance(authorization_reference, str) or not authorization_reference.strip():
            raise PermissionError("exact qualification-cancellation authority is required")
        path = self.events / f"{attention_id}.json"
        with _decision_lock(path):
            event = json.loads(path.read_text(encoding="utf-8"))
            if event.get("state") != "needs_tanner" or event.get("decision_id") is not None:
                raise RuntimeError("only an unresolved decision-free qualification request may be cancelled")
            event = {**event, "state": "cancelled_qualification",
                     "approval_outcome": "cancelled_without_decision",
                     "consumer_state": "stopped", "acknowledged": False,
                     "qualification_cancelled_at": _now(),
                     "qualification_cancellation_reference": sanitize_action(authorization_reference),
                     "creates_authority": False}
            event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
            _write_json_atomic(path, event)
            return event

    def wait_for_decision(self, attention_id, *, timeout_seconds, process_alive=None,
                          reminder_handler=None):
        deadline = time.monotonic() + timeout_seconds
        with _DECISION_CONDITION:
            while True:
                event = self.refresh_expiration(attention_id)
                if event["state"] == "expired":
                    raise TimeoutError("Tanner decision request expired")
                if event["state"] != "needs_tanner":
                    decision = json.loads((self.decisions / f"{event['decision_id']}.json").read_text(encoding="utf-8"))
                    return {"event": event, "decision": decision}
                if process_alive is not None and not process_alive():
                    event = self.mark_process_detached(attention_id)
                elif process_alive is not None:
                    event = self._renew_consumer_lease(attention_id)
                if reminder_handler is not None:
                    reminder_handler(event)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Tanner decision window expired")
                _DECISION_CONDITION.wait(timeout=min(remaining, 0.5) if process_alive else remaining)

    def consume_approve_once(self, decision_id, *, attention_id, invocation_id,
                             protocol_binding_sha256=None, approved_action_sha256=None,
                             continuation_id=None, expected_binding=None):
        path = self.decisions / f"{decision_id}.json"
        with _decision_lock(path):
            decision = json.loads(path.read_text(encoding="utf-8"))
            event = self._read_event(attention_id)
            binding = event.get("protocol_binding") or {}
            canonical = self._authority_binding(event)
            if (decision["choice"] != "approve_once" or decision["attention_id"] != attention_id
                    or decision["invocation_id"] != invocation_id or decision["consumed"]
                    or (event.get("expires_at") and
                        datetime.fromisoformat(event["expires_at"]) <= datetime.now(timezone.utc))
                    or (protocol_binding_sha256 is not None and
                        decision.get("protocol_binding_sha256") != protocol_binding_sha256)
                    or decision.get("authority_binding") != canonical
                    or (expected_binding is not None and expected_binding != canonical)
                    or (approved_action_sha256 is not None and
                        binding.get("approved_action_sha256") != approved_action_sha256)):
                raise PermissionError("one-time approval is invalid, mismatched, or already consumed")
            reserved = decision.get("continuation")
            if continuation_id is not None and (not reserved or
                    reserved.get("continuation_id") != continuation_id or reserved.get("state") != "reserved"):
                raise PermissionError("detached continuation is not the exact reserved process")
            decision = {**decision, "consumed": True, "consumed_at": _now(),
                        "consumed_by_continuation_id": continuation_id,
                        "lifecycle_state": "resumed" if continuation_id else "consumed",
                        "creates_authority": False}
            decision["consumption_receipt"] = {**canonical, "continuation_id": continuation_id,
                "consumed_at": decision["consumed_at"], "creates_continuing_authority": False}
            decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
            event = {**event, "approval_outcome": decision["lifecycle_state"]}
            event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
            self._write_transaction("consume-" + decision_id, [
                (path, decision), (self.events / f"{attention_id}.json", event)])
            return decision

    def reserve_detached_continuation(self, decision_id, *, attention_id, invocation_id,
                                      protocol_binding_sha256, continuation_id,
                                      expected_binding=None):
        path = self.decisions / f"{decision_id}.json"
        with _decision_lock(path):
            decision = json.loads(path.read_text(encoding="utf-8"))
            event = self._read_event(attention_id)
            canonical = self._authority_binding(event)
            if (decision.get("choice") != "approve_once" or decision.get("consumed")
                    or decision.get("attention_id") != attention_id
                    or decision.get("invocation_id") != invocation_id
                    or decision.get("protocol_binding_sha256") != protocol_binding_sha256
                    or decision.get("authority_binding") != canonical
                    or (expected_binding is not None and expected_binding != canonical)
                    or not self._complete_recovery_evidence(event)
                    or event.get("state") != "approved_once"
                    or (event.get("expires_at") and
                        datetime.fromisoformat(event["expires_at"]) <= datetime.now(timezone.utc))
                    or decision.get("continuation") is not None):
                raise PermissionError("detached continuation grant is stale, mismatched, or replayed")
            decision["continuation"] = {"continuation_id": continuation_id, "state": "reserved",
                "reserved_at": _now(), "original_protocol_binding_sha256": protocol_binding_sha256,
                "authority_binding": canonical,
                "recovery_evidence_sha256": _digest((event.get("protocol_binding") or {}).get(
                    "recovery_evidence"))}
            decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
            _write_json_atomic(path, decision)
            return decision

    def begin_recovery_execution(self, decision_id, continuation_id):
        """Durably claim external recovery execution once before invoking its owner."""
        path = self.decisions / f"{decision_id}.json"
        with _decision_lock(path):
            decision = json.loads(path.read_text(encoding="utf-8"))
            continuation = decision.get("continuation") or {}
            event = self._read_event(decision["attention_id"])
            if event.get("expires_at") and datetime.fromisoformat(event["expires_at"]) <= datetime.now(timezone.utc):
                raise PermissionError("reserved continuation authority has expired")
            if continuation.get("continuation_id") != continuation_id:
                raise PermissionError("continuation identity mismatch")
            if continuation.get("state") == "outcome_recorded":
                return decision, False
            if continuation.get("state") == "executing":
                # Execution may already have crossed its external boundary. Never replay it.
                decision["continuation"] = {**continuation, "state": "outcome_recorded",
                    "outcome_status": "failed", "ambiguous_execution": True,
                    "outcome_recorded_at": _now()}
                decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
                _write_json_atomic(path, decision)
                return decision, False
            if continuation.get("state") != "reserved" or not decision.get("consumed"):
                raise PermissionError("continuation is not executable")
            decision["continuation"] = {**continuation, "state": "executing",
                "execution_started_at": _now()}
            decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
            _write_json_atomic(path, decision)
            return decision, True

    def record_recovery_outcome(self, decision_id, continuation_id, *, status):
        if status not in {"completed", "failed"}:
            raise ValueError("invalid recovery outcome")
        path = self.decisions / f"{decision_id}.json"
        with _decision_lock(path):
            decision = json.loads(path.read_text(encoding="utf-8"))
            continuation = decision.get("continuation") or {}
            if (continuation.get("continuation_id") != continuation_id
                    or continuation.get("state") != "executing"):
                raise PermissionError("recovery execution is not the claimed continuation")
            decision["continuation"] = {**continuation, "state": "outcome_recorded",
                "outcome_status": status, "outcome_recorded_at": _now()}
            decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
            _write_json_atomic(path, decision)
            return decision

    def finish_detached_continuation(self, decision_id, continuation_id, *, status):
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("invalid continuation status")
        path = self.decisions / f"{decision_id}.json"
        with _decision_lock(path):
            decision = json.loads(path.read_text(encoding="utf-8"))
            continuation = decision.get("continuation") or {}
            event = self._read_event(decision["attention_id"])
            if (continuation.get("continuation_id") != continuation_id
                    or continuation.get("state") not in {"reserved", "outcome_recorded"}
                    or not decision.get("consumed")
                    or continuation.get("authority_binding") != self._authority_binding(event)):
                raise PermissionError("continuation identity mismatch")
            if (continuation.get("state") == "outcome_recorded"
                    and continuation.get("outcome_status") != status):
                raise PermissionError("continuation outcome does not match its durable receipt")
            decision["continuation"] = {**continuation, "state": status, "finished_at": _now()}
            decision["lifecycle_state"] = "completed" if status == "completed" else "failed_safe"
            decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
            event = {**event, "approval_outcome": decision["lifecycle_state"]}
            event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
            self._write_transaction("finish-" + decision_id, [
                (path, decision), (self.events / f"{decision['attention_id']}.json", event)])
            return decision

    def finish_live_action(self, decision_id, *, status):
        if status not in {"completed", "failed"}:
            raise ValueError("invalid live action status")
        path = self.decisions / f"{decision_id}.json"
        with _decision_lock(path):
            decision = json.loads(path.read_text(encoding="utf-8"))
            if not decision.get("consumed"):
                raise RuntimeError("unconsumed approval cannot be completed")
            if decision.get("lifecycle_state") in {"completed", "failed_safe"}:
                return decision
            decision["lifecycle_state"] = "completed" if status == "completed" else "failed_safe"
            decision["finished_at"] = _now()
            decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
            _write_json_atomic(path, decision)
            event = self._read_event(decision["attention_id"])
            event = {**event, "approval_outcome": decision["lifecycle_state"]}
            event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
            _write_json_atomic(self.events / f"{decision['attention_id']}.json", event)
            return decision

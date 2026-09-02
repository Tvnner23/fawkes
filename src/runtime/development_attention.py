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


ROOT = Path(os.environ.get(
    "FAWKES_DEVELOPMENT_ROOT", Path(__file__).resolve().parent.parent.parent
)).resolve()
ATTENTION_ROOT = ROOT / "database" / "development_attention"
CHOICES = {"approve_once", "deny", "cancel_campaign"}
_DECISION_CONDITION = threading.Condition()
_SECRET = re.compile(r"(?i)(authorization|token|api[_ -]?key|webhook|password|secret)\s*[:=]\s*\S+")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sanitize_action(value):
    text = "".join(character for character in str(value or "")[:2_000] if character.isprintable())
    text = re.sub(r"(?:https?|wss?)://\S+", "<redacted-endpoint>", text)
    return _SECRET.sub(lambda match: match.group(1) + "=<redacted>", text) or "unspecified protected action"


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
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else ATTENTION_ROOT
        self.events = self.root / "events"
        self.decisions = self.root / "decisions"

    def create(self, *, campaign_id, invocation_id, worker, kind, blocked_action,
               why_required, requested_authority, resources=(), reversible=None,
               provider_code=None, expires_in_seconds=3600, detail_url=None,
               protocol_binding=None):
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
        event = {"schema_version": 1, "record_type": "development_attention_event",
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
            "created_at": created.isoformat(),
            "expires_at": (created + timedelta(seconds=expires_in_seconds)).isoformat(),
            "detail_url": detail_url or f"http://localhost:8787/?view=developer&attention={logical_id}",
            "decision_id": None, "acknowledged": False, "creates_authority": False}
        event["record_sha256"] = _digest(event)
        self.events.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        return event

    def list(self, *, pending_only=False):
        if not self.events.exists():
            return []
        records = [json.loads(path.read_text(encoding="utf-8")) for path in self.events.glob("*.json")]
        if pending_only:
            records = [item for item in records if item["state"] == "needs_tanner"]
        return sorted(records, key=lambda item: item["created_at"], reverse=True)

    def get(self, attention_id):
        return json.loads((self.events / f"{attention_id}.json").read_text(encoding="utf-8"))

    def decide(self, attention_id, choice, *, authenticated_rider):
        if authenticated_rider is not True:
            raise PermissionError("authenticated Rider decision required")
        if choice not in CHOICES:
            raise ValueError("decision must be approve_once, deny, or cancel_campaign")
        event = self.get(attention_id)
        if event["state"] != "needs_tanner":
            raise RuntimeError("attention event is no longer awaiting Tanner")
        if datetime.fromisoformat(event["expires_at"]) <= datetime.now(timezone.utc):
            raise RuntimeError("attention request is stale")
        decision = {"schema_version": 1, "record_type": "development_attention_decision",
            "decision_id": f"attention-decision-{uuid.uuid4()}", "attention_id": attention_id,
            "campaign_id": event["campaign_id"], "invocation_id": event["invocation_id"],
            "choice": choice, "bounded_action_sha256": hashlib.sha256(
                event["blocked_action"].encode()).hexdigest(),
            "protocol_binding_sha256": event.get("protocol_binding_sha256"),
            "one_time": choice == "approve_once", "consumed": False,
            "creates_continuing_authority": False, "decided_by": "authenticated_tanner",
            "decided_at": _now()}
        decision["record_sha256"] = _digest(decision)
        self.decisions.mkdir(parents=True, exist_ok=True)
        (self.decisions / f"{decision['decision_id']}.json").write_text(
            json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        event = {**event, "state": "approved_once" if choice == "approve_once" else choice,
                 "decision_id": decision["decision_id"], "acknowledged": True,
                 "decided_at": decision["decided_at"]}
        event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
        (self.events / f"{attention_id}.json").write_text(
            json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with _DECISION_CONDITION:
            _DECISION_CONDITION.notify_all()
        return {"event": event, "decision": decision}

    def wait_for_decision(self, attention_id, *, timeout_seconds):
        deadline = time.monotonic() + timeout_seconds
        with _DECISION_CONDITION:
            while True:
                event = self.get(attention_id)
                if event["state"] != "needs_tanner":
                    decision = json.loads((self.decisions / f"{event['decision_id']}.json").read_text(encoding="utf-8"))
                    return {"event": event, "decision": decision}
                if datetime.fromisoformat(event["expires_at"]) <= datetime.now(timezone.utc):
                    raise TimeoutError("Tanner decision request expired")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Tanner decision window expired")
                _DECISION_CONDITION.wait(timeout=remaining)

    def consume_approve_once(self, decision_id, *, attention_id, invocation_id):
        path = self.decisions / f"{decision_id}.json"
        decision = json.loads(path.read_text(encoding="utf-8"))
        if (decision["choice"] != "approve_once" or decision["attention_id"] != attention_id
                or decision["invocation_id"] != invocation_id or decision["consumed"]):
            raise PermissionError("one-time approval is invalid, mismatched, or already consumed")
        decision = {**decision, "consumed": True, "consumed_at": _now()}
        decision.pop("record_sha256", None); decision["record_sha256"] = _digest(decision)
        path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return decision

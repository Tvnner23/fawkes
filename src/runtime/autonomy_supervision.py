"""Rider-facing projections and phone-alert intent for bounded Development.

Campaign records and Worker Exchange remain canonical.  This module stores only
logical notification delivery state; it grants no campaign or rider authority.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import re
import uuid

from src.runtime.worker_exchange import _digest
from src.runtime.development_attention import validate_attention_detail_url


PROGRESS_INTERVAL_SECONDS = 10_800
NOTIFICATION_ROOT = Path(__file__).resolve().parents[2] / "database" / "rider_notifications"


class RiderActivityStore:
    """Authenticated rider-presence signal; absence of campaign input is irrelevant."""

    def __init__(self, instance_id, *, root):
        self.instance_id = instance_id
        self.path = Path(root) / instance_id / "rider-activity.json"

    def touch(self, *, authenticated_rider):
        if authenticated_rider is not True:
            raise PermissionError("authenticated rider activity is required")
        value = {"schema_version": 1, "record_type": "rider_activity",
                 "instance_id": self.instance_id,
                 "last_active_at": datetime.now(timezone.utc).isoformat()}
        value["record_sha256"] = _digest(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return value

    def load(self):
        value = json.loads(self.path.read_text(encoding="utf-8"))
        claimed = value.get("record_sha256")
        if claimed != _digest({key: item for key, item in value.items() if key != "record_sha256"}):
            raise ValueError("rider activity integrity mismatch")
        return value


def _utc(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return parsed.astimezone(timezone.utc)


def campaign_activity_projection(record):
    """Derive a bounded, body-free activity view from durable campaign state."""
    builder_by_iteration = {item["iteration"]: item for item in record.get("builder_runs", [])}
    review_by_iteration = {item["iteration"]: item for item in record.get("reviews", [])}
    activity = []
    for event in record.get("events", []):
        detail = event.get("detail") or {}
        item = {"event_id": event["event_id"], "kind": event["kind"],
                "created_at": event["created_at"], "detail": detail}
        iteration = detail.get("iteration")
        if event["kind"] in {"builder_return_retained", "builder_failed_safe"} and iteration in builder_by_iteration:
            run = builder_by_iteration[iteration]
            item["worker"] = record["builder"]
            item["summary"] = {key: run.get(key) for key in (
                "status", "task_scope_id", "return_report_id", "verification_status",
                "failure", "transport_result_reference", "validation_evidence")}
        if event["kind"] == "independent_review_retained" and iteration in review_by_iteration:
            review = review_by_iteration[iteration]
            item["worker"] = review["reviewer"]
            item["summary"] = {key: review.get(key) for key in (
                "status", "review_report_id", "acceptance_condition_ids_satisfied",
                "violated_acceptance_condition_ids", "defects")}
        activity.append(item)
    return {"campaign_id": record["campaign_id"], "objective": record["objective"],
            "status": record["status"], "current_stage": record["status"],
            "iteration": record["iteration"], "maximum_iterations": record["maximum_iterations"],
            "builder": record["builder"], "reviewer": record["reviewer_requirement"],
            "needs_tanner": record["needs_tanner"], "cancelled": record["cancelled"],
            "recovery_references": record["recovery_references"], "activity": activity,
            "exact_worker_bodies_remain_in_worker_exchange": True,
            "hidden_chain_of_thought_exposed": False, "creates_authority": False}


class RiderNotificationStore:
    """Durable logical notifications and distinct delivery attempts."""

    def __init__(self, instance_id, *, root):
        self.instance_id = instance_id
        self.root = Path(root) / instance_id

    def _path(self, logical_id):
        return self.root / f"{logical_id}.json"

    def _write(self, value):
        path = self._path(value["notification_id"])
        value = {key: item for key, item in value.items() if key != "record_sha256"}
        value["record_sha256"] = _digest(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return value

    def create_once(self, *, kind, campaign_id, state_key, message, evidence_refs):
        logical_id = "rider-notification-" + hashlib.sha256(
            f"{self.instance_id}\0{kind}\0{campaign_id}\0{state_key}".encode()).hexdigest()
        path = self._path(logical_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), False
        value = {"schema_version": 1, "record_type": "rider_notification",
            "notification_id": logical_id, "instance_id": self.instance_id, "kind": kind,
            "campaign_id": campaign_id, "state_key": state_key, "message": message,
            "evidence_references": evidence_refs, "attempts": [], "delivered": False,
            "creates_authority": False, "created_at": datetime.now(timezone.utc).isoformat()}
        return self._write(value), True

    def deliver(self, record, sender, *, transport_name="unspecified"):
        projection_sha256 = hashlib.sha256(record["message"].encode("utf-8")).hexdigest()
        for retained in record.get("attempts", []):
            if retained.get("transport") != transport_name:
                continue
            if retained.get("status") == "in_flight":
                attempts = [({**item, "status": "accepted_receipt_ambiguous",
                              "retry_permitted": False}
                             if item.get("attempt_id") == retained.get("attempt_id") else item)
                            for item in record["attempts"]]
                return self._write({**record, "attempts": attempts})
            if retained.get("status") in {"delivered", "accepted_receipt_ambiguous"}:
                return record
            if (retained.get("status") == "failed"
                    and retained.get("failure_code") == "ValueError"
                    and retained.get("projection_sha256") == projection_sha256):
                # A deterministic local projection rejection cannot improve by
                # retrying unchanged content. A new projection digest may try once.
                return record
        attempt = {"attempt_id": f"notification-attempt-{uuid.uuid4()}",
            "attempted_at": datetime.now(timezone.utc).isoformat(), "transport": transport_name,
            "status": "in_flight", "projection_sha256": projection_sha256}
        current = self._write({**record, "attempts": [*record["attempts"], attempt]})
        try:
            receipt = sender(record["message"])
            attempt.update({"status": "delivered", "provider_receipt": receipt})
            delivered = True
        except Exception as exc:
            attempt.update({"status": "failed", "failure_code": type(exc).__name__})
            delivered = False
        value = {**current, "attempts": [*record["attempts"], attempt],
                 "delivered": record["delivered"] or delivered}
        return self._write(value)


class TannerAttentionTransportRegistry:
    """Explicit zero-authority fan-out for one canonical Tanner notification."""

    def __init__(self):
        self._transports = {}

    def register(self, name, sender, *, endpoint_authorized, recipient_identity="tanner"):
        if endpoint_authorized is not True:
            raise PermissionError("Tanner endpoint authorization is required")
        if recipient_identity != "tanner":
            raise PermissionError("Development attention may be delivered only to Tanner")
        if not name or name in self._transports:
            raise ValueError("attention transport identity must be unique")
        self._transports[name] = sender
        return self

    def dispatch(self, record, store):
        results = {}
        current = record
        for name, sender in self._transports.items():
            current = store.deliver(current, sender, transport_name=name)
            results[name] = next((item for item in reversed(current.get("attempts", []))
                                  if item.get("transport") == name), None)
        return {"notification": current, "transport_results": results,
                "creates_authority": False}


def configured_attention_transports(environment=None):
    import os
    values = os.environ if environment is None else environment
    registry = TannerAttentionTransportRegistry()
    if values.get("FAWKES_DISCORD_WEBHOOK_URL"):
        from src.runtime.discord_webhook import DiscordWebhookConfiguration, DiscordWebhookSender
        registry.register("discord_webhook",
            DiscordWebhookSender(DiscordWebhookConfiguration.from_environment(values)),
            endpoint_authorized=True)
    return registry


def expiration_reminder_stage(needs, *, now=None):
    """Return one stable escalation stage; ordinary attention has no countdown."""
    if not needs.get("expires_at"):
        return None
    now = _utc(now or datetime.now(timezone.utc))
    expires = _utc(needs["expires_at"])
    remaining = (expires - now).total_seconds()
    if remaining <= 0:
        return "expired"
    # Typed approval windows are currently one hour. Stable thresholds make
    # repeated projections idempotent within each increasingly urgent stage.
    if remaining <= 300:
        return "five_minutes"
    if remaining <= 900:
        return "fifteen_minutes"
    if remaining <= 1800:
        return "half_window"
    return "initial"


def retain_needs_tanner_notification(record, *, root=NOTIFICATION_ROOT, registry=None):
    """Retain one sanitized logical alert for each material blocker state."""
    needs = record.get("needs_tanner")
    if not needs:
        return None
    reason = str(needs.get("plain_reason") or needs.get("reason")
                 or "campaign requires rider review")[:240]
    attention_id = str(needs.get("attention_id") or "")
    detail_url = str(needs.get("detail_url") or "")
    if re.fullmatch(r"attention-[a-f0-9]{64}", attention_id):
        validate_attention_detail_url(detail_url, attention_id)
    else:
        detail_url = ""
    reminder_stage = expiration_reminder_stage(needs)
    state_key = hashlib.sha256(json.dumps(
        {"needs": needs, "reminder_stage": reminder_stage}, sort_keys=True).encode()).hexdigest()
    store = RiderNotificationStore(record["instance_id"], root=root)
    label = reason.split(":", 1)[0].split(" — Allow", 1)[0]
    deadline = str(needs.get("expires_at") or "")
    consequence = "If unanswered, this request expires and the action will not run."
    fixed = ((f"URGENT — DECIDE BEFORE {deadline}\n" if deadline else "")
             + f"{label}\nFawkes paused because: {{reason}}\n"
             + (consequence + "\n" if deadline else "")
             + f"Review and decide: {detail_url}\n"
             + "Opening or receiving this notification grants no authority.")
    # Keep the exact label, deadline, consequence, and link; bound only the
    # explanatory reason because the authenticated decision page owns detail.
    available = max(0, 479 - len(fixed.format(reason="")))
    short_reason = reason[:available].rstrip()
    if len(reason) > len(short_reason) and available > 1:
        short_reason = short_reason[:-1].rstrip() + "…"
    message = fixed.format(reason=short_reason)
    notification, _ = store.create_once(kind="needs_tanner",
        campaign_id=record["campaign_id"], state_key=state_key,
        message=message,
        evidence_refs=[{"reference_type": "development_campaign",
                        "reference_id": record["campaign_id"],
                        "record_sha256": record["record_sha256"]}])
    active = registry if registry is not None else configured_attention_transports()
    return active.dispatch(notification, store)["notification"] if active._transports else notification


def notification_eligibility(record, *, now, rider_last_active_at, quiet_hours=None):
    """Return logical phone intents; caller supplies an actual configured sender."""
    now = _utc(now)
    last_active = _utc(rider_last_active_at)
    needs = record.get("needs_tanner")
    if needs:
        state_key = hashlib.sha256(json.dumps(needs, sort_keys=True).encode()).hexdigest()
        return {"kind": "needs_tanner", "state_key": state_key, "eligible": True,
                "bypasses_quiet_hours": True}
    if record.get("status") in {"succeeded", "cancelled", "failed_safe", "tanner_escalation"}:
        return None
    inactive = (now - last_active).total_seconds() >= PROGRESS_INTERVAL_SECONDS
    if not inactive:
        return None
    if quiet_hours is None:
        return {"kind": "periodic_progress", "eligible": False,
                "reason": "quiet_hours_unconfigured"}
    in_quiet = quiet_hours["is_quiet"](now)
    bucket = int(now.timestamp()) // PROGRESS_INTERVAL_SECONDS
    return {"kind": "morning_summary" if quiet_hours.get("ended_with_suppressed") else "periodic_progress",
            "state_key": str(bucket), "eligible": not in_quiet, "suppressed": in_quiet,
            "bypasses_quiet_hours": False}

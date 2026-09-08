"""Rider-facing projections and phone-alert intent for bounded Development.

Campaign records and Worker Exchange remain canonical.  This module stores only
logical notification delivery state; it grants no campaign or rider authority.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import fcntl
import json
import os
import re
import uuid

from src.runtime.worker_exchange import _digest
from src.runtime.development_attention import sanitize_action, validate_attention_detail_url


PROGRESS_INTERVAL_SECONDS = 10_800
NOTIFICATION_ROOT = Path(__file__).resolve().parents[2] / "database" / "rider_notifications"
RUNTIME_STATE_ROOT_ENV = "FAWKES_RUNTIME_STATE_ROOT"
MAX_NOTIFICATION_CHARACTERS = 480


def _validated_notification_root(value, *, leaf=None):
    try:
        configured = Path(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("configured Rider notification root is malformed") from exc
    if not configured.is_absolute():
        raise ValueError("configured Rider notification root must be absolute")
    selected = configured.resolve(strict=False)
    if leaf is not None:
        selected = selected / leaf
    repository = Path(__file__).resolve().parents[2]
    if selected == repository or repository in selected.parents:
        raise ValueError("configured Rider notification root must be outside the repository")
    existing = selected
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if ((selected.exists() and not selected.is_dir())
            or not existing.is_dir()
            or not os.access(existing, os.W_OK | os.X_OK)):
        raise ValueError("configured Rider notification root is unusable")
    return selected


def resolve_notification_root(root=None, *, environment=None):
    """Resolve the existing store once while retaining its historical fallback."""
    if root is not None:
        return _validated_notification_root(root)
    values = os.environ if environment is None else environment
    runtime_root = values.get(RUNTIME_STATE_ROOT_ENV)
    if runtime_root:
        return _validated_notification_root(runtime_root, leaf="rider_notifications")
    return NOTIFICATION_ROOT


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


def console_timestamp(value):
    """Accept only explicit, timezone-bound lifecycle timestamps."""
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def campaign_console_reporting(record, managed=(), *, observed_at=None):
    """Read-only facts and intervals; reservations never prove provider execution.

    Missing start boundaries (notably legacy Reviewer, Apply and Git records)
    deliberately remain unknown. Event order is retained, never timestamp-sorted
    into a plausible lifecycle. No historical record is repaired here.
    """
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    now = console_timestamp(observed_at)
    events = record.get("events", [])
    runs = record.get("builder_runs", [])
    reviews = record.get("reviews", [])
    intervals = []

    def interval(stage, attempt, start, end, sources, state, verified=False, valid_order=True):
        begin, finish = console_timestamp(start), console_timestamp(end)
        reliable = bool(valid_order and now and begin and begin <= now and
                        ((finish and begin <= finish <= now) if end is not None else verified))
        duration = int(((finish or now) - begin).total_seconds()) if reliable else None
        intervals.append({"stage": stage, "attempt": attempt, "started_at": start,
            "ended_at": end, "state": state, "duration_seconds": duration,
            "active_verified": bool(reliable and end is None and verified),
            "source_references": sources})

    starts = [(index, event) for index, event in enumerate(events)
              if event.get("kind") == "builder_invocation_started"]
    for index, event in starts[-3:]:
        attempt = (event.get("detail") or {}).get("iteration")
        if not isinstance(attempt, int) or isinstance(attempt, bool):
            continue
        following = events[index + 1:]
        boundary = next((i for i, item in enumerate(following)
                         if item.get("kind") == "builder_invocation_started"), len(following))
        next_start = console_timestamp(following[boundary].get("created_at")) if boundary < len(following) else None
        following = following[:boundary]
        run = next((item for item in runs if item.get("iteration") == attempt), {})
        end = run.get("completed_at")
        source = [f"events/{event['event_id']}"]
        if run:
            source.append(f"builder_runs/iteration={attempt}/completed_at")
        # This envelope starts at dispatch, not at native turn/start. Retain a
        # reliable historical close, but never use it as live execution proof.
        interval("worker", attempt, event.get("created_at"), end, source,
                 run.get("status", "unobserved"), False,
                 valid_order=boundary == len(events[index + 1:]) or bool(
                     next_start and console_timestamp(end) and console_timestamp(end) <= next_start))
        intervals[-1]["timing_basis"] = "historical_invocation_envelope"
        intervals[-1]["invocation_id"] = str((event.get("detail") or {}).get("task_scope_id")) + "-appserver"
        retained = next((item for item in following if item.get("kind") == "builder_return_retained"), None)
        prepared = next((item for item in following if item.get("kind") == "logical_review_request_prepared"), None)
        review = next((item for item in reviews if item.get("iteration") == attempt), {})
        if retained:
            # Queue ends at dispatch preparation, not at an inferred process launch.
            interval("review_queue", attempt, retained.get("created_at"),
                (prepared or {}).get("created_at"),
                [f"events/{item['event_id']}" for item in (retained, prepared) if item],
                "dispatched" if prepared else "waiting")
        transports = [(number, item) for number, item in enumerate(record.get("review_transport_attempts", []))
                      if item.get("iteration") == attempt]
        for number, transport in transports[-4:]:
            # Only the transport close is recorded by the current lifecycle owner.
            interval("review", attempt, None, transport.get("created_at"),
                [f"review_transport_attempts/{number}/created_at"], "transport_" + transport.get("status", "unknown"))
        if review or (not transports and retained):
            interval("review", attempt, None, review.get("received_at"),
                [f"reviews/iteration={attempt}"] if review else source,
                review.get("status", "waiting"))

    for stage, field in (("application", "application_evidence"), ("git", "git_commit_evidence")):
        evidence = record.get(field) or {}
        if evidence:
            interval(stage, record.get("iteration", 0), None, None, [field], evidence.get("status", "unknown"))
    terminal = record.get("status") in {"succeeded", "failed_safe", "denied", "expired", "cancelled"}
    # Outcome is a close event, not an interval from an invented preceding stage.
    if terminal:
        interval("terminal", record.get("iteration", 0), None,
            events[-1].get("created_at") if events else None,
            [f"events/{events[-1]['event_id']}"] if events else [], record["status"])

    last_run = runs[-1] if runs else {}
    last_review = reviews[-1] if reviews else {}
    application = record.get("application_evidence") or {}
    git = record.get("git_commit_evidence") or {}
    facts = []
    failure_reason = (record.get("needs_tanner") or {}).get("failure_code") or (record.get("needs_tanner") or {}).get("reason")
    if failure_reason and record.get("status") in {"failed_safe", "tanner_escalation"}:
        facts.append("Recorded stop reason: " + str(failure_reason)[:160] + ".")
    for run in runs[-3:]:
        iteration = run.get("iteration", "?")
        facts.append(f"Worker attempt {iteration}: {run.get('status') or 'unknown'}.")
        failure = (run.get("failure") or {}).get("code")
        if failure:
            facts.append(f"Attempt {iteration} failure: {str(failure)[:120]}.")
        checks = run.get("validation_evidence") or []
        if checks:
            passed = sum(item.get("exit_status") == 0 for item in checks)
            facts.append(f"Attempt {iteration} validation: {passed}/{len(checks)} checks passed.")
    if last_review:
        facts.append(f"Independent review: {last_review.get('status') or 'unknown'}; "
                     f"{len(last_review.get('acceptance_condition_ids_satisfied') or [])} conditions satisfied.")
    if application:
        facts.append(f"Application: {application.get('status') or 'unknown'}; "
                     f"{len(application.get('applied_paths') or [])} paths recorded.")
        paths = application.get("applied_paths") or []
        if paths:
            facts.append("Applied paths: " + ", ".join(str(path) for path in paths[:4])[:350])
    if git:
        facts.append(f"Git: {git.get('status') or 'unknown'}. Recorded HEAD: {git.get('head') or 'unknown'}.")
    from src.runtime.console_observation import execution_turns
    turns = execution_turns(list(managed), observed_at=observed_at)
    for role in ("worker", "reviewer"):
        role_turns = [turn for turn in turns if turn["role"] == role]
        if role_turns:
            # Replace only the matching Worker envelope. A later queued
            # correction without turn/start must retain its unavailable clock;
            # another invocation's completed native turn cannot fill it.
            native_intervals = []
            for number, turn in enumerate(role_turns, 1):
                native_intervals.append({"stage": "review" if role == "reviewer" else "worker", "attempt": number,
                    "started_at": turn["started_at"], "ended_at": turn["ended_at"], "state": turn["state"],
                    "duration_seconds": turn["active_seconds"], "active_verified": turn["active_verified"],
                    "invocation_id": turn["invocation_id"],
                    "source_references": ["managed-turn/"+turn["invocation_id"]+"/"+turn["turn_id"]],
                    "timing_basis": "native_turn_active_time",
                    "active_time_excludes_attention": True})
            if role == "worker":
                merged=[];used=set()
                for item in (i for i in intervals if i["stage"] == "worker"):
                    matching=[i for i in native_intervals if i["invocation_id"] == item.get("invocation_id")]
                    if matching:
                        merged.extend(matching);used.update(id(i) for i in matching)
                    else:
                        merged.append(item)
                merged.extend(i for i in native_intervals if id(i) not in used)
                intervals=[i for i in intervals if i["stage"] != "worker"]+merged
            else:
                intervals=[i for i in intervals if i["stage"] != "review"]+native_intervals
    from src.runtime.console_outcome import completed_objective, blocked_objective_identity
    parents = [item.get("reference_id") for item in record.get("recovery_references", [])
               if item.get("reference_type") == "parent_campaign"]
    return {"record_sha256": record.get("record_sha256"), "observed_at": observed_at,
        "objective_closeout": completed_objective(record),
        "blocker_identity": blocked_objective_identity(record),
        "created_at": record.get("created_at"), "updated_at": record.get("updated_at"),
        "turns": turns, "timing_history_incomplete": len(managed) > 16
            or any(item.get("timing_history_incomplete") for item in managed)
            or any(item.get("history_incomplete") for item in turns),
        "timing_incomplete_roles": ["worker", "reviewer"] if len(managed) > 16
            or any(item.get("timing_history_incomplete") for item in managed)
            else sorted({item["role"] for item in turns if item.get("history_incomplete")}),
        "intervals": intervals[:24], "facts": facts[:12],
        "worker_status": last_run.get("status"),
        "worker_task_scope_id": last_run.get("task_scope_id"),
        "review_status": last_review.get("status"),
        "application_status": application.get("status"), "git_status": git.get("status"),
        "parent_campaign_id": record.get("parent_campaign_id") or (parents[0] if len(parents) == 1 else None),
        "source_references": ["builder_runs", "reviews", "application_evidence", "git_commit_evidence"],
        "creates_authority": False}


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

    def __init__(self, instance_id, *, root=None, environment=None):
        self.instance_id = instance_id
        self.state_root = resolve_notification_root(root, environment=environment)
        self.root = self.state_root / instance_id

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

    def _with_delivery_claim_lock(self, notification_id):
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / f".{notification_id}.delivery.lock"
        handle = lock_path.open("a+b")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    @staticmethod
    def _release_delivery_claim_lock(handle):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

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
        claim_lock = self._with_delivery_claim_lock(record["notification_id"])
        try:
            path = self._path(record["notification_id"])
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else record
            for retained in current.get("attempts", []):
                if retained.get("transport") != transport_name:
                    continue
                if retained.get("status") == "in_flight":
                    attempts = [({**item, "status": "accepted_receipt_ambiguous",
                                  "retry_permitted": False}
                                 if item.get("attempt_id") == retained.get("attempt_id") else item)
                                for item in current["attempts"]]
                    return self._write({**current, "attempts": attempts})
                if retained.get("status") in {"delivered", "accepted_receipt_ambiguous"}:
                    return current
                if (retained.get("status") == "failed"
                        and retained.get("failure_code") == "ValueError"
                        and retained.get("projection_sha256") == projection_sha256):
                    # A deterministic local projection rejection cannot improve by
                    # retrying unchanged content. A new projection digest may try once.
                    return current
            attempt = {"attempt_id": f"notification-attempt-{uuid.uuid4()}",
                "attempted_at": datetime.now(timezone.utc).isoformat(), "transport": transport_name,
                "status": "in_flight", "projection_sha256": projection_sha256}
            current = self._write({**current,
                "attempts": [*current.get("attempts", []), attempt]})
            try:
                receipt = sender(record["message"])
                attempt.update({"status": "delivered", "provider_receipt": receipt})
                delivered = True
            except Exception as exc:
                attempt.update({"status": "failed", "failure_code": type(exc).__name__})
                delivered = False
            attempts = [attempt if item.get("attempt_id") == attempt["attempt_id"] else item
                        for item in current.get("attempts", [])]
            value = {**current, "attempts": attempts,
                     "delivered": current.get("delivered", False) or delivered}
            return self._write(value)
        finally:
            self._release_delivery_claim_lock(claim_lock)


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


def retain_needs_tanner_notification(record, *, root=None, registry=None, environment=None):
    """Retain one sanitized logical alert for each material blocker state."""
    needs = record.get("needs_tanner")
    if not needs:
        return None
    reason = str(needs.get("plain_reason") or needs.get("reason")
                 or "campaign requires rider review")[:240]
    attention_id = str(needs.get("attention_id") or "")
    detail_url = str(needs.get("detail_url") or "")
    actionable = False
    if re.fullmatch(r"attention-[a-f0-9]{64}", attention_id):
        try:
            validate_attention_detail_url(detail_url, attention_id)
            actionable = True
        except ValueError:
            detail_url = ""
    if not actionable:
        detail_url = ""
    reminder_stage = expiration_reminder_stage(needs)
    state_key = hashlib.sha256(json.dumps(
        {"needs": needs, "reminder_stage": reminder_stage}, sort_keys=True).encode()).hexdigest()
    store = RiderNotificationStore(record["instance_id"], root=root, environment=environment)
    inferred_label = reason.split(":", 1)[0].split(" — Allow", 1)[0]
    deadline = str(needs.get("expires_at") or "")
    campaign = str(record["campaign_id"])
    label = inferred_label if inferred_label != reason else campaign
    prefix = ((f"URGENT — DECIDE BEFORE {deadline}\n" if deadline else "")
              + (f"{label}\n" if label != campaign else "")
              + f"Campaign: {campaign}\n"
              + "Fawkes paused: {reason}\n")
    if actionable:
        suffix = (("If unanswered, this request expires and the action will not run.\n"
                   if deadline else "")
                  + f"Review and decide: {detail_url}\n"
                  + "Opening this link grants no authority.")
    else:
        suffix = (("Expired requests remain unperformed.\n" if deadline else "")
                  + "This is a status notice; no decision link is available.\n"
                  + "Receiving it grants no authority.")
    fixed = prefix + suffix
    available = max(0, MAX_NOTIFICATION_CHARACTERS - len(fixed.format(reason="")))
    short_reason = reason[:available].rstrip()
    if len(reason) > len(short_reason) and available > 1:
        short_reason = short_reason[:-1].rstrip() + "…"
    message = fixed.format(reason=short_reason)
    if len(message) > MAX_NOTIFICATION_CHARACTERS:
        raise ValueError("Rider notification projection exceeds its transport-safe bound")
    notification, _ = store.create_once(kind="needs_tanner",
        campaign_id=record["campaign_id"], state_key=state_key,
        message=message,
        evidence_refs=[{"reference_type": "development_campaign",
                        "reference_id": record["campaign_id"],
                        "record_sha256": record["record_sha256"]}])
    active = registry if registry is not None else configured_attention_transports()
    return active.dispatch(notification, store)["notification"] if active._transports else notification


def retain_campaign_terminal_notification(record, *, root=None, registry=None, environment=None):
    """Send one body-free completion/failure status notice, never authority."""
    status = record.get("status")
    if status not in {"succeeded", "cancelled", "failed_safe"}:
        return None
    campaign_id = sanitize_action(record.get("campaign_id"))[:160]
    state_revision = str(record.get("state_revision", "unknown"))
    outcome = "completed successfully" if status == "succeeded" else "stopped safely"
    message = (f"Campaign: {campaign_id}\nFawkes {outcome}.\n"
               f"Status: {status}; revision: {state_revision}.\n"
               "This notice contains no source body, prompt, secret, or authority.")
    store = RiderNotificationStore(record["instance_id"], root=root, environment=environment)
    notification, _ = store.create_once(kind="campaign_terminal", campaign_id=campaign_id,
        state_key=f"{status}:{state_revision}", message=message,
        evidence_refs=[{"reference_type": "development_campaign",
                        "reference_id": campaign_id,
                        "record_sha256": record.get("record_sha256")}])
    active = registry if registry is not None else configured_attention_transports(environment)
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

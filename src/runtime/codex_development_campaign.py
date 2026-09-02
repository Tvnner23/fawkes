"""One bounded Fawkes-coordinated CODEX (REPO) builder/reviewer campaign.

This is durable coordination state over Development and Worker Exchange. It is
not a scheduler, worker registry, authority source, or general orchestrator.
"""

from datetime import datetime, timezone
from pathlib import Path
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
from src.runtime.autonomy_supervision import campaign_activity_projection, retain_needs_tanner_notification
from src.runtime.development_attention import DevelopmentAttentionStore


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
        with _lock(path):
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
            temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(path)
            return value


class CodexDevelopmentCampaign:
    """Deterministic coordinator for one fixed builder and reviewer slot."""

    def __init__(self, instance_id, *, root=None, exchange=None, builder_runner=None,
                 builder_modes=None, attention_store=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.store = DevelopmentCampaignStore(instance_id, root=root)
        self.supervision_root = (Path(root).parent / "component_supervision"
                                 if root is not None else None)
        self.exchange = exchange or WorkerExchange(instance_id)
        self.builder_runner = builder_runner or self._run_promoted_builder
        self.builder_modes = set(builder_modes or {"read_only", "repository_write"})
        self.attention_store = attention_store or DevelopmentAttentionStore()
        if not self.builder_modes <= BUILDER_MODES:
            raise ValueError("invalid builder execution mode")

    def _run_promoted_builder(self, payload):
        return run_codex_development_handoff(instance_id=self.instance_id, payload=payload,
            authenticated_rider=True, exchange=self.exchange,
            approval_handler=self._handle_typed_approval)

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
        result = self.attention_store.wait_for_decision(
            attention_id, timeout_seconds=timeout_seconds, process_alive=process_alive)
        decision = result["decision"]
        def claim(continuation_id=None):
            return self.attention_store.consume_approve_once(
                decision["decision_id"], attention_id=attention_id,
                invocation_id=approval["invocation_id"],
                protocol_binding_sha256=result["event"].get("protocol_binding_sha256"),
                approved_action_sha256=approval["protocol"]["approved_action_sha256"],
                continuation_id=continuation_id)
        def reserve(continuation_id):
            return self.attention_store.reserve_detached_continuation(
                decision["decision_id"], attention_id=attention_id,
                invocation_id=approval["invocation_id"],
                protocol_binding_sha256=result["event"].get("protocol_binding_sha256"),
                continuation_id=continuation_id)
        def finish(continuation_id, status):
            return self.attention_store.finish_detached_continuation(
                decision["decision_id"], continuation_id, status=status)
        def complete(status):
            return self.attention_store.finish_live_action(decision["decision_id"], status=status)
        return {"choice": decision["choice"], "attention_id": attention_id,
                "decision_id": decision["decision_id"], "claim": claim,
                "reserve": reserve, "finish": finish, "complete": complete}

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

    def create(self, payload, *, authenticated_rider):
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
        created = _now()
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
            "validation_commands": _validation_commands(payload.get("validation_commands", [])),
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
            "updated_at": created,
            "events": [self._event("campaign_created", {"authorization_reference": authorization_reference})],
        }
        record = self.store.write(record)
        return self._start_builder(record, correction=None)

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
        event = self.attention_store.create(
            campaign_id=campaign_id, invocation_id=invocation_id, worker=worker,
            kind=kind, blocked_action=blocked_action, why_required=why_required,
            requested_authority=requested_authority, resources=resources,
            reversible=reversible, provider_code=provider_code,
            protocol_binding=protocol_binding, expires_in_seconds=expires_in_seconds,
            expiration_reason=expiration_reason, expiration_effect=expiration_effect,
            can_request_again=can_request_again, work_lost=work_lost)
        needs = {"urgency": "urgent_blocking_flow", "reason": kind,
                 "decision_needed": "Approve this exact action once, deny it, or cancel the campaign",
                 "attention_id": event["attention_id"], "invocation_id": invocation_id,
                 "detail_url": event["detail_url"],
                 "urgency": event["urgency"], "expires_at": event["expires_at"],
                 "expiration_reason": event["expiration_reason"],
                 "expiration_effect": event["expiration_effect"],
                 "can_request_again": event["can_request_again"], "work_lost": event["work_lost"],
                 "worker_id": worker["worker_id"], "requested_authority": event["requested_authority"]}
        return self._update(record, event_kind="tanner_attention_required",
            event_detail={"attention_id": event["attention_id"], "invocation_id": invocation_id,
                          "worker_id": worker["worker_id"], "kind": kind},
            status="tanner_escalation", needs_tanner=needs,
            attention_event_ids=[*record.get("attention_event_ids", []), event["attention_id"]])

    def decide_attention(self, campaign_id, attention_id, choice, *, authenticated_rider):
        record = self.store.load(campaign_id)
        if (record.get("needs_tanner") or {}).get("attention_id") != attention_id:
            raise PermissionError("attention decision is not bound to this campaign state")
        result = self.attention_store.decide(
            attention_id, choice, authenticated_rider=authenticated_rider)
        if choice == "cancel_campaign":
            return {"campaign": self.cancel(campaign_id, authenticated_rider=True), **result}
        # Approval is retained as one consumable grant. It does not automatically
        # resume an ephemeral process or broaden the campaign scope.
        updated = self._update(record, event_kind=f"tanner_attention_{choice}",
            event_detail={"attention_id": attention_id, "decision_id": result["decision"]["decision_id"]},
            status="ready_for_bounded_continuation" if choice == "approve_once" else "failed_safe",
            needs_tanner=None)
        return {"campaign": updated, **result}

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
            "acceptance_condition_ids": record["acceptance_condition_ids"]}
        try:
            result = self.builder_runner(payload)
        except Exception as exc:
            result = {"presentation": {"status": "failed", "failure": {
                "code": type(exc).__name__, "detail": str(exc)}, "return_report_id": None},
                "transport_result": {"status": "failed"}}
        cache_after = _cleanup_python_cache(record["allowed_scope"])
        current = self.store.load(record["campaign_id"])
        presentation = result.get("presentation") if isinstance(result, dict) else None
        transport_result = result.get("transport_result") if isinstance(result, dict) else None
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
            "validation_evidence": self._run_validation(record["validation_commands"]),
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
        if run["status"] == "completed" and run["return_report_id"] and run["package_id"] and run["source_report_id"]:
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
                    provider_code=attention.get("provider_code"))
            return self._update(current, event_kind="builder_failed_safe", status="failed_safe",
                builder_runs=runs, active_builder_task_scope_id=None,
                cache_lifecycle_events=cache_events,
                needs_tanner={"urgency": "urgent_blocking_flow", "reason": "builder_transport_or_return_failed",
                              "failure_code": failure_code,
                              "decision_needed": "inspect failure evidence or use manual fallback"})
        return self._update(current, event_kind="builder_return_retained", status="awaiting_independent_review",
            builder_runs=runs, active_builder_task_scope_id=None, cache_lifecycle_events=cache_events,
            event_detail={"iteration": next_iteration, "return_report_id": run["return_report_id"]})

    @staticmethod
    def _run_validation(commands):
        evidence = []
        environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for argv in commands:
            completed = subprocess.run(argv, cwd=ROOT, env=environment, capture_output=True,
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
        satisfied = list(dict.fromkeys(review.get("acceptance_condition_ids_satisfied", ())))
        if any(item not in record["acceptance_condition_ids"] for item in satisfied):
            raise ValueError("review references an unknown acceptance condition")
        violated = list(dict.fromkeys(review.get("violated_acceptance_condition_ids", ())))
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
        if status == "correction_required" and not normalized_defects:
            raise ValueError("correction_required needs scoped defects")
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
        reviews = [*record["reviews"], review_record]
        record = self._update(record, event_kind="independent_review_retained",
            event_detail={"iteration": record["iteration"], "status": status,
                          "review_report_id": report["report_id"]},
            reviews=reviews, acceptance_satisfied=satisfied,
            reviewer_requirement={**record["reviewer_requirement"], "worker_id": reviewer_id,
                                  "transport_binding": "verified_for_recorded_review"})
        all_satisfied = set(satisfied) == set(record["acceptance_condition_ids"])
        if status == "pass" and all_satisfied:
            return self._update(record, event_kind="campaign_succeeded", status="succeeded", needs_tanner=None)
        if status == "pass_with_caveats" and all_satisfied and not violated:
            return self._update(record, event_kind="campaign_succeeded_with_nonblocking_caveats",
                                status="succeeded", needs_tanner=None)
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
        return self._start_builder(record, correction=review_record)

    def run_wsl_review(self, campaign_id, *, adapter=None):
        """Review through the promoted default WSL formal-review binding."""
        record = self.store.load(campaign_id)
        if record["status"] != "awaiting_independent_review" or record["cancelled"]:
            raise RuntimeError("campaign is not awaiting independent review")
        from src.runtime.wsl_codex_reviewer import (
            WSL_REVIEWER_REFERENCE, WslCodexReviewAdapter, prepare_wsl_review_package,
        )
        with DisposableVerifierWorkspace(ROOT) as snapshot:
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
            except Exception as exc:
                current = self.store.load(campaign_id)
                attempt = {"iteration": record["iteration"], "package_id": prepared["package_id"],
                    "invocation_id": None, "status": "transport_exception", "consumed": False,
                    "actual_process_invocation": False, "failure_code": type(exc).__name__, "created_at": _now()}
                return self._update(current, event_kind="wsl_review_transport_exception",
                    event_detail={"failure_code": type(exc).__name__}, status="failed_safe",
                    review_transport_attempts=[*current.get("review_transport_attempts", []), attempt],
                    needs_tanner={"urgency": "urgent_blocking_flow", "reason": "wsl_review_transport_failed",
                                  "decision_needed": "inspect exact failure evidence or stop campaign"})
            snapshot.verify_source_unchanged()
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
            try: evidence_reference = require_id(item.get("evidence_reference"), "evidence_reference")
            except ValueError: evidence_reference = result["return_report_id"]
            defects.append({**item, "evidence_reference": evidence_reference})
        review = {"status": result["review_status"], "review_report_id": result["return_report_id"],
            "delivery_receipt_id": result["delivery_receipt_id"],
            "verification_receipt_id": result["verification_receipt_id"],
            "acceptance_condition_ids_satisfied": result["acceptance_condition_ids_satisfied"],
            "violated_acceptance_condition_ids": result["violated_acceptance_condition_ids"],
            "defects": defects, "correctable_within_scope": result["correctable_within_scope"]}
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
            "delivery_receipt_id": result["delivery_receipt_id"],
            "verification_receipt_id": result["verification_receipt_id"],
            "acceptance_condition_ids_satisfied": result["acceptance_condition_ids_satisfied"],
            "violated_acceptance_condition_ids": result["violated_acceptance_condition_ids"],
            "defects": defects, "correctable_within_scope": result["correctable_within_scope"]}
        consumed = self.consume_review(campaign_id, review, reviewer=WINDOWS_CODEX_WORKER_REFERENCE,
                                       transport_verified=True)
        attempts = list(consumed.get("review_transport_attempts", []))
        attempts[-1] = {**attempts[-1], "consumed": True,
                        "review_report_id": result["return_report_id"]}
        return self._update(consumed, event_kind="windows_review_attempt_consumed",
                            review_transport_attempts=attempts)

    def run_to_terminal(self, campaign_id, *, reviewer_adapter=None):
        """Advance this fixed campaign through the promoted default reviewer."""
        record = self.store.load(campaign_id)
        while record["status"] == "awaiting_independent_review":
            record = self.run_wsl_review(campaign_id, adapter=reviewer_adapter)
        return record

    def cancel(self, campaign_id, *, authenticated_rider):
        if authenticated_rider is not True:
            raise PermissionError("authenticated rider authority is required")
        record = self.store.load(campaign_id)
        if record["status"] == "cancelled":
            return record
        if record["status"] == "succeeded":
            raise RuntimeError("completed campaign cannot be cancelled")
        return self._update(record, event_kind="rider_cancelled_campaign", status="cancelled",
            cancelled=True, needs_tanner=None, active_builder_task_scope_id=None)

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

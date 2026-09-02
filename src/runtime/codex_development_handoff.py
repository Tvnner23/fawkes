"""Authenticated Development entry for the one promoted Codex repository worker."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import os

from src.library.artifacts import require_id
from src.runtime.codex_worker_adapter import (
    ADAPTER_ID, PROMOTION_RECORD, CodexExecWorkerAdapter,
)
from src.runtime.codex_write_builder_adapter import (
    WRITE_ADAPTER_ID, WRITE_PROMOTION_RECORD, CodexWriteBuilderAdapter,
)
from src.runtime.worker_exchange import WorkerExchange, _digest


ROOT = Path(os.environ.get(
    "FAWKES_DEVELOPMENT_ROOT", Path(__file__).resolve().parent.parent.parent
)).resolve()
CODEX_REPO_TARGET = "codex_repo"
CODEX_REPO_WORKER_REFERENCE = {
    "worker_id": "codex-repository-wsl-fawkes",
    "role": "software_repository",
    "identity_status": "rider_attested",
    "charter_version": "1.0",
}


def resolve_codex_repo_worker(target, *, workspace=ROOT):
    """Resolve one known descriptive target; identified never means authorized."""
    if target != CODEX_REPO_TARGET:
        raise ValueError("target_worker must be the explicit codex_repo worker")
    workspace = Path(workspace).resolve()
    if workspace != ROOT or not (workspace / ".git").exists():
        raise PermissionError("Codex repository worker is bound to the Fawkes workspace")
    return {
        "target": CODEX_REPO_TARGET,
        "worker": dict(CODEX_REPO_WORKER_REFERENCE),
        "environment_id": f"codex-cli:{workspace}",
        "workspace": str(workspace),
        "identified": True,
        "authorized": False,
        "identity_evidence": "rider_attested_role_plus_promoted_local_client_workspace",
    }


def _authority(*, instance_id, task_scope_id, sender_id, authorization_reference,
               expires_at, recipient_id=None, **extra):
    value = {"decision": "authorized", "instance_id": instance_id,
             "task_scope_id": task_scope_id, "sender_worker_id": sender_id,
             "authorization_reference": authorization_reference, "expires_at": expires_at}
    if recipient_id is not None:
        value["recipient_worker_id"] = recipient_id
    value.update(extra)
    return value


def _sections(value):
    if not isinstance(value, list) or not value or len(value) > 8:
        raise ValueError("one to eight exact source sections are required")
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("source sections must be objects")
        content = item.get("content")
        if not isinstance(content, str) or not content or len(content.encode()) > 64_000:
            raise ValueError("source section content is required and bounded")
        normalized.append({"section_id": require_id(item.get("section_id"), "section_id"),
                           "title": str(item.get("title") or item.get("section_id")).strip(),
                           "content": content})
    return normalized


def _presentation(*, target, package, result, exchange):
    delivered = result.get("status") == "delivered"
    verification = (exchange._load("verification_receipts", result["verification_receipt_id"])
                    if delivered and result.get("verification_receipt_id") else None)
    returned = (exchange._load("reports", result["return_report_id"])
                if delivered and result.get("return_report_id") else None)
    sections = list(returned.get("sections", ())) if returned else []
    next_sections = [item for item in sections
                     if item.get("section_id") in {"next-recommendation", "next_recommendation"}]
    return {
        "schema_version": 1,
        "presentation_type": "codex_development_handoff",
        "task_scope_id": package["task_scope_id"],
        "worker": target["worker"],
        "environment_id": target["environment_id"],
        "status": "completed" if delivered else "failed",
        "last_trustworthy_stage": "return_retained" if returned else "delivery_failed",
        "delivered": delivered,
        "verification_status": verification.get("status") if verification else "unverified",
        "caveats": list(verification.get("caveats", ())) if verification else [],
        "disagreement": verification.get("counterclaim") if verification else None,
        "artifact_references": list(returned.get("artifact_references", ())) if returned else [],
        "evidence_references": list(returned.get("evidence_references", ())) if returned else [],
        "return_report_id": returned.get("report_id") if returned else None,
        "exact_return_sections": sections,
        "next_recommendation": next_sections[0] if next_sections else None,
        "failure": ({"code": result.get("failure_reason"), "detail": result.get("failure_detail")}
                    if not delivered else None),
        "attention_request": result.get("attention_request") if not delivered else None,
        "retry_safe": False,
        "automatic_retry_performed": False,
        "manual_fallback_available": True,
        "derived_presentation": True,
        "material_reliance_requires_exact_return_report": True,
        "creates_authority": False,
    }


def run_codex_development_handoff(*, instance_id, payload, authenticated_rider,
                                  workspace=ROOT, exchange=None, adapter=None,
                                  now=None):
    """Prepare, send, retain, and present one explicitly selected Codex task."""
    if authenticated_rider is not True:
        raise PermissionError("authenticated rider authority is required")
    if not isinstance(payload, dict):
        raise ValueError("Development handoff payload is required")
    if payload.get("instance_id") not in {None, instance_id}:
        raise PermissionError("Development handoff belongs to another Phoenix")
    target = resolve_codex_repo_worker(payload.get("target_worker"), workspace=workspace)
    task_scope_id = require_id(payload.get("task_scope_id"), "task_scope_id")
    request_id = require_id(payload.get("rider_request_id"), "rider_request_id")
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip() or len(task.encode()) > 32_000:
        raise ValueError("a bounded Codex task is required")
    if payload.get("explicitly_authorized") is not True:
        raise PermissionError("explicit Codex task authorization is required")
    sections = _sections(payload.get("source_sections"))
    if any(item["section_id"] == "approved-task" for item in sections):
        raise ValueError("approved-task is reserved for the exact authorized task")
    sections = [{"section_id": "approved-task", "title": "Exact approved task",
                 "content": task.strip()}, *sections]
    if len({item["section_id"] for item in sections}) != len(sections):
        raise ValueError("source section identities must be unique")

    exchange = exchange or WorkerExchange(instance_id)
    workspace = Path(workspace).resolve()
    execution_mode = payload.get("execution_mode", "read_only")
    if execution_mode not in {"read_only", "repository_write"}:
        raise ValueError("unsupported CODEX (REPO) execution mode")
    adapter = adapter or (CodexWriteBuilderAdapter(exchange, workspace=workspace)
                          if execution_mode == "repository_write"
                          else CodexExecWorkerAdapter(exchange, workspace=workspace))
    timestamp = now or datetime.now(timezone.utc)
    expires_at = (timestamp + timedelta(minutes=30)).isoformat()
    authorization_reference = f"rider-codex-development-{request_id}"
    sender = {"worker_id": "fawkes-development", "role": "coordination",
              "identity_status": "verified", "charter_version": "1.0"}
    report = exchange.create_report(task_scope_id=task_scope_id, sender=sender,
        authority=_authority(instance_id=instance_id, task_scope_id=task_scope_id,
            sender_id=sender["worker_id"], authorization_reference=authorization_reference,
            expires_at=expires_at), sections=sections, claims=payload.get("claims", ()),
        artifact_references=payload.get("artifact_references", ()),
        evidence_references=payload.get("evidence_references", ()),
        contract_references=payload.get("contract_references", ()),
        recovery_references=payload.get("recovery_references", ()))
    package = exchange.compose_package(report_id=report["report_id"], recipient=target["worker"],
        authority=_authority(instance_id=instance_id, task_scope_id=task_scope_id,
            sender_id=sender["worker_id"], recipient_id=target["worker"]["worker_id"],
            authorization_reference=authorization_reference, expires_at=expires_at),
        included_section_ids=[item["section_id"] for item in sections])
    task_text = task.strip()
    transport = _authority(instance_id=instance_id, task_scope_id=task_scope_id,
        sender_id=sender["worker_id"], recipient_id=target["worker"]["worker_id"],
        authorization_reference=authorization_reference, expires_at=expires_at)
    if execution_mode == "repository_write":
        allowed_scope = payload.get("allowed_scope")
        conditions = payload.get("acceptance_condition_ids")
        campaign_id = require_id(payload.get("campaign_id"), "campaign_id")
        iteration = payload.get("iteration")
        recovery = payload.get("recovery_references")
        transport.update({"adapter_id": WRITE_ADAPTER_ID, "package_id": package["package_id"],
            "recipient_environment_id": target["environment_id"],
            "write_task_sha256": hashlib.sha256(task_text.encode()).hexdigest(),
            "adapter_promotion_reference": WRITE_PROMOTION_RECORD["promotion_id"],
            "campaign_id": campaign_id, "iteration": iteration,
            "allowed_scope_sha256": _digest(allowed_scope),
            "acceptance_condition_ids_sha256": _digest(conditions),
            "recovery_references_sha256": _digest(recovery)})
    else:
        transport.update({"adapter_id": ADAPTER_ID, "package_id": package["package_id"],
            "recipient_environment_id": target["environment_id"],
            "read_only_task_sha256": hashlib.sha256(task_text.encode()).hexdigest(),
            "adapter_promotion_reference": PROMOTION_RECORD["promotion_id"]})
    returned_authority = _authority(instance_id=instance_id, task_scope_id=task_scope_id,
        sender_id=target["worker"]["worker_id"], authorization_reference=authorization_reference,
        expires_at=expires_at)
    try:
        arguments = {"package_id": package["package_id"], "transport_authority": transport,
            "return_authority": returned_authority, "recipient_environment_id": target["environment_id"]}
        if execution_mode == "repository_write":
            arguments.update({"write_task": task_text, "campaign_id": campaign_id,
                "iteration": iteration, "allowed_scope": allowed_scope,
                "acceptance_condition_ids": conditions, "recovery_references": recovery})
        else:
            arguments["read_only_task"] = task_text
        result = adapter.deliver_production_once(**arguments)
    except (PermissionError, RuntimeError, ValueError, OSError) as exc:
        result = {"status": "failed", "failure_reason": type(exc).__name__,
                  "failure_detail": str(exc), "delivered": False,
                  "manual_transfer_retirement_eligible": False, "creates_authority": False}
    return {"instance_id": instance_id, "task_scope_id": task_scope_id,
            "target": target, "source_report_id": report["report_id"],
            "package_id": package["package_id"], "authorization_reference": authorization_reference,
            "transport_result": result,
            "presentation": _presentation(target=target, package=package, result=result, exchange=exchange)}

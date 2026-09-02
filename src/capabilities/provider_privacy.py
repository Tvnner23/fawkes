"""Append-only receipts for authorized external-provider media transmission."""

from pathlib import Path
import hashlib
import json
import uuid

from src.library.artifacts import (
    PRIVACY_CLASSES, require_id, source_artifact_envelope, stable_work_id, utc_now,
)


ROOT = Path(__file__).resolve().parent.parent.parent
RECEIPTS_DIR = ROOT / "database" / "provider_transmission_receipts"


def ephemeral_provider_artifact(*, instance_id, content, artifact_kind,
                                source_domain, privacy="potentially_private",
                                owner_principal_id=None):
    """Describe transmitted text without retaining the text itself."""
    if not isinstance(content, str) or not content:
        raise ValueError("provider-bound content is required")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    artifact_id = f"ephemeral:{hashlib.sha256((instance_id + ':' + digest).encode()).hexdigest()}"
    return source_artifact_envelope(
        artifact_id=artifact_id, instance_id=instance_id,
        owner_principal_id=owner_principal_id or f"authenticated-rider:{instance_id}",
        artifact_kind=artifact_kind, source_domain=source_domain,
        evidence_era="native_phoenix_history", sha256=digest,
        media_type="text/plain", storage_reference=None,
        lifecycle_state="transmission_authorized",
        privacy={"classification": privacy, "assigned_by": "runtime",
                 "rider_visible": True, "revisable": True},
        trust="untrusted_user_content",
        retention={"decision": "temporary_only", "automatic_library_retention": False},
        actor={"actor_type": "rider", "principal_id": owner_principal_id or f"authenticated-rider:{instance_id}"},
        resource={"size_bytes": len(content.encode("utf-8")), "quota_class": "provider_request"},
    )


def _write_once(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        stable_fields = ("transmission_id", "instance_id", "artifact_id", "source_sha256",
                         "capability_id", "purpose", "status", "privacy_classification",
                         "eligibility_policy_version", "provider_eligibility_reason")
        if any(existing.get(key) != payload.get(key) for key in stable_fields):
            raise ValueError("provider transmission receipt is immutable")
        return existing
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return payload


def record_provider_transmission(*, instance_id, artifact, capability_id,
                                 provider_class, purpose, authorization_source,
                                 transformations=(), retention_configuration="provider_api_no_application_storage",
                                 status="authorized", result_derivation_id=None,
                                 failure_code=None, receipt_dir=None,
                                 correlation_id=None, causation_id=None,
                                 eligibility_decision=None):
    """Record metadata only: never payloads, credentials, or provider secrets."""
    require_id(instance_id, "instance_id")
    require_id(capability_id, "capability_id")
    if not isinstance(artifact, dict) or artifact.get("instance_id") != instance_id:
        raise ValueError("provider artifact ownership does not match Phoenix instance")
    original = artifact.get("original_source", {})
    privacy = artifact.get("privacy", {}).get("classification")
    if privacy not in PRIVACY_CLASSES:
        raise ValueError("provider transmission requires privacy classification")
    if not isinstance(authorization_source, dict) or not authorization_source.get("mode"):
        raise ValueError("provider transmission requires authorization source")
    if eligibility_decision is not None:
        provider_decision = (eligibility_decision.get("provider_transmission", {})
                             if isinstance(eligibility_decision, dict) else {})
        if provider_decision.get("allowed") is not True:
            raise PermissionError("provider_transmission_denied")
    transmission_id = stable_work_id(
        "provider-transmission", instance_id, artifact.get("artifact_id"), capability_id,
        purpose, correlation_id or causation_id or "unscoped",
    )
    receipt_id = stable_work_id("provider-transmission-receipt", transmission_id, status)
    payload = {
        "schema_version": 1, "record_type": "provider_transmission_receipt",
        "receipt_id": receipt_id, "transmission_id": transmission_id, "instance_id": instance_id,
        "artifact_id": artifact.get("artifact_id"),
        "source_sha256": original.get("sha256"), "media_type": original.get("media_type"),
        "capability_id": capability_id, "provider_class": str(provider_class),
        "purpose": str(purpose), "authorization_source": dict(authorization_source),
        "privacy_classification": privacy, "transformations": list(transformations),
        "eligibility_policy_version": (eligibility_decision.get("policy_version")
                                       if isinstance(eligibility_decision, dict) else None),
        "provider_eligibility_reason": (eligibility_decision.get("provider_transmission", {}).get("reason")
                                        if isinstance(eligibility_decision, dict) else None),
        "transmitted_at": utc_now(), "known_retention_configuration": retention_configuration,
        "result_derivation_id": result_derivation_id, "status": status,
        "failure_code": failure_code, "correlation_id": correlation_id,
        "causation_id": causation_id,
        "provenance": [{"relation": "transmitted_to_provider", "target_kind": "provider_class",
                        "target_id": str(provider_class)}],
        "payload_recorded": False, "credential_material_recorded": False,
    }
    root = Path(receipt_dir) if receipt_dir else RECEIPTS_DIR
    directory = root / instance_id / hashlib.sha256(transmission_id.encode()).hexdigest()
    filename = hashlib.sha256(receipt_id.encode()).hexdigest() + ".json"
    return _write_once(directory / filename, payload)

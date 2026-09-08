"""Versioned Phoenix source-artifact and lifecycle contracts.

This module describes evidence and authority.  It does not make temporary
media durable, grant provider access, or promote source material into Memory.
"""

from datetime import datetime, timezone
import hashlib
import json
import re
import uuid


SCHEMA_VERSION = 1
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
EVIDENCE_ERAS = {"native_phoenix_history", "inherited_history", "external_source"}
TRUST_CLASSES = {
    "untrusted_user_content", "untrusted_library_content", "untrusted_external_content",
    "system_generated_derived", "rider_attested",
}
PRIVACY_CLASSES = {"standard", "potentially_private", "highly_private", "restricted"}
LIFECYCLE_STATES = {
    "received_temporary", "validated_temporary", "privacy_classified",
    "transmission_authorized", "temporary_processed", "retention_requested",
    "durable_registered", "extraction_pending", "searchable", "failed",
    "quarantined", "superseded", "suppressed", "active_removed",
    "derived_deleted", "original_destroyed",
}
LIFECYCLE_TRANSITIONS = {
    "received_temporary": {"validated_temporary", "failed", "quarantined"},
    "validated_temporary": {"privacy_classified", "transmission_authorized", "retention_requested", "failed", "quarantined"},
    "privacy_classified": {"transmission_authorized", "retention_requested", "failed", "quarantined"},
    "transmission_authorized": {"temporary_processed", "failed"},
    "temporary_processed": {"retention_requested", "derived_deleted"},
    "retention_requested": {"durable_registered", "failed", "quarantined"},
    "durable_registered": {"extraction_pending", "superseded", "suppressed", "active_removed"},
    "extraction_pending": {"searchable", "failed", "quarantined"},
    "searchable": {"superseded", "suppressed", "active_removed", "derived_deleted"},
    "failed": {"validated_temporary", "retention_requested", "extraction_pending", "quarantined"},
    "quarantined": {"validated_temporary", "retention_requested", "suppressed"},
    "superseded": {"suppressed", "active_removed"},
    "suppressed": {"active_removed"}, "active_removed": {"original_destroyed"},
    "derived_deleted": {"extraction_pending", "active_removed"}, "original_destroyed": set(),
}
LINEAGE_RELATIONS = {
    "derived_from", "extracted_from", "summarizes", "quotes", "supports",
    "contradicts", "supersedes", "references", "imported_from",
    "transmitted_to_provider", "produced_by", "approved_by", "tested_by",
}
RETENTION_DECISIONS = {"keep_in_library"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def require_id(value, name):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError(f"valid {name} is required")
    return value


def stable_work_id(kind, *parts):
    require_id(kind, "work kind")
    encoded = json.dumps([kind, *parts], sort_keys=True, ensure_ascii=False).encode("utf-8")
    return f"work:{kind}:{hashlib.sha256(encoded).hexdigest()}"


def retention_intent(*, actor_type, principal_id, consent_context_id=None,
                     policy_id=None, requested_at=None):
    """Create explicit authority evidence for a durable retention request."""
    if actor_type not in {"rider", "phoenix", "developer", "runtime", "import", "workflow"}:
        raise ValueError("unsupported retention actor_type")
    require_id(principal_id, "principal_id")
    if consent_context_id is not None:
        require_id(consent_context_id, "consent_context_id")
    if policy_id is not None:
        require_id(policy_id, "policy_id")
    return {
        "decision": "keep_in_library", "actor_type": actor_type,
        "principal_id": principal_id, "consent_context_id": consent_context_id,
        "policy_id": policy_id, "requested_at": requested_at or utc_now(),
    }


def validate_retention_intent(value):
    if not isinstance(value, dict) or value.get("decision") not in RETENTION_DECISIONS:
        raise ValueError("explicit Keep in Library retention_intent is required")
    require_id(value.get("principal_id"), "retention principal_id")
    if value.get("actor_type") not in {"rider", "phoenix", "developer", "runtime", "import", "workflow"}:
        raise ValueError("retention actor_type is required")
    return dict(value)


def lineage_edge(relation, target_id, *, target_kind="artifact"):
    if relation not in LINEAGE_RELATIONS:
        raise ValueError("unknown provenance relation")
    require_id(target_id, "provenance target_id")
    return {"relation": relation, "target_kind": str(target_kind), "target_id": target_id}


def source_artifact_envelope(*, artifact_id, instance_id, owner_principal_id,
                             artifact_kind, source_domain, evidence_era,
                             sha256, media_type, storage_reference,
                             lifecycle_state, privacy, trust,
                             retention, actor, provenance=(), rights=None,
                             resource=None, encryption=None, identifiers=None,
                             created_at=None, event_time=None):
    require_id(artifact_id, "artifact_id")
    require_id(instance_id, "instance_id")
    require_id(owner_principal_id, "owner_principal_id")
    if evidence_era not in EVIDENCE_ERAS:
        raise ValueError("invalid evidence era")
    if lifecycle_state not in LIFECYCLE_STATES:
        raise ValueError("invalid artifact lifecycle state")
    if trust not in TRUST_CLASSES:
        raise ValueError("invalid artifact trust class")
    privacy_class = privacy.get("classification") if isinstance(privacy, dict) else None
    if privacy_class not in PRIVACY_CLASSES:
        raise ValueError("invalid artifact privacy classification")
    if not re.fullmatch(r"[0-9a-f]{64}", str(sha256)):
        raise ValueError("artifact sha256 is required")
    edges = []
    for edge in provenance:
        if not isinstance(edge, dict) or edge.get("relation") not in LINEAGE_RELATIONS:
            raise ValueError("invalid typed provenance edge")
        require_id(edge.get("target_id"), "provenance target_id")
        edges.append(dict(edge))
    encryption = dict(encryption or {"state": "not_configured", "scheme_version": None, "key_reference": None})
    for field in ("key_reference", "secret_handle"):
        value = encryption.get(field)
        if value is not None:
            require_id(value, f"opaque {field}")
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "phoenix_source_artifact",
        "artifact_id": artifact_id, "instance_id": instance_id,
        "owner_principal_id": owner_principal_id,
        "artifact_kind": str(artifact_kind), "source_domain": str(source_domain),
        "evidence_era": evidence_era,
        "original_source": {"sha256": sha256, "media_type": str(media_type),
                            "storage_reference": storage_reference},
        "created_at": created_at or utc_now(), "event_time": event_time,
        "privacy": dict(privacy), "trust": trust,
        "lifecycle": {"state": lifecycle_state}, "retention": dict(retention),
        "actor": dict(actor), "subjects": [], "participants": [],
        "consent": {"context_id": retention.get("consent_context_id"),
                    "policy_id": retention.get("policy_id")},
        "rights": dict(rights or {"usage": "rider_private_reference", "restrictions": []}),
        "resource": dict(resource or {}), "safety": {"class": "information_only"},
        "provenance": edges, "encryption": encryption,
        "identifiers": dict(identifiers or {}),
    }


def lifecycle_event(*, instance_id, artifact_id, event_type, from_state,
                    to_state, actor, idempotency_key, correlation_id=None,
                    causation_id=None, details=None):
    require_id(instance_id, "instance_id")
    require_id(artifact_id, "artifact_id")
    require_id(idempotency_key, "idempotency_key")
    if to_state not in LIFECYCLE_STATES or (from_state and from_state not in LIFECYCLE_STATES):
        raise ValueError("invalid lifecycle transition")
    if from_state and to_state not in LIFECYCLE_TRANSITIONS[from_state]:
        raise ValueError(f"disallowed lifecycle transition: {from_state} -> {to_state}")
    event_id = stable_work_id("event", instance_id, artifact_id, event_type, idempotency_key)
    return {
        "schema_version": 1, "record_type": "artifact_lifecycle_event",
        "event_id": event_id, "instance_id": instance_id, "artifact_id": artifact_id,
        "event_type": event_type, "from_state": from_state, "to_state": to_state,
        "actor": dict(actor), "idempotency_key": idempotency_key,
        "correlation_id": correlation_id, "causation_id": causation_id,
        "details": dict(details or {}), "occurred_at": utc_now(),
    }

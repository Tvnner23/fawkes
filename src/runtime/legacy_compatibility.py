"""Non-destructive eligibility projection for legacy Archive/Memory evidence."""

import hashlib
import json

from src.library.artifacts import require_id
from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract

COMPATIBILITY_VERSION = "legacy-private-compatibility-v1"
DERIVED_CLASSIFICATION = "legacy_private_unclassified"
LEGACY_DOMAINS = {"native_archive", "memory"}
OWNERSHIP_BASES = {"scoped_instance_record", "scoped_conversation_registry_and_archive_reference",
                   "scoped_memory_source_archive_chain"}
BLOCKING_FLAGS = {"foreign", "shared", "restricted", "synthetic_inappropriate", "revoked",
                  "quarantined", "suppressed", "unauthorized", "ownership_conflict"}

LEGACY_COMPATIBILITY_DEFINITION = CapabilityDefinition(
    name="retrieval.legacy_compatibility", version="1.0",
    display_name="Legacy Evidence Compatibility Review",
    description="Derive private-context compatibility and a rebuildable review projection without rewriting legacy Archive or Memory.",
    effect="read_only_derived_eligibility_and_review_projection",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read",), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="metadata_only_no_legacy_evidence_body_in_review_projection",
    features=("non_destructive_compatibility", "explicit_metadata_precedence", "ownership_provenance_gate", "rebuildable_review_projection"),
    appropriate_use=("preserve same-Phoenix legacy continuity in private context", "inventory legacy metadata debt for rider review"),
    inappropriate_use=("canonical privacy backfill", "external disclosure", "cross-principal access", "provider bypass"),
    limitations=("served planner integration still requires request-scoped eligibility and exact provider permits; legacy compatibility grants neither", "review projection has no classification-write workflow"),
    platform_support=("server", "provider_neutral", "platform_independent"),
    presentation_options=("text",),
    dependencies=("scoped Phoenix provenance", "authenticated primary rider"),
    provenance_requirements=("source evidence reference", "source schema status", "continuity ownership basis", "compatibility version"),
)


def derive_legacy_compatibility(evidence, *, instance_id, rider_principal_id):
    require_id(instance_id, "instance_id"); require_id(rider_principal_id, "rider_principal_id")
    if not isinstance(evidence, dict): return _result(None, None, "blocked", "provenance_invalid")
    domain, evidence_id = evidence.get("domain"), evidence.get("evidence_id")
    if domain not in LEGACY_DOMAINS:
        return _result(domain, evidence_id, "blocked", "legacy_domain_not_supported")
    if evidence.get("privacy_classification") is not None or evidence.get("owner_principal_id") is not None:
        return _result(domain, evidence_id, "explicit_classification_present", "explicit_modern_metadata_wins", explicit=True)
    if evidence.get("instance_id") != instance_id:
        return _result(domain, evidence_id, "ownership_uncertain", "foreign_phoenix")
    if evidence.get("provenance_valid") is not True or not isinstance(evidence.get("original_evidence_reference"), dict) or not evidence.get("original_evidence_reference"):
        return _result(domain, evidence_id, "blocked", "provenance_invalid")
    basis = evidence.get("continuity_ownership_basis")
    if basis not in OWNERSHIP_BASES:
        return _result(domain, evidence_id, "ownership_uncertain", "ownership_uncertain")
    blocked = sorted(set(evidence.get("eligibility_flags") or ()) & BLOCKING_FLAGS)
    if blocked:
        return _result(domain, evidence_id, "blocked", "explicit_ineligible_state", basis=basis, flags=blocked)
    schema = evidence.get("source_schema_version")
    if not isinstance(schema, int) or schema < 1:
        return _result(domain, evidence_id, "needs_review", "legacy_schema_unknown", basis=basis)
    return _result(domain, evidence_id, "compatibility_eligible", "same_phoenix_legacy_private_continuity",
                   basis=basis, source_schema_version=schema, rider_principal_id=rider_principal_id)


def apply_legacy_compatibility(evidence, compatibility):
    projected = dict(evidence)
    if compatibility.get("migration_status") == "compatibility_eligible":
        projected["owner_principal_id"] = compatibility["derived_owner_principal_id"]
        projected["legacy_compatibility"] = compatibility
    return projected


def build_legacy_review_projection(evidence_records, *, instance_id, rider_principal_id):
    items = []
    for evidence in evidence_records:
        decision = derive_legacy_compatibility(evidence, instance_id=instance_id,
                                               rider_principal_id=rider_principal_id)
        items.append({key: decision.get(key) for key in ("source_domain", "evidence_id",
            "migration_status", "reason", "source_schema_version", "explicit_modern_classification",
            "ownership_provenance_basis", "review_status")})
    counts = {}
    for item in items: counts[item["migration_status"]] = counts.get(item["migration_status"], 0) + 1
    payload = {"schema_version": 1, "record_type": "legacy_evidence_review_projection",
        "projection_version": COMPATIBILITY_VERSION, "instance_id": instance_id,
        "rider_principal_id": rider_principal_id, "derived": True, "rebuildable": True,
        "canonical_records_modified": False, "summary": counts, "items": items,
        "sensitive_content_logged": False}
    payload["projection_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return payload


def _result(domain, evidence_id, status, reason, *, explicit=False, basis=None, flags=(),
            source_schema_version=None, rider_principal_id=None):
    return {"schema_version": 1, "record_type": "legacy_compatibility_decision",
        "compatibility_version": COMPATIBILITY_VERSION,
        "derived_compatibility_classification": DERIVED_CLASSIFICATION if status == "compatibility_eligible" else None,
        "source_domain": domain, "evidence_id": evidence_id, "source_schema_version": source_schema_version,
        "original_metadata_status": "explicit_modern" if explicit else "legacy_missing_modern_privacy_owner",
        "explicit_modern_classification": explicit, "migration_status": status,
        "review_status": "not_reviewed", "reason": reason, "ownership_provenance_basis": basis,
        "blocking_flags": list(flags), "derived_owner_principal_id": rider_principal_id if status == "compatibility_eligible" else None,
        "canonical_record_modified": False, "sensitive_content_logged": False}

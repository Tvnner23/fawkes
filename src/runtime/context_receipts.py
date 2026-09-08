"""Durable audit receipts for the context supplied to live responses."""

from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

from src.runtime.context_composer import sanitize_composition_audit
from src.capabilities.core import CapabilityDefinition


ROOT = Path(__file__).resolve().parent.parent.parent
CONTEXT_RECEIPTS_DIR = ROOT / "database" / "context_receipts"

CONTEXT_INSPECTOR_DEFINITION = CapabilityDefinition(
    name="context.inspect", version="1.0",
    display_name="Context Inspector",
    description="Inspect body-free composition and authorization evidence for an existing response.",
    permissions=("context.read_authorized",), effect="read_only",
    privacy_handling="instance-scoped body-free receipt and Replay projection",
    features=("composition_summary", "allocation_observability", "permit_status",
              "receipt_replay_linkage", "zero_retrieval_observability"),
    appropriate_use=("explain how an already-completed response context was assembled",),
    inappropriate_use=("trigger retrieval", "view evidence bodies", "grant authority", "change evidence selection"),
    limitations=("shows recorded body-free evidence only", "does not independently judge response quality"),
    dependencies=("context receipt", "Retrieval Flight Recorder"),
    provenance_requirements=("Phoenix instance", "response message identity", "context package identity"),
)


def _write_json_once(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        comparable_existing = {k: v for k, v in existing.items() if k != "created_at"}
        comparable_payload = {k: v for k, v in payload.items() if k != "created_at"}
        if comparable_existing != comparable_payload:
            raise ValueError("context receipt ID already exists with different data")
        return existing
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
    return payload


def save_context_receipt(
    *,
    instance_id,
    conversation_id,
    request_message_id,
    response_message_id,
    model,
    memories=(),
    archive_passages=(),
    conversation_context=(),
    response_archive_id=None,
    development_sources=(),
    research_sources=(),
    library_sources=(),
    media_sources=(),
    presentation=None,
    retrieval_audit=None,
    path=None,
):
    """Persist the exact source references supplied for one response."""
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            instance_id,
            conversation_id,
            request_message_id,
            response_message_id,
            model,
        )
    ):
        raise ValueError("context receipt identifiers and model are required")

    receipt = {
        "schema_version": 7,
        "receipt_id": response_message_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "instance_id": instance_id,
        "conversation_id": conversation_id,
        "request_message_id": request_message_id,
        "response_message_id": response_message_id,
        "response_archive_id": response_archive_id,
        "model": model,
        "memory_sources": [
            {
                "memory_id": memory.get("memory_id"),
                "memory_type": memory.get("memory_type"),
                "content": memory.get("content"),
                "source_message_ids": list(memory.get("source_message_ids", ())),
                "source_archive_ids": list(memory.get("source_archive_ids", ())),
                "source_work_item_ids": list(
                    memory.get("source_work_item_ids", ())
                ),
                "authority_class": memory.get("authority_class"),
                "privacy_classification": memory.get("privacy_classification"),
                "eligibility": memory.get("eligibility"),
            }
            for memory in memories
        ],
        "archive_sources": [
            {
                key: passage.get(key)
                for key in (
                    "conversation_id",
                    "message_id",
                    "role",
                    "content",
                    "created_at",
                    "source_archive_id",
                    "canonicalizer_version",
                    "retrieval_score",
                    "matched_terms",
                    "authority_class", "privacy_classification", "eligibility",
                )
            }
            for passage in archive_passages
        ],
        "conversation_sources": [
            {
                key: message.get(key)
                for key in (
                    "conversation_id",
                    "message_id",
                    "role",
                    "content",
                    "created_at",
                    "source_archive_id",
                )
            }
            for message in conversation_context
        ],
        "development_sources": list(development_sources),
        "research_sources": list(research_sources),
        "library_sources": [
            {
                key: passage.get(key)
                for key in (
                    "source_id", "source_title", "source_sha256", "extraction_id",
                    "extractor", "extractor_version", "segment_id", "text",
                    "location", "matched_terms", "retrieval_score", "trust",
                    "authority_class", "privacy_classification", "eligibility",
                )
            }
            for passage in library_sources
        ],
        "media_sources": list(media_sources),
        "presentation": presentation,
        "retrieval_audit": _sanitize_retrieval_audit(retrieval_audit),
    }
    receipt_path = (
        Path(path)
        if path is not None
        else CONTEXT_RECEIPTS_DIR / f"{response_message_id}.json"
    )
    return _write_json_once(receipt_path, receipt)


def _sanitize_retrieval_audit(value):
    """Preserve policy decisions without duplicating excluded evidence text."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("retrieval audit must be an object")
    allowed = {"policy_version", "eligible_domains", "domain_status", "allocation", "continuity_projections", "candidate_generation", "representation_preference", "ambiguity_decision", "clarification_consumption", "context_composition",
               "warnings", "deterministic_replay_input_sha256", "transmission_authorization"}
    result = {key: value[key] for key in allowed if key in value}
    if "context_composition" in result:
        result["context_composition"] = sanitize_composition_audit(result["context_composition"])
    result["exclusions"] = []
    for item in value.get("exclusions", ()):
        if not isinstance(item, dict):
            continue
        result["exclusions"].append({key: item.get(key) for key in (
            "domain", "stage", "reason", "evidence_id", "eligibility") if key in item})
    result["selected_evidence"] = []
    for item in value.get("selected_evidence", ()):
        if not isinstance(item, dict):
            continue
        result["selected_evidence"].append({key: item.get(key) for key in (
            "candidate_id", "evidence_id", "domain", "authority_class",
            "privacy_classification", "original_evidence_reference", "eligibility")
            if key in item})
    return result


def load_context_receipt(response_message_id, *, directory=None):
    root = Path(directory) if directory is not None else CONTEXT_RECEIPTS_DIR
    path = root / f"{response_message_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_context_inspector(receipt, *, flight=None):
    """Project existing body-free evidence into a rider-readable inspection record."""
    if not isinstance(receipt, dict) or not receipt.get("receipt_id"):
        raise ValueError("a context receipt is required")
    audit = receipt.get("retrieval_audit") or {}
    if not isinstance(audit.get("context_composition"), dict):
        raise ValueError("context composition evidence is unavailable")
    composition = sanitize_composition_audit(audit.get("context_composition")) or {}
    allocation = composition.get("allocation") or {}
    summaries = composition.get("source_summary") or []
    selected = list(allocation.get("selected_evidence_ids") or [])
    omitted = list(allocation.get("omitted_evidence_ids") or [])
    domains = {}
    contradiction_ids, ambiguity_ids = set(), set()
    for item in summaries:
        domain = item.get("domain") or "unknown"
        domains[domain] = domains.get(domain, 0) + 1
        contradiction_ids.update(item.get("contradiction_group_ids") or ())
        ambiguity_ids.update(item.get("ambiguity_set_ids") or ())
    transmission = audit.get("transmission_authorization") or {}
    manifest_id = composition.get("transmission_manifest_id") or transmission.get("manifest_id")
    exclusions = [{key: item.get(key) for key in ("evidence_id", "domain", "stage", "reason")
                   if key in item} for item in audit.get("exclusions", ()) if isinstance(item, dict)]
    replay = None
    if flight is not None:
        if (not isinstance(flight, dict) or flight.get("instance_id") != receipt.get("instance_id")
                or flight.get("response_message_id") != receipt.get("response_message_id")
                or flight.get("context_receipt_id") != receipt.get("receipt_id")):
            raise ValueError("context receipt and Replay evidence do not match")
        replay = {key: flight.get(key) for key in ("flight_id", "evidence_sha256", "context_receipt_id")}
    warnings = list((allocation.get("warnings") or ()))
    status = "retrieved_context_used" if selected else "zero_retrieval"
    result = {
        "schema_version": 1, "record_type": "context_inspector_projection",
        "response_message_id": receipt.get("response_message_id"),
        "context_receipt_id": receipt.get("receipt_id"),
        "composition_status": status,
        "purpose_profile": composition.get("purpose_profile") or {},
        "allocation_policy_version": allocation.get("policy_version"),
        "package_id": composition.get("package_id"),
        "input_evidence_ids": list(allocation.get("input_evidence_ids") or []),
        "selected_evidence_ids": selected, "omitted_evidence_ids": omitted,
        "source_domains": domains,
        "allocation": {key: allocation.get(key) for key in
                       ("total_budget", "unit", "per_domain_selected", "per_domain_chars",
                        "tie_break", "contradiction_policy", "decision_sha256") if key in allocation},
        "indicators": {"contradiction_group_ids": sorted(contradiction_ids),
                       "ambiguity_set_ids": sorted(ambiguity_ids),
                       "uncertain_source_count": sum(1 for item in summaries if item.get("uncertainty"))},
        "warnings": warnings, "exclusions": exclusions,
        "transmission": {"status": transmission.get("status") or ("authorized" if manifest_id else "no_retrieved_evidence"),
                         "manifest_id": manifest_id,
                         "authorized_evidence_ids": list(transmission["authorized_evidence_ids"]
                                                         if "authorized_evidence_ids" in transmission else selected),
                         "denied_evidence_ids": list(transmission.get("denied_evidence_ids") or [])},
        "replay": replay, "contains_source_bodies": False,
        "authority": {"creates_authority": False, "retrieval_authority": False,
                      "transmission_authority": False, "mutation_authority": False},
    }
    return result

"""Instance-scoped Retrieval Flight Recorder and side-effect-free Replay Lab.

Flight records are diagnostic evidence about an already completed live turn.
They never replace Archive/context receipts. Replays write only derived
comparison records and cannot append conversation, Memory, or Development.
"""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid

from src.runtime.context_composer import sanitize_composition_audit

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.library.artifacts import require_id


ROOT = Path(__file__).resolve().parent.parent.parent
REPLAY_ROOT = ROOT / "database" / "retrieval_replay"

RETRIEVAL_REPLAY_DEFINITION = CapabilityDefinition(
    name="retrieval.replay", version="1.0",
    display_name="Retrieval Flight Recorder and Replay Lab",
    description="Record live retrieval decisions and compare bounded candidate policies without changing conversation history.",
    effect="diagnostic evidence and derived replay comparisons only",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "create"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="instance_scoped_private_turn_evidence",
    features=("immutable_flight_records", "side_effect_free_replay", "evidence_diff", "reviewed_regression_promotion"),
    appropriate_use=("diagnose retrieval behavior", "compare versioned retrieval candidates"),
    inappropriate_use=("alter ordinary conversation history", "promote failures without review", "claim semantic or response quality from evidence overlap alone"),
    limitations=("current live recorder observes selected evidence and declared policies, not every pre-ranking internal candidate", "response comparison is deterministic text/digest evidence, not an independent semantic judgment"),
    platform_support=("server", "provider_neutral", "platform_independent"),
    presentation_options=("text",),
    dependencies=("context receipt", "canonical Archive response"),
    provenance_requirements=("Phoenix instance", "request and response identity", "component versions", "source evidence identities"),
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_once(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        comparable_existing = {key: value for key, value in existing.items()
                               if key not in {"recorded_at", "created_at"}}
        comparable_payload = {key: value for key, value in payload.items()
                              if key not in {"recorded_at", "created_at"}}
        if comparable_existing != comparable_payload:
            raise ValueError("retrieval evidence identity already exists with different data")
        return existing
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
    return payload


def instance_replay_root(instance_id, *, root=None):
    return (Path(root) if root else REPLAY_ROOT) / require_id(instance_id, "instance_id")


def _evidence_ref(domain, item):
    keys = {
        "memory": ("memory_id", "memory_type", "source_archive_ids"),
        "archive": ("message_id", "conversation_id", "source_archive_id", "retrieval_score"),
        "library": ("source_id", "extraction_id", "segment_id", "retrieval_score"),
        "conversation": ("message_id", "conversation_id", "source_archive_id"),
    }[domain]
    return {"domain": domain, **{key: item.get(key) for key in keys}}


def _planning_ref(item):
    """Flight diagnostics retain decisions and identity, never candidate text."""
    if not isinstance(item, dict):
        return {}
    return {key: item.get(key) for key in (
        "candidate_id", "evidence_id", "domain", "authority_class",
        "privacy_classification", "original_evidence_reference", "adapter_version",
        "projection", "domain_rank", "estimated_chars", "eligibility",
        "native_evidence_identity", "continuity_projection_id", "ambiguity_set_ids",
        "candidate_reference_ambiguity_set_ids", "candidate_generation_reasons",
        "duplicate_relationship", "contradiction_group_ids") if key in item}


def record_live_flight(*, instance_id, conversation_id, request_message_id,
                       response_message_id, response_archive_id, request_text,
                       model, result, context_receipt_id, elapsed_ms=None,
                       root=None):
    """Persist what the runtime actually selected for one completed turn."""
    for value, name in ((conversation_id, "conversation_id"),
                        (request_message_id, "request_message_id"),
                        (response_message_id, "response_message_id"),
                        (response_archive_id, "response_archive_id"),
                        (context_receipt_id, "context_receipt_id"), (model, "model")):
        require_id(value, name)
    if not isinstance(request_text, str):
        raise ValueError("request_text is required")
    selected = []
    for domain, key in (("memory", "memories"), ("archive", "archive_passages"),
                        ("library", "library_passages"), ("conversation", "conversation_context")):
        selected.extend(_evidence_ref(domain, item) for item in result.get(key, ()))
    continuity = result.get("continuity") or {}
    trace = result.get("retrieval_trace") or {}
    response_text = result.get("text") or ""
    payload = {
        "schema_version": 1, "record_type": "retrieval_flight",
        "flight_id": response_message_id, "recorded_at": _now(),
        "instance_id": instance_id, "conversation_id": conversation_id,
        "request_message_id": request_message_id,
        "response_message_id": response_message_id,
        "response_archive_id": response_archive_id,
        "context_receipt_id": context_receipt_id,
        "request": {"text": request_text},
        "capability_selection": trace.get("capability_selection", []),
        "retrieval_plan": trace.get("retrieval_plan", {}),
        "queries": trace.get("queries", []),
        "candidates": [_planning_ref(item) for item in trace.get("candidates", [])],
        "candidate_observability": "selected_and_policy_exclusions_only",
        "selected_evidence": selected,
        "exclusions": trace.get("exclusions", []),
        "context_allocation": trace.get("context_allocation", {}),
        "planner_warnings": trace.get("warnings", []),
        "deterministic_replay_inputs": trace.get("deterministic_replay_inputs"),
        "transmission_authorization": trace.get("transmission_authorization"),
        "context_composition": sanitize_composition_audit(trace.get("context_composition")),
        "continuity": continuity,
        "response": {"text": response_text, "sha256": hashlib.sha256(response_text.encode()).hexdigest()},
        "execution": {"model": model, "latency_ms": elapsed_ms,
                      "usage": _public_usage(result.get("usage")), "warnings": list(result.get("warnings", ()))},
        "ordinary_history_mutated_by_recording": False,
    }
    payload["evidence_sha256"] = _digest({k: v for k, v in payload.items() if k not in {"recorded_at", "evidence_sha256"}})
    path = instance_replay_root(instance_id, root=root) / "flights" / f"{response_message_id}.json"
    return _write_once(path, payload)


def _public_usage(usage):
    if usage is None:
        return None
    if isinstance(usage, dict):
        return {str(k): v for k, v in usage.items() if isinstance(v, (str, int, float, bool, type(None)))}
    result = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, (int, float)):
            result[key] = value
    return result or None


def load_flight(instance_id, flight_id, *, root=None):
    path = instance_replay_root(instance_id, root=root) / "flights" / f"{require_id(flight_id, 'flight_id')}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("instance_id") != instance_id:
        raise ValueError("retrieval flight Phoenix ownership mismatch")
    return record


def replay_flight(*, instance_id, flight_id, candidate_id, candidate_version,
                  runner, root=None):
    """Run an explicitly supplied diagnostic candidate against immutable input.

    The runner receives a detached JSON value. It must return selected_evidence
    and may return response text, latency_ms, cost, and notes.
    """
    require_id(candidate_id, "candidate_id"); require_id(candidate_version, "candidate_version")
    baseline = load_flight(instance_id, flight_id, root=root)
    if baseline is None:
        raise ValueError("retrieval flight was not found")
    detached = json.loads(json.dumps({"request": baseline["request"],
                                      "retrieval_plan": baseline["retrieval_plan"],
                                      "queries": baseline.get("queries", []),
                                      "candidates": baseline.get("candidates", []),
                                      "exclusions": baseline.get("exclusions", []),
                                      "context_allocation": baseline.get("context_allocation", {}),
                                      "deterministic_replay_inputs": baseline.get("deterministic_replay_inputs"),
                                      "transmission_authorization": baseline.get("transmission_authorization"),
                                      "context_composition": baseline.get("context_composition"),
                                      "selected_evidence": baseline["selected_evidence"]}))
    candidate = runner(detached)
    if not isinstance(candidate, dict) or not isinstance(candidate.get("selected_evidence"), list):
        raise ValueError("replay runner must return selected_evidence")
    before = [_digest(item) for item in baseline["selected_evidence"]]
    after = [_digest(item) for item in candidate["selected_evidence"]]
    candidate_text = candidate.get("response_text")
    replay_id = hashlib.sha256(f"{flight_id}\0{candidate_id}\0{candidate_version}".encode()).hexdigest()[:32]
    record = {
        "schema_version": 1, "record_type": "retrieval_replay",
        "replay_id": replay_id, "recorded_at": _now(), "instance_id": instance_id,
        "flight_id": flight_id,
        "candidate": {"candidate_id": candidate_id, "candidate_version": candidate_version},
        "evidence_diff": {"baseline_count": len(before), "candidate_count": len(after),
                          "added": [item for item in after if item not in before],
                          "removed": [item for item in before if item not in after],
                          "order_changed": before != after and set(before) == set(after)},
        "response_diff": {"baseline_sha256": baseline["response"]["sha256"],
                          "candidate_sha256": (hashlib.sha256(candidate_text.encode()).hexdigest()
                                               if isinstance(candidate_text, str) else None),
                          "semantic_quality_assessed": False},
        "execution": {"latency_ms": candidate.get("latency_ms"), "cost": candidate.get("cost"),
                      "notes": candidate.get("notes")},
        "ordinary_history_mutated": False, "status": "completed",
    }
    return _write_once(instance_replay_root(instance_id, root=root) / "replays" / f"{replay_id}.json", record)


def promote_regression(*, instance_id, replay_id, reviewer_principal_id,
                       failure_statement, expected_evidence, root=None):
    """Append a reviewed regression case; never silently infer failure."""
    for value, name in ((replay_id, "replay_id"), (reviewer_principal_id, "reviewer_principal_id")):
        require_id(value, name)
    if not isinstance(failure_statement, str) or not failure_statement.strip():
        raise ValueError("reviewed failure_statement is required")
    replay_path = instance_replay_root(instance_id, root=root) / "replays" / f"{replay_id}.json"
    if not replay_path.exists():
        raise ValueError("replay was not found")
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    if replay.get("instance_id") != instance_id:
        raise ValueError("replay Phoenix ownership mismatch")
    case_id = hashlib.sha256(f"{instance_id}\0{replay_id}\0{failure_statement.strip()}".encode()).hexdigest()[:32]
    record = {"schema_version": 1, "record_type": "retrieval_regression_case",
              "case_id": case_id, "created_at": _now(), "instance_id": instance_id,
              "source_replay_id": replay_id, "reviewer_principal_id": reviewer_principal_id,
              "failure_statement": failure_statement.strip(),
              "expected_evidence": list(expected_evidence), "status": "active",
              "automatic_promotion": False}
    return _write_once(instance_replay_root(instance_id, root=root) / "regressions" / f"{case_id}.json", record)

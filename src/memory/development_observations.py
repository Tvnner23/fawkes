"""Instance-scoped, provenance-first observations of Phoenix development.

Observations are evidence and interpretation, never executable personality
state. This module deliberately has no dependency on chat prompting, Memory
retrieval, development proposals, or developer-review application.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

from src.capture.canonical import canonical_messages


ROOT = Path(__file__).resolve().parent.parent.parent
OBSERVATION_DIR = ROOT / "memory" / "development" / "observations"
RECORDS_DIR = OBSERVATION_DIR / "records"
EVENTS_DIR = OBSERVATION_DIR / "events"

OBSERVATION_CATEGORIES = {
    # A witnessed output pattern. Recording it makes no claim that it is a
    # Phoenix tendency, desired development, or personality trait.
    "observed_response_pattern",
    "phoenix_behavior",
    "relationship_development",
    "system_defect",
    "base_phoenix_candidate",
    # An interaction signal, not a personality dimension or defect verdict.
    "correction_signal",
}
OBSERVATION_STATUSES = {"tentative", "emerging", "contested", "closed"}
EVIDENCE_RELATIONS = {"supporting", "contradicting", "contextual"}
RIDER_EVALUATIONS = {"desired", "undesired", "mixed", "neutral", "not_provided"}
DEVELOPMENT_SIGNALS = {"reinforce", "discourage", "observe_only"}
LONGITUDINAL_STATUSES = {
    "isolated", "emerging", "established", "contradicted", "retired"
}
CONFIDENCE_STATES = {"tentative", "developing", "well_supported", "uncertain"}
OBSERVER_TYPES = {
    "rider", "observed_phoenix", "system_runtime", "developer_reviewer",
    "peer_phoenix", "legacy_actor",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _resolve_evidence(*, instance_id, conversation_id, message_ids, relation):
    if relation not in EVIDENCE_RELATIONS:
        raise ValueError(f"invalid evidence relation: {relation}")
    if not isinstance(message_ids, (list, tuple)):
        raise ValueError("message_ids must be a list or tuple")
    requested = tuple(dict.fromkeys(message_ids))
    if not requested:
        raise ValueError("at least one evidence message is required")
    messages = {
        message["message_id"]: message
        for message in canonical_messages(conversation_id,instance_id=instance_id)
    }
    missing = [message_id for message_id in requested if message_id not in messages]
    if missing:
        raise ValueError("evidence message was not found in canonical history")

    evidence = []
    for message_id in requested:
        message = messages[message_id]
        if message.get("instance_id") != instance_id:
            raise ValueError("evidence does not belong to this Phoenix instance")
        archive_id = message.get("source_archive_id")
        if not archive_id:
            raise ValueError("canonical evidence is missing Archive provenance")
        evidence.append(
            {
                "evidence_id": str(uuid.uuid4()),
                "relation": relation,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "source_archive_id": archive_id,
                "role": message["role"],
                "content": message["content"],
                "observed_at": _now(),
            }
        )
    return evidence


def _observer_attribution(value, *, observed_by, instance_id):
    """Normalize attribution without implementing peer evaluation behavior."""
    if value is None:
        actor_type = {
            "rider": "rider",
            "phoenix": "observed_phoenix",
            "developer": "developer_reviewer",
            "reviewer": "developer_reviewer",
        }.get(observed_by)
        if actor_type is None:
            actor_type = (
                "system_runtime"
                if "runtime" in observed_by or "evaluator" in observed_by
                else "legacy_actor"
            )
        return {
            "schema_version": 1,
            "actor_type": actor_type,
            "actor_id": observed_by,
            "phoenix_instance_id": (
                instance_id if actor_type == "observed_phoenix" else None
            ),
            "consent_context": None,
        }
    if not isinstance(value, dict):
        raise ValueError("observer_attribution must be an object")
    actor_type = value.get("actor_type")
    if actor_type not in OBSERVER_TYPES:
        raise ValueError(f"invalid observer actor_type: {actor_type}")
    phoenix_id = value.get("phoenix_instance_id")
    consent = value.get("consent_context")
    if actor_type == "peer_phoenix":
        if not isinstance(phoenix_id, str) or not phoenix_id.strip():
            raise ValueError("peer Phoenix attribution requires phoenix_instance_id")
        if not isinstance(consent, dict) or not consent.get("basis"):
            raise ValueError("peer Phoenix attribution requires consent context")
    return {
        "schema_version": 1,
        "actor_type": actor_type,
        "actor_id": value.get("actor_id"),
        "phoenix_instance_id": phoenix_id,
        "consent_context": consent,
    }


def _append_event(observation_id, *, instance_id, event_type, details):
    event = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "observation_id": observation_id,
        "instance_id": instance_id,
        "event_type": event_type,
        "created_at": _now(),
        "details": details,
    }
    _atomic_write(EVENTS_DIR / observation_id / f"{event['event_id']}.json", event)
    return event


def create_development_observation(
    *,
    instance_id,
    category,
    interpretation,
    uncertainty,
    conversation_id,
    message_ids,
    evidence_relation="supporting",
    status="tentative",
    observed_by="phoenix",
    observed_pattern=None,
    rider_evaluation="not_provided",
    rider_reason=None,
    development_signal="observe_only",
    longitudinal_status="isolated",
    confidence_state="tentative",
    phoenix_interpretation=None,
    observer_attribution=None,
):
    """Create an observation grounded in canonical Archive-backed messages."""
    instance_id = _require_text(instance_id, "instance_id")
    interpretation = _require_text(interpretation, "interpretation")
    uncertainty = _require_text(uncertainty, "uncertainty")
    conversation_id = _require_text(conversation_id, "conversation_id")
    observed_by = _require_text(observed_by, "observed_by")
    if category not in OBSERVATION_CATEGORIES:
        raise ValueError(f"invalid observation category: {category}")
    if status not in OBSERVATION_STATUSES:
        raise ValueError(f"invalid observation status: {status}")
    if rider_evaluation not in RIDER_EVALUATIONS:
        raise ValueError(f"invalid rider evaluation: {rider_evaluation}")
    if development_signal not in DEVELOPMENT_SIGNALS:
        raise ValueError(f"invalid development signal: {development_signal}")
    if longitudinal_status not in LONGITUDINAL_STATUSES:
        raise ValueError(f"invalid longitudinal status: {longitudinal_status}")
    if confidence_state not in CONFIDENCE_STATES:
        raise ValueError(f"invalid confidence state: {confidence_state}")
    observed_pattern = _require_text(
        observed_pattern or interpretation, "observed_pattern"
    )
    if rider_reason is not None:
        rider_reason = _require_text(rider_reason, "rider_reason")
    if phoenix_interpretation is not None:
        phoenix_interpretation = _require_text(
            phoenix_interpretation, "phoenix_interpretation"
        )
    attribution = _observer_attribution(
        observer_attribution, observed_by=observed_by, instance_id=instance_id
    )
    evidence = _resolve_evidence(
        instance_id=instance_id,
        conversation_id=conversation_id,
        message_ids=message_ids,
        relation=evidence_relation,
    )
    observation_id = str(uuid.uuid4())
    now = _now()
    record = {
        "schema_version": 3,
        "record_type": "development_observation",
        "observation_id": observation_id,
        "instance_id": instance_id,
        "category": category,
        "observed_pattern": observed_pattern,
        "rider_evaluation": rider_evaluation,
        "rider_reason": rider_reason,
        "development_signal": development_signal,
        "longitudinal_status": longitudinal_status,
        "confidence_state": confidence_state,
        # Reserved for a future Phoenix-authored reflection. Rider or developer
        # interpretation must never be stored in this field.
        "phoenix_interpretation": phoenix_interpretation,
        "current_interpretation": interpretation,
        "uncertainty": uncertainty,
        "status": status,
        "observed_by": observed_by,
        "observer_attribution": attribution,
        "created_at": now,
        "updated_at": now,
        "evidence": evidence,
        "effect": "observational_only",
    }
    _atomic_write(RECORDS_DIR / f"{observation_id}.json", record)
    _append_event(
        observation_id,
        instance_id=instance_id,
        event_type="observation_created",
        details={
            "category": category,
            "observed_pattern": observed_pattern,
            "rider_evaluation": rider_evaluation,
            "development_signal": development_signal,
            "longitudinal_status": longitudinal_status,
            "confidence_state": confidence_state,
            "interpretation": interpretation,
            "uncertainty": uncertainty,
            "status": status,
            "evidence_ids": [item["evidence_id"] for item in evidence],
        },
    )
    return record


def revise_observation_dimensions(
    observation_id,
    *,
    instance_id,
    category,
    observed_pattern,
    rider_evaluation,
    rider_reason,
    development_signal,
    longitudinal_status,
    confidence_state,
    reason,
):
    """Correct an observation's interpretation dimensions without altering evidence.

    This is an append-audited classification revision, not a development action.
    In particular, it cannot create Phoenix self-interpretation or executable state.
    """
    record = get_development_observation(observation_id, instance_id=instance_id)
    if record is None:
        raise ValueError("development observation not found")
    observed_pattern = _require_text(observed_pattern, "observed_pattern")
    rider_reason = _require_text(rider_reason, "rider_reason")
    reason = _require_text(reason, "reason")
    if category not in OBSERVATION_CATEGORIES:
        raise ValueError(f"invalid observation category: {category}")
    if rider_evaluation not in RIDER_EVALUATIONS:
        raise ValueError(f"invalid rider evaluation: {rider_evaluation}")
    if development_signal not in DEVELOPMENT_SIGNALS:
        raise ValueError(f"invalid development signal: {development_signal}")
    if longitudinal_status not in LONGITUDINAL_STATUSES:
        raise ValueError(f"invalid longitudinal status: {longitudinal_status}")
    if confidence_state not in CONFIDENCE_STATES:
        raise ValueError(f"invalid confidence state: {confidence_state}")

    dimensions = (
        "category", "observed_pattern", "rider_evaluation", "rider_reason",
        "development_signal", "longitudinal_status", "confidence_state",
        "phoenix_interpretation",
    )
    previous = {name: record.get(name) for name in dimensions}
    current = {
        "category": category,
        "observed_pattern": observed_pattern,
        "rider_evaluation": rider_evaluation,
        "rider_reason": rider_reason,
        "development_signal": development_signal,
        "longitudinal_status": longitudinal_status,
        "confidence_state": confidence_state,
        "phoenix_interpretation": None,
    }
    record.update(current)
    record.update(schema_version=2, updated_at=_now())
    _atomic_write(RECORDS_DIR / f"{observation_id}.json", record)
    _append_event(
        observation_id,
        instance_id=instance_id,
        event_type="observation_dimensions_revised",
        details={"previous": previous, "current": current, "reason": reason},
    )
    return record


def get_development_observation(observation_id, *, instance_id):
    path = RECORDS_DIR / f"{observation_id}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("instance_id") != instance_id:
        return None
    return record


def list_development_observations(*, instance_id, category=None, status=None):
    if not RECORDS_DIR.exists():
        return []
    records = []
    for path in RECORDS_DIR.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("instance_id") != instance_id:
            continue
        if category is not None and record.get("category") != category:
            continue
        if status is not None and record.get("status") != status:
            continue
        records.append(record)
    return sorted(records, key=lambda item: item.get("updated_at", ""), reverse=True)


def add_observation_evidence(
    observation_id,
    *,
    instance_id,
    conversation_id,
    message_ids,
    relation,
):
    record = get_development_observation(observation_id, instance_id=instance_id)
    if record is None:
        raise ValueError("development observation not found")
    evidence = _resolve_evidence(
        instance_id=instance_id,
        conversation_id=conversation_id,
        message_ids=message_ids,
        relation=relation,
    )
    existing = {
        (item["relation"], item["conversation_id"], item["message_id"])
        for item in record["evidence"]
    }
    additions = [
        item for item in evidence
        if (item["relation"], item["conversation_id"], item["message_id"])
        not in existing
    ]
    if not additions:
        return record
    record["evidence"].extend(additions)
    record["updated_at"] = _now()
    _atomic_write(RECORDS_DIR / f"{observation_id}.json", record)
    _append_event(
        observation_id,
        instance_id=instance_id,
        event_type="evidence_added",
        details={
            "relation": relation,
            "evidence_ids": [item["evidence_id"] for item in additions],
        },
    )
    return record


def revise_observation(
    observation_id,
    *,
    instance_id,
    interpretation,
    uncertainty,
    status,
    reason,
):
    record = get_development_observation(observation_id, instance_id=instance_id)
    if record is None:
        raise ValueError("development observation not found")
    interpretation = _require_text(interpretation, "interpretation")
    uncertainty = _require_text(uncertainty, "uncertainty")
    reason = _require_text(reason, "reason")
    if status not in OBSERVATION_STATUSES:
        raise ValueError(f"invalid observation status: {status}")
    previous = {
        "interpretation": record["current_interpretation"],
        "uncertainty": record["uncertainty"],
        "status": record["status"],
    }
    record.update(
        current_interpretation=interpretation,
        uncertainty=uncertainty,
        status=status,
        updated_at=_now(),
    )
    _atomic_write(RECORDS_DIR / f"{observation_id}.json", record)
    _append_event(
        observation_id,
        instance_id=instance_id,
        event_type="interpretation_revised",
        details={
            "previous": previous,
            "current": {
                "interpretation": interpretation,
                "uncertainty": uncertainty,
                "status": status,
            },
            "reason": reason,
        },
    )
    return record


def observation_history(observation_id, *, instance_id):
    if get_development_observation(observation_id, instance_id=instance_id) is None:
        return []
    directory = EVENTS_DIR / observation_id
    if not directory.exists():
        return []
    events = []
    for path in directory.glob("*.json"):
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if event.get("instance_id") == instance_id:
            events.append(event)
    return sorted(events, key=lambda item: item.get("created_at", ""))


def development_progression(*, instance_id):
    """Return an instance-scoped chronology over existing observation events.

    This is a camera over the ledger. It calculates no trait, score, promotion,
    or personality state and performs no writes.
    """
    if not EVENTS_DIR.exists():
        return []
    events = []
    for observation_directory in EVENTS_DIR.iterdir():
        if not observation_directory.is_dir():
            continue
        for path in observation_directory.glob("*.json"):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if event.get("instance_id") == instance_id:
                events.append(event)
    return sorted(events, key=lambda item: item.get("created_at", ""))

import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.capabilities.core import CapabilityDefinition


ROOT = Path(__file__).resolve().parent.parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
FEEDBACK_DIR = STATE_ROOT / "memory" / "development" / "feedback"

CONTEXT_FEEDBACK_SCHEMA_VERSION = 1
CONTEXT_FEEDBACK_POLICY_VERSION = "context-retrieval-feedback-v1"
CONTEXT_FEEDBACK_TYPES = {
    "context_helped",
    "context_irrelevant",
    "important_context_missing",
    "wrong_source_or_history",
    "clarification_preferred",
}

CONTEXT_RETRIEVAL_FEEDBACK_DEFINITION = CapabilityDefinition(
    name="context.feedback", version="1.0",
    display_name="Context Retrieval Feedback",
    description="Record authenticated rider evidence about one inspected context decision without applying it.",
    permissions=("development.record_observation",), effect="create_observational_evidence",
    privacy_handling="Phoenix-scoped body-free decision references",
    features=("versioned_feedback_types", "exact_context_linkage", "idempotent_recording",
              "no_automatic_learning_or_ranking"),
    appropriate_use=("record rider evaluation of an inspected retrieval decision",),
    inappropriate_use=("change retrieval policy", "grant authority", "mutate Memory", "retrain a model"),
    limitations=("feedback is evidence only", "adaptation requires later Development review and promotion"),
    dependencies=("Context Inspector", "Development feedback evidence store"),
    provenance_requirements=("authenticated rider", "Phoenix instance", "context receipt and package identity"),
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def record_context_retrieval_feedback(*, instance_id, rider_principal_id,
                                      response_message_id, context_receipt_id,
                                      package_id, allocation_decision_sha256,
                                      transmission_manifest_id, replay_flight_id,
                                      feedback_type, directory=None):
    """Record rider evidence about one exact composition; never apply it."""
    from src.library.artifacts import require_id
    for value, name in ((instance_id, "instance_id"), (rider_principal_id, "rider_principal_id"),
                        (response_message_id, "response_message_id"),
                        (context_receipt_id, "context_receipt_id")):
        require_id(value, name)
    if feedback_type not in CONTEXT_FEEDBACK_TYPES:
        raise ValueError("unsupported context retrieval feedback type")
    for value, name in ((package_id, "package_id"),
                        (allocation_decision_sha256, "allocation_decision_sha256"),
                        (transmission_manifest_id, "transmission_manifest_id"),
                        (replay_flight_id, "replay_flight_id")):
        if value is not None:
            require_id(value, name)
    identity = {
        "policy_version": CONTEXT_FEEDBACK_POLICY_VERSION,
        "instance_id": instance_id, "rider_principal_id": rider_principal_id,
        "response_message_id": response_message_id,
        "context_receipt_id": context_receipt_id, "package_id": package_id,
        "allocation_decision_sha256": allocation_decision_sha256,
        "transmission_manifest_id": transmission_manifest_id,
        "replay_flight_id": replay_flight_id, "feedback_type": feedback_type,
    }
    feedback_id = "context-feedback-" + hashlib.sha256(_canonical(identity).encode()).hexdigest()
    feedback = {
        "schema_version": CONTEXT_FEEDBACK_SCHEMA_VERSION,
        "record_type": "context_retrieval_feedback",
        "feedback_id": feedback_id, **identity,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "effect": "observational_only_no_automatic_change",
        "authority": {"creates_authority": False, "retrieval_authority": False,
                      "ranking_authority": False, "eligibility_authority": False,
                      "transmission_authority": False, "mutation_authority": False,
                      "approval_authority": False},
        "contains_context_bodies": False,
    }
    root = Path(directory) if directory is not None else FEEDBACK_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{feedback_id}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        comparable = {key: value for key, value in existing.items() if key != "created_at"}
        expected = {key: value for key, value in feedback.items() if key != "created_at"}
        if comparable != expected:
            raise ValueError("context feedback identity already exists with different data")
        return {**existing, "replayed": True}
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(feedback, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return {**feedback, "replayed": False}


def record_review_feedback(
    review_record,
    *,
    human_decision,
    reviewer="user",
    note="",
):
    """
    Record the difference between Fawkes's original judgment and
    the human's final decision.

    The original review record is never modified.
    """
    if human_decision not in {"accept", "reject"}:
        raise ValueError(
            f"Invalid human decision: {human_decision}"
        )

    if not review_record.get("review_id"):
        raise ValueError("review_record must contain review_id")

    feedback = {
        "feedback_id": str(uuid4()),
        "review_id": review_record["review_id"],
        "instance_id": review_record.get("instance_id"),
        "candidate_id": review_record["candidate_id"],
        "fawkes_decision": review_record.get(
            "decision",
        ),
        "fawkes_tier": review_record.get(
            "tier",
        ),
        "fawkes_confidence": review_record.get(
            "confidence",
        ),
        "fawkes_importance": review_record.get(
            "importance",
        ),
        "human_decision": human_decision,
        "reviewer": reviewer,
        "note": note.strip(),
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    FEEDBACK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = FEEDBACK_DIR / f"{feedback['feedback_id']}.json"

    path.write_text(
        json.dumps(
            feedback,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return feedback

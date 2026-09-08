"""Failure-safe persistence boundary for live Fawkes conversation turns."""

import json

from src.ingest import ingest_bytes
from src.memory.archive_retrieval import project_retained_message
from src.runtime.personal_recording import EffectiveRecordingPolicy, RecordingPolicyError


def persist_live_message(
    *,
    instance_id,
    conversation_id,
    message_id,
    role,
    text,
    model_slug=None,
    title="Fawkes CLI Session",
    source="fawkes_cli",
    recording_policy=None,
):
    if role not in {"user", "assistant"}:
        raise ValueError("role must be user or assistant")
    record = {
        "schema_version": 1,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "role": role,
        "model_slug": model_slug,
        "text": text,
    }
    if recording_policy is not None:
        if (not isinstance(recording_policy, EffectiveRecordingPolicy)
                or recording_policy.instance_id != instance_id
                or type(recording_policy.policy_revision) is not int
                or recording_policy.policy_revision < 0
                or type(recording_policy.memory_learning) is not bool):
            raise RecordingPolicyError("A matching effective recording policy is required")
        if recording_policy.archive_recording is not True or recording_policy.mode != "retained":
            raise RecordingPolicyError("The latched policy does not allow Archive recording")
        # The existing immutable payload digest covers this body-free decision.
        # Future discovery must use this turn's decision, not a later setting.
        record["recording_policy"] = {
            "schema_version": 1,
            "policy_revision": recording_policy.policy_revision,
            "mode": recording_policy.mode,
            "memory_learning": recording_policy.memory_learning,
        }
    metadata = ingest_bytes(
        (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
        f"{title} [{role} message]",
        source=source,
        capture_type="message_state",
        encoding="utf-8",
        conversation_id=conversation_id,
        instance_id=instance_id,
        capture_event_id=(
            f"{source}:{instance_id}:{conversation_id}:{message_id}"
        ),
        # Normal conversation output is deliberately separate from archive
        # receipts. The returned metadata remains complete for audit tooling.
        emit_receipt=False,
    )
    project_retained_message(metadata)
    return metadata

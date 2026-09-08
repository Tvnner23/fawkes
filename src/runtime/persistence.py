"""Failure-safe persistence boundary for live Fawkes conversation turns."""

import json

from src.ingest import ingest_bytes
from src.memory.archive_retrieval import project_retained_message


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

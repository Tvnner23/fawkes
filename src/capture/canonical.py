import json
from collections import defaultdict
from pathlib import Path

from .normalize import normalize_message_text


ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "archive" / "raw"
META_DIR = ROOT / "archive" / "meta"


def load_message_states(conversation_id: str):
    states = defaultdict(list)

    for meta_path in META_DIR.glob("*.json"):
        try:
            metadata = json.loads(
                meta_path.read_text(encoding="utf-8")
            )
        except Exception:
            continue

        if (
            metadata.get("conversation_id") != conversation_id
            or metadata.get("capture_type") != "message_state"
        ):
            continue

        raw_path = RAW_DIR / metadata["raw_file"]

        try:
            record = json.loads(
                raw_path.read_text(encoding="utf-8")
            )
        except Exception:
            continue

        if record.get("message_id") is None:
            continue

        states[record["message_id"]].append(
            {
                "archive_id": metadata["archive_id"],
                "created_at": metadata["created_at"],
                "message_id": record["message_id"],
                "role": record.get("role"),
                "text": record.get("text", ""),
                "model_slug": record.get("model_slug"),
            }
        )

    return states


def choose_latest_state(states):
    return max(
        states,
        key=lambda state: state["created_at"],
    )


def canonical_messages(conversation_id: str):
    states_by_id = load_message_states(conversation_id)

    messages = []

    for message_id, revisions in states_by_id.items():
        state = choose_latest_state(revisions)

        role = state["role"]

        if role not in {"user", "assistant"}:
            continue

        text = normalize_message_text(
            role,
            state["text"],
        )

        if not text.strip():
            continue

        messages.append(
            {
                "message_id": message_id,
                "role": role,
                "content": text,
                "model_slug": state["model_slug"],
                "created_at": state["created_at"],
                "source_archive_id": state["archive_id"],
                "revision_count": len(revisions),
            }
        )

    messages.sort(
        key=lambda message: message["created_at"]
    )

    return messages


def reconstruct_canonical_conversation(conversation_id: str):
    messages = canonical_messages(conversation_id)

    return {
        "schema_version": 1,
        "conversation_id": conversation_id,
        "message_count": len(messages),
        "messages": messages,
    }

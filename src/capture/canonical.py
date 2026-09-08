import json
import hashlib
import os
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

from .normalize import normalize_message_text
from .storage import metadata_paths,read_metadata,decode_object


ROOT = Path(__file__).resolve().parent.parent.parent
STATE_ROOT = Path(os.environ.get('FAWKES_RUNTIME_STATE_ROOT') or ROOT)
RAW_DIR = STATE_ROOT / "archive" / "raw"
META_DIR = STATE_ROOT / "archive" / "meta"


def _capture_time(value):
    if not isinstance(value,str):raise ValueError('Capture timestamp is unavailable')
    parsed=datetime.fromisoformat(value)
    if parsed.tzinfo is None:raise ValueError('Capture timestamp has no timezone')
    return parsed.astimezone(timezone.utc)


def _memory_learning_eligible(record):
    """Legacy captures stay eligible; a present invalid decision fails closed."""
    if "recording_policy" not in record:
        return True
    policy = record["recording_policy"]
    if not isinstance(policy, dict) or set(policy) != {
        "schema_version", "policy_revision", "mode", "memory_learning"
    }:
        return False
    return (
        type(policy["schema_version"]) is int and policy["schema_version"] == 1
        and type(policy["policy_revision"]) is int and policy["policy_revision"] >= 0
        and policy["mode"] == "retained"
        and policy["memory_learning"] is True
    )


def message_allows_memory_learning(message):
    """Accept only an exact eligible flag, retaining legacy projected inputs."""
    return message.get("memory_learning_eligible", True) is True


def load_message_states(conversation_id: str, *, instance_id=None, include_unscoped=False,
                        raw_dir=None, meta_dir=None, strict=False):
    states = defaultdict(list)
    raw_dir=RAW_DIR if raw_dir is None else Path(raw_dir)
    meta_dir=META_DIR if meta_dir is None else Path(meta_dir)

    for meta_path in metadata_paths(meta_dir,allow_missing=not strict):
        metadata = read_metadata(meta_path)

        if (
            metadata.get("conversation_id") != conversation_id
            or metadata.get("capture_type") != "message_state"
        ):
            continue
        owner=metadata.get('instance_id')
        if instance_id is not None and owner != instance_id and not (owner is None and include_unscoped):
            continue

        name=metadata.get('raw_file')
        if not isinstance(name,str) or not name or Path(name).name!=name or '/' in name or '\\' in name:
            raise ValueError('Archive raw-file reference is not local')
        raw_path = raw_dir / name
        if raw_path.is_symlink() or raw_path.resolve().parent != raw_dir.resolve():
            raise ValueError('Archive raw-file reference escapes storage')

        try:
            data=raw_path.read_bytes()
            if metadata.get('sha256') and hashlib.sha256(data).hexdigest()!=metadata['sha256']:
                raise ValueError('Archive content digest mismatch')
            if metadata.get('size_bytes') is not None and metadata['size_bytes']!=len(data):
                raise ValueError('Archive content length mismatch')
            record = decode_object(data)
        except (OSError,ValueError):
            raise ValueError('Selected Archive content is unreadable or invalid')

        if not isinstance(record,dict) or not isinstance(record.get('message_id'),str) or not record['message_id']:
            raise ValueError('Selected message identity is unavailable')
        if not isinstance(record.get('text',''),str) or not isinstance(record.get('role'),str):
            raise ValueError('Selected message role/text is malformed')
        if record.get('conversation_id') not in (None,conversation_id):
            raise ValueError('Archive content and metadata conversation disagree')
        _capture_time(metadata.get('created_at'))

        states[(owner,record["message_id"])].append(
            {
                "archive_id": metadata["archive_id"],
                "instance_id": metadata.get("instance_id"),
                "created_at": metadata["created_at"],
                "message_id": record["message_id"],
                "role": record.get("role"),
                "text": record.get("text", ""),
                "model_slug": record.get("model_slug"),
                "memory_learning_eligible": _memory_learning_eligible(record),
            }
        )

    return states


def choose_latest_state(states):
    return max(
        states,
        key=lambda state: (_capture_time(state["created_at"]),state['archive_id']),
    )


def canonical_messages(conversation_id: str, *, instance_id=None, include_unscoped=False,
                       raw_dir=None, meta_dir=None, strict=False):
    states_by_id = load_message_states(conversation_id,instance_id=instance_id,
        include_unscoped=include_unscoped,raw_dir=raw_dir,meta_dir=meta_dir,strict=strict)
    owners={owner for owner,_ in states_by_id}
    if instance_id is None and len(owners)>1:
        raise ValueError('An explicit instance is required for a shared conversation identity')
    ids=[message_id for _,message_id in states_by_id]
    if len(ids)!=len(set(ids)):
        raise ValueError('Scoped and legacy message identities conflict; explicit migration decision required')

    messages = []

    for (owner,message_id), revisions in states_by_id.items():
        state = choose_latest_state(revisions)
        first=min(revisions,key=lambda revision:(_capture_time(revision['created_at']),revision['archive_id']))

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
                "created_at": first["created_at"],
                "first_observed_at": first['created_at'],
                "revision_captured_at": state['created_at'],
                "ordering_basis": 'first_observed_capture',
                "source_created_at": None,
                "source_archive_id": state["archive_id"],
                "instance_id": state.get("instance_id"),
                "revision_count": len(revisions),
                # Later revisions cannot activate a previously disabled identity.
                "memory_learning_eligible": all(
                    revision["memory_learning_eligible"] for revision in revisions
                ),
            }
        )

    messages.sort(
        key=lambda message: (_capture_time(message["created_at"]),message['message_id'])
    )

    return messages


def reconstruct_canonical_conversation(conversation_id: str, **scope):
    messages = canonical_messages(conversation_id,**scope)

    return {
        "schema_version": 1,
        "conversation_id": conversation_id,
        "message_count": len(messages),
        "messages": messages,
    }

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import uuid

ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
CONVERSATION_DIR = STATE_ROOT / "conversations"
REGISTRY_PATH = CONVERSATION_DIR / "registry.json"
DEFAULT_REGISTRY_PATH = REGISTRY_PATH

CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)


def load_registry():
    if not REGISTRY_PATH.exists():
        return {"schema_version": 1, "conversations": []}

    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_registry(registry):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = REGISTRY_PATH.with_name(
        f".{REGISTRY_PATH.name}.{uuid.uuid4().hex}.tmp"
    )
    temporary.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(REGISTRY_PATH)


def create_conversation(title: str, instance_id=None, *, legacy_unscoped=False):
    if not isinstance(instance_id, str) or not instance_id.strip():
        if not legacy_unscoped and REGISTRY_PATH == DEFAULT_REGISTRY_PATH:
            raise ValueError("instance_id is required for new conversations")
        instance_id = None
    registry = load_registry()

    conversation_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    conversation = {
        "conversation_id": conversation_id,
        "title": title,
        "instance_id": instance_id,
        "created_at": created_at,
    }

    registry["conversations"].append(conversation)

    _write_registry(registry)

    return conversation


def get_conversation(conversation_id: str):
    registry = load_registry()

    for conversation in registry["conversations"]:
        if conversation["conversation_id"] == conversation_id:
            return conversation

    return None


def get_latest_conversation(instance_id=None):
    """
    Return the most recently created conversation, or None when no
    conversations have been recorded yet.
    """
    registry = load_registry()

    conversations = registry.get("conversations", [])

    if instance_id is not None:
        conversations = [
            conversation
            for conversation in conversations
            if conversation.get("instance_id") == instance_id
        ]

    if not conversations:
        return None

    return max(
        conversations,
        key=lambda conversation: conversation.get(
            "created_at",
            "",
        ),
    )

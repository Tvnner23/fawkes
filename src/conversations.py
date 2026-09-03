from pathlib import Path
from datetime import datetime, timezone
import json
import os
import uuid

ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
CONVERSATION_DIR = STATE_ROOT / "conversations"
REGISTRY_PATH = CONVERSATION_DIR / "registry.json"

CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)


def load_registry():
    if not REGISTRY_PATH.exists():
        return {"schema_version": 1, "conversations": []}

    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def create_conversation(title: str, instance_id=None):
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

    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    return conversation


def get_conversation(conversation_id: str):
    registry = load_registry()

    for conversation in registry["conversations"]:
        if conversation["conversation_id"] == conversation_id:
            return conversation

    return None

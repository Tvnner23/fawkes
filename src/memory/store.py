from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid


ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_ROOT = ROOT / "memory"
MEMORY_RECORDS_DIR = MEMORY_ROOT / "records"
MEMORY_EVENTS_DIR = MEMORY_ROOT / "events"


@dataclass
class Memory:
    memory_id: str
    memory_type: str
    content: str
    created_at: str
    updated_at: str
    status: str = "active"
    importance: float = 0.5
    confidence: float = 1.0
    source_message_ids: tuple = ()
    source_archive_ids: tuple = ()
    supersedes: str | None = None

    def to_dict(self):
        return asdict(self)


def _ensure_memory_dir():
    MEMORY_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_EVENTS_DIR.mkdir(parents=True, exist_ok=True)


def _memory_path(memory_id: str) -> Path:
    return MEMORY_RECORDS_DIR / f"{memory_id}.json"



def _event_path(event_id: str) -> Path:
    return MEMORY_EVENTS_DIR / f"{event_id}.json"


def append_memory_event(
    memory_id: str,
    event_type: str,
    *,
    data=None,
    source_message_ids=(),
    source_archive_ids=(),
):
    _ensure_memory_dir()

    now = datetime.now(timezone.utc).isoformat()
    event_id = str(uuid.uuid4())

    event = {
        "event_id": event_id,
        "memory_id": memory_id,
        "event_type": event_type,
        "created_at": now,
        "data": data or {},
        "source_message_ids": tuple(source_message_ids),
        "source_archive_ids": tuple(source_archive_ids),
    }

    path = _event_path(event_id)
    path.write_text(
        json.dumps(event, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return event


def create_memory(
    memory_type: str,
    content: str,
    *,
    importance: float = 0.5,
    confidence: float = 1.0,
    source_message_ids=(),
    source_archive_ids=(),
    supersedes=None,
):
    _ensure_memory_dir()

    now = datetime.now(timezone.utc).isoformat()

    memory_id = str(uuid.uuid4())

    memory = Memory(
        memory_id=memory_id,
        memory_type=memory_type,
        content=content,
        created_at=now,
        updated_at=now,
        importance=importance,
        confidence=confidence,
        source_message_ids=tuple(source_message_ids),
        source_archive_ids=tuple(source_archive_ids),
        supersedes=supersedes,
    )

    path = _memory_path(memory_id)
    payload = memory.to_dict()

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    append_memory_event(
        memory.memory_id,
        "created",
        data={
            "memory_type": memory.memory_type,
            "content": memory.content,
            "importance": memory.importance,
            "confidence": memory.confidence,
            "status": memory.status,
            "supersedes": memory.supersedes,
        },
        source_message_ids=memory.source_message_ids,
        source_archive_ids=memory.source_archive_ids,
    )

    return memory


def revise_memory(
    memory_id: str,
    *,
    content=None,
    memory_type=None,
    importance=None,
    confidence=None,
    status=None,
    source_message_ids=(),
    source_archive_ids=(),
):
    current = load_memory(memory_id)

    if current is None:
        return None

    previous = dict(current)

    if content is not None:
        current["content"] = content
    if memory_type is not None:
        current["memory_type"] = memory_type
    if importance is not None:
        current["importance"] = importance
    if confidence is not None:
        current["confidence"] = confidence
    if status is not None:
        current["status"] = status

    current["updated_at"] = datetime.now(timezone.utc).isoformat()

    path = _memory_path(memory_id)
    path.write_text(
        json.dumps(current, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    append_memory_event(
        memory_id,
        "revised",
        data={
            "previous": previous,
            "current": current,
        },
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
    )

    return current


def supersede_memory(
    memory_id: str,
    memory_type: str,
    content: str,
    *,
    importance: float = 0.5,
    confidence: float = 1.0,
    source_message_ids=(),
    source_archive_ids=(),
):
    old = load_memory(memory_id)

    if old is None:
        return None

    new_memory = create_memory(
        memory_type,
        content,
        importance=importance,
        confidence=confidence,
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
        supersedes=memory_id,
    )

    old["status"] = "superseded"
    old["updated_at"] = datetime.now(timezone.utc).isoformat()

    old_path = _memory_path(memory_id)
    old_path.write_text(
        json.dumps(old, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    append_memory_event(
        memory_id,
        "superseded",
        data={
            "superseded_by": new_memory.memory_id,
        },
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
    )

    return new_memory


def load_memory(memory_id: str):
    path = _memory_path(memory_id)

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def list_memories(status="active"):
    _ensure_memory_dir()

    memories = []

    for path in sorted(MEMORY_RECORDS_DIR.glob("*.json")):
        try:
            memory = json.loads(
                path.read_text(encoding="utf-8")
            )
        except Exception:
            continue

        if status is None or memory.get("status") == status:
            memories.append(memory)

    return memories


def memory_fingerprint(memory: dict):
    material = json.dumps(
        {
            "memory_type": memory.get("memory_type"),
            "content": memory.get("content"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid


ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_DIR = ROOT / "archive" / "memory"


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
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _memory_path(memory_id: str) -> Path:
    return MEMORY_DIR / f"{memory_id}.json"


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

    return memory


def load_memory(memory_id: str):
    path = _memory_path(memory_id)

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def list_memories(status="active"):
    _ensure_memory_dir()

    memories = []

    for path in sorted(MEMORY_DIR.glob("*.json")):
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

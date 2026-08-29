from pathlib import Path
from datetime import datetime, timezone
import json
import uuid

ROOT = Path(__file__).resolve().parent.parent
INSTANCE_DIR = ROOT / "instances"
REGISTRY_PATH = INSTANCE_DIR / "registry.json"

INSTANCE_DIR.mkdir(parents=True, exist_ok=True)


def load_registry():
    if not REGISTRY_PATH.exists():
        return {"schema_version": 1, "instances": []}

    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def create_instance(name: str, instance_type: str = "phoenix"):
    registry = load_registry()

    instance_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    instance = {
        "instance_id": instance_id,
        "name": name,
        "instance_type": instance_type,
        "created_at": created_at,
    }

    registry["instances"].append(instance)

    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    return instance


def get_instance(instance_id: str):
    registry = load_registry()

    for instance in registry["instances"]:
        if instance["instance_id"] == instance_id:
            return instance

    return None

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import uuid

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "archive" / "raw"
META_DIR = ROOT / "archive" / "meta"

RAW_DIR.mkdir(parents=True, exist_ok=True)
META_DIR.mkdir(parents=True, exist_ok=True)


def find_duplicate(sha256: str):
    for meta_path in META_DIR.glob("*.json"):
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if metadata.get("sha256") == sha256:
            return metadata

    return None


def ingest_bytes(
    raw_bytes: bytes,
    title: str,
    source: str,
    capture_type: str,
    original_filename=None,
    encoding=None,
    instance_id=None,
    conversation_id=None,
):
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    duplicate = find_duplicate(sha256)

    if duplicate:
        print("Duplicate detected: archive not written again.")
        print(f'Existing Archive ID: {duplicate["archive_id"]}')
        print(f"SHA-256: {sha256}")
        return duplicate

    archive_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    extension = Path(original_filename).suffix if original_filename else ".bin"
    raw_filename = f"{archive_id}{extension}"

    raw_path = RAW_DIR / raw_filename
    meta_path = META_DIR / f"{archive_id}.json"

    raw_path.write_bytes(raw_bytes)

    metadata = {
        "schema_version": 1,
        "archive_id": archive_id,
        "title": title,
        "created_at": created_at,
        "sha256": sha256,
        "raw_file": raw_filename,
        "original_filename": original_filename,
        "size_bytes": len(raw_bytes),
        "ingest_method": source,
        "capture_type": capture_type,
        "encoding": encoding,
        "instance_id": instance_id,
        "conversation_id": conversation_id,
    }

    meta_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Archived: {archive_id}")
    print(f"SHA-256: {sha256}")

    return metadata

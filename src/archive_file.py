from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
RAW_DIR = STATE_ROOT / "archive" / "raw"
META_DIR = STATE_ROOT / "archive" / "meta"

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


def archive_file(source_path: str, title: str):
    source = Path(source_path)

    if not source.exists():
        print("Source file not found.")
        sys.exit(1)

    if not source.is_file():
        print("Source path is not a file.")
        sys.exit(1)

    raw_bytes = source.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    duplicate = find_duplicate(sha256)

    if duplicate:
        print("Duplicate detected: file not archived again.")
        print(f'Existing Archive ID: {duplicate["archive_id"]}')
        print(f"SHA-256: {sha256}")
        return

    archive_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    extension = source.suffix
    raw_filename = f"{archive_id}{extension}"
    raw_path = RAW_DIR / raw_filename
    meta_path = META_DIR / f"{archive_id}.json"

    shutil.copyfile(source, raw_path)

    metadata = {
        "schema_version": 1,
        "archive_id": archive_id,
        "title": title,
        "created_at": created_at,
        "sha256": sha256,
        "raw_file": raw_filename,
        "original_filename": source.name,
        "size_bytes": len(raw_bytes),
        "ingest_method": "file_copy",
        "encoding": None,
    }

    meta_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Archived: {archive_id}")
    print(f"Original file: {source}")
    print(f"Raw file: {raw_path}")
    print(f"Metadata: {meta_path}")
    print(f"Size: {len(raw_bytes)} bytes")
    print(f"SHA-256: {sha256}")


def main():
    if len(sys.argv) != 3:
        print('Usage: python src/archive_file.py SOURCE_FILE "TITLE"')
        sys.exit(1)

    archive_file(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()

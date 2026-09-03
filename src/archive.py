from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
RAW_DIR = STATE_ROOT / "archive" / "raw"
META_DIR = STATE_ROOT / "archive" / "meta"

RAW_DIR.mkdir(parents=True, exist_ok=True)
META_DIR.mkdir(parents=True, exist_ok=True)


def archive_text(text: str, title: str):
    archive_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    raw_bytes = text.encode("utf-8")
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    raw_path = RAW_DIR / f"{archive_id}.txt"
    meta_path = META_DIR / f"{archive_id}.json"

    raw_path.write_bytes(raw_bytes)

    metadata = {
        "schema_version": 1,
        "archive_id": archive_id,
        "title": title,
        "created_at": created_at,
        "sha256": sha256,
        "raw_file": raw_path.name,
        "original_filename": None,
        "size_bytes": len(raw_bytes),
        "ingest_method": "text_stdin",
        "encoding": "utf-8",
    }

    meta_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"Archived: {archive_id}")
    print(f"Raw file: {raw_path}")
    print(f"Metadata: {meta_path}")
    print(f"SHA-256: {sha256}")


def main():
    if len(sys.argv) < 2:
        print('Usage: python src/archive.py "TITLE"')
        sys.exit(1)

    title = sys.argv[1]
    text = sys.stdin.read()

    if not text:
        print("No archive text received.")
        sys.exit(1)

    archive_text(text, title)


if __name__ == "__main__":
    main()

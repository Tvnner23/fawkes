from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "archive" / "raw"
META_DIR = ROOT / "archive" / "meta"


def verify_archive(archive_id: str):
    meta_path = META_DIR / f"{archive_id}.json"

    if not meta_path.exists():
        print("Metadata file not found.")
        sys.exit(1)

    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("Archive integrity: FAILED")
        print(f"Metadata unreadable: {exc}")
        sys.exit(1)

    raw_file = metadata.get("raw_file")
    expected_hash = metadata.get("sha256")

    if not raw_file:
        print("Archive integrity: FAILED")
        print("Metadata missing required field: raw_file")
        sys.exit(1)

    if not expected_hash:
        print("Archive integrity: FAILED")
        print("Metadata missing required field: sha256")
        sys.exit(1)

    raw_path = RAW_DIR / raw_file

    if not raw_path.exists():
        print("Archive integrity: FAILED")
        print("Raw archive file not found.")
        sys.exit(1)

    try:
        raw_bytes = raw_path.read_bytes()
    except OSError as exc:
        print("Archive integrity: FAILED")
        print(f"Raw archive file unreadable: {exc}")
        sys.exit(1)

    actual_hash = hashlib.sha256(raw_bytes).hexdigest()

    if actual_hash == expected_hash:
        print("Archive integrity: VERIFIED")
        print(f"Archive ID: {archive_id}")
        print(f"SHA-256: {actual_hash}")
    else:
        print("Archive integrity: FAILED")
        print(f"Expected: {expected_hash}")
        print(f"Actual:   {actual_hash}")
        sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: python src/verify_archive.py ARCHIVE_ID")
        sys.exit(1)

    verify_archive(sys.argv[1])


if __name__ == "__main__":
    main()

from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "archive" / "raw"
META_DIR = ROOT / "archive" / "meta"


def main():
    meta_files = sorted(META_DIR.glob("*.json"))

    if not meta_files:
        print("No archived items found.")
        return

    total = 0
    verified = 0
    failed = 0

    for meta_path in meta_files:
        total += 1

        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(f"FAILED: unreadable metadata: {meta_path.name}")
            failed += 1
            continue

        archive_id = metadata.get("archive_id", meta_path.stem)
        raw_file = metadata.get("raw_file")

        if not raw_file:
            print(f"FAILED: {archive_id} has no raw_file entry")
            failed += 1
            continue

        raw_path = RAW_DIR / raw_file

        if not raw_path.exists():
            print(f"FAILED: {archive_id} raw file missing")
            failed += 1
            continue

        actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        expected_hash = metadata.get("sha256")

        if actual_hash == expected_hash:
            print(f"VERIFIED: {archive_id}")
            verified += 1
        else:
            print(f"FAILED: {archive_id}")
            failed += 1

    print()
    print(f"Total: {total}")
    print(f"Verified: {verified}")
    print(f"Failed: {failed}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

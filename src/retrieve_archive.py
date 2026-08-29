from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "archive" / "raw"
META_DIR = ROOT / "archive" / "meta"


def retrieve_archive(archive_id: str):
    meta_path = META_DIR / f"{archive_id}.json"

    if not meta_path.exists():
        print("Metadata file not found.")
        sys.exit(1)

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    raw_path = RAW_DIR / metadata["raw_file"]

    if not raw_path.exists():
        print("Raw archive file not found.")
        sys.exit(1)

    print(raw_path.read_text(encoding="utf-8"), end="")


def main():
    if len(sys.argv) != 2:
        print("Usage: python src/retrieve_archive.py ARCHIVE_ID")
        sys.exit(1)

    retrieve_archive(sys.argv[1])


if __name__ == "__main__":
    main()

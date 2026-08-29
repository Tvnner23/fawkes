from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "archive" / "raw"
META_DIR = ROOT / "archive" / "meta"


def main():
    if len(sys.argv) < 2:
        print('Usage: python src/search_archive.py "SEARCH TERM"')
        sys.exit(1)

    query = " ".join(sys.argv[1:]).lower()
    matches = []

    for meta_path in META_DIR.glob("*.json"):
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

        raw_path = RAW_DIR / metadata["raw_file"]

        if not raw_path.exists():
            continue

        raw_text = raw_path.read_text(encoding="utf-8")

        searchable = f'{metadata["title"]}\n{raw_text}'.lower()

        if query in searchable:
            matches.append(metadata)

    if not matches:
        print("No matching archived items found.")
        return

    for metadata in matches:
        print(f'Title: {metadata["title"]}')
        print(f'Created: {metadata["created_at"]}')
        print(f'Archive ID: {metadata["archive_id"]}')
        print()


if __name__ == "__main__":
    main()

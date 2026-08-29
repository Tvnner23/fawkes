from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
META_DIR = ROOT / "archive" / "meta"


def main():
    files = sorted(META_DIR.glob("*.json"))

    if not files:
        print("No archived items found.")
        return

    for meta_path in files:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

        print(f'Title: {metadata["title"]}')
        print(f'Created: {metadata["created_at"]}')
        print(f'Archive ID: {metadata["archive_id"]}')
        print()


if __name__ == "__main__":
    main()

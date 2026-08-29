from pathlib import Path
from datetime import datetime, timezone
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"
META_DIR = ARCHIVE_DIR / "meta"
DATABASE_DIR = ROOT / "database"
MANIFEST_FILE = DATABASE_DIR / "archive_manifest.json"


def main():
    if not META_DIR.exists():
        print("Metadata directory not found.")
        sys.exit(1)

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    entries = []

    for metadata_path in sorted(META_DIR.glob("*.json")):
        try:
            metadata = json.loads(metadata_path.read_text())
        except Exception as exc:
            print(f"Failed to read metadata: {metadata_path.name}")
            print(exc)
            sys.exit(1)

        entries.append(metadata)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
        "entries": entries,
    }

    temp_file = MANIFEST_FILE.with_suffix(".json.tmp")
    temp_file.write_text(
        json.dumps(manifest, indent=2, sort_keys=True)
    )
    temp_file.replace(MANIFEST_FILE)

    print("Manifest built.")
    print(f"Entries: {len(entries)}")
    print(f"Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()

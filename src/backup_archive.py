from pathlib import Path
from datetime import datetime, timezone
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"
BACKUP_DIR = ROOT / "backups"


def main():
    if not ARCHIVE_DIR.exists():
        print("Archive directory not found.")
        sys.exit(1)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_DIR / f"archive-{timestamp}"

    if destination.exists():
        print("Backup destination already exists.")
        sys.exit(1)

    shutil.copytree(ARCHIVE_DIR, destination)

    print("Backup complete.")
    print(f"Source: {ARCHIVE_DIR}")
    print(f"Backup: {destination}")


if __name__ == "__main__":
    main()

from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python src/restore_archive.py "
            "BACKUP_DIRECTORY DESTINATION_DIRECTORY"
        )
        sys.exit(1)

    backup_dir = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()

    if not backup_dir.exists():
        print(f"Backup directory not found: {backup_dir}")
        sys.exit(1)

    if not backup_dir.is_dir():
        print(f"Backup path is not a directory: {backup_dir}")
        sys.exit(1)

    if destination == ARCHIVE_DIR.resolve():
        print("Refusing to overwrite the live Archive.")
        print("Restore to a separate directory first.")
        sys.exit(1)

    if destination.exists():
        print(f"Destination already exists: {destination}")
        sys.exit(1)

    shutil.copytree(backup_dir, destination)

    print("Restore complete.")
    print(f"Backup: {backup_dir}")
    print(f"Restored to: {destination}")


if __name__ == "__main__":
    main()

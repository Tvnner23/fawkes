from pathlib import Path
import filecmp
import sys

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"


def compare_directories(left: Path, right: Path):
    comparison = filecmp.dircmp(left, right)

    differences = []

    for name in comparison.left_only:
        differences.append(f"Only in {left}: {name}")

    for name in comparison.right_only:
        differences.append(f"Only in {right}: {name}")

    for name in comparison.diff_files:
        differences.append(f"Different file: {left / name}")

    for name in comparison.funny_files:
        differences.append(f"Could not compare: {left / name}")

    for name, subcomparison in comparison.subdirs.items():
        differences.extend(
            compare_directories(left / name, right / name)
        )

    return differences


def main():
    if len(sys.argv) != 2:
        print("Usage: python src/verify_backup.py BACKUP_DIRECTORY")
        sys.exit(1)

    backup_dir = Path(sys.argv[1]).resolve()

    if not ARCHIVE_DIR.exists():
        print("Archive directory not found.")
        sys.exit(1)

    if not backup_dir.exists():
        print(f"Backup directory not found: {backup_dir}")
        sys.exit(1)

    if not backup_dir.is_dir():
        print(f"Backup path is not a directory: {backup_dir}")
        sys.exit(1)

    differences = compare_directories(ARCHIVE_DIR, backup_dir)

    if differences:
        print("BACKUP VERIFICATION FAILED")
        for difference in differences:
            print(difference)
        sys.exit(1)

    print("BACKUP VERIFIED")
    print(f"Archive: {ARCHIVE_DIR}")
    print(f"Backup: {backup_dir}")


if __name__ == "__main__":
    main()

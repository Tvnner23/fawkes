from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_SCRIPT = ROOT / "src" / "archive_file.py"


def main():
    if len(sys.argv) != 2:
        print("Usage: python src/bulk_archive.py DIRECTORY")
        sys.exit(1)

    source_dir = Path(sys.argv[1])

    if not source_dir.exists():
        print("Directory not found.")
        sys.exit(1)

    if not source_dir.is_dir():
        print("Source path is not a directory.")
        sys.exit(1)

    files = sorted(path for path in source_dir.iterdir() if path.is_file())

    if not files:
        print("No files found.")
        return

    print(f"Found {len(files)} file(s).")
    print()

    for source in files:
        print(f"Archiving: {source.name}")

        result = subprocess.run(
            [
                sys.executable,
                str(ARCHIVE_SCRIPT),
                str(source),
                source.name,
            ]
        )

        if result.returncode != 0:
            print(f"FAILED: {source.name}")
            sys.exit(result.returncode)

        print()

    print(f"Bulk archive complete: {len(files)} file(s) archived.")


if __name__ == "__main__":
    main()

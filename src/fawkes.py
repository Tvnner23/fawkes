import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def run_script(script_name, args=None, use_stdin=False):
    if args is None:
        args = []

    command = [sys.executable, str(SRC / script_name), *args]

    if use_stdin:
        subprocess.run(command)
    else:
        subprocess.run(command)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python src/fawkes.py list')
        print('  python src/fawkes.py search "TERM"')
        print('  python src/fawkes.py retrieve ARCHIVE_ID')
        print('  python src/fawkes.py verify ARCHIVE_ID')
        print('  printf "TEXT" | python src/fawkes.py archive "TITLE"')
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command == "list":
        run_script("list_archive.py")

    elif command == "search":
        run_script("search_archive.py", args)

    elif command == "retrieve":
        run_script("retrieve_archive.py", args)

    elif command == "verify":
        run_script("verify_archive.py", args)

    elif command == "archive":
        run_script("archive.py", args, use_stdin=True)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()

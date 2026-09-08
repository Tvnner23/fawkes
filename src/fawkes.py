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
        result = subprocess.run(command)
    else:
        result = subprocess.run(command)

    sys.exit(result.returncode)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python src/fawkes.py list')
        print('  python src/fawkes.py chat')
        print('  python src/fawkes.py app')
        print('  python src/fawkes.py search "TERM"')
        print('  python src/fawkes.py retrieve ARCHIVE_ID')
        print('  python src/fawkes.py verify ARCHIVE_ID')
        print('  python src/fawkes.py verify-all')
        print('  printf "TEXT" | python src/fawkes.py archive "TITLE"')
        print('  python src/fawkes.py archive-file SOURCE_FILE "TITLE"')
        print('  python src/fawkes.py bulk-archive DIRECTORY')
        print('  python src/fawkes.py backup')
        print('  python src/fawkes.py verify-backup BACKUP_DIRECTORY')
        print('  python src/fawkes.py restore BACKUP_DIRECTORY DESTINATION_DIRECTORY')
        print('  python src/fawkes.py manifest')
        print('  python src/fawkes.py test')
        print('  python src/fawkes.py capture SOURCE_FILE TITLE')
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command in {"chat", "app"}:
        module = "src.runtime.chat_cli" if command == "chat" else "src.app.server"
        result = subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT)
        sys.exit(result.returncode)

    elif command == "list":
        run_script("list_archive.py")

    elif command == "search":
        run_script("search_archive.py", args)

    elif command == "retrieve":
        run_script("retrieve_archive.py", args)

    elif command == "verify":
        run_script("verify_archive.py", args)

    elif command == "verify-all":
        run_script("verify_all.py")

    elif command == "archive":
        run_script("archive.py", args, use_stdin=True)

    elif command == "archive-file":
        run_script("archive_file.py", args)

    elif command == "bulk-archive":
        run_script("bulk_archive.py", args)

    elif command == "backup":
        run_script("backup_archive.py")

    elif command == "verify-backup":
        run_script("verify_backup.py", args)

    elif command == "restore":
        run_script("restore_archive.py", args)

    elif command == "manifest":
        run_script("build_manifest.py")

    elif command == "test":
        run_script("run_tests.py")

    elif command == "capture":
        if len(sys.argv) != 4:
            print("Usage: python src/fawkes.py capture SOURCE_FILE TITLE")
            sys.exit(1)
        run_script(
            "capture_conversation.py",
            [sys.argv[2], sys.argv[3]],
        )

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()

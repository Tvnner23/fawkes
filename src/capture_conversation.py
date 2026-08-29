from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def capture_conversation(source_file: str, title: str):
    source = Path(source_file).expanduser().resolve()

    if not source.exists():
        print("Conversation source file not found.")
        return 1

    if not source.is_file():
        print("Conversation source must be a file.")
        return 1

    result = subprocess.run(
        [
            sys.executable,
            str(SRC / "archive_file.py"),
            str(source),
            title,
        ]
    )

    return result.returncode


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python src/capture_conversation.py "
            "SOURCE_FILE TITLE"
        )
        sys.exit(1)

    sys.exit(capture_conversation(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()

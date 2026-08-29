import subprocess
import sys


def main():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
            "-v",
        ]
    )

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

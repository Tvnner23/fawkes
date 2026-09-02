import subprocess
import unittest
from pathlib import Path

from src.runtime.expression import SHUTDOWN_SIGNOFFS, STARTUP_GREETINGS


class FawkesLiveLauncherTests(unittest.TestCase):
    def test_public_chat_command_starts_and_exits_cleanly(self):
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [str(root / ".venv" / "bin" / "python"), "src/fawkes.py", "chat"],
            cwd=root,
            input="exit\n",
            text=True,
            capture_output=True,
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            any(f"Fawkes: {greeting}" in result.stdout for greeting in STARTUP_GREETINGS),
            result.stdout,
        )
        self.assertTrue(
            any(f"Fawkes: {signoff}" in result.stdout for signoff in SHUTDOWN_SIGNOFFS),
            result.stdout,
        )
        lines = result.stdout.splitlines()
        disconnect_line = "Type 'exit' to disconnect.".center(60)
        disconnect_index = lines.index(disconnect_line)
        greeting_index = next(
            index
            for index, line in enumerate(lines)
            if any(line == f"Fawkes: {greeting}" for greeting in STARTUP_GREETINGS)
        )
        self.assertEqual(greeting_index, disconnect_index + 1)
        self.assertNotIn("Archived:", result.stdout)
        self.assertNotIn("SHA-256:", result.stdout)
        self.assertNotIn("Resuming conversation:", result.stdout)
        self.assertNotIn("Created conversation:", result.stdout)
        self.assertNotIn("Recovered ", result.stdout)
        self.assertNotIn("Prepared historical search index:", result.stdout)


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest
import sys
from unittest.mock import patch
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
        disconnect_line = "Type 'exit' to disconnect; /private or /retained selects future turns."
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

    def test_public_entrypoints_use_this_interpreter_and_propagate_arguments_and_exit(self):
        from src import fawkes
        for command, module in (('chat', 'src.runtime.chat_cli'), ('app', 'src.app.server')):
            with self.subTest(command=command), patch.object(sys, 'argv', ['fawkes.py', command, '--help']):
                with patch.object(fawkes.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as run:
                    with self.assertRaises(SystemExit) as caught:
                        fawkes.main()
                    self.assertEqual(caught.exception.code, 7)
                    run.assert_called_once_with([sys.executable, '-m', module, '--help'], cwd=fawkes.ROOT)


if __name__ == "__main__":
    unittest.main()

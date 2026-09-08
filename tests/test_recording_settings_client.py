"""Exercise the actual normal app script in its synthetic DOM."""
from pathlib import Path
import subprocess
import unittest


class RecordingSettingsClientTests(unittest.TestCase):
    def test_actual_client_controls_private_transition_and_ambiguous_updates(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["node", "tests/js/recording_settings_harness.js"],
            cwd=root, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("recording-settings-client-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()

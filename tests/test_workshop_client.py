"""Synthetic DOM qualification of the actual ordinary-user Workshop client."""
from pathlib import Path
import subprocess
import unittest


class WorkshopClientTests(unittest.TestCase):
    def test_actual_client_is_inert_versioned_private_and_truthful(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["node", "tests/js/workshop_harness.js"], cwd=root,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("workshop-client-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()

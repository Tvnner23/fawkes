import json
import tempfile
import unittest
from pathlib import Path

from src.memory.review_feedback import record_context_retrieval_feedback


class ContextRetrievalFeedbackTests(unittest.TestCase):
    def _record(self, directory, **overrides):
        values = {
            "instance_id": "fawkes", "rider_principal_id": "authenticated-rider:fawkes",
            "response_message_id": "response-1", "context_receipt_id": "response-1",
            "package_id": "package-1", "allocation_decision_sha256": "allocation-1",
            "transmission_manifest_id": "permit-1", "replay_flight_id": "response-1",
            "feedback_type": "context_helped", "directory": directory,
        }
        values.update(overrides)
        return record_context_retrieval_feedback(**values)

    def test_feedback_is_body_free_observational_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self._record(Path(tmp))
            second = self._record(Path(tmp))
            files = list(Path(tmp).glob("*.json"))
            stored = json.loads(files[0].read_text())
        self.assertEqual(len(files), 1)
        self.assertEqual(first["feedback_id"], second["feedback_id"])
        self.assertFalse(first["replayed"]); self.assertTrue(second["replayed"])
        self.assertEqual(stored["effect"], "observational_only_no_automatic_change")
        self.assertFalse(any(stored["authority"].values()))
        self.assertFalse(stored["contains_context_bodies"])
        self.assertNotIn("content", stored); self.assertNotIn("text", stored)

    def test_unknown_type_and_foreign_path_like_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unsupported"):
                self._record(Path(tmp), feedback_type="make_ranking_policy")
            with self.assertRaisesRegex(ValueError, "valid instance_id"):
                self._record(Path(tmp), instance_id="../foreign")


if __name__ == "__main__":
    unittest.main()

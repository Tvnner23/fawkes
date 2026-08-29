import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.consolidate as consolidate
import src.memory.store as store
from src.memory.semantic import SemanticMemoryAssessment


class FawkesMemoryConsolidationTests(unittest.TestCase):
    def test_non_memory_assessment_is_ignored(self):
        assessment = SemanticMemoryAssessment(
            should_remember=False,
            memory_type=None,
            meaning=None,
            confidence=0.95,
            importance=0.1,
            reasoning="Ephemeral request.",
        )

        result = consolidate.consolidate_assessment(assessment)

        self.assertEqual(result.action, "ignored")
        self.assertIsNone(result.memory_id)

    def test_incomplete_memory_assessment_needs_review(self):
        assessment = SemanticMemoryAssessment(
            should_remember=True,
            memory_type=None,
            meaning="The rider has a durable preference.",
            confidence=0.6,
            importance=0.7,
        )

        result = consolidate.consolidate_assessment(assessment)

        self.assertEqual(result.action, "needs_review")
        self.assertIsNone(result.memory_id)

    def test_valid_assessment_creates_persistent_memory_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                assessment = SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="preference",
                    meaning="The rider prefers progress shown as XP bars.",
                    confidence=0.98,
                    importance=0.9,
                    reasoning="Repeated correction indicates a durable preference.",
                )

                result = consolidate.consolidate_assessment(
                    assessment,
                    source_message_ids=("message-1",),
                    source_archive_ids=("archive-1",),
                )

                self.assertEqual(result.action, "created")
                self.assertIsNotNone(result.memory_id)

                saved = store.load_memory(result.memory_id)

                self.assertEqual(saved["memory_type"], "preference")
                self.assertEqual(
                    saved["content"],
                    "The rider prefers progress shown as XP bars.",
                )
                self.assertEqual(saved["confidence"], 0.98)
                self.assertEqual(saved["importance"], 0.9)
                self.assertEqual(
                    saved["source_message_ids"],
                    ["message-1"],
                )
                self.assertEqual(
                    saved["source_archive_ids"],
                    ["archive-1"],
                )


if __name__ == "__main__":
    unittest.main()

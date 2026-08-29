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

    def test_revising_evidence_updates_existing_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                existing = store.create_memory(
                    memory_type="goal",
                    content="Focus on cybersecurity.",
                    confidence=0.70,
                    importance=0.80,
                )

                assessment = SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="goal",
                    meaning="Focus primarily on networking.",
                    confidence=0.92,
                    importance=0.90,
                )

                result = consolidate.consolidate_assessment(
                    assessment,
                    matcher=FakeMatcher("revises"),
                    existing_memories=(existing.__dict__,),
                )

                self.assertEqual(result.action, "revised")
                self.assertEqual(result.memory_id, existing.memory_id)

                saved = store.load_memory(existing.memory_id)

                self.assertEqual(saved["content"], "Focus primarily on networking.")
                self.assertEqual(saved["confidence"], 0.92)
                self.assertEqual(saved["importance"], 0.90)

    def test_superseding_evidence_replaces_existing_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                existing = store.create_memory(
                    memory_type="goal",
                    content="Focus on cybersecurity.",
                    confidence=0.75,
                    importance=0.80,
                )

                assessment = SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="goal",
                    meaning="Focus on networking instead.",
                    confidence=0.95,
                    importance=0.90,
                )

                result = consolidate.consolidate_assessment(
                    assessment,
                    matcher=FakeMatcher("supersedes"),
                    existing_memories=(existing.__dict__,),
                )

                self.assertEqual(result.action, "superseded")
                self.assertNotEqual(result.memory_id, existing.memory_id)

                old_saved = store.load_memory(existing.memory_id)
                new_saved = store.load_memory(result.memory_id)

                self.assertEqual(old_saved["status"], "superseded")
                self.assertEqual(new_saved["supersedes"], existing.memory_id)
                self.assertEqual(new_saved["content"], "Focus on networking instead.")


if __name__ == "__main__":
    unittest.main()

# Relation-driven consolidation tests start here

class FakeMatcher:
    def __init__(self, relation, confidence=0.95):
        self.relation = relation
        self.confidence = confidence

    def compare(self, **kwargs):
        from src.memory.compare import MemoryComparison
        return MemoryComparison(
            relation=self.relation,
            confidence=self.confidence,
        )

class FawkesMemoryEvolutionTests(unittest.TestCase):
    def test_supporting_evidence_strengthens_existing_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                existing = store.create_memory(
                    memory_type="preference",
                    content="The rider prefers commands before explanations.",
                    confidence=0.60,
                    importance=0.70,
                )

                assessment = SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="preference",
                    meaning="The rider prefers command-first instructions.",
                    confidence=0.95,
                    importance=0.85,
                )

                result = consolidate.consolidate_assessment(
                    assessment,
                    matcher=FakeMatcher("supports"),
                    existing_memories=(existing.__dict__,),
                )

                self.assertEqual(result.action, "strengthened")
                self.assertEqual(result.memory_id, existing.memory_id)

                saved = store.load_memory(existing.memory_id)

                self.assertGreater(saved["confidence"], 0.60)

    def test_contradicting_evidence_does_not_destroy_existing_memory(self):
        existing = {
            "memory_id": "memory-1",
            "memory_type": "belief",
            "content": "Remote work is preferred.",
            "confidence": 0.80,
            "importance": 0.70,
        }

        assessment = SemanticMemoryAssessment(
            should_remember=True,
            memory_type="belief",
            meaning="Office work is preferred.",
            confidence=0.85,
            importance=0.70,
        )

        result = consolidate.consolidate_assessment(
            assessment,
            matcher=FakeMatcher("contradicts"),
            existing_memories=(existing,),
        )

        self.assertEqual(result.action, "conflict_detected")
        self.assertEqual(result.memory_id, "memory-1")

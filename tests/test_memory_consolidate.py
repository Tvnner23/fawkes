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

class FawkesSemanticDuplicateConsolidationTests(unittest.TestCase):
    def test_semantic_duplicate_strengthens_existing_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records),                  patch.object(store, "MEMORY_EVENTS_DIR", events):

                existing = store.create_memory(
                    memory_type="career_goal",
                    content="The user chose networking as their career direction.",
                    confidence=0.80,
                    importance=0.90,
                )

                assessment = SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="goal",
                    meaning="Focus primarily on networking.",
                    confidence=0.95,
                    importance=0.90,
                )

                result = consolidate.consolidate_assessment(
                    assessment,
                    matcher=FakeMatcher("duplicate"),
                    existing_memories=(existing.__dict__,),
                    source_message_ids=("independent-confirmation",),
                )

                self.assertEqual(
                    result.action,
                    "duplicate_strengthened",
                )
                self.assertEqual(
                    result.memory_id,
                    existing.memory_id,
                )

                saved = store.load_memory(existing.memory_id)

                self.assertEqual(
                    saved["content"],
                    "The user chose networking as their career direction.",
                )
                self.assertGreater(
                    saved["confidence"],
                    0.80,
                )

                active = store.list_memories(status="active")

                self.assertEqual(
                    len(active),
                    1,
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
                    source_message_ids=("independent-confirmation",),
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


class MultiMemoryMatcher:
    def __init__(self):
        self.compared = []

    def compare(
        self,
        *,
        new_meaning,
        new_memory_type,
        existing_memory,
        conversation_context=(),
    ):
        self.compared.append(existing_memory["memory_id"])

        from src.memory.compare import MemoryComparison

        if existing_memory["content"] == "The rider prefers networking work.":
            return MemoryComparison(
                relation="supports",
                confidence=0.95,
                reasoning="This is the matching durable memory.",
            )

        return MemoryComparison(
            relation="related_to",
            confidence=0.60,
            reasoning="Related, but not the same memory.",
        )


class FawkesMultiMemoryConsolidationTests(unittest.TestCase):
    def test_consolidation_can_evaluate_multiple_existing_memories(self):
        assessment = SemanticMemoryAssessment(
            should_remember=True,
            memory_type="preference",
            meaning="The rider prefers networking work.",
            confidence=0.94,
            importance=0.88,
        )

        matcher = MultiMemoryMatcher()

        existing_memories = (
            {
                "memory_id": "unrelated-memory",
                "memory_type": "knowledge",
                "content": "The rider is researching cybersecurity careers.",
                "confidence": 0.80,
                "importance": 0.70,
            },
            {
                "memory_id": "target-memory",
                "memory_type": "preference",
                "content": "The rider prefers networking work.",
                "confidence": 0.70,
                "importance": 0.80,
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                existing = store.create_memory(
                    memory_type="preference",
                    content="The rider prefers networking work.",
                    confidence=0.70,
                    importance=0.80,
                )

                existing_memories = (
                    existing_memories[0],
                    {
                        **existing_memories[1],
                        "memory_id": existing.memory_id,
                    },
                )

                result = consolidate.consolidate_assessment(
                    assessment,
                    matcher=matcher,
                    existing_memories=existing_memories,
                )

        self.assertEqual(result.action, "strengthened")
        self.assertEqual(result.memory_id, existing_memories[1]["memory_id"])
        self.assertEqual(
            matcher.compared,
            ["unrelated-memory", existing_memories[1]["memory_id"]],
        )


class FawkesExistingDuplicateCleanupTests(unittest.TestCase):
    def test_marking_duplicate_superseded_does_not_create_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                canonical = store.create_memory(
                    memory_type="career_goal",
                    content="The user chose networking as their career direction.",
                    confidence=0.99,
                    importance=0.90,
                )

                duplicate = store.create_memory(
                    memory_type="goal",
                    content="Focus primarily on networking.",
                    confidence=0.95,
                    importance=0.90,
                )

                before = store.list_memories(status=None)

                result = store.mark_memory_superseded(
                    duplicate.memory_id,
                    superseded_by=canonical.memory_id,
                )

                after = store.list_memories(status=None)

                self.assertEqual(
                    len(after),
                    len(before),
                )

                self.assertEqual(
                    result["status"],
                    "superseded",
                )

                self.assertEqual(
                    result["superseded_by"],
                    canonical.memory_id,
                )

                self.assertEqual(
                    store.load_memory(canonical.memory_id)["status"],
                    "active",
                )

                active = store.list_memories(status="active")

                self.assertEqual(
                    len(active),
                    1,
                )

                self.assertEqual(
                    active[0]["memory_id"],
                    canonical.memory_id,
                )


if __name__ == "__main__":
    unittest.main()


class FawkesSemanticDuplicateCleanupTests(unittest.TestCase):
    def test_cleanup_keeps_best_canonical_and_preserves_duplicate_history(self):
        import src.memory.store as store

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                canonical = store.create_memory(
                    memory_type="career_goal",
                    content=(
                        "The user chose networking as their career direction."
                    ),
                    confidence=0.99,
                    importance=0.95,
                    source_message_ids=("canonical-message",),
                    source_archive_ids=("canonical-archive",),
                )

                duplicate = store.create_memory(
                    memory_type="goal",
                    content="Focus primarily on networking.",
                    confidence=0.80,
                    importance=0.70,
                    source_message_ids=("duplicate-message",),
                    source_archive_ids=("duplicate-archive",),
                )

                class FakeMatcher:
                    def compare(self, **kwargs):
                        from src.memory.compare import MemoryComparison

                        return MemoryComparison(
                            relation="duplicate",
                            confidence=0.99,
                            reasoning="Same underlying career direction.",
                        )

                from src.memory.consolidate import (
                    cleanup_semantic_duplicates,
                )

                results = cleanup_semantic_duplicates(
                    matcher=FakeMatcher(),
                    memories=store.list_memories(status="active"),
                )

                self.assertEqual(
                    len(results),
                    1,
                )

                result = results[0]

                self.assertEqual(
                    result.canonical_memory_id,
                    canonical.memory_id,
                )

                self.assertEqual(
                    result.superseded_memory_id,
                    duplicate.memory_id,
                )

                surviving = store.load_memory(
                    canonical.memory_id,
                )

                retired = store.load_memory(
                    duplicate.memory_id,
                )

                self.assertEqual(
                    surviving["status"],
                    "active",
                )

                self.assertEqual(
                    retired["status"],
                    "superseded",
                )

                self.assertEqual(
                    retired["superseded_by"],
                    canonical.memory_id,
                )

                self.assertIn(
                    "canonical-message",
                    surviving["source_message_ids"],
                )

                self.assertIn(
                    "duplicate-message",
                    surviving["source_message_ids"],
                )

                self.assertIn(
                    "canonical-archive",
                    surviving["source_archive_ids"],
                )

                self.assertIn(
                    "duplicate-archive",
                    surviving["source_archive_ids"],
                )

                self.assertEqual(
                    len(store.list_memories(status="active")),
                    1,
                )

    def test_canonical_selection_is_deterministic(self):
        from src.memory.consolidate import _canonical_memory

        memories = [
            {
                "memory_id": "newer",
                "importance": 0.90,
                "confidence": 0.99,
                "created_at": "2026-08-30T02:00:00+00:00",
            },
            {
                "memory_id": "older",
                "importance": 0.90,
                "confidence": 0.99,
                "created_at": "2026-08-30T01:00:00+00:00",
            },
        ]

        self.assertEqual(
            _canonical_memory(memories)["memory_id"],
            "older",
        )

    def test_cleanup_ignores_low_confidence_duplicate_claims(self):
        from src.memory.consolidate import cleanup_semantic_duplicates

        memories = [
            {
                "memory_id": "memory-1",
                "memory_type": "goal",
                "content": "Focus on networking.",
                "importance": 0.90,
                "confidence": 0.99,
                "created_at": "2026-08-30T01:00:00+00:00",
            },
            {
                "memory_id": "memory-2",
                "memory_type": "career_goal",
                "content": "Networking is my career.",
                "importance": 0.90,
                "confidence": 0.99,
                "created_at": "2026-08-30T02:00:00+00:00",
            },
        ]

        class FakeMatcher:
            def compare(self, **kwargs):
                from src.memory.compare import MemoryComparison

                return MemoryComparison(
                    relation="duplicate",
                    confidence=0.89,
                    reasoning="Possibly related, but uncertain.",
                )

        results = cleanup_semantic_duplicates(
            matcher=FakeMatcher(),
            memories=memories,
        )

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()

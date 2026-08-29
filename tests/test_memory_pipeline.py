import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.store as store
from src.memory.pipeline import process_memory_candidate
from src.memory.semantic import SemanticMemoryAssessment
from src.memory.compare import MemoryComparison


class FakeEvaluator:
    def evaluate(self, *, content, conversation_context=()):
        return SemanticMemoryAssessment(
            should_remember=True,
            memory_type="preference",
            meaning="The rider prefers networking work.",
            confidence=0.94,
            importance=0.88,
        )


class FakeMatcher:
    def compare(
        self,
        *,
        new_meaning,
        new_memory_type,
        existing_memory,
        conversation_context=(),
    ):
        return MemoryComparison(
            relation="supports",
            confidence=0.95,
        )


class FawkesMemoryPipelineTests(unittest.TestCase):
    def test_candidate_flows_through_semantic_evaluation_and_consolidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                candidate = {
                    "candidate_id": "message-1",
                    "content": "I prefer networking work.",
                    "source_message_ids": ("message-1",),
                    "source_archive_ids": ("archive-1",),
                }

                result = process_memory_candidate(
                    candidate,
                    evaluator=FakeEvaluator(),
                )

                self.assertEqual(result.action, "created")
                self.assertIsNotNone(result.memory_id)
                self.assertEqual(
                    result.assessment.memory_type,
                    "preference",
                )

    def test_existing_memory_can_be_strengthened_through_pipeline(self):
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

                candidate = {
                    "candidate_id": "message-2",
                    "content": "I still prefer networking work.",
                    "source_message_ids": ("message-2",),
                    "source_archive_ids": ("archive-2",),
                }

                result = process_memory_candidate(
                    candidate,
                    evaluator=FakeEvaluator(),
                    matcher=FakeMatcher(),
                )

                self.assertEqual(result.action, "strengthened")
                self.assertEqual(
                    result.memory_id,
                    existing.memory_id,
                )


if __name__ == "__main__":
    unittest.main()


class ContextCapturingMatcher:
    def __init__(self):
        self.received_context = None

    def compare(
        self,
        *,
        new_meaning,
        new_memory_type,
        existing_memory,
        conversation_context=(),
    ):
        self.received_context = conversation_context
        return MemoryComparison(
            relation="supports",
            confidence=0.95,
        )


class ContextCapturingEvaluator:
    def __init__(self):
        self.received_context = None

    def evaluate(self, *, content, conversation_context=()):
        self.received_context = conversation_context
        return SemanticMemoryAssessment(
            should_remember=True,
            memory_type="preference",
            meaning="The rider prefers networking work.",
            confidence=0.94,
            importance=0.88,
        )


class FawkesMemoryPipelineContextTests(unittest.TestCase):
    def test_conversation_context_reaches_semantic_evaluation_and_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                store.create_memory(
                    memory_type="preference",
                    content="The rider prefers networking work.",
                    confidence=0.70,
                    importance=0.80,
                )

                evaluator = ContextCapturingEvaluator()
                matcher = ContextCapturingMatcher()

                context = (
                    {"role": "assistant", "content": "What career direction?"},
                    {"role": "user", "content": "Networking."},
                )

                candidate = {
                    "candidate_id": "message-1",
                    "content": "That's still what I prefer.",
                    "source_message_ids": ("message-1",),
                    "source_archive_ids": ("archive-1",),
                }

                result = process_memory_candidate(
                    candidate,
                    evaluator=evaluator,
                    matcher=matcher,
                    conversation_context=context,
                )

                self.assertEqual(result.action, "strengthened")
                self.assertEqual(
                    evaluator.received_context,
                    context,
                )
                self.assertEqual(
                    matcher.received_context,
                    context,
                )

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


class FawkesRealProviderPipelineTests(unittest.TestCase):
    def test_openai_provider_implements_semantic_evaluator_contract(self):
        from src.memory.openai_provider import OpenAISemanticMemoryProvider
        from src.memory.semantic import evaluate_semantically
        from src.memory.semantic_provider import ModelSemanticMemoryEvaluator

        class FakeResponse:
            output_text = (
                '{"should_remember": true, '
                '"memory_type": "career_goal", '
                '"meaning": "The user chose networking as their career direction.", '
                '"confidence": 0.99, '
                '"importance": 0.90, '
                '"reasoning": "Durable career decision."}'
            )

        class FakeResponses:
            def create(self, **kwargs):
                return FakeResponse()

        class FakeClient:
            responses = FakeResponses()

        evaluator = OpenAISemanticMemoryProvider(
            client=FakeClient(),
            model="test-model",
        )

        evaluator = ModelSemanticMemoryEvaluator(evaluator)

        result = evaluate_semantically(
            evaluator,
            content="Yeah, that's the one.",
            conversation_context=(
                {
                    "role": "assistant",
                    "content": "So networking is the career direction you're choosing?",
                },
                {
                    "role": "user",
                    "content": "Yeah, that's the one.",
                },
            ),
        )

        self.assertTrue(result.should_remember)
        self.assertEqual(result.memory_type, "career_goal")
        self.assertEqual(
            result.meaning,
            "The user chose networking as their career direction.",
        )
        self.assertEqual(result.confidence, 0.99)
        self.assertEqual(result.importance, 0.90)


if __name__ == "__main__":
    unittest.main()


class FawkesEndToEndMemoryFlowTests(unittest.TestCase):
    def test_full_pipeline_uses_canonical_conversation_context(self):
        from src.memory.openai_provider import OpenAISemanticMemoryProvider
        from src.memory.semantic_provider import ModelSemanticMemoryEvaluator
        from src.memory.pipeline import process_candidates

        class FakeResponse:
            output_text = (
                '{"should_remember": true, '
                '"memory_type": "career_goal", '
                '"meaning": "The user chose networking as their career direction.", '
                '"confidence": 0.99, '
                '"importance": 0.90, '
                '"reasoning": "The conversation establishes a durable career decision."}'
            )

        class FakeResponses:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        client = FakeClient()
        provider = OpenAISemanticMemoryProvider(
            client=client,
            model="test-model",
        )
        evaluator = ModelSemanticMemoryEvaluator(provider)

        candidates = [
            {
                "candidate_id": "message-1",
                "content": "Yeah, that's the one.",
                "source_message_ids": ("message-1",),
                "source_archive_ids": ("archive-1",),
            }
        ]

        context = (
            {
                "role": "assistant",
                "content": "So networking is the career direction you're choosing?",
            },
            {
                "role": "user",
                "content": "Yeah, that's the one.",
            },
        )

        results = process_candidates(
            candidates,
            evaluator=evaluator,
            conversation_context=context,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "created")
        self.assertEqual(
            client.responses.calls[0]["model"],
            "test-model",
        )
        self.assertIn(
            "networking is the career direction",
            client.responses.calls[0]["input"][1]["content"].lower(),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesConversationMemoryFlowTests(unittest.TestCase):
    def test_conversation_flow_builds_context_from_canonical_history(self):
        from unittest.mock import patch
        from src.memory.pipeline import process_conversation

        canonical = (
            {
                "message_id": "message-1",
                "role": "assistant",
                "content": "So networking is the career direction you're choosing?",
            },
            {
                "message_id": "message-2",
                "role": "user",
                "content": "Yeah, that's the one.",
            },
        )

        candidates = (
            {
                "candidate_id": "message-2",
                "content": "Yeah, that's the one.",
                "source_message_ids": ("message-2",),
                "source_archive_ids": ("archive-2",),
            },
        )

        class CapturingEvaluator:
            def __init__(self):
                self.context = None

            def evaluate(self, *, content, conversation_context=()):
                self.context = conversation_context
                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="career_goal",
                    meaning="The user chose networking as their career direction.",
                    confidence=0.99,
                    importance=0.90,
                )

        evaluator = CapturingEvaluator()

        with patch(
            "src.memory.pipeline.canonical_messages",
            return_value=canonical,
        ), patch(
            "src.memory.pipeline.extract_memory_candidates",
            return_value=list(candidates),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                records = root / "records"
                events = root / "events"

                with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                     patch.object(store, "MEMORY_EVENTS_DIR", events):

                    results = process_conversation(
                        "conversation-1",
                        evaluator=evaluator,
                    )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "created")
        self.assertEqual(evaluator.context, canonical)


if __name__ == "__main__":
    unittest.main()

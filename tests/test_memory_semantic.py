import unittest

from src.memory.semantic import (
    SemanticMemoryAssessment,
    evaluate_semantically,
)


class FakeSemanticEvaluator:
    def __init__(self):
        self.last_content = None
        self.last_context = None

    def evaluate(self, *, content, conversation_context=()):
        self.last_content = content
        self.last_context = conversation_context

        return SemanticMemoryAssessment(
            should_remember=True,
            memory_type="decision",
            meaning="The rider chose networking as the main career direction.",
            confidence=0.95,
            importance=0.9,
            reasoning="Interpreted from the supplied conversation context.",
        )


class FawkesSemanticMemoryTests(unittest.TestCase):
    def test_semantic_evaluator_is_provider_independent(self):
        evaluator = FakeSemanticEvaluator()

        result = evaluate_semantically(
            evaluator,
            content="Yeah, that's the one.",
            conversation_context=(
                {
                    "role": "assistant",
                    "content": "So networking is your main direction?",
                },
            ),
        )

        self.assertTrue(result.should_remember)
        self.assertEqual(result.memory_type, "decision")
        self.assertEqual(
            result.meaning,
            "The rider chose networking as the main career direction.",
        )

    def test_conversation_context_is_forwarded(self):
        evaluator = FakeSemanticEvaluator()

        context = (
            {"role": "user", "content": "I'm comparing networking and cybersecurity."},
            {"role": "assistant", "content": "Networking seems like the better fit."},
        )

        evaluate_semantically(
            evaluator,
            content="Yeah, that's the one.",
            conversation_context=context,
        )

        self.assertEqual(evaluator.last_content, "Yeah, that's the one.")
        self.assertEqual(evaluator.last_context, context)

    def test_evaluate_conversation_uses_semantic_evaluator(self):
        from src.memory.evaluate import evaluate_conversation
        from unittest.mock import patch

        class FakeEvaluator:
            def evaluate(self, *, content, conversation_context=()):
                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="preference",
                    meaning="The rider prefers networking over general cybersecurity work.",
                    confidence=0.94,
                    importance=0.88,
                )

        candidate = {
            "candidate_id": "message-1",
            "memory_type": "unclassified",
            "content": "I strongly prefer networking over general cybersecurity work.",
            "importance": None,
            "confidence": None,
            "source_message_ids": ("message-1",),
            "source_archive_ids": ("archive-1",),
            "created_at": "2026-08-29T00:00:00+00:00",
        }

        with patch(
            "src.memory.evaluate.extract_memory_candidates",
            return_value=[candidate],
        ):
            results = evaluate_conversation(
                "conversation-1",
                evaluator=FakeEvaluator(),
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["decision"], "likely_memory")
        self.assertEqual(results[0]["memory_type"], "preference")
        self.assertEqual(
            results[0]["meaning"],
            "The rider prefers networking over general cybersecurity work.",
        )
        self.assertEqual(results[0]["evaluation_confidence"], 0.94)
        self.assertEqual(results[0]["importance"], 0.88)


if __name__ == "__main__":
    unittest.main()


class FawkesSemanticNoPrefixTests(unittest.TestCase):
    def test_semantic_evaluator_can_identify_memory_without_prefix_signal(self):
        class ContextAwareEvaluator:
            def __init__(self):
                self.received_context = None

            def evaluate(self, *, content, conversation_context=()):
                self.received_context = conversation_context

                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="decision",
                    meaning="The rider chose networking as his career direction.",
                    confidence=0.96,
                    importance=0.91,
                )

        evaluator = ContextAwareEvaluator()

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

        result = evaluate_semantically(
            evaluator,
            content="Yeah, that's the one.",
            conversation_context=context,
        )

        self.assertTrue(result.should_remember)
        self.assertEqual(result.memory_type, "decision")
        self.assertEqual(
            result.meaning,
            "The rider chose networking as his career direction.",
        )
        self.assertEqual(result.confidence, 0.96)
        self.assertEqual(result.importance, 0.91)
        self.assertEqual(evaluator.received_context, context)


class FawkesRelationshipSemanticMemoryTests(unittest.TestCase):
    def test_semantic_evaluator_can_classify_shared_inside_joke(self):
        from src.memory.semantic import SemanticMemoryAssessment
        from src.memory.semantic_provider import ModelSemanticMemoryEvaluator

        class FakeProvider:
            def evaluate_memory(self, *, content, conversation_context=()):
                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="inside_joke",
                    meaning="A recurring playful way Tanner addresses Fawkes.",
                    confidence=0.95,
                    importance=0.70,
                    reasoning="The shared conversational context establishes this as relationship humor.",
                )

        evaluator = ModelSemanticMemoryEvaluator(FakeProvider())

        result = evaluator.evaluate(
            content="you little fawker",
            conversation_context=(
                {
                    "role": "assistant",
                    "content": "Absolutely, dingus mode engaged.",
                },
                {
                    "role": "user",
                    "content": "next command you lil fawker",
                },
            ),
        )

        self.assertTrue(result.should_remember)
        self.assertEqual(result.memory_type, "inside_joke")
        self.assertIn("playful", result.meaning.lower())
        self.assertGreaterEqual(result.confidence, 0.90)


if __name__ == "__main__":
    unittest.main()

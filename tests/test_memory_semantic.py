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


if __name__ == "__main__":
    unittest.main()

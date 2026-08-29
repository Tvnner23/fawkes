import unittest

from src.memory.compare import MemoryComparison, compare_memory


class FakeMatcher:
    def __init__(self):
        self.received = None

    def compare(
        self,
        *,
        new_meaning,
        new_memory_type,
        existing_memory,
        conversation_context=(),
    ):
        self.received = {
            "new_meaning": new_meaning,
            "new_memory_type": new_memory_type,
            "existing_memory": existing_memory,
            "conversation_context": conversation_context,
        }

        return MemoryComparison(
            relation="supports",
            confidence=0.92,
            reasoning="The new evidence reinforces the existing preference.",
        )


class FawkesMemoryComparisonTests(unittest.TestCase):
    def test_memory_matcher_is_provider_independent(self):
        matcher = FakeMatcher()

        existing = {
            "memory_id": "memory-1",
            "memory_type": "preference",
            "content": "The rider prefers concise instructions.",
        }

        result = compare_memory(
            matcher,
            new_meaning="The rider prefers commands before explanations.",
            new_memory_type="preference",
            existing_memory=existing,
        )

        self.assertEqual(result.relation, "supports")
        self.assertEqual(result.confidence, 0.92)

    def test_comparison_context_is_forwarded(self):
        matcher = FakeMatcher()

        context = (
            {"role": "assistant", "content": "Should I put commands first?"},
            {"role": "user", "content": "Yeah, that's the one."},
        )

        existing = {
            "memory_id": "memory-2",
            "memory_type": "preference",
            "content": "The rider has a preferred instruction format.",
        }

        compare_memory(
            matcher,
            new_meaning="The rider prefers commands first.",
            new_memory_type="preference",
            existing_memory=existing,
            conversation_context=context,
        )

        self.assertEqual(
            matcher.received["conversation_context"],
            context,
        )


if __name__ == "__main__":
    unittest.main()

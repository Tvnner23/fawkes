import unittest

from src.memory.preflight import (
    estimate_context_chars,
    estimate_request_chars,
    preflight_candidate,
)


class FawkesMemoryPreflightTests(unittest.TestCase):

    def test_context_size_is_estimated(self):
        context = (
            {
                "role": "assistant",
                "content": "Hello",
            },
            {
                "role": "user",
                "content": "World",
            },
        )

        size = estimate_context_chars(context)

        self.assertGreater(size, 0)

    def test_request_size_includes_candidate(self):
        context = (
            {
                "role": "assistant",
                "content": "Hello",
            },
        )

        context_size = estimate_context_chars(context)

        request_size = estimate_request_chars(
            content="World",
            conversation_context=context,
        )

        self.assertEqual(
            request_size,
            context_size + len("World"),
        )

    def test_safe_request_passes_preflight(self):
        context = (
            {
                "role": "assistant",
                "content": "Hello",
            },
        )

        size = preflight_candidate(
            content="World",
            conversation_context=context,
            max_request_chars=1_000,
        )

        self.assertGreater(size, 0)

    def test_oversized_request_is_rejected(self):
        context = (
            {
                "role": "assistant",
                "content": "A" * 1_000,
            },
        )

        with self.assertRaises(ValueError):
            preflight_candidate(
                content="B" * 1_000,
                conversation_context=context,
                max_request_chars=100,
            )


if __name__ == "__main__":
    unittest.main()

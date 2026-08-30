import unittest
from unittest.mock import patch

from src.memory.archive_context import build_archive_context


class FawkesArchiveContextWindowTests(unittest.TestCase):

    def setUp(self):
        self.canonical = tuple(
            {
                "message_id": f"message-{i}",
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"message content {i}",
            }
            for i in range(10)
        )

    def test_centered_context_includes_candidate_and_neighbors(self):
        with patch(
            "src.memory.archive_context.canonical_messages",
            return_value=self.canonical,
        ):
            context = build_archive_context(
                "conversation-1",
                center_message_id="message-5",
                before=2,
                after=2,
            )

        self.assertEqual(
            [message["content"] for message in context],
            [
                "message content 3",
                "message content 4",
                "message content 5",
                "message content 6",
                "message content 7",
            ],
        )

    def test_centered_context_clips_at_start_of_conversation(self):
        with patch(
            "src.memory.archive_context.canonical_messages",
            return_value=self.canonical,
        ):
            context = build_archive_context(
                "conversation-1",
                center_message_id="message-1",
                before=5,
                after=2,
            )

        self.assertEqual(
            [message["content"] for message in context],
            [
                "message content 0",
                "message content 1",
                "message content 2",
                "message content 3",
            ],
        )

    def test_centered_context_clips_at_end_of_conversation(self):
        with patch(
            "src.memory.archive_context.canonical_messages",
            return_value=self.canonical,
        ):
            context = build_archive_context(
                "conversation-1",
                center_message_id="message-8",
                before=2,
                after=5,
            )

        self.assertEqual(
            [message["content"] for message in context],
            [
                "message content 6",
                "message content 7",
                "message content 8",
                "message content 9",
            ],
        )

    def test_unknown_center_message_is_rejected(self):
        with patch(
            "src.memory.archive_context.canonical_messages",
            return_value=self.canonical,
        ):
            with self.assertRaises(ValueError):
                build_archive_context(
                    "conversation-1",
                    center_message_id="does-not-exist",
                )

    def test_legacy_tail_window_still_works(self):
        with patch(
            "src.memory.archive_context.canonical_messages",
            return_value=self.canonical,
        ):
            context = build_archive_context(
                "conversation-1",
                max_messages=3,
            )

        self.assertEqual(
            [message["content"] for message in context],
            [
                "message content 7",
                "message content 8",
                "message content 9",
            ],
        )


if __name__ == "__main__":
    unittest.main()


class FawkesCandidateContextTests(unittest.TestCase):
    def test_dry_run_uses_candidate_centered_context(self):
        from src.memory.dry_run import dry_run_conversation

        class FakeEvaluator:
            def __init__(self):
                self.contexts = []

            def evaluate(self, *, content, conversation_context=()):
                from src.memory.semantic import SemanticMemoryAssessment

                self.contexts.append(tuple(conversation_context))

                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="career_goal",
                    meaning="The user chose networking.",
                    confidence=0.99,
                    importance=0.90,
                )

        candidates = [
            {
                "candidate_id": "message-5",
                "content": "Yeah, that's the one.",
                "memory_type": "unclassified",
                "importance": None,
                "confidence": None,
                "source_message_ids": ("message-5",),
                "source_archive_ids": ("archive-5",),
                "created_at": "2026-08-29T00:05:00",
            }
        ]

        canonical = tuple(
            {
                "message_id": f"message-{i}",
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"message content {i}",
            }
            for i in range(10)
        )

        evaluator = FakeEvaluator()

        with patch(
            "src.memory.dry_run.extract_memory_candidates",
            return_value=candidates,
        ), patch(
            "src.memory.dry_run.gate_memory_candidates",
            return_value=candidates,
        ), patch(
            "src.memory.dry_run.build_archive_context",
            return_value=tuple(
                {
                    "role": message["role"],
                    "content": message["content"],
                }
                for message in canonical[3:8]
            ),
        ):
            report = dry_run_conversation(
                "conversation-1",
                evaluator=evaluator,
                context_before=2,
                context_after=2,
            )

        self.assertEqual(len(report["results"]), 1)
        self.assertEqual(
            report["results"][0]["context_message_count"],
            5,
        )
        self.assertEqual(
            [m["content"] for m in evaluator.contexts[0]],
            [
                "message content 3",
                "message content 4",
                "message content 5",
                "message content 6",
                "message content 7",
            ],
        )


if __name__ == "__main__":
    unittest.main()

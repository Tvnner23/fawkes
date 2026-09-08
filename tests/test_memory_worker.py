import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import src.memory.store as store
from src.memory.ledger import (
    discover_candidate,
    get_work_item,
    recover_stale_work_items,
    update_work_item,
)
from src.memory.semantic import SemanticMemoryAssessment
from src.memory.worker import (
    apply_accepted_batch,
    apply_next_accepted,
    discover_history,
    evaluate_batch,
    evaluate_next,
)


class RememberingEvaluator:
    def evaluate(self, *, content, conversation_context=()):
        return SemanticMemoryAssessment(
            should_remember=True,
            memory_type="decision",
            meaning="The rider chose SQLite for the canonical index.",
            confidence=0.95,
            importance=0.9,
            reasoning="An explicit architecture decision.",
            supporting_message_ids=("message-1",),
            supporting_archive_ids=("archive-1",),
        )


class FailingEvaluator:
    def evaluate(self, *, content, conversation_context=()):
        raise ConnectionError("temporary provider failure")


class ContextOnlyEvaluator:
    def evaluate(self, *, content, conversation_context=()):
        return SemanticMemoryAssessment(
            should_remember=True,
            memory_type="goal",
            meaning="The rider plans to become a network engineer.",
            confidence=0.95,
            importance=0.9,
            reasoning="The fact appears only in a neighboring message.",
            supporting_message_ids=("message-context",),
            supporting_archive_ids=("archive-context",),
        )


class MultiMessageEvaluator:
    def evaluate(self, *, content, conversation_context=()):
        return SemanticMemoryAssessment(
            should_remember=True,
            memory_type="goal",
            meaning="The rider chose networking as a career direction.",
            confidence=0.97,
            importance=0.9,
            reasoning="The candidate confirms the option named immediately before it.",
            supporting_message_ids=("message-context", "message-1"),
            supporting_archive_ids=("archive-context", "archive-1"),
        )


class MemoryWorkerTests(unittest.TestCase):
    def _queued_item(self, path):
        item = discover_candidate(
            instance_id="fawkes",
            conversation_id="conversation-1",
            message_id="message-1",
            canonical_revision="archive-1",
            source_archive_ids=("archive-1",),
            candidate_content="We chose SQLite for the canonical index.",
            path=path,
        )
        return update_work_item(
            item["work_item_id"], status="queued", path=path
        )

    def test_evaluation_is_persisted_before_memory_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.sqlite3"
            self._queued_item(ledger)

            with patch(
                "src.memory.worker.build_archive_context", return_value=()
            ):
                evaluated = evaluate_next(
                    instance_id="fawkes",
                    evaluator=RememberingEvaluator(),
                    path=ledger,
                )

            self.assertEqual(evaluated["status"], "accepted")
            self.assertEqual(evaluated["decision"], "accept")
            self.assertEqual(evaluated["assessment"]["audit"]["tier"], "S")

    def test_approved_application_is_instance_scoped_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.sqlite3"
            records = root / "records"
            events = root / "events"
            queued = self._queued_item(ledger)
            assessment = RememberingEvaluator().evaluate(
                content="candidate"
            )
            accepted = update_work_item(
                queued["work_item_id"],
                status="accepted",
                decision="accept",
                assessment={
                    "semantic": {
                        "should_remember": assessment.should_remember,
                        "memory_type": assessment.memory_type,
                        "meaning": assessment.meaning,
                        "confidence": assessment.confidence,
                        "importance": assessment.importance,
                        "reasoning": assessment.reasoning,
                        "supporting_message_ids": ["message-1"],
                        "supporting_archive_ids": ["archive-1"],
                    },
                    "audit": {"decision": "accept", "tier": "S"},
                },
                path=ledger,
            )

            with patch.object(store, "MEMORY_RECORDS_DIR", records), patch.object(
                store, "MEMORY_EVENTS_DIR", events
            ), patch(
                "src.memory.worker.build_archive_context", return_value=()
            ):
                applied = apply_next_accepted(
                    instance_id="fawkes", path=ledger
                )
                update_work_item(
                    accepted["work_item_id"], status="accepted", path=ledger
                )
                recovered = apply_next_accepted(
                    instance_id="fawkes", path=ledger
                )
                memories = store.list_memories(
                    status="active", instance_id="fawkes"
                )
                other = store.list_memories(
                    status="active", instance_id="other"
                )

            self.assertEqual(applied["status"], "consolidated")
            self.assertEqual(recovered["status"], "consolidated")
            self.assertEqual(len(memories), 1)
            self.assertEqual(other, [])
            self.assertIn(
                accepted["work_item_id"], memories[0]["source_work_item_ids"]
            )

    def test_stale_evaluation_is_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite3"
            queued = self._queued_item(ledger)
            update_work_item(
                queued["work_item_id"], status="evaluating", path=ledger
            )
            recovered = recover_stale_work_items(
                instance_id="fawkes",
                older_than=datetime.now(timezone.utc) + timedelta(seconds=1),
                path=ledger,
            )
            item = get_work_item(queued["work_item_id"], path=ledger)

            self.assertEqual(recovered, 1)
            self.assertEqual(item["status"], "queued")

    def test_failed_evaluation_consumes_only_one_batch_slot_per_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite3"
            first = self._queued_item(ledger)
            second = discover_candidate(
                instance_id="fawkes",
                conversation_id="conversation-2",
                message_id="message-2",
                canonical_revision="archive-2",
                source_archive_ids=("archive-2",),
                candidate_content="I prefer concise technical explanations.",
                path=ledger,
            )
            update_work_item(second["work_item_id"], status="queued", path=ledger)

            with patch(
                "src.memory.worker.build_archive_context", return_value=()
            ):
                results = evaluate_batch(
                    instance_id="fawkes",
                    evaluator=FailingEvaluator(),
                    limit=10,
                    path=ledger,
                )

            self.assertEqual(len(results), 2)
            self.assertEqual(
                {item["work_item_id"] for item in results},
                {first["work_item_id"], second["work_item_id"]},
            )
            self.assertTrue(
                all(item["status"] == "failed_evaluation_retryable" for item in results)
            )
            self.assertTrue(all(item["attempt_count"] == 1 for item in results))

    def test_candidate_only_support_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite3"
            self._queued_item(ledger)
            with patch(
                "src.memory.worker.build_archive_context", return_value=()
            ):
                result = evaluate_next(
                    instance_id="fawkes",
                    evaluator=RememberingEvaluator(),
                    path=ledger,
                )

            self.assertEqual(result["status"], "accepted")
            self.assertEqual(
                result["assessment"]["semantic"]["supporting_message_ids"],
                ["message-1"],
            )

    def test_context_only_unsupported_fact_requires_review(self):
        context = (
            {
                "role": "assistant",
                "content": "You plan to become a network engineer.",
                "message_id": "message-context",
                "source_archive_id": "archive-context",
                "instance_id": "fawkes",
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite3"
            self._queued_item(ledger)
            with patch(
                "src.memory.worker.build_archive_context", return_value=context
            ):
                result = evaluate_next(
                    instance_id="fawkes",
                    evaluator=ContextOnlyEvaluator(),
                    path=ledger,
                )

            self.assertEqual(result["status"], "review")
            self.assertIn("candidate message", result["decision_reason"])

    def test_multi_message_conclusion_persists_all_supporting_provenance(self):
        context = (
            {
                "role": "assistant",
                "content": "Was networking the career direction you chose?",
                "message_id": "message-context",
                "source_archive_id": "archive-context",
                "instance_id": "fawkes",
            },
            {
                "role": "user",
                "content": "Yes, that's the one.",
                "message_id": "message-1",
                "source_archive_id": "archive-1",
                "instance_id": "fawkes",
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.sqlite3"
            records = root / "records"
            events = root / "events"
            self._queued_item(ledger)
            with patch(
                "src.memory.worker.build_archive_context", return_value=context
            ):
                evaluated = evaluate_next(
                    instance_id="fawkes",
                    evaluator=MultiMessageEvaluator(),
                    path=ledger,
                )
            self.assertEqual(evaluated["status"], "accepted")

            with patch.object(store, "MEMORY_RECORDS_DIR", records), patch.object(
                store, "MEMORY_EVENTS_DIR", events
            ), patch(
                "src.memory.worker.build_archive_context", return_value=context
            ):
                applied = apply_next_accepted(
                    instance_id="fawkes", path=ledger
                )
                memory = store.load_memory(applied["resulting_memory_ids"][0])

            self.assertEqual(
                set(memory["source_message_ids"]),
                {"message-1", "message-context"},
            )
            self.assertEqual(
                set(memory["source_archive_ids"]),
                {"archive-1", "archive-context"},
            )

    def test_failed_consolidation_consumes_only_one_batch_slot_per_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite3"
            first = self._queued_item(ledger)
            second = discover_candidate(
                instance_id="fawkes",
                conversation_id="conversation-2",
                message_id="message-2",
                canonical_revision="archive-2",
                source_archive_ids=("archive-2",),
                candidate_content="Substantive candidate two.",
                path=ledger,
            )
            for item in (first, second):
                update_work_item(
                    item["work_item_id"],
                    status="accepted",
                    decision="accept",
                    assessment={"semantic": None, "audit": {"decision": "accept"}},
                    path=ledger,
                )

            results = apply_accepted_batch(
                instance_id="fawkes", limit=10, path=ledger
            )

            self.assertEqual(len(results), 2)
            self.assertEqual(
                {item["work_item_id"] for item in results},
                {first["work_item_id"], second["work_item_id"]},
            )
            self.assertTrue(
                all(
                    item["status"] == "failed_consolidation_retryable"
                    for item in results
                )
            )
            self.assertTrue(all(item["attempt_count"] == 1 for item in results))

    def test_history_discovery_limit_advances_past_existing_items(self):
        messages = [
            {
                "message_id": f"message-{index}",
                "role": "user",
                "content": f"Candidate {index}",
                "created_at": f"2026-01-0{index + 1}T00:00:00+00:00",
                "source_archive_id": f"archive-{index}",
                "instance_id": "fawkes",
            }
            for index in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.memory.worker.list_conversation_ids",
            return_value=("conversation-1",),
        ), patch(
            "src.memory.worker.canonical_messages", return_value=messages
        ):
            ledger = Path(tmp) / "ledger.sqlite3"
            first = discover_history(
                instance_id="fawkes", limit=1, path=ledger
            )
            second = discover_history(
                instance_id="fawkes", limit=1, path=ledger
            )

            self.assertEqual(first[0]["message_id"], "message-0")
            self.assertEqual(second[0]["message_id"], "message-1")


if __name__ == "__main__":
    unittest.main()

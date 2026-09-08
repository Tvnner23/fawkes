import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import src.ingest as ingest
import src.instances as instances
from src.memory.archive_retrieval import (
    index_canonical_message,
    rebuild_archive_index,
    retrieve_archive_passages,
)
from src.memory.ledger import (
    discover_candidate,
    list_work_items,
    update_work_item,
)


class FawkesCaptureEventTests(unittest.TestCase):
    def test_replayed_event_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            meta = root / "meta"

            with patch.object(ingest, "RAW_DIR", raw), patch.object(
                ingest,
                "META_DIR",
                meta,
            ):
                raw.mkdir()
                meta.mkdir()

                first = ingest.ingest_bytes(
                    b"same capture",
                    "Capture",
                    source="browser_live",
                    capture_type="near_live",
                    capture_event_id="event-1",
                )
                replay = ingest.ingest_bytes(
                    b"same capture",
                    "Capture",
                    source="browser_live",
                    capture_type="near_live",
                    capture_event_id="event-1",
                )

            self.assertEqual(first["archive_id"], replay["archive_id"])
            self.assertFalse(first["_capture_event_replayed"])
            self.assertTrue(replay["_capture_event_replayed"])
            self.assertEqual(len(list(raw.glob("*"))), 1)
            self.assertEqual(len(list(meta.glob("*.json"))), 1)

    def test_separate_events_can_reuse_one_blob(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            meta = root / "meta"

            with patch.object(ingest, "RAW_DIR", raw), patch.object(
                ingest,
                "META_DIR",
                meta,
            ):
                raw.mkdir()
                meta.mkdir()

                first = ingest.ingest_bytes(
                    b"shared bytes",
                    "First observation",
                    source="browser_live",
                    capture_type="near_live",
                    conversation_id="conversation-1",
                    capture_event_id="event-1",
                )
                second = ingest.ingest_bytes(
                    b"shared bytes",
                    "Second observation",
                    source="browser_live",
                    capture_type="near_live",
                    conversation_id="conversation-2",
                    capture_event_id="event-2",
                )

                saved = [
                    json.loads(path.read_text(encoding="utf-8"))
                    for path in meta.glob("*.json")
                ]

            self.assertNotEqual(first["archive_id"], second["archive_id"])
            self.assertEqual(first["raw_file"], second["raw_file"])
            self.assertFalse(first["blob_reused"])
            self.assertTrue(second["blob_reused"])
            self.assertEqual(len(list(raw.glob("*"))), 1)
            self.assertEqual(len(saved), 2)
            self.assertEqual(
                {record["capture_event_id"] for record in saved},
                {"event-1", "event-2"},
            )


class FawkesDefaultInstanceTests(unittest.TestCase):
    def test_default_fawkes_instance_is_stable(self):
        with TemporaryDirectory() as tmp:
            instance_dir = Path(tmp) / "instances"
            registry = instance_dir / "registry.json"

            with patch.object(instances, "INSTANCE_DIR", instance_dir), patch.object(
                instances,
                "REGISTRY_PATH",
                registry,
            ), patch.dict("os.environ", {}, clear=True):
                first = instances.get_or_create_default_instance()
                second = instances.get_or_create_default_instance()

            self.assertEqual(first["instance_id"], second["instance_id"])
            self.assertEqual(first["name"], "Fawkes")


class FawkesArchiveRetrievalIndexTests(unittest.TestCase):
    def test_index_is_instance_scoped_and_returns_provenance(self):
        messages = (
            {
                "message_id": "message-1",
                "role": "user",
                "content": "We chose SQLite for the historical index.",
                "created_at": "2026-08-30T00:00:00+00:00",
                "source_archive_id": "archive-1",
                "instance_id": "fawkes",
            },
        )

        with TemporaryDirectory() as tmp, patch(
            "src.memory.archive_retrieval.list_conversation_ids",
            return_value=("conversation-1",),
        ), patch(
            "src.memory.archive_retrieval.canonical_messages",
            return_value=messages,
        ):
            path = Path(tmp) / "archive.sqlite3"
            count = rebuild_archive_index(instance_id="fawkes", path=path)
            results = retrieve_archive_passages(
                "historical SQLite",
                instance_id="fawkes",
                path=path,
            )
            other = retrieve_archive_passages(
                "historical SQLite",
                instance_id="other-phoenix",
                path=path,
            )

        self.assertEqual(count, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_archive_id"], "archive-1")
        self.assertEqual(other, [])

    def test_vague_return_message_does_not_retrieve_procedural_history(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.sqlite3"
            index_canonical_message(
                instance_id="fawkes",
                conversation_id="old-coding-session",
                message_id="old-command",
                role="assistant",
                content="Back to the exact step. Run: cat .gitignore and paste it.",
                created_at="2026-08-29T00:00:00+00:00",
                source_archive_id="archive-command",
                path=path,
            )

            self.assertEqual(
                retrieve_archive_passages(
                    "and were back", instance_id="fawkes", path=path
                ),
                [],
            )
            self.assertEqual(
                retrieve_archive_passages(
                    "and we're back", instance_id="fawkes", path=path
                ),
                [],
            )

    def test_greeting_does_not_trigger_broad_historical_retrieval(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.sqlite3"
            index_canonical_message(
                instance_id="fawkes",
                conversation_id="old-session",
                message_id="hello",
                role="assistant",
                content="Hello Fawkes. Run this old command.",
                created_at="2026-08-29T00:00:00+00:00",
                source_archive_id="archive-hello",
                path=path,
            )
            self.assertEqual(
                retrieve_archive_passages(
                    "hello Fawkes", instance_id="fawkes", path=path
                ),
                [],
            )

    def test_procedural_history_requires_explicit_procedural_query(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.sqlite3"
            index_canonical_message(
                instance_id="fawkes",
                conversation_id="old-coding-session",
                message_id="old-command",
                role="assistant",
                content="Use this gitignore command: cat .gitignore",
                created_at="2026-08-29T00:00:00+00:00",
                source_archive_id="archive-command",
                path=path,
            )
            vague = retrieve_archive_passages(
                "What did we use?", instance_id="fawkes", path=path
            )
            explicit = retrieve_archive_passages(
                "What gitignore command did we use?",
                instance_id="fawkes",
                path=path,
            )

            self.assertEqual(vague, [])
            self.assertEqual(len(explicit), 1)
            self.assertEqual(explicit[0]["message_id"], "old-command")

    def test_relevant_history_is_recalled_without_explicit_memory_request(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.sqlite3"
            index_canonical_message(
                instance_id="fawkes",
                conversation_id="project-history",
                message_id="browser-capture-decision",
                role="user",
                content=(
                    "For browser capture, structured message extraction should "
                    "remain primary and DOM text should remain the fallback."
                ),
                created_at="2026-08-29T00:00:00+00:00",
                source_archive_id="archive-browser-decision",
                path=path,
            )

            results = retrieve_archive_passages(
                "How should we continue the browser capture work?",
                instance_id="fawkes",
                path=path,
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(
                results[0]["message_id"], "browser-capture-decision"
            )
            self.assertEqual(results[0]["matched_terms"], ["browser", "capture"])

    def test_current_conversation_is_left_to_recent_context_path(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.sqlite3"
            for conversation_id, message_id in (
                ("current", "current-message"),
                ("historical", "historical-message"),
            ):
                index_canonical_message(
                    instance_id="fawkes",
                    conversation_id=conversation_id,
                    message_id=message_id,
                    role="user",
                    content="Subnetting uses network masks.",
                    created_at="2026-08-29T00:00:00+00:00",
                    source_archive_id=f"archive-{message_id}",
                    path=path,
                )

            results = retrieve_archive_passages(
                "Where did we discuss subnetting network masks?",
                instance_id="fawkes",
                exclude_conversation_id="current",
                path=path,
            )

            self.assertEqual(
                [result["message_id"] for result in results],
                ["historical-message"],
            )


class FawkesProcessingLedgerTests(unittest.TestCase):
    def test_discovery_is_idempotent_and_progress_is_observable(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite3"
            first = discover_candidate(
                instance_id="fawkes",
                conversation_id="conversation-1",
                message_id="message-1",
                canonical_revision="archive-1",
                source_archive_ids=("archive-1",),
                path=path,
            )
            second = discover_candidate(
                instance_id="fawkes",
                conversation_id="conversation-1",
                message_id="message-1",
                canonical_revision="archive-1",
                source_archive_ids=("archive-1",),
                path=path,
            )
            updated = update_work_item(
                first["work_item_id"],
                status="failed_retryable",
                error="provider unavailable",
                increment_attempt=True,
                path=path,
            )
            items = list_work_items(instance_id="fawkes", path=path)

        self.assertEqual(first["work_item_id"], second["work_item_id"])
        self.assertEqual(len(items), 1)
        self.assertEqual(updated["status"], "failed_retryable")
        self.assertEqual(updated["attempt_count"], 1)
        self.assertEqual(updated["source_archive_ids"], ["archive-1"])


if __name__ == "__main__":
    unittest.main()

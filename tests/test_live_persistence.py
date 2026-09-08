import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import src.ingest as ingest
import src.memory.archive_retrieval as archive_retrieval
from src.memory.archive_retrieval import ensure_archive_index, retrieve_archive_passages
from src.runtime.persistence import persist_live_message


class FawkesLivePersistenceTests(unittest.TestCase):
    def _patch_storage(self, root):
        return (
            patch.object(ingest, "RAW_DIR", root / "raw"),
            patch.object(ingest, "META_DIR", root / "meta"),
            patch.object(
                archive_retrieval, "INDEX_PATH", root / "canonical.sqlite3"
            ),
        )

    def test_live_message_is_immediately_searchable_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_patch, meta_patch, index_patch = self._patch_storage(root)
            with raw_patch, meta_patch, index_patch:
                metadata = persist_live_message(
                    instance_id="fawkes",
                    conversation_id="conversation-1",
                    message_id="message-1",
                    role="user",
                    text="I prefer private local conversations.",
                )
                results = retrieve_archive_passages(
                    "private conversations",
                    instance_id="fawkes",
                    path=root / "canonical.sqlite3",
                )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["message_id"], "message-1")
            self.assertEqual(
                results[0]["source_archive_id"], metadata["archive_id"]
            )

    def test_live_persistence_keeps_complete_receipt_but_prints_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_patch, meta_patch, index_patch = self._patch_storage(root)
            output = StringIO()
            with raw_patch, meta_patch, index_patch, redirect_stdout(output):
                metadata = persist_live_message(
                    instance_id="fawkes",
                    conversation_id="conversation-1",
                    message_id="message-1",
                    role="user",
                    text="Keep the conversation clean.",
                )

            self.assertEqual(output.getvalue(), "")
            self.assertTrue(metadata["archive_id"])
            self.assertTrue(metadata["sha256"])
            self.assertEqual(metadata["conversation_id"], "conversation-1")
            self.assertEqual(metadata["instance_id"], "fawkes")
            self.assertIn("message-1", metadata["capture_event_id"])

    def test_explicit_ingest_path_still_prints_audit_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_patch, meta_patch, _ = self._patch_storage(root)
            output = StringIO()
            with raw_patch, meta_patch, redirect_stdout(output):
                metadata = ingest.ingest_bytes(
                    b"auditable payload",
                    "Audit capture",
                    source="test",
                    capture_type="text",
                )

            receipt = output.getvalue()
            self.assertIn(f"Archived: {metadata['archive_id']}", receipt)
            self.assertIn(f"SHA-256: {metadata['sha256']}", receipt)

    def test_replaying_same_live_message_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_patch, meta_patch, index_patch = self._patch_storage(root)
            with raw_patch, meta_patch, index_patch:
                kwargs = {
                    "instance_id": "fawkes",
                    "conversation_id": "conversation-1",
                    "message_id": "message-1",
                    "role": "user",
                    "text": "Same durable turn.",
                }
                first = persist_live_message(**kwargs)
                second = persist_live_message(**kwargs)
                results = retrieve_archive_passages(
                    "durable turn",
                    instance_id="fawkes",
                    path=root / "canonical.sqlite3",
                )

            self.assertEqual(first["archive_id"], second["archive_id"])
            self.assertTrue(second["_capture_event_replayed"])
            self.assertEqual(len(results), 1)

    def test_identical_text_in_distinct_turns_keeps_distinct_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_patch, meta_patch, index_patch = self._patch_storage(root)
            with raw_patch, meta_patch, index_patch:
                first = persist_live_message(
                    instance_id="fawkes",
                    conversation_id="conversation-1",
                    message_id="message-1",
                    role="user",
                    text="Hello Fawkes.",
                )
                second = persist_live_message(
                    instance_id="fawkes",
                    conversation_id="conversation-2",
                    message_id="message-2",
                    role="user",
                    text="Hello Fawkes.",
                )

            self.assertNotEqual(first["archive_id"], second["archive_id"])
            self.assertNotEqual(first["capture_event_id"], second["capture_event_id"])
            self.assertEqual(first["conversation_id"], "conversation-1")
            self.assertEqual(second["conversation_id"], "conversation-2")

    def test_missing_archive_index_is_rebuilt_on_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.sqlite3"
            with patch(
                "src.memory.archive_retrieval.rebuild_archive_index",
                return_value=42,
            ) as rebuild:
                result = ensure_archive_index(
                    instance_id="fawkes",
                    include_unscoped=True,
                    path=path,
                )

            self.assertEqual(result, {"rebuilt": True, "indexed": 42})
            rebuild.assert_called_once_with(
                instance_id="fawkes", include_unscoped=True, path=path
            )

    def test_populated_archive_index_is_not_rebuilt_on_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "canonical.sqlite3"
            archive_retrieval.index_canonical_message(
                instance_id="fawkes",
                conversation_id="conversation-1",
                message_id="message-1",
                role="user",
                content="Persisted history.",
                created_at="2026-01-01T00:00:00+00:00",
                source_archive_id="archive-1",
                path=path,
            )
            with patch(
                "src.memory.archive_retrieval.rebuild_archive_index"
            ) as rebuild:
                result = ensure_archive_index(
                    instance_id="fawkes", path=path
                )

            self.assertEqual(result, {"rebuilt": False, "indexed": 0})
            rebuild.assert_not_called()


if __name__ == "__main__":
    unittest.main()

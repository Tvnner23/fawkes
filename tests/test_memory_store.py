import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.store as store


class FawkesMemoryStoreTests(unittest.TestCase):
    def test_memory_records_and_events_use_separate_runtime_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                memory = store.create_memory(
                    "goal",
                    "Build Phoenix continuity.",
                    source_message_ids=("message-1",),
                    source_archive_ids=("archive-1",),
                )

                event = store.append_memory_event(
                    memory.memory_id,
                    "created",
                    data={"memory_type": memory.memory_type},
                    source_message_ids=memory.source_message_ids,
                    source_archive_ids=memory.source_archive_ids,
                )

                memory_path = records / f"{memory.memory_id}.json"
                event_path = events / f"{event['event_id']}.json"

                self.assertTrue(memory_path.exists())
                self.assertTrue(event_path.exists())

                saved_event = json.loads(event_path.read_text(encoding="utf-8"))

                self.assertEqual(saved_event["memory_id"], memory.memory_id)
                self.assertEqual(saved_event["event_type"], "created")
                self.assertEqual(saved_event["source_message_ids"], ["message-1"])
                self.assertEqual(saved_event["source_archive_ids"], ["archive-1"])

    def test_append_memory_event_does_not_modify_memory_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                memory = store.create_memory(
                    "preference",
                    "The rider prefers concise answers.",
                )

                memory_path = records / f"{memory.memory_id}.json"
                before = memory_path.read_bytes()

                store.append_memory_event(
                    memory.memory_id,
                    "confidence_changed",
                    data={"confidence": 0.8},
                )

                after = memory_path.read_bytes()

                self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

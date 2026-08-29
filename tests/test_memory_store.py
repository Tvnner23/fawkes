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

    def test_create_memory_automatically_writes_created_event(self):
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

                event_files = list(events.glob("*.json"))
                self.assertEqual(len(event_files), 1)

                saved_event = json.loads(
                    event_files[0].read_text(encoding="utf-8")
                )

                self.assertEqual(saved_event["memory_id"], memory.memory_id)
                self.assertEqual(saved_event["event_type"], "created")
                self.assertEqual(saved_event["data"]["memory_type"], "goal")
                self.assertEqual(
                    saved_event["data"]["content"],
                    "Build Phoenix continuity.",
                )
                self.assertEqual(
                    saved_event["source_message_ids"],
                    ["message-1"],
                )
                self.assertEqual(
                    saved_event["source_archive_ids"],
                    ["archive-1"],
                )

    def test_revise_memory_updates_current_state_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                memory = store.create_memory(
                    "preference",
                    "The rider prefers short progress updates.",
                    source_message_ids=("message-1",),
                )

                revised = store.revise_memory(
                    memory.memory_id,
                    content="The rider prefers detailed progress updates with XP bars.",
                    confidence=0.95,
                    source_message_ids=("message-2",),
                )

                self.assertIsNotNone(revised)
                self.assertEqual(
                    revised["content"],
                    "The rider prefers detailed progress updates with XP bars.",
                )
                self.assertEqual(revised["confidence"], 0.95)
                self.assertEqual(revised["created_at"], memory.created_at)
                self.assertNotEqual(revised["updated_at"], memory.updated_at)

                event_files = list(events.glob("*.json"))
                self.assertEqual(len(event_files), 2)

                saved_events = [
                    json.loads(p.read_text(encoding="utf-8"))
                    for p in event_files
                ]

                revised_events = [
                    e for e in saved_events
                    if e["event_type"] == "revised"
                ]

                self.assertEqual(len(revised_events), 1)
                self.assertEqual(
                    revised_events[0]["data"]["previous"]["content"],
                    "The rider prefers short progress updates.",
                )
                self.assertEqual(
                    revised_events[0]["data"]["current"]["content"],
                    "The rider prefers detailed progress updates with XP bars.",
                )
                self.assertEqual(
                    revised_events[0]["source_message_ids"],
                    ["message-2"],
                )

    def test_supersede_memory_preserves_old_record_and_links_new_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                old = store.create_memory(
                    "goal",
                    "Focus on cybersecurity.",
                    source_message_ids=("message-1",),
                )

                new = store.supersede_memory(
                    old.memory_id,
                    "goal",
                    "Focus primarily on networking.",
                    source_message_ids=("message-2",),
                )

                old_saved = store.load_memory(old.memory_id)
                new_saved = store.load_memory(new.memory_id)

                self.assertEqual(old_saved["status"], "superseded")
                self.assertEqual(new_saved["status"], "active")
                self.assertEqual(new_saved["supersedes"], old.memory_id)

                event_files = list(events.glob("*.json"))
                saved_events = [
                    json.loads(p.read_text(encoding="utf-8"))
                    for p in event_files
                ]

                superseded_events = [
                    e for e in saved_events
                    if e["event_type"] == "superseded"
                    and e["memory_id"] == old.memory_id
                ]

                self.assertEqual(len(superseded_events), 1)
                self.assertEqual(
                    superseded_events[0]["data"]["superseded_by"],
                    new.memory_id,
                )
                self.assertEqual(
                    superseded_events[0]["source_message_ids"],
                    ["message-2"],
                )

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

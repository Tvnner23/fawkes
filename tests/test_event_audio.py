import json
import tempfile
import unittest
from pathlib import Path

from src.capabilities.event_audio import (
    EVENT_SOUND_DEFINITION, SOUND_EVENTS, SoundPreferenceStore,
    public_sound_settings,
)


class EventAudioTests(unittest.TestCase):
    def test_registry_has_approved_slots_and_deferred_unapproved_events(self):
        events = {item.event_id: item for item in SOUND_EVENTS}
        self.assertEqual(len(events), len(SOUND_EVENTS))
        self.assertTrue(events["message.sent"].approved)
        self.assertEqual(events["message.sent"].asset_identity, "Clean Premium 01")
        self.assertFalse(events["thinking.started.male"].approved)
        self.assertEqual(EVENT_SOUND_DEFINITION.authority.execution_boundary, "internal")

    def test_missing_assets_are_never_exposed_as_substitutes(self):
        payload = public_sound_settings("fawkes", root=Path(tempfile.mkdtemp()))
        for item in payload["events"]:
            if not item["available"]:
                self.assertIsNone(item["asset_url"])

    def test_master_and_individual_preferences_persist_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SoundPreferenceStore("fawkes", root=tmp)
            store.update({"master_enabled": False, "volume": 0.4, "events": {"message.sent": True, "message.received": False}})
            loaded = SoundPreferenceStore("fawkes", root=tmp).load()
            self.assertFalse(loaded["master_enabled"])
            self.assertTrue(loaded["events"]["message.sent"])
            self.assertFalse(loaded["events"]["message.received"])
            self.assertEqual(loaded["volume"], 0.4)
            store.update({"master_enabled": True})
            self.assertFalse(store.load()["events"]["message.received"])

    def test_invalid_or_unknown_preferences_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SoundPreferenceStore("fawkes", root=tmp)
            with self.assertRaises(ValueError): store.update({"volume": 2})
            with self.assertRaises(ValueError): store.update({"events": {"secret.sound": True}})

    def test_corrupt_preferences_fall_back_without_mutating_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SoundPreferenceStore("fawkes", root=tmp)
            store.path.parent.mkdir(parents=True)
            store.path.write_text("not json", encoding="utf-8")
            loaded = store.load()
            self.assertTrue(loaded["master_enabled"])
            self.assertEqual(store.path.read_text(encoding="utf-8"), "not json")


if __name__ == "__main__":
    unittest.main()

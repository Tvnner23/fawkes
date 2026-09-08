"""Synthetic filesystem tests only; no app initialization or provider calls."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.runtime import personal_recording as recording


def _process_update(root, mode, connection):
    try:
        connection.send("ready")
        connection.recv()
        try:
            policy = recording.RecordingPolicyStore("fawkes", root=root).update(
                {"mode": mode}, expected_revision=0)
            connection.send(("updated", policy.revision, policy.mode))
        except recording.RecordingPolicyConflict:
            connection.send(("conflict",))
    finally:
        connection.close()


class PersonalRecordingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = recording.RecordingPolicyStore("fawkes", root=self.root)

    def put(self, value):
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))

    def test_missing_policy_defaults_without_any_write(self):
        self.assertEqual(list(self.root.iterdir()), [])
        policy = self.store.load()
        self.assertEqual(policy.revision, 0)
        self.assertEqual(policy.mode, "retained")
        self.assertTrue(all(getattr(policy, key) for key in recording.EDITABLE_CATEGORIES))
        self.assertFalse(policy.sensor_retention)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_configured_root_is_resolved_at_construction_and_can_be_overridden(self):
        with patch.dict(os.environ, {"FAWKES_RUNTIME_STATE_ROOT": str(self.root / "configured")}):
            configured = recording.RecordingPolicyStore("fawkes")
            explicit = recording.RecordingPolicyStore("fawkes", root=self.root / "explicit")
        self.assertEqual(configured.path, self.root / "configured/database/preferences/fawkes/personal_recording.json")
        self.assertEqual(explicit.root, self.root / "explicit")
        configured.update({"mode": "private"}, expected_revision=0)
        self.assertEqual(configured.load().mode, "private")
        self.assertFalse(explicit.path.exists())

    def test_update_is_scoped_revisioned_and_preserves_unedited_categories(self):
        other = recording.RecordingPolicyStore("ghost", root=self.root)
        first = self.store.update({"categories": {"memory_learning": False}}, expected_revision=0)
        second = self.store.update({"mode": "private"}, expected_revision=1)
        self.assertEqual((first.revision, second.revision), (1, 2))
        self.assertFalse(second.memory_learning)
        self.assertTrue(second.archive_recording)
        self.assertEqual(self.store.load(), second)
        self.assertEqual(other.load().revision, 0)
        self.assertEqual(other.load().mode, "retained")
        self.assertFalse(other.path.exists())
        self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)

    def test_invalid_instance_identifiers_are_rejected(self):
        for value in (None, "", ".", "..", "../other", "a/b", "a\\b", "a\x00b", "x" * 129):
            with self.subTest(value=value), self.assertRaises(recording.RecordingPolicyError):
                recording.RecordingPolicyStore(value, root=self.root)

    def test_invalid_updates_and_unavailable_sensor_are_rejected_without_writes(self):
        invalid = [None, [], {"unknown": True}, {"revision": 3}, {"instance_id": "other"},
                   {"mode": True}, {"mode": "PRIVATE"}, {"categories": []},
                   {"categories": {"unknown": False}},
                   {"categories": {"sensor_retention": False}},
                   {"categories": {"sensor_retention": True}}]
        invalid.extend({"categories": {"archive_recording": value}}
                       for value in (0, 1, None, "false", [], {}))
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(recording.RecordingPolicyError):
                self.store.update(changes, expected_revision=0)
        for revision in (True, False, -1, 0.0, "0", None):
            with self.subTest(revision=revision), self.assertRaises(recording.RecordingPolicyError):
                self.store.update({}, expected_revision=revision)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_malformed_and_duplicate_json_never_default_or_overwrite(self):
        valid = json.dumps(recording.RecordingPolicy("fawkes").public())
        invalid = [b"\xff", "not json", "null", "[]", "{}", "x" * 16_385,
                   valid.replace('"revision": 0', '"revision": 0, "revision": 1'),
                   valid.replace('"archive_recording": true',
                                 '"archive_recording": true, "archive_recording": false')]
        for data in invalid:
            with self.subTest(data=str(data)[:70]):
                self.put(data)
                before = self.store.path.read_bytes()
                with self.assertRaises(recording.RecordingPolicyError):
                    self.store.load()
                with self.assertRaises(recording.RecordingPolicyError):
                    self.store.update({"mode": "retained"}, expected_revision=0)
                self.assertEqual(self.store.path.read_bytes(), before)

    def test_strict_persisted_schema_owner_and_values(self):
        invalid = []
        for key, value in (("schema_version", True), ("schema_version", 2),
                           ("instance_id", "ghost"), ("revision", True),
                           ("revision", -1), ("mode", "unknown"), ("extra", 1)):
            payload = recording.RecordingPolicy("fawkes").public()
            payload[key] = value
            invalid.append(payload)
        for key, value in (("archive_recording", 1), ("memory_learning", "false"),
                           ("sensor_retention", True), ("unknown", False)):
            payload = recording.RecordingPolicy("fawkes").public()
            payload["categories"][key] = value
            invalid.append(payload)
        payload = recording.RecordingPolicy("fawkes").public()
        del payload["categories"]["social_archive"]
        invalid.append(payload)
        for payload in invalid:
            with self.subTest(payload=payload):
                self.put(json.dumps(payload))
                with self.assertRaises(recording.RecordingPolicyError):
                    self.store.latch()

    def test_symlink_policy_and_ancestor_are_rejected_without_touching_target(self):
        target = self.root / "target.json"
        target.write_text(json.dumps(recording.RecordingPolicy("fawkes").public()))
        self.store.path.parent.mkdir(parents=True)
        self.store.path.symlink_to(target)
        with self.assertRaises(recording.RecordingPolicyError):
            self.store.load()
        with self.assertRaises(recording.RecordingPolicyError):
            self.store.update({"mode": "private"}, expected_revision=0)
        self.assertEqual(json.loads(target.read_text())["revision"], 0)
        alias = self.root / "alias"
        alias.symlink_to(self.root / "database", target_is_directory=True)
        linked = recording.RecordingPolicyStore("fawkes", root=alias)
        with self.assertRaises(recording.RecordingPolicyError):
            linked.load()
        with self.assertRaises(recording.RecordingPolicyError):
            linked.update({}, expected_revision=0)

    def test_nonregular_and_hardlinked_policy_are_rejected(self):
        self.store.path.parent.mkdir(parents=True)
        self.store.path.mkdir()
        with self.assertRaises(recording.RecordingPolicyError):
            self.store.load()
        self.store.path.rmdir()
        os.mkfifo(self.store.path)
        with self.assertRaises(recording.RecordingPolicyError):
            self.store.load()
        self.store.path.unlink()
        target = self.root / "hardlink-target"
        target.write_text(json.dumps(recording.RecordingPolicy("fawkes").public()))
        os.link(target, self.store.path)
        with self.assertRaises(recording.RecordingPolicyError):
            self.store.load()

    def test_symlink_or_nonregular_shared_lock_is_rejected(self):
        self.store.path.parent.mkdir(parents=True)
        lock = self.store.path.with_name(".personal_recording.lock")
        target = self.root / "target"
        target.write_text("untouched")
        lock.symlink_to(target)
        with self.assertRaises(recording.RecordingPolicyError):
            self.store.update({}, expected_revision=0)
        self.assertEqual(target.read_text(), "untouched")
        lock.unlink()
        os.mkfifo(lock)
        with self.assertRaises(recording.RecordingPolicyError):
            self.store.update({}, expected_revision=0)
        self.assertFalse(self.store.path.exists())

    def test_stale_revision_does_not_change_policy(self):
        first = self.store.update({"mode": "private"}, expected_revision=0)
        with self.assertRaises(recording.RecordingPolicyConflict):
            self.store.update({"mode": "retained"}, expected_revision=0)
        self.assertEqual(self.store.load(), first)

    def test_replaced_lock_while_waiting_cannot_publish_policy(self):
        first = self.store.update({"mode": "private"}, expected_revision=0)
        lock = self.store.path.with_name(".personal_recording.lock")
        original = recording.fcntl.flock
        def replace_then_acquire(fd, operation):
            lock.rename(lock.with_suffix(".old"))
            lock.write_bytes(b"")
            return original(fd, operation)
        with patch.object(recording.fcntl, "flock", side_effect=replace_then_acquire):
            with self.assertRaises(recording.RecordingPolicyError):
                self.store.update({"mode": "retained"}, expected_revision=1)
        self.assertEqual(self.store.load(), first)

    def test_replaced_directory_while_waiting_cannot_publish_detached_policy(self):
        first = self.store.update({"mode": "private"}, expected_revision=0)
        folder = self.store.path.parent
        retained = folder.with_name("retained-old-policy")
        original = recording.fcntl.flock
        def replace_then_acquire(fd, operation):
            folder.rename(retained)
            folder.mkdir()
            return original(fd, operation)
        with patch.object(recording.fcntl, "flock", side_effect=replace_then_acquire):
            with self.assertRaises(recording.RecordingPolicyError):
                self.store.update({"mode": "retained"}, expected_revision=1)
        self.assertFalse(self.store.path.exists())
        self.assertEqual(json.loads((retained / self.store.path.name).read_text()), first.public())

    def test_separate_store_concurrent_cas_has_exactly_one_winner(self):
        barrier = threading.Barrier(2)
        def update(mode):
            store = recording.RecordingPolicyStore("fawkes", root=self.root)
            barrier.wait(timeout=5)
            try:
                return store.update({"mode": mode}, expected_revision=0)
            except recording.RecordingPolicyConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, ("private", "retained")))
        self.assertEqual(results.count("conflict"), 1)
        winner = next(value for value in results if value != "conflict")
        self.assertEqual(self.store.load(), winner)
        self.assertEqual(winner.revision, 1)

    def test_separate_process_cas_uses_shared_file_lock(self):
        context = multiprocessing.get_context("fork")
        processes = []
        channels = []
        try:
            for mode in ("private", "retained"):
                parent, child = context.Pipe()
                process = context.Process(target=_process_update,
                                          args=(self.root, mode, child))
                process.start()
                child.close()
                processes.append(process)
                channels.append(parent)
            for channel in channels:
                self.assertTrue(channel.poll(5), "synthetic child did not start")
                self.assertEqual(channel.recv(), "ready")
            for channel in channels:
                channel.send("update")
            results = []
            for channel in channels:
                self.assertTrue(channel.poll(5), "synthetic CAS child did not finish")
                results.append(channel.recv())
            self.assertEqual([item[0] for item in results].count("conflict"), 1)
            winner = next(item for item in results if item[0] == "updated")
            self.assertEqual((self.store.load().revision, self.store.load().mode), winner[1:])
            for process in processes:
                process.join(5)
                self.assertEqual(process.exitcode, 0)
        finally:
            for channel in channels:
                channel.close()
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(5)

    def test_prepublication_failure_preserves_old_policy_and_cleans_temporary(self):
        old = self.store.update({"mode": "private"}, expected_revision=0)
        before = self.store.path.read_bytes()
        for operation in ("replace", "fsync"):
            with self.subTest(operation=operation):
                with patch.object(recording.os, operation, side_effect=OSError("synthetic failure")):
                    with self.assertRaises(recording.RecordingPolicyError):
                        self.store.update({"mode": "retained"}, expected_revision=1)
                self.assertEqual(self.store.path.read_bytes(), before)
                self.assertEqual(self.store.load(), old)
                self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])

    def test_postpublication_sync_failure_reports_uncertainty_not_fake_rollback(self):
        self.store.update({"mode": "private"}, expected_revision=0)
        original = recording.os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory sync failure")
            return original(fd)
        with patch.object(recording.os, "fsync", side_effect=fail_directory):
            with self.assertRaises(recording.RecordingPolicyDurabilityError):
                self.store.update({"mode": "retained"}, expected_revision=1)
        self.assertEqual(self.store.load().revision, 2)
        self.assertEqual(self.store.load().mode, "retained")

    def test_private_and_archive_off_force_all_personal_retention_off(self):
        for changes in ({"mode": "private"},
                        {"mode": "retained", "categories": {"archive_recording": False}}):
            configured = self.store.update(changes, expected_revision=self.store.load().revision)
            self.assertTrue(configured.memory_learning)
            effective = configured.effective(mode="retained")
            self.assertEqual(effective.mode, "private")
            self.assertTrue(all(not getattr(effective, key) for key in recording.CATEGORIES))

    def test_individual_retention_controls_remain_distinct_in_retained_mode(self):
        for category in recording.EDITABLE_CATEGORIES[1:]:
            changes = {name: name != category for name in recording.EDITABLE_CATEGORIES}
            policy = self.store.update({"categories": changes},
                                       expected_revision=self.store.load().revision)
            effective = policy.effective()
            self.assertEqual(effective.mode, "retained")
            self.assertFalse(getattr(effective, category))
            self.assertTrue(all(getattr(effective, name) for name in changes if name != category))
            self.assertFalse(effective.sensor_retention)

    def test_off_on_latches_are_immutable_and_do_not_retain_caller_dicts(self):
        retained = self.store.latch()
        configured = self.store.update({"mode": "private"}, expected_revision=0)
        private = self.store.latch()
        self.store.update({"mode": "retained"}, expected_revision=1)
        self.assertEqual((retained.mode, private.mode, self.store.latch().mode),
                         ("retained", "private", "retained"))
        self.assertEqual((retained.policy_revision, private.policy_revision), (0, 1))
        for value, field in ((configured, "mode"), (private, "archive_recording")):
            with self.assertRaises(FrozenInstanceError):
                setattr(value, field, True)
        public = private.public()
        public["categories"]["archive_recording"] = True
        self.assertFalse(private.archive_recording)
        self.assertFalse(configured.effective().archive_recording)

    def test_per_turn_private_override_is_nonpersistent_and_invalid_modes_fail(self):
        private = self.store.latch(mode="private")
        self.assertEqual(private.mode, "private")
        self.assertEqual(self.store.load().mode, "retained")
        self.assertEqual(list(self.root.iterdir()), [])
        for mode in (True, 0, "PRIVATE", ""):
            with self.subTest(mode=mode), self.assertRaises(recording.RecordingPolicyError):
                self.store.latch(mode=mode)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from src.runtime.disposable_verifier import (
    LEGACY_SNAPSHOT_POLICY_VERSION, SNAPSHOT_POLICY_VERSION,
    DisposableVerifierWorkspace, candidate_manifest, materialize_candidate,
    snapshot_identity,
)


class DisposableVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        (self.source / "tracked.txt").write_bytes(b"exact\x00source\n")
        (self.source / "dirty.txt").write_text("uncommitted candidate", encoding="utf-8")
        (self.source / ".git").mkdir()
        (self.source / ".git" / "secret-ish").write_text("excluded", encoding="utf-8")
        (self.source / "database").mkdir()
        (self.source / "database" / "runtime.json").write_text("excluded", encoding="utf-8")
        (self.source / "archive").mkdir()
        (self.source / "archive" / "runtime.bin").write_bytes(b"excluded")
        (self.source / ".env").write_text("TOKEN=excluded", encoding="utf-8")
        (self.source / "download.bin:Zone.Identifier").write_text("metadata", encoding="utf-8")

    def test_snapshot_is_exact_includes_dirty_bytes_and_excludes_runtime_state(self):
        destination = Path(self.temp.name) / "snapshot"
        provenance = materialize_candidate(self.source, destination)
        self.assertEqual((destination / "tracked.txt").read_bytes(), b"exact\x00source\n")
        self.assertEqual((destination / "dirty.txt").read_text(), "uncommitted candidate")
        self.assertFalse((destination / "database").exists())
        self.assertFalse((destination / "archive").exists())
        self.assertFalse((destination / ".env").exists())
        self.assertFalse((destination / "download.bin:Zone.Identifier").exists())
        self.assertTrue((destination / ".git").is_dir())
        self.assertFalse((destination / ".git" / "secret-ish").exists())
        self.assertTrue(provenance["includes_uncommitted_worktree"])
        self.assertFalse(provenance["credentials_copied"])
        self.assertEqual(candidate_manifest(self.source)["candidate_snapshot_id"],
                         candidate_manifest(destination)["candidate_snapshot_id"])

    def test_disposable_mutation_cannot_change_source_and_cleanup_is_bounded(self):
        with DisposableVerifierWorkspace(self.source, parent=self.temp.name) as fixture:
            disposable_root = fixture.root.parent
            (fixture.root / "tracked.txt").write_text("mutated only here", encoding="utf-8")
            (fixture.root / "held-out.json").write_text("{}", encoding="utf-8")
            self.assertTrue(fixture.verify_source_unchanged())
            self.assertEqual((self.source / "tracked.txt").read_bytes(), b"exact\x00source\n")
        self.assertFalse(disposable_root.exists())
        self.assertTrue(self.source.exists())

    def test_nonempty_destination_fails_closed(self):
        destination = Path(self.temp.name) / "occupied"
        destination.mkdir()
        (destination / "x").write_text("x")
        with self.assertRaisesRegex(ValueError, "must be empty"):
            materialize_candidate(self.source, destination)

    def test_portable_identity_uses_normalized_paths_and_ordinal_byte_order(self):
        entries = [
            {"path": "nested/b.txt", "sha256": "04" * 32, "byte_length": 4},
            {"path": "a.txt", "sha256": "02" * 32, "byte_length": 2},
            {"path": "nested/A.txt", "sha256": "03" * 32, "byte_length": 3},
            {"path": "B.txt", "sha256": "01" * 32, "byte_length": 1},
        ]
        identity, normalized = snapshot_identity(entries)
        windows_entries = [{**item, "path": item["path"].replace("/", "\\")}
                           for item in reversed(entries)]
        windows_identity, windows_normalized = snapshot_identity(windows_entries)
        self.assertEqual(identity, windows_identity)
        self.assertEqual(normalized, windows_normalized)
        self.assertEqual([item["path"] for item in normalized],
                         ["B.txt", "a.txt", "nested/A.txt", "nested/b.txt"])
        self.assertEqual(SNAPSHOT_POLICY_VERSION, "phoenix-portable-snapshot-identity-v2")
        legacy_identity, _ = snapshot_identity(entries,
                                               policy_version=LEGACY_SNAPSHOT_POLICY_VERSION)
        self.assertNotEqual(identity, legacy_identity)

        mutated = [dict(item) for item in entries]
        mutated[0] = {**mutated[0], "sha256": "05" * 32}
        mutated_identity, _ = snapshot_identity(mutated)
        self.assertNotEqual(identity, mutated_identity)

    def test_portable_case_collision_fails_instead_of_following_host_behavior(self):
        entries = [
            {"path": "A.txt", "sha256": "01" * 32, "byte_length": 1},
            {"path": "a.txt", "sha256": "02" * 32, "byte_length": 1},
        ]
        with self.assertRaisesRegex(ValueError, "portable path identity collision"):
            snapshot_identity(entries)


if __name__ == "__main__":
    unittest.main()

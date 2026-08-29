from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "src"


class FawkesArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        shutil.copytree(SOURCE_DIR, self.root / "src")

        (self.root / "archive" / "raw").mkdir(parents=True)
        (self.root / "archive" / "meta").mkdir(parents=True)
        (self.root / "backups").mkdir()
        (self.root / "database").mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_fawkes(self, *args, input_text=None):
        return subprocess.run(
            [sys.executable, "src/fawkes.py", *args],
            cwd=self.root,
            input=input_text,
            text=True,
            capture_output=True,
        )

    def test_text_archive_preserves_exact_bytes(self):
        text = "Fawkes test.\nMemory may evolve. The Archive does not.\n"

        result = self.run_fawkes(
            "archive",
            "Automated Test",
            input_text=text,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        meta_files = list((self.root / "archive" / "meta").glob("*.json"))
        self.assertEqual(len(meta_files), 1)

        metadata = json.loads(meta_files[0].read_text(encoding="utf-8"))
        raw_path = self.root / "archive" / "raw" / metadata["raw_file"]

        self.assertEqual(raw_path.read_bytes(), text.encode("utf-8"))

        expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.assertEqual(metadata["sha256"], expected_hash)
        self.assertEqual(metadata["schema_version"], 1)
        self.assertIsNone(metadata["original_filename"])
        self.assertEqual(metadata["size_bytes"], len(text.encode("utf-8")))
        self.assertEqual(metadata["ingest_method"], "text_stdin")
        self.assertEqual(metadata["encoding"], "utf-8")

    def test_verify_rejects_malformed_metadata(self):
        archive_id = "malformed-metadata-test"
        meta_path = self.root / "archive" / "meta" / f"{archive_id}.json"
        meta_path.write_text("{not valid json", encoding="utf-8")

        result = self.run_fawkes("verify", archive_id)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Archive integrity: FAILED", result.stdout)
        self.assertIn("Metadata unreadable:", result.stdout)

    def test_verify_rejects_metadata_missing_raw_file(self):
        archive_id = "missing-raw-file-test"
        meta_path = self.root / "archive" / "meta" / f"{archive_id}.json"
        meta_path.write_text(
            '{"sha256": "abc123"}\n',
            encoding="utf-8",
        )

        result = self.run_fawkes("verify", archive_id)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Archive integrity: FAILED", result.stdout)
        self.assertIn("Metadata missing required field: raw_file", result.stdout)

    def test_verify_rejects_metadata_missing_sha256(self):
        archive_id = "missing-sha256-test"
        meta_path = self.root / "archive" / "meta" / f"{archive_id}.json"
        meta_path.write_text(
            '{"raw_file": "example.txt"}\n',
            encoding="utf-8",
        )

        result = self.run_fawkes("verify", archive_id)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Archive integrity: FAILED", result.stdout)
        self.assertIn("Metadata missing required field: sha256", result.stdout)

    def test_verify_detects_tampering(self):
        text = "Original immutable archive data."

        archive_result = self.run_fawkes(
            "archive",
            "Tamper Test",
            input_text=text,
        )
        self.assertEqual(archive_result.returncode, 0)

        meta_file = next((self.root / "archive" / "meta").glob("*.json"))
        metadata = json.loads(meta_file.read_text(encoding="utf-8"))

        raw_path = self.root / "archive" / "raw" / metadata["raw_file"]
        raw_path.write_text("TAMPERED", encoding="utf-8")

        verify_result = self.run_fawkes(
            "verify",
            metadata["archive_id"],
        )

        self.assertNotEqual(verify_result.returncode, 0)
        self.assertIn("FAILED", verify_result.stdout)


class FawkesWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        shutil.copytree(SOURCE_DIR, self.root / "src")

        (self.root / "archive" / "raw").mkdir(parents=True)
        (self.root / "archive" / "meta").mkdir(parents=True)
        (self.root / "backups").mkdir()
        (self.root / "database").mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_fawkes(self, *args, input_text=None):
        return subprocess.run(
            [sys.executable, "src/fawkes.py", *args],
            cwd=self.root,
            input=input_text,
            text=True,
            capture_output=True,
        )

    def test_duplicate_file_is_not_archived_twice(self):
        source = self.root / "duplicate.txt"
        source.write_bytes(b"same bytes every time\n")

        first = self.run_fawkes(
            "archive-file",
            str(source),
            "Duplicate Test",
        )
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        second = self.run_fawkes(
            "archive-file",
            str(source),
            "Duplicate Test Again",
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("Duplicate detected", second.stdout)

        meta_files = list((self.root / "archive" / "meta").glob("*.json"))
        raw_files = list((self.root / "archive" / "raw").glob("*"))

        self.assertEqual(len(meta_files), 1)
        self.assertEqual(len(raw_files), 1)

        metadata = json.loads(meta_files[0].read_text(encoding="utf-8"))
        self.assertEqual(metadata["schema_version"], 1)
        self.assertEqual(metadata["original_filename"], "duplicate.txt")
        self.assertEqual(metadata["size_bytes"], len(b"same bytes every time\n"))
        self.assertEqual(metadata["ingest_method"], "file_copy")
        self.assertIsNone(metadata["encoding"])

    def test_verify_all_rejects_metadata_missing_sha256(self):
        archive_id = "verify-all-missing-sha256"
        raw_path = self.root / "archive" / "raw" / f"{archive_id}.txt"
        meta_path = self.root / "archive" / "meta" / f"{archive_id}.json"

        raw_path.write_text("data", encoding="utf-8")
        meta_path.write_text(
            '{"archive_id": "verify-all-missing-sha256", '
            '"raw_file": "verify-all-missing-sha256.txt"}\n',
            encoding="utf-8",
        )

        result = self.run_fawkes("verify-all")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "FAILED: verify-all-missing-sha256 has no sha256 entry",
            result.stdout,
        )
        self.assertIn("Failed: 1", result.stdout)

    def test_unified_capture_archives_once_and_rejects_duplicate(self):
        source = self.root / "capture.txt"
        source.write_text(
            "User: capture test\n\nFawkes: archived once\n",
            encoding="utf-8",
        )

        first = self.run_fawkes(
            "capture",
            str(source),
            "Capture Test",
        )
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        second = self.run_fawkes(
            "capture",
            str(source),
            "Capture Test Again",
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("Duplicate detected", second.stdout)

        meta_files = list((self.root / "archive" / "meta").glob("*.json"))
        raw_files = list((self.root / "archive" / "raw").glob("*"))

        self.assertEqual(len(meta_files), 1)
        self.assertEqual(len(raw_files), 1)

    def test_backup_and_restore_match_archive(self):
        archive_result = self.run_fawkes(
            "archive",
            "Backup Test",
            input_text="Archive data for backup testing.\n",
        )
        self.assertEqual(
            archive_result.returncode,
            0,
            archive_result.stdout + archive_result.stderr,
        )

        backup_result = self.run_fawkes("backup")
        self.assertEqual(
            backup_result.returncode,
            0,
            backup_result.stdout + backup_result.stderr,
        )

        backup_dirs = list((self.root / "backups").glob("archive-*"))
        self.assertEqual(len(backup_dirs), 1)

        backup_dir = backup_dirs[0]

        verify_result = self.run_fawkes(
            "verify-backup",
            str(backup_dir),
        )
        self.assertEqual(
            verify_result.returncode,
            0,
            verify_result.stdout + verify_result.stderr,
        )

        restore_dir = self.root / "restored"

        restore_result = self.run_fawkes(
            "restore",
            str(backup_dir),
            str(restore_dir),
        )
        self.assertEqual(
            restore_result.returncode,
            0,
            restore_result.stdout + restore_result.stderr,
        )

        archive_files = sorted(
            p.relative_to(self.root / "archive")
            for p in (self.root / "archive").rglob("*")
            if p.is_file()
        )

        restored_files = sorted(
            p.relative_to(restore_dir)
            for p in restore_dir.rglob("*")
            if p.is_file()
        )

        self.assertEqual(archive_files, restored_files)

        for relative_path in archive_files:
            self.assertEqual(
                (self.root / "archive" / relative_path).read_bytes(),
                (restore_dir / relative_path).read_bytes(),
            )

    def test_manifest_matches_metadata_entries(self):
        for index in range(2):
            result = self.run_fawkes(
                "archive",
                f"Manifest Test {index}",
                input_text=f"manifest item {index}\n",
            )
            self.assertEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )

        manifest_result = self.run_fawkes("manifest")
        self.assertEqual(
            manifest_result.returncode,
            0,
            manifest_result.stdout + manifest_result.stderr,
        )

        manifest_path = self.root / "database" / "archive_manifest.json"
        self.assertTrue(manifest_path.exists())

        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        meta_files = list((self.root / "archive" / "meta").glob("*.json"))

        self.assertEqual(manifest["entry_count"], len(meta_files))
        self.assertEqual(len(manifest["entries"]), len(meta_files))


if __name__ == "__main__":
    unittest.main()


class FawkesReconstructionTests(unittest.TestCase):
    def test_shifted_overlapping_snapshots_reconstruct_in_order(self):
        from src.capture.reconstruct import merge_snapshot, parse_messages

        snapshot_one = """User: first message

Fawkes: first answer

User: second message

Fawkes: second answer"""

        snapshot_two = """User: second message

Fawkes: second answer

User: third message

Fawkes: third answer"""

        reconstructed = []

        reconstructed, merged_one = merge_snapshot(
            reconstructed,
            parse_messages(snapshot_one),
        )

        reconstructed, merged_two = merge_snapshot(
            reconstructed,
            parse_messages(snapshot_two),
        )

        self.assertTrue(merged_one)
        self.assertTrue(merged_two)
        self.assertEqual(
            reconstructed,
            [
                {"role": "user", "content": "first message"},
                {"role": "assistant", "content": "first answer"},
                {"role": "user", "content": "second message"},
                {"role": "assistant", "content": "second answer"},
                {"role": "user", "content": "third message"},
                {"role": "assistant", "content": "third answer"},
            ],
        )

    def test_streaming_message_prefers_more_complete_version(self):
        from src.capture.reconstruct import merge_snapshot, parse_messages

        snapshot_one = """User: question

Fawkes: This answer is still"""

        snapshot_two = """User: question

Fawkes: This answer is still being generated."""

        reconstructed, _ = merge_snapshot(
            [],
            parse_messages(snapshot_one),
        )

        reconstructed, merged = merge_snapshot(
            reconstructed,
            parse_messages(snapshot_two),
        )

        self.assertTrue(merged)
        self.assertEqual(
            reconstructed[-1]["content"],
            "This answer is still being generated.",
        )

    def test_unprovable_snapshot_is_flagged_not_guessed(self):
        from src.capture.reconstruct import merge_snapshot, parse_messages

        base = parse_messages(
            """User: known message

Fawkes: known answer"""
        )

        unrelated = parse_messages(
            """User: disconnected message

Fawkes: disconnected answer"""
        )

        reconstructed, merged = merge_snapshot(base, unrelated)

        self.assertFalse(merged)
        self.assertEqual(reconstructed, base)

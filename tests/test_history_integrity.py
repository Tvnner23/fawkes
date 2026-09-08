"""Synthetic regressions for the independently rejected native History cases."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from tests import test_historical_search as fixtures


class NativeHistoryIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.search, _, _, self.archive_id, self.raw = fixtures.HistoricalSearchTests().setup_domains(self.root)
        self.meta = self.root / "archive/meta" / (self.archive_id + ".json")
        self.raw_path = self.root / "archive/raw" / (self.archive_id + ".json")

    def mutate(self, **changes):
        value = json.loads(self.meta.read_text())
        value.update(changes)
        self.meta.write_text(json.dumps(value))

    def test_wrong_retained_length_is_rejected(self):
        self.mutate(size_bytes=len(self.raw) + 1)
        with self.assertRaises(ValueError):
            self.search.evidence("native_archive", self.archive_id)

    def test_missing_digest_or_length_never_becomes_verified_original(self):
        original = self.meta.read_text()
        for field in ("sha256", "size_bytes"):
            with self.subTest(field=field):
                value = json.loads(original)
                del value[field]
                self.meta.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    self.search.evidence("native_archive", self.archive_id)

    def test_non_object_metadata_does_not_hide_healthy_inherited_history(self):
        self.meta.write_text("[]")
        try:
            result = self.search.search("shared phrase")
        except Exception as exc:
            self.fail("Native metadata escaped the domain boundary: " + type(exc).__name__)
        self.assertEqual(result["domain_status"]["native_archive"]["status"], "degraded")
        self.assertEqual([item["domain"] for item in result["results"]], ["inherited_history"])

    def test_duplicate_metadata_and_wrong_identity_are_domain_failures(self):
        original = self.meta.read_text()
        for body in ('{"archive_id":"one","archive_id":"two"}',
                     json.dumps({**json.loads(original), "archive_id": "other"})):
            with self.subTest(body=body):
                self.meta.write_text(body)
                result = self.search.search("shared phrase")
                self.assertEqual(result["domain_status"]["native_archive"]["status"], "degraded")
                self.assertEqual([item["domain"] for item in result["results"]], ["inherited_history"])

    def test_raw_symlink_outside_selected_root_is_rejected(self):
        outside = self.root / "outside.json"
        outside.write_bytes(self.raw)
        self.raw_path.unlink()
        self.raw_path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.search.evidence("native_archive", self.archive_id)
        self.assertEqual(outside.read_bytes(), self.raw)

    def test_metadata_symlink_is_rejected_without_hiding_other_domain(self):
        outside = self.root / "outside-meta.json"
        outside.write_bytes(self.meta.read_bytes())
        self.meta.unlink()
        self.meta.symlink_to(outside)
        result = self.search.search("shared phrase")
        self.assertEqual(result["domain_status"]["native_archive"]["status"], "degraded")
        self.assertEqual([item["domain"] for item in result["results"]], ["inherited_history"])

    def test_nonregular_raw_is_rejected_without_blocking(self):
        self.raw_path.unlink()
        os.mkfifo(self.raw_path)
        with self.assertRaises(ValueError):
            self.search.evidence("native_archive", self.archive_id)

    def test_changed_bytes_and_unsafe_references_are_rejected(self):
        original = self.meta.read_text()
        for raw_file in ("../outside.json", "..\\outside.json", "", ".."):
            with self.subTest(raw_file=raw_file):
                self.meta.write_text(original)
                self.mutate(raw_file=raw_file)
                with self.assertRaises(ValueError):
                    self.search.evidence("native_archive", self.archive_id)
        self.meta.write_text(original)
        self.raw_path.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.search.evidence("native_archive", self.archive_id)


if __name__ == "__main__":
    unittest.main()

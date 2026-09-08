"""Offline source preservation/navigation checks; no application or provider."""
import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path

from tests.test_repository_documentation import broken_links

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SOURCE_PATH = ROOT / "tests/fixtures/repository_cleanup_source_bindings.json"
SOURCE_SHA256 = "8fa8f5bb80a638e261db18f32fb615b80ee657bff6daf60ef186f8ff263ee718"


def sources():
    raw = SOURCE_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("source projection changed; revalidate original evidence before updating")
    return json.loads(raw)


def inventory_errors(value, root=None, source=None):
    """Validate immutable capture; optionally verify its original material root.

    An accepted successor checkout is not the historical unfinished checkout.
    Omitting root validates the complete source-bound capture, not preservation
    of external original files. Material verification remains explicit.
    """
    source = sources() if source is None else source
    errors, seen = [], set()
    if value.get("schema_version") != 1:
        errors.append("unknown schema")
    for key in ("base_commit", "status_sha256", "source_inventory_sha256",
                "source_inventory_locator", "git_staged_paths"):
        if value.get(key) != source[key]:
            errors.append("source binding mismatch: " + key)
    if value.get("path_count") != len(source["nodes_by_path"]):
        errors.append("source count mismatch")
    for group in value["groups"]:
        for item in group["items"]:
            relative, node = item["path"], item["node"]
            if relative in seen:
                errors.append("duplicate path")
            seen.add(relative)
            original = source["nodes_by_path"].get(relative)
            if original is None:
                errors.append("path absent from source: " + relative)
            elif (group["name"] != original["group"] or node != original["node"]
                  or item.get("git_state") != original["git_state"]):
                errors.append("source classification/material mismatch: " + relative)
            if item["independent_acceptance"] != "not established for this retained delta":
                errors.append("unsupported acceptance claim")
            if root is None:
                continue
            path = root / relative
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                errors.append("missing or unsupported node: " + relative)
                continue
            actual = {"type": "regular", "mode": stat.S_IMODE(path.stat().st_mode),
                      "byte_length": path.stat().st_size,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            if actual != node:
                errors.append("material drift: " + relative)
    if len(seen) != value["path_count"]:
        errors.append("coverage mismatch")
    if seen != set(source["nodes_by_path"]):
        errors.append("source path set mismatch")
    return errors


def status_errors(value, source=None):
    source = sources() if source is None else source
    errors = []
    expected = {"base_commit": source["base_commit"], "console": source["console"],
                "console_evidence": source["console_evidence"],
                "cleanup_batch1": source["cleanup_batch1"],
                "historical_pointer_sha256": source["historical_pointer_sha256"],
                "milestone_completion_sha256": source["source_console_complete_sha256"],
                "github_backup": source["backup"],
                "github_backup_evidence": {"sha256": source["source_github_backup_sha256"],
                    "retained_path": source["source_github_backup_locator"]}}
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            errors.append("status source mismatch: " + key)
    return errors


class RepositoryWorkInventoryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads((DOCS / "repository-work-inventory.json").read_text())
        self.evidence = json.loads((DOCS / "repository-status-evidence.json").read_text())

    def test_historical_capture_matches_all_original_source_bindings(self):
        self.assertEqual([], inventory_errors(self.inventory))
        self.assertEqual(126, self.inventory["path_count"])
        self.assertEqual(0, self.inventory["git_staged_paths"])

    def test_optional_original_material_check_detects_bytes_mode_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sample.txt"
            path.write_bytes(b"retained original\n")
            path.chmod(0o644)
            node = {"type":"regular", "mode":0o644, "byte_length":18,
                    "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            source = {"base_commit":"original", "status_sha256":"status",
                "source_inventory_sha256":"inventory", "source_inventory_locator":"capture",
                "git_staged_paths":0, "nodes_by_path":{"sample.txt":{
                    "group":"fixture", "node":node, "git_state":"untracked"}}}
            value = {key:source[key] for key in ("base_commit", "status_sha256",
                "source_inventory_sha256", "source_inventory_locator", "git_staged_paths")}
            value.update(schema_version=1, path_count=1, groups=[{"name":"fixture", "items":[{
                "path":"sample.txt", "node":node, "git_state":"untracked",
                "independent_acceptance":"not established for this retained delta"}]}])
            self.assertEqual([], inventory_errors(value, root, source))
            path.write_bytes(b"changed")
            self.assertIn("material drift: sample.txt", inventory_errors(value, root, source))
            path.write_bytes(b"retained original\n")
            path.chmod(0o600)
            self.assertIn("material drift: sample.txt", inventory_errors(value, root, source))
            path.unlink()
            self.assertIn("missing or unsupported node: sample.txt", inventory_errors(value, root, source))

    def test_duplicate_missing_and_changed_nodes_are_detected(self):
        value = json.loads(json.dumps(self.inventory))
        group = value["groups"][0]["items"]
        group.append(dict(group[0]))
        self.assertIn("duplicate path", inventory_errors(value, ROOT))
        group.pop()
        group[0]["node"]["sha256"] = "0" * 64
        self.assertTrue(any(x.startswith("material drift") for x in inventory_errors(value, ROOT)))
        group[0]["path"] = "src/__missing_inventory_fixture__.py"
        self.assertTrue(any(x.startswith("missing or unsupported") for x in inventory_errors(value, ROOT)))

    def test_omission_and_schema_change_do_not_silently_pass(self):
        value = json.loads(json.dumps(self.inventory))
        value["groups"][0]["items"].pop()
        self.assertIn("coverage mismatch", inventory_errors(value, ROOT))
        value["schema_version"] = 2
        self.assertIn("unknown schema", inventory_errors(value, ROOT))

    def test_exact_inventory_and_historical_pointer_digests(self):
        for name, key in (
            ("repository-work-inventory.json", "unfinished_inventory_sha256"),
            ("phoenix/CURRENT_IMPLEMENTATION_2026-09-08_CAPTURE.md", "historical_pointer_sha256"),
        ):
            self.assertEqual(self.evidence[key], hashlib.sha256((DOCS / name).read_bytes()).hexdigest())

    def test_status_has_separate_receipt_snapshot_commit_and_physical_evidence(self):
        self.assertEqual([], status_errors(self.evidence))
        console = self.evidence["console"]
        self.assertEqual(self.evidence["base_commit"], console["accepted_integrated_deployed_commit"])
        self.assertTrue(console["snapshot"].startswith("candidate-snapshot-"))
        self.assertEqual(40, len(console["accepted_integrated_deployed_commit"]))
        for key in ("mutation", "acceptance_receipt"):
            self.assertEqual(64, len(console[key]))
        self.assertEqual("passed, Tanner observed", console["physical_menu_check"])
        self.assertEqual(1, console["application_count"])
        for ref in self.evidence["console_evidence"].values():
            self.assertEqual(64, len(ref["sha256"]))
            self.assertFalse(Path(ref["retained_path"]).is_absolute())

    def test_substituted_console_identities_and_reference_hashes_fail(self):
        for key in ("snapshot", "mutation", "acceptance_receipt", "worker_thread",
                    "accepted_integrated_deployed_commit", "physical_menu_check"):
            value = json.loads(json.dumps(self.evidence))
            value["console"][key] = "fabricated-" + "0" * 64
            with self.subTest(key=key):
                self.assertIn("status source mismatch: console", status_errors(value))
        for key in self.evidence["console_evidence"]:
            for field in ("sha256", "retained_path"):
                value = json.loads(json.dumps(self.evidence))
                value["console_evidence"][key][field] = "0" * 64
                self.assertIn("status source mismatch: console_evidence", status_errors(value))

    def test_regenerated_inventory_digest_cannot_conceal_source_substitution(self):
        for key in ("status_sha256", "source_inventory_sha256", "base_commit",
                    "source_inventory_locator", "git_staged_paths"):
            value = json.loads(json.dumps(self.inventory))
            value[key] = "substituted"
            self.assertIn("source binding mismatch: " + key, inventory_errors(value, ROOT))
        for field in ("git_state", "group"):
            value = json.loads(json.dumps(self.inventory))
            if field == "group": value["groups"][0]["name"] = "unrelated group"
            else: value["groups"][0]["items"][0][field] = "already committed"
            evidence = json.loads(json.dumps(self.evidence))
            evidence["unfinished_inventory_sha256"] = hashlib.sha256(json.dumps(value).encode()).hexdigest()
            self.assertTrue(any(x.startswith("source classification/material mismatch")
                                for x in inventory_errors(value, ROOT)))

    def test_source_omission_cannot_be_hidden_by_reducing_count(self):
        value = json.loads(json.dumps(self.inventory))
        value["groups"][0]["items"].pop()
        value["path_count"] -= 1
        self.assertIn("source path set mismatch", inventory_errors(value, ROOT))

    def test_backup_status_is_exact_and_not_full_dirty_tree(self):
        self.assertEqual([], status_errors(self.evidence))
        self.assertFalse(self.evidence["github_backup"]["backup_is_full_working_tree"])
        value = json.loads(json.dumps(self.evidence))
        value["github_backup"]["head"] = "0" * 40
        self.assertIn("status source mismatch: github_backup", status_errors(value))

    def test_external_guide_dates_obsolete_combined_absence_claim(self):
        guide = (DOCS / "EXTERNAL_REVIEW_GUIDE.md").read_text()
        self.assertIn("That combined absence claim is no longer current", guide)
        self.assertIn("../package-lock.json", guide)
        self.assertIn("../deploy/systemd/", guide)

    def test_current_navigation_and_historical_links_resolve(self):
        for name in ("REPOSITORY_WORK.md", "EXTERNAL_REVIEW_GUIDE.md",
                     "phoenix/CURRENT_IMPLEMENTATION.md",
                     "phoenix/CURRENT_IMPLEMENTATION_2026-09-08_CAPTURE.md"):
            path = DOCS / name
            with self.subTest(document=name):
                self.assertEqual([], broken_links(path, path.read_text()))

    def test_current_pointer_does_not_repeat_obsolete_immediate_task(self):
        current = (DOCS / "phoenix/CURRENT_IMPLEMENTATION.md").read_text()
        self.assertIn("private Pi console milestone is complete", current)
        self.assertIn("Repository cleanup | In progress", current)
        self.assertIn("CURRENT_IMPLEMENTATION_2026-09-08_CAPTURE.md", current)
        self.assertNotIn("**Current outcome:** finish", current)
        self.assertIn("authenticated non-force push and remote read-back", current)


if __name__ == "__main__":
    unittest.main()

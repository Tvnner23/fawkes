import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import tests.test_wsl_codex_reviewer as reviewer_fixtures

from src.runtime.worker_exchange import _digest
from src.runtime.windows_codex_reviewer import (
    WindowsCodexReviewAdapter, _review_exact_change_evidence,
    independent_review_acceptance_receipt, prepare_windows_review_package,
)
from src.runtime.wsl_codex_reviewer import WslCodexReviewAdapter


class ExactFileReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "review-supplement").mkdir()
        self.changes = [{
            "path": "src/example.py",
            "before_node_binding": {"schema": "fawkes.filesystem_node.v1",
                                    "state": "present", "file_type": "regular",
                                    "mode": 0o644, "body_length": 4,
                                    "body_sha256": hashlib.sha256(b"old\n").hexdigest()},
            "after_node_binding": {"schema": "fawkes.filesystem_node.v1",
                                   "state": "present", "file_type": "regular",
                                   "mode": 0o644, "body_length": 4,
                                   "body_sha256": hashlib.sha256(b"new\n").hexdigest()},
        }]
        self.retention = {
            "record_type": "codex_candidate_retention_receipt",
            "exact_change_evidence_sha256": _digest(self.changes),
        }
        self.retention["record_sha256"] = _digest(self.retention)

    def tearDown(self):
        self.temporary.cleanup()

    def package(self, *, pointer=None, inline=None):
        sections = [{"section_id": "candidate-retention-receipt",
                     "content": json.dumps(self.retention, sort_keys=True,
                                           separators=(",", ":"))}]
        if inline is not None:
            sections.append({"section_id": "exact-change-evidence",
                             "content": inline})
        if pointer is not None:
            sections.append({"section_id": "exact-change-evidence-reference",
                             "content": json.dumps(pointer, sort_keys=True,
                                                   separators=(",", ":"))})
        return {"included_sections": sections}

    def authority(self):
        return {
            "candidate_retention_receipt_sha256": self.retention["record_sha256"],
            "exact_change_evidence_sha256": _digest(self.changes),
        }

    def write_reference(self, body=None):
        data = body if body is not None else (
            json.dumps(self.changes, indent=2, sort_keys=True) + "\n").encode()
        path = self.root / "review-supplement/exact-change-evidence.json"
        path.write_bytes(data)
        return {
            "exact_candidate_relative_path": "review-supplement/exact-change-evidence.json",
            "sha256": hashlib.sha256(data).hexdigest(),
            "byte_length": len(data), "complete": True, "external_retrieval": False,
        }

    def test_inline_and_exact_file_forms_resolve_identically(self):
        inline = json.dumps(self.changes, sort_keys=True, separators=(",", ":"))
        first = _review_exact_change_evidence(
            self.package(inline=inline), transport_authority=self.authority())
        second = _review_exact_change_evidence(
            self.package(pointer=self.write_reference()),
            candidate_snapshot_root=self.root, transport_authority=self.authority())
        self.assertEqual(first, second)

    def test_reference_rejects_missing_extra_changed_or_wrongly_typed_fields(self):
        valid = self.write_reference()
        variants = []
        for key in valid:
            value = dict(valid); value.pop(key); variants.append(value)
        value = dict(valid); value["extra"] = True; variants.append(value)
        value = dict(valid); value["byte_length"] = True; variants.append(value)
        value = dict(valid); value["complete"] = 1; variants.append(value)
        value = dict(valid); value["external_retrieval"] = 0; variants.append(value)
        value = dict(valid); value["sha256"] = "0" * 64; variants.append(value)
        value = dict(valid); value["exact_candidate_relative_path"] = "../outside"; variants.append(value)
        for pointer in variants:
            with self.subTest(pointer=pointer):
                with self.assertRaises(PermissionError):
                    _review_exact_change_evidence(
                        self.package(pointer=pointer),
                        candidate_snapshot_root=self.root,
                        transport_authority=self.authority())

    def test_reference_rejects_missing_tampered_symlink_and_oversize_files(self):
        pointer = self.write_reference()
        path = self.root / pointer["exact_candidate_relative_path"]
        path.write_bytes(b"[]\n")
        with self.assertRaises(PermissionError):
            _review_exact_change_evidence(self.package(pointer=pointer),
                candidate_snapshot_root=self.root, transport_authority=self.authority())
        path.unlink()
        outside = self.root / "outside.json"; outside.write_bytes(b"[]\n")
        path.symlink_to(outside)
        symlink_pointer = dict(pointer, byte_length=3,
                               sha256=hashlib.sha256(b"[]\n").hexdigest())
        with self.assertRaises(PermissionError):
            _review_exact_change_evidence(self.package(pointer=symlink_pointer),
                candidate_snapshot_root=self.root, transport_authority=self.authority())
        path.unlink()
        oversize = dict(pointer, byte_length=4_500_001)
        with self.assertRaises(PermissionError):
            _review_exact_change_evidence(self.package(pointer=oversize),
                candidate_snapshot_root=self.root, transport_authority=self.authority())

    def test_descriptor_read_rejects_final_path_replacement_and_growth(self):
        pointer = self.write_reference()
        target = self.root / pointer["exact_candidate_relative_path"]
        outside = self.root / "outside.json"
        outside.write_bytes(target.read_bytes())
        original_open = os.open
        replaced = False

        def replace_before_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if path == "exact-change-evidence.json" and dir_fd is not None and not replaced:
                replaced = True
                target.unlink()
                target.symlink_to(outside)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with patch("src.runtime.windows_codex_reviewer.os.open",
                   side_effect=replace_before_open):
            with self.assertRaises(PermissionError):
                _review_exact_change_evidence(self.package(pointer=pointer),
                    candidate_snapshot_root=self.root,
                    transport_authority=self.authority())
        self.assertTrue(replaced)

        target.unlink()
        pointer = self.write_reference()
        original_read = os.read
        grown = False

        def grow_before_read(descriptor, amount):
            nonlocal grown
            if not grown:
                grown = True
                with target.open("ab") as stream:
                    stream.write(b"x")
            return original_read(descriptor, amount)

        with patch("src.runtime.windows_codex_reviewer.os.read",
                   side_effect=grow_before_read):
            with self.assertRaises(PermissionError):
                _review_exact_change_evidence(self.package(pointer=pointer),
                    candidate_snapshot_root=self.root,
                    transport_authority=self.authority())
        self.assertTrue(grown)

    def test_duplicate_json_keys_and_ambiguous_forms_fail_closed(self):
        pointer = self.write_reference()
        duplicate = (b'[{"path":"src/example.py","path":"src/substituted.py",'
                     b'"before_node_binding":{}}]\n')
        pointer = self.write_reference(duplicate)
        with self.assertRaises(PermissionError):
            _review_exact_change_evidence(self.package(pointer=pointer),
                candidate_snapshot_root=self.root, transport_authority=self.authority())
        inline = json.dumps(self.changes, sort_keys=True, separators=(",", ":"))
        with self.assertRaises(PermissionError):
            _review_exact_change_evidence(self.package(pointer=pointer, inline=inline),
                candidate_snapshot_root=self.root, transport_authority=self.authority())

    def test_authority_and_retention_mismatches_fail(self):
        pointer = self.write_reference()
        for key in ("candidate_retention_receipt_sha256",
                    "exact_change_evidence_sha256"):
            authority = self.authority(); authority[key] = "0" * 64
            with self.subTest(key=key), self.assertRaises(PermissionError):
                _review_exact_change_evidence(self.package(pointer=pointer),
                    candidate_snapshot_root=self.root,
                    transport_authority=authority)

    def test_exact_file_form_mints_the_same_bound_canonical_receipt(self):
        package = self.package(pointer=self.write_reference())
        package.update({
            "package_id": "worker-package-fixture",
            "record_sha256": "1" * 64,
            "source_report_id": "source-report-fixture",
            "authority_expires_at": "2030-01-01T00:00:00+00:00",
        })
        reviewer = {"worker_id": "independent-reviewer",
                    "role": "formal_reviewer"}
        response = {"review_status": "pass", "recipient": reviewer,
                    "acceptance_condition_ids_satisfied": ["exact"]}
        authority = {
            **self.authority(),
            "builder_package_id": "worker-package-builder",
            "mutation_manifest_sha256": "2" * 64,
            "allowed_scope_sha256": "3" * 64,
        }
        receipt = independent_review_acceptance_receipt(
            response=response, campaign_id="campaign-fixture", package=package,
            candidate_snapshot_id="candidate-snapshot-fixture",
            invocation_id="review-invocation-fixture", reviewer=reviewer,
            return_report={"report_id": "return-report-fixture",
                           "record_sha256": "4" * 64},
            delivery_receipt_id="delivery-fixture",
            verification_receipt_id="verification-fixture",
            transport_authority=authority,
            candidate_snapshot_root=self.root)
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["exact_change_evidence_sha256"],
                         _digest(self.changes))
        self.assertEqual(receipt["candidate_retention_receipt_sha256"],
                         self.retention["record_sha256"])
        self.assertEqual(receipt["authoritative_preimages_sha256"], _digest([{
            "path": self.changes[0]["path"],
            "before_node_binding": self.changes[0]["before_node_binding"],
        }]))

    @staticmethod
    def _reference_delivery_subject(case, prepared):
        exchange = case.exchange
        original = exchange._load("packages", prepared["package_id"])
        source = exchange._load("reports", original["source_report_id"])
        sections = [dict(item) for item in source["sections"]]
        exact = next(item for item in sections
                     if item["section_id"] == "exact-change-evidence")
        body = exact["content"].encode("utf-8")
        supplement = case.workspace / "review-supplement"
        supplement.mkdir(exist_ok=True)
        evidence = supplement / "exact-change-evidence.json"
        evidence.write_bytes(body)
        pointer = {
            "exact_candidate_relative_path":
                "review-supplement/exact-change-evidence.json",
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_length": len(body), "complete": True,
            "external_retrieval": False,
        }
        sections = [item for item in sections
                    if item["section_id"] != "exact-change-evidence"]
        sections.append({"section_id": "exact-change-evidence-reference",
                         "title": "Exact retained evidence reference",
                         "content": json.dumps(pointer, sort_keys=True,
                                               separators=(",", ":"))})
        manifest = reviewer_fixtures.candidate_manifest(case.workspace)
        snapshot = {
            **manifest, "record_sha256": _digest(manifest),
            "file_count": len(manifest["files"]),
            "total_byte_length": sum(item["byte_length"]
                                     for item in manifest["files"]),
        }
        retention_section = next(item for item in sections
                                 if item["section_id"] == "candidate-retention-receipt")
        retention = json.loads(retention_section["content"])
        retention["candidate_snapshot"] = snapshot
        retention.pop("record_sha256", None)
        retention["record_sha256"] = _digest(retention)
        retention_section["content"] = json.dumps(
            retention, sort_keys=True, separators=(",", ":"))
        snapshot_section = next(item for item in sections
                                if item["section_id"] == "candidate-snapshot")
        snapshot_section["content"] = json.dumps(
            {key: snapshot[key] for key in (
                "candidate_snapshot_id", "file_count", "total_byte_length",
                "record_sha256")}, sort_keys=True, separators=(",", ":"))
        auth_ref = "fixture-exact-file-reference-delivery"
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        authority = {
            "decision": "authorized", "instance_id": "fawkes",
            "task_scope_id": source["task_scope_id"],
            "sender_worker_id": source["sender"]["worker_id"],
            "authorization_reference": auth_ref, "expires_at": expires,
        }
        report = exchange.create_report(
            task_scope_id=source["task_scope_id"], sender=source["sender"],
            authority=authority, sections=sections, claims=source["claims"],
            evidence_references=source["evidence_references"],
            contract_references=source["contract_references"],
            recovery_references=source["recovery_references"])
        package_authority = {
            **authority,
            "recipient_worker_id": original["recipient"]["worker_id"],
        }
        package = exchange.compose_package(
            report_id=report["report_id"], recipient=original["recipient"],
            authority=package_authority,
            included_section_ids=[item["section_id"] for item in sections])
        transport = {
            **prepared["transport_authority"],
            "package_id": package["package_id"],
            "authorization_reference": auth_ref,
            "candidate_snapshot_id": snapshot["candidate_snapshot_id"],
            "candidate_record_sha256": snapshot["record_sha256"],
            "candidate_retention_receipt_sha256": retention["record_sha256"],
        }
        return_authority = {
            **prepared["return_authority"],
            "authorization_reference": auth_ref,
            "expires_at": expires,
        }
        return package, transport, return_authority, snapshot

    def test_reference_form_reaches_both_real_adapter_delivery_boundaries(self):
        class Probe:
            def __init__(self):
                self.live = 0

            def __call__(self, command, *, prompt, environment, timeout):
                if "--version" in command:
                    return SimpleNamespace(returncode=0,
                                           stdout="codex-cli fixture\n", stderr="")
                if command[1:3] == ["login", "status"]:
                    return SimpleNamespace(returncode=0,
                                           stdout="Logged in using ChatGPT\n", stderr="")
                self.live += 1
                return SimpleNamespace(returncode=1, stdout="", stderr="fixture stop")

        for route in ("windows", "wsl"):
            with self.subTest(route=route):
                case = reviewer_fixtures.WslFormalReviewerTests("runTest")
                case.setUp()
                try:
                    prepared = (prepare_windows_review_package(
                        exchange=case.exchange, campaign_record=case.campaign,
                        candidate_snapshot=case.provenance, workspace=case.workspace)
                        if route == "windows" else case.prepared)
                    expected = case.campaign["builder_runs"][-1][
                        "candidate_retention_receipt"]["exact_change_evidence_sha256"]
                    self.assertEqual(
                        prepared["transport_authority"]["exact_change_evidence_sha256"],
                        expected)
                    package, transport, return_authority, snapshot = (
                        self._reference_delivery_subject(case, prepared))
                    probe = Probe()
                    adapter_class = (WindowsCodexReviewAdapter if route == "windows"
                                     else WslCodexReviewAdapter)
                    result = adapter_class(
                        case.exchange, run_process=probe,
                        timeout_seconds=5).deliver_production_once(
                            package_id=package["package_id"],
                            transport_authority=transport,
                            return_authority=return_authority,
                            campaign_id=case.campaign["campaign_id"],
                            builder_return_report_id=case.campaign[
                                "builder_runs"][-1]["return_report_id"],
                            candidate_snapshot_id=snapshot["candidate_snapshot_id"],
                            candidate_snapshot_root=case.workspace,
                            invocation_id=f"fixture-{route}-reference")
                    self.assertEqual(probe.live, 1)
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual(result["failure_reason"], "client_failure")
                finally:
                    case.doCleanups()


if __name__ == "__main__":
    unittest.main()

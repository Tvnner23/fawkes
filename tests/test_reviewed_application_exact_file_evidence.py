import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime.codex_write_builder_adapter import CodexWriteBuilderAdapter
from src.runtime.durable_reviewed_application import unrelated_workspace_sha256
from src.runtime.windows_codex_reviewer import independent_review_acceptance_receipt
from src.runtime.worker_exchange import _digest
from tests import test_autonomy_production_transports as fixture_module


class ReviewedApplicationExactFileEvidenceTests(unittest.TestCase):
    def setUp(self):
        probe = fixture_module.AutonomyProductionTransportTests(
            "test_deferred_candidate_applies_once_only_after_review_gate")
        probe.setUp()
        try:
            probe_result = probe.invoke(defer_authoritative_apply=True)
            self.exact_body = json.dumps(
                probe_result["exact_change_evidence"],
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        finally:
            probe.doCleanups()

        self.fixture = fixture_module.AutonomyProductionTransportTests(
            "test_deferred_candidate_applies_once_only_after_review_gate")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        evidence = self.fixture.workspace / "review-supplement/exact-change-evidence.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(self.exact_body)
        (self.fixture.workspace / "src/sibling.py").write_text(
            "stable sibling\n", encoding="utf-8")
        (self.fixture.workspace / ".git").rmdir()
        for arguments in (
            ("init", "-q"),
            ("config", "user.name", "Fixture"),
            ("config", "user.email", "fixture@invalid"),
            ("add", "src/allowed.py", "src/sibling.py",
             "review-supplement/exact-change-evidence.json"),
            ("commit", "-qm", "base"),
        ):
            subprocess.run(
                ["git", *arguments], cwd=self.fixture.workspace, check=True)

    def reference_acceptance(self, result, *, pointer_change=None):
        fx = self.fixture
        reviewer = {
            "worker_id": "independent-reviewer",
            "role": "formal_reviewer",
            "identity_status": "rider_attested",
            "charter_version": "1",
        }
        returned = fx.exchange._load("reports", result["return_report_id"])
        campaign = fx.retained_review_campaign(
            result,
            returned,
            objective="Apply one exact reviewed fixture mutation.",
            validation_evidence=[{"command": "fixture-validation", "status": "passed"}],
        )
        retention = campaign["builder_runs"][-1]["candidate_retention_receipt"]
        pointer = {
            "exact_candidate_relative_path":
                "review-supplement/exact-change-evidence.json",
            "sha256": hashlib.sha256(self.exact_body).hexdigest(),
            "byte_length": len(self.exact_body),
            "complete": True,
            "external_retrieval": False,
        }
        if pointer_change is not None:
            pointer_change(pointer)
        source = fx.exchange.create_report(
            task_scope_id=fx.task,
            sender=fx.sender,
            authority=fixture_module.authority(
                "fawkes", fx.task, fx.sender["worker_id"]),
            sections=[
                {
                    "section_id": "exact-builder-return",
                    "title": "Exact builder return",
                    "content": json.dumps(returned, sort_keys=True),
                },
                {
                    "section_id": "candidate-retention-receipt",
                    "title": "Exact pre-review candidate-retention receipt",
                    "content": json.dumps(
                        retention, sort_keys=True, separators=(",", ":")),
                },
                {
                    "section_id": "exact-change-evidence-reference",
                    "title": "Exact same-candidate evidence",
                    "content": json.dumps(
                        pointer, sort_keys=True, separators=(",", ":")),
                },
            ],
            claims=[{
                "claim_id": "done",
                "area": "development",
                "statement": "The bounded change is exact.",
                "maturity": "in_development",
                "change_class": "software_system",
            }],
            evidence_references=[{
                "reference_type": "worker_exchange_report",
                "reference_id": returned["report_id"],
                "sha256": returned["record_sha256"],
            }],
        )
        review_authority = fixture_module.authority(
            "fawkes", fx.task, fx.sender["worker_id"], reviewer["worker_id"])
        package = fx.exchange.compose_package(
            report_id=source["report_id"],
            recipient=reviewer,
            authority=review_authority,
            included_section_ids=[
                "exact-builder-return",
                "candidate-retention-receipt",
                "exact-change-evidence-reference",
            ],
        )
        delivery = fx.exchange.record_delivery(
            package_id=package["package_id"],
            authority=review_authority,
            adapter_id="fixture-independent-reviewer",
            adapter_version="1",
            status="delivered",
            delivery_reference="fixture-delivery",
        )
        verification = fx.exchange.record_verification(
            package_id=package["package_id"],
            recipient=reviewer,
            authority=review_authority,
            status="accepted",
            checked_claim_ids=["done"],
            evidence_references=[{"reference_id": returned["report_id"]}],
            method="deterministic fixture review",
            material_reliance=True,
            relied_source_section_ids=["exact-builder-return"],
        )
        report = fx.exchange.create_return_report(
            source_package_id=package["package_id"],
            task_scope_id=fx.task,
            sender=reviewer,
            authority=fixture_module.authority(
                "fawkes", fx.task, reviewer["worker_id"]),
            sections=[{
                "section_id": "verdict",
                "title": "Verdict",
                "content": "Accepted.",
            }],
        )
        response = {
            "review_status": "pass",
            "recipient": reviewer,
            "acceptance_condition_ids_satisfied": ["done"],
        }
        transport = {
            "builder_package_id": fx.package["package_id"],
            "mutation_manifest_sha256": result["workspace_changes_sha256"],
            "allowed_scope_sha256": _digest(fx.scopes),
            "candidate_retention_receipt_sha256": retention["record_sha256"],
            "exact_change_evidence_sha256":
                retention["exact_change_evidence_sha256"],
        }
        receipt = independent_review_acceptance_receipt(
            response=response,
            campaign_id=fx.campaign,
            package=package,
            candidate_snapshot_id=result["candidate_snapshot"]["candidate_snapshot_id"],
            invocation_id="fixture-reference-review-invocation",
            reviewer=reviewer,
            return_report=report,
            delivery_receipt_id=delivery["delivery_receipt_id"],
            verification_receipt_id=verification["verification_receipt_id"],
            transport_authority=transport,
            candidate_snapshot_root=Path(result["candidate_workspace"]),
        )
        return report["report_id"], receipt

    def apply(self, result, report_id, receipt):
        adapter = CodexWriteBuilderAdapter(
            self.fixture.exchange,
            workspace=self.fixture.workspace,
            run_process=fixture_module.FakeWriteCodex(self.fixture.workspace),
            timeout_seconds=5,
        )
        return adapter.apply_reviewed_candidate_once(
            package_id=self.fixture.package["package_id"],
            campaign_id=self.fixture.campaign,
            review_report_id=report_id,
            review_acceptance_receipt=receipt,
        )

    def test_exact_same_candidate_reference_applies_once(self):
        result = self.fixture.invoke(defer_authoritative_apply=True)
        self.assertEqual(
            result["exact_change_evidence"], json.loads(self.exact_body))
        report_id, receipt = self.reference_acceptance(result)
        applied = self.apply(result, report_id, receipt)
        self.assertEqual(applied["status"], "applied_verified_after_review")
        self.assertEqual(
            (self.fixture.workspace / "src/allowed.py").read_text(), "changed\n")

    def test_reference_hash_tampering_fails_before_apply(self):
        result = self.fixture.invoke(defer_authoritative_apply=True)
        report_id, receipt = self.reference_acceptance(result)
        evidence = (Path(result["candidate_workspace"])
                    / "review-supplement/exact-change-evidence.json")
        evidence.write_bytes(self.exact_body + b" ")
        with self.assertRaisesRegex(PermissionError, "stale"):
            self.apply(result, report_id, receipt)
        self.assertEqual(
            (self.fixture.workspace / "src/allowed.py").read_text(), "before\n")

    def test_legacy_inline_application_remains_supported(self):
        result = self.fixture.invoke(defer_authoritative_apply=True)
        report_id, receipt = self.fixture.review_acceptance(result)
        applied = self.apply(result, report_id, receipt)
        self.assertEqual(applied["status"], "applied_verified_after_review")

    def test_directory_scope_uses_exact_durable_race_boundary(self):
        self.fixture.scopes = ["src"]
        result = self.fixture.invoke(defer_authoritative_apply=True)
        report_id, receipt = self.reference_acceptance(result)
        applied = self.apply(result, report_id, receipt)
        self.assertEqual(applied["status"], "applied_verified_after_review")
        self.assertEqual(
            (self.fixture.workspace / "src/sibling.py").read_text(),
            "stable sibling\n",
        )

    def test_directory_scope_still_rejects_neighboring_preapply_drift(self):
        self.fixture.scopes = ["src"]
        result = self.fixture.invoke(defer_authoritative_apply=True)
        report_id, receipt = self.reference_acceptance(result)
        (self.fixture.workspace / "src/sibling.py").write_text(
            "neighbor drift\n", encoding="utf-8")
        with self.assertRaisesRegex(PermissionError, "unrelated workspace changed"):
            self.apply(result, report_id, receipt)
        self.assertEqual(
            (self.fixture.workspace / "src/allowed.py").read_text(), "before\n")

    def test_directory_scope_rejects_drift_between_broad_and_exact_scans(self):
        self.fixture.scopes = ["src"]
        result = self.fixture.invoke(defer_authoritative_apply=True)
        report_id, receipt = self.reference_acceptance(result)
        sibling = self.fixture.workspace / "src/sibling.py"
        calls = 0

        def inject_after_initial_check(repository, scope):
            nonlocal calls
            value = unrelated_workspace_sha256(repository, scope)
            calls += 1
            if calls == 1:
                sibling.write_text("inter-scan neighbor drift\n", encoding="utf-8")
            return value

        with patch(
            "src.runtime.codex_write_builder_adapter.unrelated_workspace_sha256",
            side_effect=inject_after_initial_check,
        ):
            with self.assertRaisesRegex(PermissionError, "unrelated workspace changed"):
                self.apply(result, report_id, receipt)
        self.assertEqual(calls, 3)
        self.assertEqual(
            (self.fixture.workspace / "src/allowed.py").read_text(), "before\n")


if __name__ == "__main__":
    unittest.main()

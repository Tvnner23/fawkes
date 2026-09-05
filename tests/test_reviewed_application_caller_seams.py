import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.runtime.codex_write_builder_adapter import CodexWriteBuilderAdapter
from src.runtime.worker_exchange import _digest
from tests import test_autonomy_production_transports as transport_fixture


class ReviewedApplicationCallerSeamTests(unittest.TestCase):
    def setUp(self):
        self.fixture = transport_fixture.AutonomyProductionTransportTests(
            "test_deferred_candidate_applies_once_only_after_review_gate")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        (self.fixture.workspace/".git").rmdir()
        subprocess.run(["git","init","-q"],cwd=self.fixture.workspace,check=True)
        subprocess.run(["git","config","user.name","Fixture"],cwd=self.fixture.workspace,check=True)
        subprocess.run(["git","config","user.email","fixture@invalid"],cwd=self.fixture.workspace,check=True)
        (self.fixture.workspace/"neighbor.txt").write_text("neighbor baseline\n")
        subprocess.run(["git","add","src/allowed.py","neighbor.txt"],cwd=self.fixture.workspace,check=True)
        subprocess.run(["git","commit","-qm","base"],cwd=self.fixture.workspace,check=True)

    def completed(self):
        result = self.fixture.invoke(defer_authoritative_apply=True)
        report_id, acceptance = self.fixture.review_acceptance(result)
        adapter = CodexWriteBuilderAdapter(self.fixture.exchange,
            workspace=self.fixture.workspace,
            run_process=transport_fixture.FakeWriteCodex(self.fixture.workspace), timeout_seconds=5)
        applied = adapter.apply_reviewed_candidate_once(
            package_id=self.fixture.package["package_id"],
            campaign_id=self.fixture.campaign, review_report_id=report_id,
            review_acceptance_receipt=acceptance)
        arguments={"operation_id":applied["operation_id"],
            "package_id":self.fixture.package["package_id"],
            "campaign_id":self.fixture.campaign,"review_report_id":report_id,
            "review_acceptance_receipt":acceptance}
        return adapter, applied, arguments

    def test_completed_application_retrieval_is_idempotent(self):
        adapter, applied, arguments = self.completed()
        self.assertEqual(adapter.reconcile_reviewed_candidate_application(**arguments), applied)
        self.assertEqual(adapter.reconcile_reviewed_candidate_application(**arguments), applied)
        self.assertEqual(applied["application_count"], 1)

    def test_neighboring_operation_and_postimage_drift_fail_closed(self):
        adapter, applied, arguments = self.completed()
        with self.assertRaises(PermissionError):
            adapter.reconcile_reviewed_candidate_application(
                **{**arguments,"operation_id":"neighbor"})
        (self.fixture.workspace/"src/allowed.py").write_text("post-terminal drift\n")
        with self.assertRaisesRegex(PermissionError,"drift"):
            adapter.reconcile_reviewed_candidate_application(**arguments)

    def test_tampered_terminal_receipt_fails_closed(self):
        adapter, applied, arguments = self.completed()
        path = (adapter.root/"write-candidate"/self.fixture.package["package_id"]/
                "application.json")
        value=json.loads(path.read_text());value["application_count"]=2
        path.write_text(json.dumps(value))
        with self.assertRaises(PermissionError):
            adapter.reconcile_reviewed_candidate_application(**arguments)

    def test_terminal_reconciliation_rejects_neighboring_state_drift(self):
        adapter, _applied, arguments = self.completed()
        (self.fixture.workspace/"neighbor.txt").write_text("neighbor changed\n")
        with self.assertRaisesRegex(PermissionError,"neighboring|projection drift"):
            adapter.reconcile_reviewed_candidate_application(**arguments)

    def test_canonical_owner_issues_and_resolves_exact_git_eligibility(self):
        adapter, applied, _arguments = self.completed()
        immutable={"maximum_duration_seconds":3600,"maximum_worker_turns":2,
          "maximum_reviewer_turns":4,"maximum_provider_turns":6,
          "maximum_cost_units":6,"maximum_correction_cycles":2,"maximum_iterations":3,
          "created_at":datetime.now(timezone.utc).isoformat(),
          "expires_at":(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
          "contract":"conservative-provider-reservation-failed-safe-v0.1"}
        budget={**immutable,"consumed_worker_turns":1,"consumed_reviewer_turns":2,
          "consumed_provider_turns":3,"consumed_cost_units":3,
          "consumed_correction_cycles":0,"provider_action":None,"provider_actions":[],
          "budget_sha256":_digest(immutable)}
        campaign={"campaign_id":self.fixture.campaign,
          "status":"review_accepted_application_pending","stepwise_v01":True,
          "execution_budget_v01":budget}
        campaign["record_sha256"]=_digest(campaign)
        with self.assertRaisesRegex(PermissionError,"prohibited"):
            adapter.retain_git_commit_eligibility(
              terminal_application_receipt=applied,campaign_record=campaign,
              commit_operation_id=applied["operation_id"])
        self.assertFalse(list(adapter.root.rglob("git-eligibility.json")))


if __name__ == "__main__":
    unittest.main()

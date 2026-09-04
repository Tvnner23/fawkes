import json
import subprocess
import unittest
from pathlib import Path

from src.runtime.codex_write_builder_adapter import CodexWriteBuilderAdapter
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
        subprocess.run(["git","add","src/allowed.py"],cwd=self.fixture.workspace,check=True)
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


if __name__ == "__main__":
    unittest.main()

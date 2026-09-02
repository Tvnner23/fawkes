import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_autonomy_production_transports import FakeWriteCodex, authority
from src.runtime.codex_write_builder_adapter import CodexWriteBuilderAdapter
from src.runtime.disposable_verifier import DisposableVerifierWorkspace, candidate_manifest
from src.runtime.codex_development_campaign import (
    CAMPAIGN_CONTRACT_VERSION, DEFAULT_REVIEWER_ROLE, DEFAULT_REVIEWER_WORKER_ID,
    FORMAL_REVIEW_ROLE, MAX_ITERATIONS, CodexDevelopmentCampaign,
)
from src.runtime.codex_development_handoff import CODEX_REPO_WORKER_REFERENCE
from src.runtime.worker_exchange import WorkerExchange, _digest
from src.runtime.wsl_codex_reviewer import (
    FORMAL_REVIEW_ROLE, WSL_ADAPTER_ID, WSL_ADAPTER_QUALIFIED, WSL_ADAPTER_PROMOTED, WSL_ENVIRONMENT_ID,
    WSL_QUALIFICATION_CONTRACT, WSL_REVIEWER_REFERENCE, WSL_REVIEWER_ROLE,
    WSL_REVIEWER_WORKER_ID, WslCodexReviewAdapter, prepare_wsl_review_package,
)


class FakeWslReviewer:
    def __init__(self, *, status="pass", malformed=False, mutate=False):
        self.status, self.malformed, self.mutate = status, malformed, mutate

    def __call__(self, command, *, prompt, environment, timeout):
        if "--version" in command: return SimpleNamespace(returncode=0, stdout="codex-cli 0.151.0\n", stderr="")
        if command[1:3] == ["login", "status"]: return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        output = Path(command[command.index("--output-last-message") + 1])
        start = "----- BEGIN EXACT WORKER EXCHANGE PACKAGE -----\n"
        package_text = prompt.split(start, 1)[1].split("\n----- END EXACT WORKER EXCHANGE PACKAGE -----", 1)[0]
        package = json.loads(package_text)
        if self.mutate:
            (Path(command[command.index("--cd") + 1]) / "src/allowed.py").write_text("reviewer mutation\n")
        violated = ["done"] if self.status == "correction_required" else []
        satisfied = ["done"] if self.status == "pass" else []
        response = {"schema_version": 1, "package_id": package["package_id"],
            "package_sha256": hashlib.sha256(package_text.encode()).hexdigest(),
            "source_report_id": package["source_report_id"], "task_scope_id": package["task_scope_id"],
            "recipient": {"worker_id": WSL_REVIEWER_WORKER_ID, "role": WSL_REVIEWER_ROLE,
                          "environment_id": WSL_ENVIRONMENT_ID},
            "source_summary_distinction_confirmed": True, "review_status": self.status,
            "acceptance_condition_ids_satisfied": satisfied,
            "violated_acceptance_condition_ids": violated,
            "defects": ([{"defect_id": "defect", "acceptance_condition_id": "done",
                          "evidence_reference": "exact-builder-return"}]
                        if self.status == "correction_required" else []),
            "correctable_within_scope": self.status == "correction_required",
            "sections": [{"section_id": "verdict", "title": "Verdict", "content": self.status}],
            "verification": {"status": ("accepted" if self.status == "pass" else
                "disputed" if self.status == "correction_required" else "insufficient"),
                "checked_claim_ids": ["done"], "evidence_references": package["evidence_references"],
                "method": "exact frozen candidate review", "material_reliance": True,
                "relied_source_section_ids": ["exact-builder-return"], "caveats": [],
                "counterclaim": ({"claim": "Acceptance condition is not met",
                    "evidence_reference": "exact-builder-return"}
                    if self.status == "correction_required" else None)}}
        output.write_text("{" if self.malformed else json.dumps(response), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="event", stderr="")


class WslFormalReviewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.workspace = root / "repo"; self.workspace.mkdir()
        (self.workspace / ".git").mkdir(); (self.workspace / "src").mkdir()
        (self.workspace / "src/allowed.py").write_text("before\n")
        self.exchange = WorkerExchange("fawkes", root=root / "exchange")
        sender = {"worker_id": "fawkes-development", "role": "coordination",
                  "identity_status": "verified", "charter_version": "1.0"}
        worker = {"worker_id": "codex-repository-wsl-fawkes", "role": "software_repository",
                  "identity_status": "rider_attested", "charter_version": "1.0"}
        report = self.exchange.create_report(task_scope_id="write-task", sender=sender,
            authority=authority("fawkes", "write-task", sender["worker_id"]),
            sections=[{"section_id": "task", "title": "Task", "content": "bounded change"}],
            claims=[{"claim_id": "done", "area": "development", "statement": "change done",
                     "maturity": "in_development", "change_class": "software_system"}])
        base = authority("fawkes", "write-task", sender["worker_id"], worker["worker_id"])
        package = self.exchange.compose_package(report_id=report["report_id"], recipient=worker,
            authority=base, included_section_ids=["task"])
        scopes = ["src/allowed.py"]; recovery = [{"reference_type": "working_checkpoint", "reference_id": "before"}]
        write_task = "Modify only src/allowed.py."
        transport = {**base, "adapter_id": "codex-cli-exec-local-write", "package_id": package["package_id"],
            "recipient_environment_id": f"codex-cli:{self.workspace.resolve()}",
            "write_task_sha256": hashlib.sha256(write_task.encode()).hexdigest(), "campaign_id": "campaign",
            "iteration": 1, "allowed_scope_sha256": _digest(scopes),
            "acceptance_condition_ids_sha256": _digest(["done"]), "recovery_references_sha256": _digest(recovery)}
        result = CodexWriteBuilderAdapter(self.exchange, workspace=self.workspace,
            run_process=FakeWriteCodex(self.workspace), timeout_seconds=5).deliver_candidate_once(
            package_id=package["package_id"], transport_authority=transport,
            return_authority=authority("fawkes", "write-task", worker["worker_id"]),
            recipient_environment_id=f"codex-cli:{self.workspace.resolve()}", write_task=write_task,
            campaign_id="campaign", iteration=1, allowed_scope=scopes,
            acceptance_condition_ids=["done"], recovery_references=recovery)
        returned = self.exchange._load("reports", result["return_report_id"])
        self.campaign = {"instance_id": "fawkes", "campaign_id": "campaign",
            "status": "awaiting_independent_review", "iteration": 1, "objective": "Review exact change.",
            "acceptance_condition_ids": ["done"], "acceptance_conditions": {"done": "Change is exact."},
            "allowed_scope": scopes, "recovery_references": recovery, "contract_version": "fixture-v1",
            "builder_runs": [{"iteration": 1, "return_report_id": returned["report_id"],
                "package_id": package["package_id"],
                "transport_result_reference": {"workspace_changes_sha256": result["workspace_changes_sha256"]},
                "validation_evidence": [{"argv": ["test"], "exit_status": 0}],
                "completed_at": datetime.now(timezone.utc).isoformat()}]}
        manifest = candidate_manifest(self.workspace)
        self.provenance = {**manifest, "record_sha256": _digest(manifest),
            "file_count": len(manifest["files"]),
            "total_byte_length": sum(x["byte_length"] for x in manifest["files"])}
        self.prepared = prepare_wsl_review_package(exchange=self.exchange, campaign_record=self.campaign,
            candidate_snapshot=self.provenance, workspace=self.workspace)

    def invoke(self, fake=None, **changes):
        kwargs = {"package_id": self.prepared["package_id"],
            "transport_authority": {**self.prepared["transport_authority"], **changes.pop("authority", {})},
            "return_authority": self.prepared["return_authority"], "campaign_id": "campaign",
            "builder_return_report_id": self.campaign["builder_runs"][-1]["return_report_id"],
            "candidate_snapshot_id": self.provenance["candidate_snapshot_id"],
            "candidate_snapshot_root": self.workspace, **changes}
        return WslCodexReviewAdapter(self.exchange, run_process=fake or FakeWslReviewer(),
            timeout_seconds=5).deliver_candidate_once(**kwargs)

    def test_identity_functional_role_and_zero_authority_are_distinct(self):
        self.assertEqual(WSL_REVIEWER_REFERENCE["functional_role"], FORMAL_REVIEW_ROLE)
        self.assertNotEqual(WSL_REVIEWER_WORKER_ID, "codex-repository-wsl-fawkes")
        self.assertFalse(WSL_REVIEWER_REFERENCE["identified_is_authorized"])
        self.assertTrue(WSL_ADAPTER_QUALIFIED)
        self.assertTrue(WSL_ADAPTER_PROMOTED)
        self.assertEqual(WSL_REVIEWER_REFERENCE["transport_status"], "promoted_bounded_read_only")
        self.assertEqual(len(WSL_QUALIFICATION_CONTRACT["hard_invariants"]), 16)

    def test_exact_frozen_package_pass_retains_lineage_and_no_authority(self):
        result = self.invoke()
        self.assertEqual((result["status"], result["review_status"]), ("delivered", "pass"))
        self.assertFalse(result["creates_authority"])
        self.assertEqual(result["candidate_snapshot_id"], self.provenance["candidate_snapshot_id"])
        self.assertEqual(result["builder_return_reference"], self.prepared["builder_return_reference"])

    def test_wrong_candidate_worker_campaign_and_write_authority_fail_closed(self):
        with self.assertRaises(PermissionError): self.invoke(candidate_snapshot_id="candidate-snapshot-wrong")
        with self.assertRaises(PermissionError): self.invoke(authority={"campaign_id": "wrong"})
        package = self.exchange._load("packages", self.prepared["package_id"])
        package["recipient"]["worker_id"] = "codex-repository-wsl-fawkes"
        with unittest.mock.patch.object(self.exchange, "_load", return_value=package):
            with self.assertRaises(PermissionError): self.invoke()

    def test_structured_correction_insufficient_and_malformed(self):
        correction = self.invoke(FakeWslReviewer(status="correction_required"))
        self.assertEqual(correction["review_status"], "correction_required")
        self.setUp(); insufficient = self.invoke(FakeWslReviewer(status="insufficient_evidence"))
        self.assertEqual(insufficient["review_status"], "insufficient_evidence")
        self.setUp(); malformed = self.invoke(FakeWslReviewer(malformed=True))
        self.assertEqual(malformed["failure_reason"], "malformed_or_unbound_response")

    def test_read_only_mutation_timeout_replay_and_production_gate_fail_closed(self):
        changed = self.invoke(FakeWslReviewer(mutate=True))
        self.assertEqual(changed["failure_reason"], "candidate_snapshot_changed")
        self.setUp()
        def timeout(*args, **kwargs): raise subprocess.TimeoutExpired("codex", 1)
        failed = self.invoke(timeout); self.assertEqual(failed["failure_reason"], "preflight_failure")
        self.setUp(); self.invoke()
        with self.assertRaises(RuntimeError): self.invoke()
        with self.assertRaises(PermissionError):
            WslCodexReviewAdapter(self.exchange).deliver_production_once(
                package_id=self.prepared["package_id"],
                transport_authority={k: v for k, v in self.prepared["transport_authority"].items()
                                     if k != "adapter_promotion_reference"},
                return_authority=self.prepared["return_authority"], campaign_id="campaign",
                builder_return_report_id=self.campaign["builder_runs"][-1]["return_report_id"],
                candidate_snapshot_id=self.provenance["candidate_snapshot_id"],
                candidate_snapshot_root=self.workspace)

    def _formal_campaign(self):
        coordinator = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "campaigns",
                                               exchange=self.exchange)
        now = datetime.now(timezone.utc).isoformat()
        record = {"schema_version": 1, "record_type": "codex_development_campaign",
            "contract_version": CAMPAIGN_CONTRACT_VERSION, "campaign_id": "campaign",
            "instance_id": "fawkes", "objective": self.campaign["objective"],
            "objective_sha256": hashlib.sha256(self.campaign["objective"].encode()).hexdigest(),
            "objective_mode": "repository_write", "acceptance_condition_ids": ["done"],
            "acceptance_conditions": self.campaign["acceptance_conditions"],
            "allowed_scope": self.campaign["allowed_scope"], "source_sections": [],
            "validation_commands": [], "rider_authorization_reference": "test-rider-authority",
            "recovery_references": self.campaign["recovery_references"],
            "builder": {**CODEX_REPO_WORKER_REFERENCE, "target": "codex_repo",
                        "execution_mode_required": "repository_write", "identified_is_authorized": False},
            "reviewer_requirement": {"functional_role": FORMAL_REVIEW_ROLE,
                "role": DEFAULT_REVIEWER_ROLE, "worker_id": DEFAULT_REVIEWER_WORKER_ID,
                "transport_binding": "wsl-codex-exec-exact-review-v0.1",
                "must_differ_from_builder": True, "identity_is_authority": False},
            "maximum_iterations": MAX_ITERATIONS, "iteration": 1,
            "status": "awaiting_independent_review", "active_builder_task_scope_id": None,
            "builder_runs": self.campaign["builder_runs"], "reviews": [], "review_requests": [],
            "review_transport_attempts": [], "cache_lifecycle_events": [], "acceptance_satisfied": [],
            "needs_tanner": None, "cancelled": False, "automatic_promotion": False,
            "creates_authority": False, "state_revision": 1, "created_at": now, "updated_at": now,
            "events": []}
        coordinator.store.write(record)
        return coordinator

    def test_campaign_default_uses_promoted_wsl_and_consumes_terminal_pass(self):
        coordinator = self._formal_campaign()
        with patch("src.runtime.codex_development_campaign.ROOT", self.workspace):
            terminal = coordinator.run_to_terminal("campaign", reviewer_adapter=WslCodexReviewAdapter(
                self.exchange, run_process=FakeWslReviewer(), timeout_seconds=5))
        self.assertEqual(terminal["status"], "succeeded")
        self.assertEqual(terminal["reviews"][-1]["reviewer"]["worker_id"], WSL_REVIEWER_WORKER_ID)
        self.assertEqual(terminal["maximum_iterations"], 3)
        self.assertFalse(terminal["creates_authority"])

    @unittest.skipUnless(os.environ.get("FAWKES_WSL_CAMPAIGN_ACCEPTANCE") == "1",
                         "set FAWKES_WSL_CAMPAIGN_ACCEPTANCE=1 for real production review path")
    def test_real_campaign_default_wsl_review_reaches_terminal_decision(self):
        coordinator = self._formal_campaign()
        with patch("src.runtime.codex_development_campaign.ROOT", self.workspace):
            terminal = coordinator.run_to_terminal("campaign")
        self.assertIn(terminal["status"], {"succeeded", "tanner_escalation"})
        self.assertEqual(terminal["reviewer_requirement"]["worker_id"], WSL_REVIEWER_WORKER_ID)
        self.assertEqual(terminal["maximum_iterations"], 3)

    @unittest.skipUnless(os.environ.get("FAWKES_WSL_CODEX_QUALIFICATION") == "1",
                         "set FAWKES_WSL_CODEX_QUALIFICATION=1 for real WSL route")
    def test_real_authenticated_wsl_formal_review_route(self):
        with DisposableVerifierWorkspace(self.workspace) as frozen:
            prepared = prepare_wsl_review_package(exchange=self.exchange, campaign_record=self.campaign,
                candidate_snapshot=frozen.provenance, workspace=self.workspace)
            result = WslCodexReviewAdapter(self.exchange, timeout_seconds=420).deliver_candidate_once(
                package_id=prepared["package_id"], transport_authority=prepared["transport_authority"],
                return_authority=prepared["return_authority"], campaign_id="campaign",
                builder_return_report_id=self.campaign["builder_runs"][-1]["return_report_id"],
                candidate_snapshot_id=frozen.provenance["candidate_snapshot_id"],
                candidate_snapshot_root=frozen.root)
        self.assertEqual(result["status"], "delivered")
        self.assertIn(result["review_status"], {"pass", "pass_with_caveats", "correction_required", "insufficient_evidence", "blocked"})


if __name__ == "__main__": unittest.main()

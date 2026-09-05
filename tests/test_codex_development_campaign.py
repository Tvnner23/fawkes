import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.runtime.codex_development_campaign import (
    CAMPAIGN_ACCEPTANCE_CONTRACT, CAMPAIGN_CONTRACT_VERSION, MAX_ITERATIONS,
    DEFAULT_REVIEWER_BINDING_ASSURANCE, DEFAULT_REVIEWER_ROLE, DEFAULT_REVIEWER_WORKER_ID,
    FORMAL_REVIEW_ROLE,
    ROOT,
    CodexDevelopmentCampaign,
    _cleanup_python_cache,
    stepwise_campaign_budget_limits,
    stepwise_campaign_status_disposition,
)
from src.runtime.codex_development_handoff import run_codex_development_handoff
from src.runtime.phase0_integrity import SCOPED_ROOTS
from src.runtime.worker_exchange import WorkerExchange, _digest
from src.runtime.development_attention import DevelopmentAttentionStore
from src.runtime.disposable_verifier import candidate_manifest
from src.runtime.codex_app_server import typed_approval
from src.runtime.wsl_codex_reviewer import _review_attention_binding


BUILDER_ID = "codex-repository-wsl-fawkes"
REVIEWER = {"worker_id": DEFAULT_REVIEWER_WORKER_ID, "role": DEFAULT_REVIEWER_ROLE,
            "identity_status": "rider_attested", "charter_version": "1.0"}


def authority(instance_id, task_scope_id, sender, recipient=None):
    value = {"decision": "authorized", "instance_id": instance_id, "task_scope_id": task_scope_id,
             "sender_worker_id": sender, "authorization_reference": f"test-{task_scope_id}",
             "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    if recipient:
        value["recipient_worker_id"] = recipient
    return value


class SuccessfulBuilderAdapter:
    def __init__(self, exchange):
        self.exchange = exchange
        self.candidate = exchange.root.parent / "retained-candidate"
        self.candidate.mkdir(parents=True, exist_ok=True)
        (self.candidate / "fixture.txt").write_text("candidate\n", encoding="utf-8")

    def deliver_production_once(self, **arguments):
        package = self.exchange._load("packages", arguments["package_id"])
        delivery = self.exchange.record_delivery(package_id=package["package_id"],
            authority=arguments["transport_authority"], adapter_id="fixture-builder",
            adapter_version="1", status="delivered", delivery_reference=f"fixture-{package['task_scope_id']}")
        claims = [item["claim_id"] for item in package["claims"]]
        verification = self.exchange.record_verification(package_id=package["package_id"],
            recipient=package["recipient"], authority=arguments["transport_authority"], status="accepted",
            checked_claim_ids=claims, evidence_references=[], method="deterministic builder fixture")
        returned = self.exchange.create_return_report(source_package_id=package["package_id"],
            task_scope_id=package["task_scope_id"], sender=package["recipient"],
            authority=arguments["return_authority"], sections=[
                {"section_id": "result", "title": "Exact builder result",
                 "content": "Bounded candidate and validation evidence produced."}],
            evidence_references=[])
        manifest = candidate_manifest(self.candidate)
        snapshot = {"candidate_snapshot_id": manifest["candidate_snapshot_id"],
            "record_sha256": __import__("hashlib").sha256(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "file_count": len(manifest["files"]),
            "total_byte_length": sum(item["byte_length"] for item in manifest["files"])}
        mutation_sha = _digest([])
        exact_evidence_sha = _digest([])
        application = {"record_type": "codex_candidate_retention_intent",
            "status": "awaiting_independent_review", "applied_paths": [],
            "mutation_manifest_sha256": mutation_sha,
            "exact_change_evidence_sha256": exact_evidence_sha,
            "candidate_snapshot_id": snapshot["candidate_snapshot_id"],
            "candidate_record_sha256": snapshot["record_sha256"],
            "creates_authority": False}
        application["application_record_sha256"] = _digest(application)
        return {"status": "delivered", "delivery_receipt_id": delivery["delivery_receipt_id"],
            "verification_receipt_id": verification["verification_receipt_id"],
            "return_report_id": returned["report_id"], "adapter_promoted": True,
            "candidate_qualified": True, "candidate_workspace": str(self.candidate),
            "candidate_snapshot": {key: snapshot[key] for key in
                ("candidate_snapshot_id", "record_sha256", "file_count", "total_byte_length")},
            "workspace_changes_sha256": mutation_sha,
            "exact_change_evidence_sha256": exact_evidence_sha,
            "application_evidence": application,
            "invocation_id": arguments.get("invocation_id") or "fixture-builder-invocation",
            "creates_authority": False}


class CampaignFixture:
    def __init__(self, root):
        self.instance_id = "fawkes"
        self.exchange = WorkerExchange(self.instance_id, root=root / "exchange")
        self.adapter = SuccessfulBuilderAdapter(self.exchange)
        self.builder_payloads = []
        self.applications = []

        def builder(payload):
            self.builder_payloads.append(payload)
            return run_codex_development_handoff(instance_id=self.instance_id, payload=payload,
                authenticated_rider=True, exchange=self.exchange, adapter=self.adapter)

        def apply_candidate(**kwargs):
            self.applications.append(kwargs)
            return {"status":"applied_verified_after_review", "applied_paths":[], **kwargs}
        runtime=root/"runtime";runtime.mkdir()
        self.campaign = CodexDevelopmentCampaign(self.instance_id, root=root / "campaigns",
            exchange=self.exchange, builder_runner=builder, builder_modes={"repository_write"},
            candidate_applier=apply_candidate,runtime_state_root=runtime)

    def payload(self, campaign_id="campaign-one"):
        return {"instance_id": self.instance_id, "campaign_id": campaign_id,
            "target_builder": "codex_repo", "objective_mode": "repository_write",
            "objective": "Implement only the bounded fixture change and validate it.",
            "acceptance_condition_ids": ["tests-pass", "scope-held"],
            "acceptance_conditions": {"tests-pass": "Focused tests pass.",
                                      "scope-held": "No files outside allowed scope change."},
            "allowed_scope": ["src/runtime/fixture.py", "tests/test_fixture.py"],
            "source_sections": [{"section_id": "rider-context", "title": "Exact rider context",
                                 "content": "Do not modify unrelated systems."}],
            "rider_authorization_reference": "tanner-fixture-campaign",
            "validation_policy": "intentionally_not_applicable",
            "validation_not_applicable_reason_code": "no_deterministic_validation_applicable",
            "recovery_references": [{"reference_type": "working_checkpoint",
                                     "reference_id": "checkpoint-before-fixture"}],
            "explicitly_authorized": True}

    def review(self, campaign_id, status, *, satisfied=(), defects=(), violated=(), correctable=True):
        record = self.campaign.store.load(campaign_id)
        task_scope = f"{campaign_id}-windows-review-{record['iteration']}"
        sender = {"worker_id": "fawkes-development", "role": "coordination",
                  "identity_status": "verified", "charter_version": "1.0"}
        builder_return = self.exchange._load("reports", record["builder_runs"][-1]["return_report_id"])
        source = self.exchange.create_report(task_scope_id=task_scope, sender=sender,
            authority=authority(self.instance_id, task_scope, sender["worker_id"]),
            sections=[{"section_id": "review-target", "title": "Review target",
                       "content": "Review the exact retained builder candidate."}], claims=[],
            evidence_references=[{"reference_type": "worker_exchange_report",
                "reference_id": builder_return["report_id"],
                "sha256": builder_return["record_sha256"]}])
        transport = authority(self.instance_id, task_scope, sender["worker_id"], REVIEWER["worker_id"])
        package = self.exchange.compose_package(report_id=source["report_id"], recipient=REVIEWER,
            authority=transport, included_section_ids=["review-target"])
        delivery = self.exchange.record_delivery(package_id=package["package_id"], authority=transport,
            adapter_id="windows-review-fixture", adapter_version="1", status="delivered",
            delivery_reference=f"review-delivery-{record['iteration']}")
        exchange_status = {"pass": "accepted", "pass_with_caveats": "accepted_with_caveats",
            "correction_required": "disputed", "insufficient_evidence": "insufficient",
            "blocked": "unverified"}[status]
        verification = self.exchange.record_verification(package_id=package["package_id"], recipient=REVIEWER,
            authority=transport, status=exchange_status, checked_claim_ids=[], evidence_references=[],
            method="independent deterministic review fixture",
            caveats=["fixture caveat"] if exchange_status == "accepted_with_caveats" else [],
            counterclaim={"claim": "candidate defect", "evidence_reference": "review-evidence"}
                         if exchange_status == "disputed" else None)
        returned = self.exchange.create_return_report(source_package_id=package["package_id"],
            task_scope_id=task_scope, sender=REVIEWER,
            authority=authority(self.instance_id, task_scope, REVIEWER["worker_id"]),
            sections=[{"section_id": "verdict", "title": "Exact independent verdict",
                       "content": "Exact defect and evidence from the independent reviewer."}],
            evidence_references=[])
        review = {"status": status, "review_report_id": returned["report_id"],
            "invocation_id": f"fixture-review-{record['iteration']}",
            "recipient": {"worker_id": REVIEWER["worker_id"], "role": REVIEWER["role"],
                          "environment_id": "fixture-read-only"},
            "delivery_receipt_id": delivery["delivery_receipt_id"],
            "verification_receipt_id": verification["verification_receipt_id"],
            "acceptance_condition_ids_satisfied": list(satisfied),
            "violated_acceptance_condition_ids": list(violated), "defects": list(defects),
            "correctable_within_scope": bool(correctable)}
        if status in {"pass", "pass_with_caveats"}:
            retention=record["builder_runs"][-1]["candidate_retention_receipt"]
            receipt={"schema_version":1,
                "record_type":"codex_independent_review_acceptance_receipt",
                "status":"accepted","campaign_id":campaign_id,
                "package_id":record["builder_runs"][-1]["package_id"],
                "review_package_id":package["package_id"],
                "review_package_sha256":package["record_sha256"],
                "source_report_id":package["source_report_id"],
                "review_report_id":returned["report_id"],
                "review_report_sha256":returned["record_sha256"],
                "review_invocation_id":review["invocation_id"],
                "reviewer_worker_id":REVIEWER["worker_id"],"reviewer_role":REVIEWER["role"],
                "recipient":{"worker_id":REVIEWER["worker_id"],"role":REVIEWER["role"],
                             "environment_id":"fixture-read-only"},
                "candidate_snapshot_id":retention["candidate_snapshot"]["candidate_snapshot_id"],
                "mutation_manifest_sha256":retention["mutation_manifest_sha256"],
                "allowed_scope_sha256":retention["allowed_scope_sha256"],
                "candidate_retention_receipt_sha256":retention["record_sha256"],
                "acceptance_condition_ids_sha256":_digest(sorted(satisfied)),
                "delivery_receipt_id":delivery["delivery_receipt_id"],
                "verification_receipt_id":verification["verification_receipt_id"],
                "verdict":status,
                "creates_authority":False,"created_at":datetime.now(timezone.utc).isoformat()}
            receipt["record_sha256"]=_digest(receipt); review["review_acceptance_receipt"]=receipt
        return review



class CodexDevelopmentCampaignTests(unittest.TestCase):
    def _review_native_approval_fixture(self, campaign_id):
        campaign = self.fixture.campaign
        campaign.attention_store = DevelopmentAttentionStore(
            Path(self.tmp.name) / f"{campaign_id}-attention")
        record = campaign.create(self.fixture.payload(campaign_id),
                                 authenticated_rider=True)
        retention = record["builder_runs"][-1]["candidate_retention_receipt"]
        sender = {"worker_id": "fawkes-development", "role": "coordination",
                  "identity_status": "verified", "charter_version": "1.0"}
        task = f"{campaign_id}-review-1"
        report = self.fixture.exchange.create_report(
            task_scope_id=task, sender=sender,
            authority=authority("fawkes", task, sender["worker_id"]),
            sections=[
                {"section_id": "review-target", "title": "Review target",
                 "content": "Review the exact retained candidate."},
                {"section_id": "candidate-snapshot", "title": "Candidate snapshot",
                 "content": json.dumps(retention["candidate_snapshot"],
                                       sort_keys=True)},
                {"section_id": "candidate-retention-receipt",
                 "title": "Candidate retention receipt",
                 "content": json.dumps(retention, sort_keys=True)},
            ], claims=[])
        package_authority = authority(
            "fawkes", task, sender["worker_id"], REVIEWER["worker_id"])
        package = self.fixture.exchange.compose_package(
            report_id=report["report_id"], recipient=REVIEWER,
            authority=package_authority, included_section_ids=[
                "review-target", "candidate-snapshot",
                "candidate-retention-receipt"])
        record = campaign._update(record, event_kind="review_requested_fixture",
            review_requests=[{"iteration": record["iteration"],
                              "package_id": package["package_id"]}])
        transport = {
            "candidate_record_sha256": retention["candidate_snapshot"]["record_sha256"],
            "mutation_manifest_sha256": retention["mutation_manifest_sha256"],
            "exact_change_evidence_sha256": retention["exact_change_evidence_sha256"],
            "allowed_scope_sha256": retention["allowed_scope_sha256"],
            "candidate_retention_receipt_sha256": retention["record_sha256"],
        }
        reviewer = {"worker_id": REVIEWER["worker_id"], "role": REVIEWER["role"],
                    "environment_id": "fixture-review-read-only"}
        return campaign, record, package, transport, reviewer

    @staticmethod
    def _typed_review_approval(campaign_id, package, transport, reviewer,
                               invocation_id, item_id):
        binding = _review_attention_binding(
            package=package, transport_authority=transport,
            campaign_id=campaign_id,
            candidate_snapshot_id=transport["candidate_snapshot_id"],
            reviewer=reviewer, reviewer_invocation_id=invocation_id)
        return typed_approval(
            "item/commandExecution/requestApproval",
            {"threadId": "thread-review", "turnId": "turn-review",
             "itemId": item_id, "command": f"read-only {item_id}",
             "cwd": "/disposable", "reason": "bounded review evidence",
             "availableDecisions": ["accept", "decline", "cancel"]},
            campaign_id=campaign_id, invocation_id=invocation_id,
            worker=reviewer, process_id=os.getpid(),
            active_thread_id="thread-review", active_turn_id="turn-review",
            approval_binding=binding, reviewer_invocation_id=invocation_id)

    def _wait_for_attention(self, campaign, *, excluding=()):
        excluded = set(excluding)
        for _ in range(200):
            events = [item for item in campaign.attention_store.list(pending_only=True)
                      if item["attention_id"] not in excluded]
            if events:
                return events[0]
            threading.Event().wait(0.01)
        self.fail("canonical Reviewer Attention event was not retained")

    def test_reviewer_can_request_two_separately_bound_native_actions_in_one_turn(self):
        campaign_id = "review-native-multiaction"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        invocation = "review-native-invocation"
        first = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation, "item-one")
        first_result, first_failure = {}, []
        thread = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, first, first_result, first_failure))
        thread.start()
        first_event = self._wait_for_attention(campaign)
        decided = campaign.decide_attention(
            campaign_id, first_event["attention_id"], "approve_once",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(first_event))
        thread.join(2)
        self.assertEqual(first_failure, [])
        self.assertEqual(decided["campaign"]["status"],
                         "reviewer_native_action_approved")
        first_result["value"]["claim"]()
        with self.assertRaises(PermissionError):
            first_result["value"]["claim"]()
        first_result["value"]["complete"]("failed")
        self.assertEqual(campaign.store.load(campaign_id)["status"],
                         "awaiting_independent_review")

        second = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation, "item-two")
        second_result, second_failure = {}, []
        thread = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, second, second_result, second_failure))
        thread.start()
        second_event = self._wait_for_attention(
            campaign, excluding={first_event["attention_id"]})
        campaign.decide_attention(
            campaign_id, second_event["attention_id"], "deny",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(second_event))
        thread.join(2)
        self.assertEqual(second_failure, [])
        self.assertEqual(second_result["value"]["choice"], "deny")
        self.assertEqual(campaign.store.load(campaign_id)["status"], "failed_safe")

    def test_reviewer_action_cannot_resume_before_campaign_publication(self):
        campaign_id = "review-native-publication-race"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        invocation = "review-publication-race-invocation"
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation, "race-item")
        action_completed = threading.Event()
        action_failures = []

        def paused_action():
            try:
                decision = campaign._handle_typed_approval(
                    approval, timeout_seconds=2, process_alive=lambda: True)
                decision["claim"]()
                decision["complete"]("completed")
                action_completed.set()
            except BaseException as exc:
                action_failures.append(exc)

        waiter = threading.Thread(target=paused_action)
        waiter.start()
        event = self._wait_for_attention(campaign)
        publication_entered = threading.Event()
        release_publication = threading.Event()
        original_update = campaign._update

        def blocked_publication(record, **changes):
            if changes.get("event_kind") == "tanner_attention_approve_once":
                publication_entered.set()
                if not release_publication.wait(2):
                    raise TimeoutError("test publication barrier timed out")
            return original_update(record, **changes)

        decision_failures = []
        def decide():
            try:
                campaign.decide_attention(
                    campaign_id, event["attention_id"], "approve_once",
                    authenticated_rider=True,
                    expected_identity=campaign.attention_store._authority_binding(event))
            except BaseException as exc:
                decision_failures.append(exc)

        with patch.object(campaign, "_update", side_effect=blocked_publication):
            decider = threading.Thread(target=decide)
            decider.start()
            self.assertTrue(publication_entered.wait(2))
            self.assertFalse(action_completed.is_set())
            self.assertEqual(action_failures, [])
            release_publication.set()
            decider.join(2)
            waiter.join(2)

        self.assertEqual(decision_failures, [])
        self.assertEqual(action_failures, [])
        self.assertTrue(action_completed.is_set())
        terminal = campaign.store.load(campaign_id)
        self.assertEqual(terminal["status"], "awaiting_independent_review")
        self.assertIsNone(terminal.get("active_review_native_action"))
        self.assertFalse(terminal["creates_continuing_authority"])

    def test_review_decision_interrupted_before_campaign_publication_closes_failed_safe(self):
        campaign_id = "review-native-decision-publication-crash"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        invocation = "review-publication-crash-invocation"
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation,
            "publication-crash-item")
        result, failures = {}, []
        waiter = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, approval, result, failures))
        waiter.start()
        event = self._wait_for_attention(campaign)
        original_update = campaign._update

        def interrupt_publication(record, **changes):
            if changes.get("event_kind") == "tanner_attention_approve_once":
                raise SystemExit("process interrupted before campaign publication")
            return original_update(record, **changes)

        with patch.object(campaign, "_update", side_effect=interrupt_publication):
            with self.assertRaisesRegex(SystemExit, "before campaign publication"):
                campaign.decide_attention(
                    campaign_id, event["attention_id"], "approve_once",
                    authenticated_rider=True,
                    expected_identity=campaign.attention_store._authority_binding(event))
        lifecycle = campaign.attention_store.lifecycle(event["attention_id"])
        self.assertEqual(lifecycle["decision"]["campaign_publication"]["state"],
                         "pending")
        self.assertFalse(lifecycle["decision"]["creates_authority"])
        reconciled = campaign.reconcile_attention_decision(campaign_id)
        waiter.join(2)
        self.assertEqual(reconciled["status"], "failed_safe")
        self.assertEqual(reconciled["needs_tanner"]["reason"],
                         "attention_decision_publication_interrupted")
        lifecycle = campaign.attention_store.lifecycle(event["attention_id"])
        self.assertEqual(lifecycle["decision"]["campaign_publication"]["state"],
                         "failed_safe")
        self.assertFalse(lifecycle["decision"]["creates_authority"])
        self.assertFalse(reconciled["creates_continuing_authority"])

    def test_terminal_live_reviewer_action_reconciles_after_campaign_checkpoint_crash(self):
        campaign_id = "review-native-live-checkpoint-crash"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        invocation = "review-live-checkpoint-invocation"
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation,
            "live-checkpoint-item")
        result, failures = {}, []
        waiter = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, approval, result, failures))
        waiter.start()
        event = self._wait_for_attention(campaign)
        campaign.decide_attention(
            campaign_id, event["attention_id"], "approve_once",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(event))
        waiter.join(2)
        self.assertEqual(failures, [])
        result["value"]["claim"]()
        with patch.object(campaign, "_finish_review_native_action",
                          side_effect=RuntimeError("crash after live terminal write")):
            with self.assertRaisesRegex(RuntimeError, "after live terminal"):
                result["value"]["complete"]("completed")

        retained = campaign.store.load(campaign_id)
        self.assertEqual(retained["status"], "reviewer_native_action_approved")
        self.assertEqual(campaign.attention_store.lifecycle(
            event["attention_id"])["decision"]["lifecycle_state"], "completed")
        reconciled = campaign.advance_once(campaign_id)
        self.assertEqual(reconciled["status"], "awaiting_independent_review")
        self.assertIsNone(reconciled.get("active_review_native_action"))
        self.assertFalse(reconciled["creates_continuing_authority"])

    def test_detached_reviewer_action_restores_campaign_after_transport_loss(self):
        campaign_id = "review-native-detached-closure"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        invocation = "review-detached-invocation"
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation,
            "detached-item")
        result, failures = {}, []
        waiter = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, approval, result, failures))
        waiter.start()
        event = self._wait_for_attention(campaign)
        campaign.decide_attention(
            campaign_id, event["attention_id"], "approve_once",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(event))
        waiter.join(2)
        self.assertEqual(failures, [])
        continuation_id = "review-detached-continuation"
        with patch.object(campaign.attention_store,
                          "_complete_recovery_evidence", return_value=True):
            result["value"]["reserve"](continuation_id)
            result["value"]["claim"](continuation_id)
            finished = result["value"]["finish"](continuation_id, "failed")

        terminal = campaign.store.load(campaign_id)
        self.assertEqual(terminal["status"], "awaiting_independent_review")
        self.assertIsNone(terminal.get("active_review_native_action"))
        lifecycle = campaign.attention_store.lifecycle(event["attention_id"])
        self.assertEqual(lifecycle["decision"]["lifecycle_state"], "failed_safe")
        self.assertFalse(terminal["creates_authority"])
        self.assertFalse(terminal["creates_continuing_authority"])
        self.assertEqual(
            result["value"]["finish"](continuation_id, "failed"), finished)

    def test_terminal_detached_reviewer_action_reconciles_after_campaign_checkpoint_crash(self):
        campaign_id = "review-native-detached-checkpoint-crash"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        invocation = "review-detached-checkpoint-invocation"
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation,
            "detached-checkpoint-item")
        result, failures = {}, []
        waiter = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, approval, result, failures))
        waiter.start()
        event = self._wait_for_attention(campaign)
        campaign.decide_attention(
            campaign_id, event["attention_id"], "approve_once",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(event))
        waiter.join(2)
        self.assertEqual(failures, [])
        continuation_id = "review-detached-checkpoint-continuation"
        with patch.object(campaign.attention_store,
                          "_complete_recovery_evidence", return_value=True):
            result["value"]["reserve"](continuation_id)
            result["value"]["claim"](continuation_id)
            with patch.object(campaign, "_finish_review_native_action",
                              side_effect=RuntimeError("crash after Attention terminal write")):
                with self.assertRaisesRegex(RuntimeError, "crash after Attention"):
                    result["value"]["finish"](continuation_id, "failed")

            retained = campaign.store.load(campaign_id)
            self.assertEqual(retained["status"], "reviewer_native_action_approved")
            self.assertEqual(campaign.attention_store.lifecycle(
                event["attention_id"])["decision"]["lifecycle_state"], "failed_safe")
            recovery_calls = []
            recovered = campaign.resume_reserved_continuation(
                campaign_id, event["attention_id"],
                result["value"]["decision_id"], continuation_id,
                recovery_runner=lambda *args, **kwargs: recovery_calls.append(
                    (args, kwargs)))

        self.assertEqual(recovery_calls, [])
        self.assertEqual(recovered["campaign"]["status"],
                         "awaiting_independent_review")
        self.assertIsNone(recovered["campaign"].get("active_review_native_action"))
        self.assertFalse(recovered["campaign"]["creates_continuing_authority"])

    def test_unresumable_reviewer_transport_loss_closes_failed_safe(self):
        campaign_id = "review-native-unresumable-loss"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        invocation = "review-unresumable-invocation"
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer, invocation, "lost-item")
        result, failures = {}, []
        waiter = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, approval, result, failures))
        waiter.start()
        event = self._wait_for_attention(campaign)
        campaign.decide_attention(
            campaign_id, event["attention_id"], "approve_once",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(event))
        waiter.join(2)
        self.assertEqual(failures, [])

        with self.assertRaises(PermissionError):
            result["value"]["reserve"]("unavailable-continuation")
        terminal = campaign.store.load(campaign_id)
        self.assertEqual(terminal["status"], "failed_safe")
        self.assertEqual(terminal["needs_tanner"]["reason"],
                         "reviewer_native_action_transport_lost")
        lifecycle = campaign.attention_store.lifecycle(event["attention_id"])
        self.assertTrue(lifecycle["decision"]["consumed"])
        self.assertEqual(lifecycle["decision"]["lifecycle_state"], "failed_safe")
        self.assertFalse(terminal["creates_authority"])
        self.assertFalse(terminal["creates_continuing_authority"])

    @staticmethod
    def _capture_approval_result(campaign, approval, result, failures,
                                 timeout_seconds=2):
        try:
            result["value"] = campaign._handle_typed_approval(
                approval, timeout_seconds=timeout_seconds,
                process_alive=lambda: True)
        except BaseException as exc:
            failures.append(exc)

    def test_reviewer_attention_expiry_closes_campaign_failed_safe(self):
        campaign_id = "review-native-expiry"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer,
            "review-expiry-invocation", "expiry-item")
        result, failures = {}, []
        thread = threading.Thread(target=lambda: self._capture_approval_result(
            campaign, approval, result, failures, timeout_seconds=0.05))
        thread.start(); thread.join(2)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], TimeoutError)
        terminal = campaign.store.load(campaign_id)
        self.assertEqual(terminal["status"], "failed_safe")
        self.assertFalse(terminal["creates_authority"])
        self.assertFalse(terminal["creates_continuing_authority"])

    def test_restart_reconciles_decision_free_expired_reviewer_attention(self):
        campaign_id = "review-native-expired-restart"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer,
            "review-expired-restart-invocation", "expired-restart-item")
        paused = campaign.require_tanner(
            campaign_id, invocation_id=approval["invocation_id"],
            worker=approval["worker"], kind=approval["kind"],
            blocked_action=approval["blocked_action"],
            why_required=approval["why_required"],
            requested_authority=approval["requested_authority"],
            resources=approval["resources"], reversible=approval["reversible"],
            provider_code=approval["provider_code"],
            protocol_binding=approval["protocol"], expires_in_seconds=3600,
            expiration_reason="bounded review expired",
            expiration_effect="protected action remains unperformed",
            can_request_again=True, work_lost=False)
        attention_id = paused["needs_tanner"]["attention_id"]
        path = campaign.attention_store.events / f"{attention_id}.json"
        event = json.loads(path.read_text(encoding="utf-8"))
        event["expires_at"] = (datetime.now(timezone.utc)
            - timedelta(seconds=1)).isoformat()
        event.pop("record_sha256", None); event["record_sha256"] = _digest(event)
        path.write_text(json.dumps(event), encoding="utf-8")

        terminal = campaign.advance_once(campaign_id)
        self.assertEqual(terminal["status"], "failed_safe")
        self.assertEqual(terminal["needs_tanner"]["reason"],
                         "attention_unavailable_or_expired")
        self.assertFalse(terminal["creates_authority"])
        self.assertFalse(terminal["creates_continuing_authority"])

    def test_restart_reconciles_decision_free_unavailable_reviewer_wait(self):
        campaign_id = "review-native-unavailable-restart"
        campaign, _record, package, transport, reviewer = (
            self._review_native_approval_fixture(campaign_id))
        retention = campaign.store.load(campaign_id)["builder_runs"][-1][
            "candidate_retention_receipt"]
        transport["candidate_snapshot_id"] = retention["candidate_snapshot"][
            "candidate_snapshot_id"]
        approval = self._typed_review_approval(
            campaign_id, package, transport, reviewer,
            "review-unavailable-restart-invocation", "unavailable-restart-item")
        paused = campaign.require_tanner(
            campaign_id, invocation_id=approval["invocation_id"],
            worker=approval["worker"], kind=approval["kind"],
            blocked_action=approval["blocked_action"],
            why_required=approval["why_required"],
            requested_authority=approval["requested_authority"],
            resources=approval["resources"], reversible=approval["reversible"],
            provider_code=approval["provider_code"],
            protocol_binding=approval["protocol"], expires_in_seconds=3600,
            expiration_reason="bounded review transport lost",
            expiration_effect="protected action remains unperformed",
            can_request_again=True, work_lost=False)
        attention_id = paused["needs_tanner"]["attention_id"]
        with patch.object(campaign.attention_store,
                          "_complete_recovery_evidence", return_value=False):
            campaign.attention_store.mark_process_detached(attention_id)

        terminal = campaign.advance_once(campaign_id)
        self.assertEqual(terminal["status"], "failed_safe")
        self.assertEqual(terminal["needs_tanner"]["reason"],
                         "reviewer_native_action_transport_lost")
        self.assertFalse(terminal["creates_authority"])
        self.assertFalse(terminal["creates_continuing_authority"])

    def test_campaign_validation_uses_shared_external_environment_without_secrets(self):
        external = Path(self.tmp.name) / "external-state"
        external.mkdir()
        campaign = CodexDevelopmentCampaign("fawkes",
            root=Path(self.tmp.name) / "validation-campaigns",
            runtime_state_root=external, worker_timeout_seconds=1800)
        captured = []

        def run(argv, **kwargs):
            captured.append((argv, kwargs))
            return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch.dict(os.environ, {"UNRELATED_HOST_SETTING": "not-forwarded"}, clear=False), patch(
                                         "src.runtime.codex_development_campaign.subprocess.run",
                                         side_effect=run):
            evidence = campaign._run_validation([["python3", "-m", "unittest"]])
        self.assertEqual(evidence[0]["exit_status"], 0)
        environment = captured[0][1]["env"]
        self.assertEqual(environment["FAWKES_RUNTIME_STATE_ROOT"], str(external.resolve()))
        self.assertNotIn("UNRELATED_HOST_SETTING", environment)
        self.assertEqual(campaign.worker_timeout_seconds, 1800)

    def test_campaign_validation_preserves_default_and_rejects_invalid_roots(self):
        campaign = CodexDevelopmentCampaign("fawkes",
            root=Path(self.tmp.name) / "default-campaigns")
        self.assertIsNone(campaign.runtime_state_root)
        self.assertEqual(campaign.worker_timeout_seconds, 180)
        for value in ("relative", ROOT, Path(self.tmp.name) / "missing"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CodexDevelopmentCampaign("fawkes",
                    root=Path(self.tmp.name) / "invalid-campaigns",
                    runtime_state_root=value)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.fixture = CampaignFixture(Path(self.tmp.name))

    def _reserved_recovery_fixture(self, campaign_id):
        campaign = self.fixture.campaign
        protocol = {"method": "item/commandExecution/requestApproval", "item_id": "recovery-item",
            "approved_action_sha256": "a" * 64, "rider_id": "tanner",
            "recipient_sha256": "r" * 64, "candidate_snapshot_id": "candidate-recovery",
            "candidate_record_sha256": "c" * 64, "mutation_digest_sha256": "m" * 64,
            "authorized_scope_sha256": "s" * 64}
        protocol["recovery_evidence"] = {"recovery_id": "recovery-once",
            "payload_sha256": "p" * 64, "candidate_snapshot_id": "candidate-recovery",
            "mutation_digest_sha256": "m" * 64, "authorized_scope_sha256": "s" * 64,
            "protocol_binding_sha256": _digest(protocol)}
        attention = campaign.attention_store.create(campaign_id=campaign_id,
            invocation_id="recovery-invocation", worker={"worker_id": BUILDER_ID, "role": "builder"},
            kind="native_codex_approval_required", blocked_action="bounded recovery",
            why_required="test recovery", requested_authority="execute once",
            protocol_binding=protocol, expires_in_seconds=3600,
            expiration_reason="staleness", expiration_effect="remains unperformed",
            can_request_again=True, work_lost=False)
        campaign.attention_store.mark_process_detached(attention["attention_id"])
        attention = campaign.attention_store.get(attention["attention_id"])
        decision = campaign.attention_store.decide(attention["attention_id"], "approve_once",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(attention))["decision"]
        continuation = "continuation-once"
        campaign.attention_store.reserve_detached_continuation(decision["decision_id"],
            attention_id=attention["attention_id"], invocation_id=attention["invocation_id"],
            protocol_binding_sha256=attention["protocol_binding_sha256"],
            continuation_id=continuation,
            expected_binding=campaign.attention_store._authority_binding(attention))
        base = {"schema_version": 1, "record_type": "codex_development_campaign",
            "contract_version": CAMPAIGN_CONTRACT_VERSION, "campaign_id": campaign_id,
            "instance_id": "fawkes", "objective": "recovery", "objective_sha256": "o" * 64,
            "objective_mode": "repository_write", "acceptance_condition_ids": ["condition"],
            "acceptance_conditions": {"condition": "condition"}, "allowed_scope": ["fixture.txt"],
            "source_sections": [], "validation_commands": [],
            "validation_policy": "intentionally_not_applicable", "validation_declaration": {},
            "rider_authorization_reference": "test", "recovery_references": [{}],
            "builder": {"worker_id": BUILDER_ID}, "reviewer_requirement": {}, "maximum_iterations": 3,
            "iteration": 1, "status": "ready_for_bounded_continuation",
            "active_builder_task_scope_id": None, "builder_runs": [], "reviews": [],
            "review_requests": [], "review_transport_attempts": [], "cache_lifecycle_events": [],
            "acceptance_satisfied": [], "needs_tanner": None,
            "attention_event_ids": [attention["attention_id"]], "cancelled": False,
            "automatic_promotion": False, "creates_authority": False, "state_revision": 1,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
            "events": []}
        campaign.store.write(base)
        return campaign, attention, decision, continuation

    def test_reserved_recovery_executes_once_across_crash_repeat_and_concurrency(self):
        campaign, attention, decision, continuation = self._reserved_recovery_fixture("recovery-crash")
        calls = []
        def runner(_evidence, *, idempotency_id):
            calls.append(idempotency_id)
            return {"idempotency_id": idempotency_id, "status": "completed"}
        with patch.object(campaign.attention_store, "finish_detached_continuation",
                          side_effect=OSError("injected completion projection crash")):
            with self.assertRaises(OSError):
                campaign.resume_reserved_continuation("recovery-crash", attention["attention_id"],
                    decision["decision_id"], continuation, recovery_runner=runner)
        recovered = campaign.resume_reserved_continuation("recovery-crash", attention["attention_id"],
            decision["decision_id"], continuation, recovery_runner=runner)
        self.assertEqual(recovered["campaign"]["status"], "ready")
        self.assertEqual(len(calls), 1)
        with self.assertRaises(PermissionError):
            campaign.resume_reserved_continuation("recovery-crash", attention["attention_id"],
                decision["decision_id"], continuation, recovery_runner=runner)
        self.assertEqual(len(calls), 1)

        campaign, attention, decision, continuation = self._reserved_recovery_fixture("recovery-concurrent")
        entered = threading.Event(); release = threading.Event(); concurrent_calls = []
        def blocking_runner(_evidence, *, idempotency_id):
            concurrent_calls.append(idempotency_id); entered.set(); release.wait(2)
            return {"idempotency_id": idempotency_id, "status": "completed"}
        results = []
        def resume():
            try:
                results.append(campaign.resume_reserved_continuation("recovery-concurrent",
                    attention["attention_id"], decision["decision_id"], continuation,
                    recovery_runner=blocking_runner))
            except Exception as exc:
                results.append(exc)
        first = threading.Thread(target=resume); second = threading.Thread(target=resume)
        first.start(); entered.wait(1); second.start(); release.set(); first.join(2); second.join(2)
        self.assertEqual(len(concurrent_calls), 1)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)

    def test_contract_is_fixed_small_and_has_no_orchestration_or_promotion(self):
        self.assertEqual(MAX_ITERATIONS, 3)
        self.assertEqual(CAMPAIGN_ACCEPTANCE_CONTRACT["hard_limits"]["maximum_builder_iterations"], 3)
        self.assertFalse(CAMPAIGN_ACCEPTANCE_CONTRACT["hard_limits"]["worker_discovery"])
        self.assertFalse(CAMPAIGN_ACCEPTANCE_CONTRACT["hard_limits"]["automatic_promotion"])
        self.assertEqual(CAMPAIGN_ACCEPTANCE_CONTRACT["hard_limits"]["reviewer_role"],
                         FORMAL_REVIEW_ROLE)
        self.assertEqual(CAMPAIGN_ACCEPTANCE_CONTRACT["hard_limits"]["default_reviewer_worker_id"],
                         DEFAULT_REVIEWER_WORKER_ID)
        self.assertTrue(DEFAULT_REVIEWER_BINDING_ASSURANCE["promoted"])
        self.assertEqual(DEFAULT_REVIEWER_BINDING_ASSURANCE["hard_invariants"], "8/8")
        self.assertIn("database/development_campaigns", SCOPED_ROOTS)

    def test_campaign_list_keeps_legacy_contract_visible_without_503(self):
        campaign = self.fixture.campaign
        campaign.create(self.fixture.payload("visible-current"), authenticated_rider=True)
        current = campaign.store.path("visible-current")
        record = json.loads(current.read_text())
        record["contract_version"] = "historical-contract-v0"
        from src.runtime.worker_exchange import _digest
        record["record_sha256"] = _digest({key: value for key, value in record.items()
                                           if key != "record_sha256"})
        current.write_text(json.dumps(record))
        listed = campaign.list_presentations()
        self.assertEqual(listed[0]["status"], "historical_contract_unavailable")
        self.assertFalse(listed[0]["live_activity"]["creates_authority"])

    def test_run_to_terminal_uses_wsl_default_and_never_windows_fallback_implicitly(self):
        campaign = self.fixture.campaign
        record = campaign.create(self.fixture.payload("wsl-default"), authenticated_rider=True)
        self.assertEqual(record["reviewer_requirement"]["worker_id"], DEFAULT_REVIEWER_WORKER_ID)
        calls = []
        def wsl(campaign_id, *, adapter=None):
            calls.append(("wsl", campaign_id))
            current = campaign.store.load(campaign_id)
            return campaign._update(current, event_kind="fixture_wsl_terminal", status="succeeded")
        def windows(*args, **kwargs):
            raise AssertionError("Windows fallback must not be selected implicitly")
        campaign.run_wsl_review, campaign.run_windows_review = wsl, windows
        terminal = campaign.run_to_terminal("wsl-default")
        self.assertEqual(terminal["status"], "succeeded")
        self.assertEqual(calls, [("wsl", "wsl-default")])

    def test_disposable_python_cache_cleanup_is_narrow_and_detectable(self):
        root = Path(self.tmp.name) / "cache-root"
        cache = root / "tests/__pycache__"; cache.mkdir(parents=True)
        bytecode = cache / "test_fixture.cpython-314.pyc"; bytecode.write_bytes(b"cache")
        removed = _cleanup_python_cache(["tests/test_fixture.py"], root=root)
        self.assertEqual(removed[0]["path"], "tests/__pycache__/test_fixture.cpython-314.pyc")
        self.assertFalse(cache.exists())
        cache.mkdir(); (cache / "meaningful.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            _cleanup_python_cache(["tests/test_fixture.py"], root=root)
        self.assertTrue((cache / "meaningful.json").exists())

    def test_builder_exception_is_retained_as_body_free_failure_evidence(self):
        def failed_builder(_payload):
            raise ValueError("workspace exceeds bounded write snapshot file limit")

        campaign = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "failed-campaign",
            exchange=self.fixture.exchange, builder_runner=failed_builder,
            builder_modes={"repository_write"})
        record = campaign.create(self.fixture.payload("failed-builder"), authenticated_rider=True)
        self.assertEqual(record["status"], "failed_safe")
        self.assertEqual(record["builder_runs"][0]["failure"], {
            "code": "ValueError", "detail": "workspace exceeds bounded write snapshot file limit"})
        self.assertEqual(record["needs_tanner"]["failure_code"], "ValueError")

    def test_native_approval_failure_becomes_exact_needs_tanner_and_deny_is_bounded(self):
        def approval_builder(payload):
            invocation_id = "synthetic-native-approval-1"
            snapshot = {"candidate_snapshot_id": "candidate-snapshot-attention-1",
                        "record_sha256": "a" * 64, "file_count": 1,
                        "total_byte_length": 1}
            mutation_sha = "b" * 64
            exact_action = {"method": "tool.approval_required",
                            "action": "touch harmless.txt", "cwd": "/disposable"}
            return {"source_report_id": None, "package_id": None,
                "presentation": {"status": "failed", "verification_status": "unverified",
                    "return_report_id": None,
                    "failure": {"code": "native_approval_required", "detail": "noninteractive stop"},
                    "attention_request": {"campaign_id": payload["campaign_id"],
                        "invocation_id": invocation_id,
                        "blocked_action": "touch harmless.txt", "why_required": "workspace write",
                        "requested_authority": "write harmless.txt once",
                        "resources": ["harmless.txt"], "reversible": True,
                        "provider_code": "tool.approval_required", "exact_action": exact_action,
                        "protocol": {"version": "fixture-v1", "method": "tool.approval_required",
                            "item_id": "item-attention-1",
                            "approved_action_sha256": _digest(exact_action),
                            "candidate_snapshot_id": snapshot["candidate_snapshot_id"],
                            "candidate_record_sha256": snapshot["record_sha256"],
                            "mutation_digest_sha256": mutation_sha,
                            "authorized_scope_sha256": _digest(payload["allowed_scope"])}},
                    },
                "transport_result": {"status": "failed", "invocation_id": invocation_id,
                    "candidate_snapshot": snapshot, "workspace_changes_sha256": mutation_sha}}
        attention = DevelopmentAttentionStore(Path(self.tmp.name) / "attention")
        campaign = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "approval-campaign",
            exchange=self.fixture.exchange, builder_runner=approval_builder,
            builder_modes={"repository_write"}, attention_store=attention)
        record = campaign.create(self.fixture.payload("approval-campaign"), authenticated_rider=True)
        self.assertEqual(record["status"], "tanner_escalation")
        self.assertEqual(record["needs_tanner"]["reason"], "native_codex_approval_required")
        event = attention.get(record["needs_tanner"]["attention_id"])
        self.assertEqual(event["blocked_action"], "touch harmless.txt")
        result = campaign.decide_attention(record["campaign_id"], event["attention_id"], "deny",
                                           authenticated_rider=True,
                                           expected_identity=attention._authority_binding(event))
        self.assertEqual(result["campaign"]["status"], "failed_safe")
        self.assertFalse(result["decision"]["creates_continuing_authority"])

    def test_worker_attention_lineage_is_complete_and_coordinator_bound(self):
        payload = self.fixture.payload("attention-binding")
        record = {"campaign_id": payload["campaign_id"], "allowed_scope": payload["allowed_scope"]}
        snapshot = {"candidate_snapshot_id": "candidate-snapshot-bound",
                    "record_sha256": "c" * 64}
        exact_action = {"method": "tool.approval_required", "action": "bounded",
                        "cwd": "/disposable"}
        protocol = {"version": "fixture-v1", "method": exact_action["method"],
            "item_id": "item-bound", "approved_action_sha256": _digest(exact_action),
            "candidate_snapshot_id": snapshot["candidate_snapshot_id"],
            "candidate_record_sha256": snapshot["record_sha256"],
            "mutation_digest_sha256": "d" * 64,
            "authorized_scope_sha256": _digest(payload["allowed_scope"])}
        attention = {"campaign_id": payload["campaign_id"], "invocation_id": "invocation-bound",
            "provider_code": exact_action["method"], "exact_action": exact_action,
            "protocol": protocol}
        transport = {"invocation_id": "invocation-bound", "candidate_snapshot": snapshot,
                     "workspace_changes_sha256": "d" * 64}
        self.assertEqual(
            CodexDevelopmentCampaign._validated_worker_attention_binding(
                record, attention, transport), protocol)
        mutations = (
            ("missing candidate", lambda a, _t: a["protocol"].pop("candidate_snapshot_id")),
            ("altered action", lambda a, _t: a["protocol"].update(
                {"approved_action_sha256": "e" * 64})),
            ("neighboring candidate", lambda _a, t: t["candidate_snapshot"].update(
                {"candidate_snapshot_id": "candidate-snapshot-neighbor"})),
            ("neighboring invocation", lambda _a, t: t.update(
                {"invocation_id": "invocation-neighbor"})),
            ("altered scope", lambda a, _t: a["protocol"].update(
                {"authorized_scope_sha256": "f" * 64})),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate_attention = json.loads(json.dumps(attention))
                candidate_transport = json.loads(json.dumps(transport))
                mutate(candidate_attention, candidate_transport)
                with self.assertRaises(PermissionError):
                    CodexDevelopmentCampaign._validated_worker_attention_binding(
                        record, candidate_attention, candidate_transport)

    def test_incomplete_worker_attention_never_creates_approvable_event(self):
        def incomplete_builder(payload):
            return {"source_report_id": None, "package_id": None,
                "presentation": {"status": "failed", "verification_status": "unverified",
                    "return_report_id": None,
                    "failure": {"code": "native_approval_required", "detail": "bounded stop"},
                    "attention_request": {"campaign_id": payload["campaign_id"],
                        "invocation_id": "incomplete-attention", "blocked_action": "bounded",
                        "why_required": "approval", "requested_authority": "once",
                        "provider_code": "tool.approval_required", "protocol": {}}},
                "transport_result": {"status": "failed", "invocation_id": "incomplete-attention"}}
        attention = DevelopmentAttentionStore(Path(self.tmp.name) / "incomplete-attention")
        campaign = CodexDevelopmentCampaign("fawkes",
            root=Path(self.tmp.name) / "incomplete-attention-campaign",
            exchange=self.fixture.exchange, builder_runner=incomplete_builder,
            builder_modes={"repository_write"}, attention_store=attention)
        record = campaign.create(self.fixture.payload("incomplete-attention"),
                                 authenticated_rider=True)
        self.assertEqual(record["status"], "failed_safe")
        self.assertEqual(record["needs_tanner"]["failure_code"], "attention_lineage_mismatch")
        self.assertEqual(list(attention.events.glob("*.json")), [])

    def test_repository_write_is_an_explicit_separate_builder_mode(self):
        campaign = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "real-scope",
                                            exchange=self.fixture.exchange,
                                            builder_runner=self.fixture.campaign.builder_runner)
        self.assertIn("repository_write", campaign.builder_modes)
        self.assertIn("read_only", campaign.builder_modes)

    def test_correction_cycle_rejects_noncanonical_application_callback(self):
        record = self.fixture.campaign.create(self.fixture.payload(), authenticated_rider=True)
        self.assertEqual(record["status"], "awaiting_independent_review")
        defect = {"defect_id": "missing-test", "acceptance_condition_id": "tests-pass",
                  "evidence_reference": "review-evidence"}
        review = self.fixture.review("campaign-one", "correction_required",
                                     satisfied=["scope-held"], defects=[defect], violated=["tests-pass"])
        record = self.fixture.campaign.consume_review("campaign-one", review,
            reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(record["iteration"], 2)
        self.assertEqual(record["status"], "awaiting_independent_review")
        second_source = self.fixture.exchange._load("reports", record["builder_runs"][-1]["source_report_id"])
        self.assertTrue(any("Exact defect and evidence" in item["content"] for item in second_source["sections"]))
        passed = self.fixture.review("campaign-one", "pass", satisfied=["tests-pass", "scope-held"])
        record = self.fixture.campaign.consume_review("campaign-one", passed,
            reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(record["status"], "failed_safe")
        self.assertFalse(record["automatic_promotion"])
        self.assertEqual(len(record["builder_runs"]), 2)
        self.assertEqual(self.fixture.applications, [])

    def test_verdict_and_callback_dictionary_cannot_complete_campaign(self):
        record = self.fixture.campaign.create(self.fixture.payload("transaction-order"),
                                              authenticated_rider=True)
        run = record["builder_runs"][-1]
        receipt = run["candidate_retention_receipt"]
        self.assertEqual(record["status"], "awaiting_independent_review")
        self.assertEqual(receipt["record_type"], "codex_candidate_retention_receipt")
        self.assertEqual(receipt["status"], "awaiting_independent_review")
        self.assertEqual(receipt["applied_paths"], [])
        self.assertEqual(self.fixture.applications, [])
        review = self.fixture.review("transaction-order", "pass",
                                     satisfied=["tests-pass", "scope-held"])
        terminal = self.fixture.campaign.consume_review("transaction-order", review,
            reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(terminal["status"], "failed_safe")
        self.assertEqual(self.fixture.applications, [])
        kinds = [item["kind"] for item in terminal["events"]]
        self.assertLess(kinds.index("builder_return_retained"),
                        kinds.index("independent_review_retained"))
        self.assertLess(kinds.index("independent_review_retained"),
                        kinds.index("reviewed_candidate_apply_failed"))
        with self.assertRaisesRegex(RuntimeError, "not awaiting"):
            self.fixture.campaign.consume_review("transaction-order", review,
                reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(self.fixture.applications, [])

    def test_validated_acceptance_receipt_is_durable_across_campaign_restart(self):
        campaign_id = "durable-acceptance"
        self.fixture.campaign.create(self.fixture.payload(campaign_id),
                                     authenticated_rider=True)
        review = self.fixture.review(campaign_id, "pass",
                                     satisfied=["tests-pass", "scope-held"])
        terminal = self.fixture.campaign.consume_review(campaign_id, review,
            reviewer=REVIEWER, transport_verified=True)
        retained = terminal["reviews"][-1]["review_acceptance_receipt"]
        self.assertEqual(retained, review["review_acceptance_receipt"])
        restarted = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "campaigns",
            exchange=self.fixture.exchange, builder_runner=self.fixture.campaign.builder_runner,
            builder_modes={"repository_write"},
            candidate_applier=self.fixture.campaign.candidate_applier)
        self.assertEqual(restarted.store.load(campaign_id)["reviews"][-1][
            "review_acceptance_receipt"], retained)

    def test_rehashed_identity_bearing_acceptance_fields_fail_before_application(self):
        fields = ("review_invocation_id", "review_report_sha256", "reviewer_role",
                  "recipient", "acceptance_condition_ids_sha256",
                  "review_package_sha256", "source_report_id", "verdict")
        for index, field in enumerate(fields):
            with self.subTest(field=field):
                campaign_id = f"rehashed-receipt-{index}"
                self.fixture.campaign.create(self.fixture.payload(campaign_id),
                                             authenticated_rider=True)
                review = self.fixture.review(campaign_id, "pass",
                    satisfied=["tests-pass", "scope-held"])
                receipt = review["review_acceptance_receipt"]
                receipt[field] = ({"worker_id": REVIEWER["worker_id"],
                                   "role": REVIEWER["role"],
                                   "environment_id": "neighbor-read-only"}
                                  if field == "recipient" else f"neighbor-{field}")
                receipt["record_sha256"] = _digest({key: value for key, value in
                    receipt.items() if key != "record_sha256"})
                before = len(self.fixture.applications)
                with self.assertRaisesRegex(PermissionError, "acceptance receipt"):
                    self.fixture.campaign.consume_review(campaign_id, review,
                        reviewer=REVIEWER, transport_verified=True)
                self.assertEqual(len(self.fixture.applications), before)
                self.assertEqual(self.fixture.campaign.store.load(campaign_id)["reviews"], [])

    def test_campaign_owned_terminal_reconciliation_uses_exact_canonical_adapter(self):
        from tests.test_reviewed_application_caller_seams import (
            ReviewedApplicationCallerSeamTests,
        )
        seam = ReviewedApplicationCallerSeamTests(
            "test_completed_application_retrieval_is_idempotent")
        seam.setUp(); self.addCleanup(seam.doCleanups)
        adapter, applied, arguments = seam.completed()
        directory = adapter.root / "write-candidate" / arguments["package_id"]
        result = json.loads((directory / "result.json").read_text())
        request = json.loads((directory / "request.json").read_text())
        review_package = adapter.exchange._load("packages",
            arguments["review_acceptance_receipt"]["review_package_id"])
        retention_section = next(item for item in review_package["included_sections"]
            if item["section_id"] == "candidate-retention-receipt")
        retention = json.loads(retention_section["content"])
        campaign_root = Path(self.tmp.name) / "canonical-reconciliation-campaigns"
        campaign = CodexDevelopmentCampaign("fawkes", root=campaign_root,
            exchange=adapter.exchange,
            candidate_applier=adapter.apply_reviewed_candidate_once)
        template = self.fixture.campaign.create(self.fixture.payload("reconcile-template"),
                                                authenticated_rider=True)
        record = {**template, "campaign_id": arguments["campaign_id"],
            "status": "review_accepted_application_pending",
            "allowed_scope": request["allowed_scope"],
            "builder_runs": [{"package_id": arguments["package_id"],
                "candidate_snapshot": result["candidate_snapshot"],
                "candidate_retention_receipt": retention}],
            "reviews": [{"status": "pass",
                "review_report_id": arguments["review_report_id"],
                "review_package_id": arguments["review_acceptance_receipt"][
                    "review_package_id"],
                "review_acceptance_receipt": arguments["review_acceptance_receipt"],
                "reviewed_application_operation_id": applied["operation_id"]}],
            "application_evidence": None, "state_revision": 8}
        record.pop("record_sha256", None)
        campaign.store.write(record)
        restarted = CodexDevelopmentCampaign("fawkes", root=campaign_root,
            exchange=adapter.exchange,
            candidate_applier=adapter.apply_reviewed_candidate_once)
        recovered = restarted.run_to_terminal(arguments["campaign_id"])
        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(recovered["application_evidence"], applied)
        first = restarted.reconcile_completed_application(arguments["campaign_id"])
        second = restarted.reconcile_completed_application(arguments["campaign_id"])
        self.assertEqual(first, applied)
        self.assertEqual(second, applied)
        self.assertEqual(applied["application_count"], 1)

    def test_campaign_terminal_reconciliation_rejects_nonterminal_and_neighbor_receipt(self):
        campaign_id = "nonterminal-reconciliation"
        self.fixture.campaign.create(self.fixture.payload(campaign_id),
                                     authenticated_rider=True)
        with self.assertRaisesRegex(RuntimeError, "not terminally successful"):
            self.fixture.campaign.reconcile_completed_application(campaign_id)
        review = self.fixture.review(campaign_id, "pass",
                                     satisfied=["tests-pass", "scope-held"])
        terminal = self.fixture.campaign.consume_review(campaign_id, review,
            reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(terminal["status"], "failed_safe")
        forged = json.loads(json.dumps(terminal))
        receipt = forged["reviews"][-1]["review_acceptance_receipt"]
        receipt["candidate_snapshot_id"] = "candidate-snapshot-neighbor"
        receipt["record_sha256"] = _digest(
            {key: value for key, value in receipt.items() if key != "record_sha256"})
        forged["status"] = "succeeded"
        forged["application_evidence"] = {
            "status": "applied_verified_after_review", "application_count": 1,
            "operation_id": forged["reviews"][-1]["reviewed_application_operation_id"],
            "review_report_id": forged["reviews"][-1]["review_report_id"],
            "review_acceptance_receipt_sha256": receipt["record_sha256"],
        }
        forged["state_revision"] += 1
        forged.pop("record_sha256", None)
        self.fixture.campaign.store.write(forged,
            expected_revision=terminal["state_revision"])
        with self.assertRaisesRegex(PermissionError, "incomplete|neighboring"):
            self.fixture.campaign.reconcile_completed_application(campaign_id)

    def test_failed_validation_never_reaches_review_or_application(self):
        payload = {**self.fixture.payload("validation-fails"),
            "validation_policy": "required",
            "validation_commands": [["python3", "-m", "unittest", "missing.fixture"]]}
        with patch("src.runtime.codex_development_campaign.subprocess.run",
                   return_value=type("Completed", (), {"returncode": 1,
                       "stdout": "", "stderr": "failed"})()):
            record = self.fixture.campaign.create(payload, authenticated_rider=True)
        self.assertEqual(record["status"], "failed_safe")
        self.assertEqual(record["reviews"], [])
        self.assertEqual(self.fixture.applications, [])

    def test_missing_required_validation_fails_before_builder_or_review(self):
        payload = {**self.fixture.payload("validation-missing"),
                   "validation_policy": "required", "validation_commands": []}
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            self.fixture.campaign.create(payload, authenticated_rider=True)
        self.assertEqual(self.fixture.builder_payloads, [])
        self.assertEqual(self.fixture.applications, [])

    def test_not_applicable_validation_has_bound_non_vacuous_declaration(self):
        record = self.fixture.campaign.create(self.fixture.payload("validation-na"),
                                              authenticated_rider=True)
        declaration = record["validation_declaration"]
        self.assertEqual(declaration["status"], "intentionally_not_applicable")
        self.assertEqual(len(declaration["record_sha256"]), 64)
        evidence=record["builder_runs"][0]["validation_evidence"]
        self.assertEqual(len(evidence),1)
        self.assertEqual(evidence[0]["record_type"],"candidate_validation_not_applicable_receipt")
        self.assertEqual(evidence[0]["candidate_snapshot_id"],
                         record["builder_runs"][0]["candidate_retention_receipt"]["candidate_snapshot"]["candidate_snapshot_id"])
        self.assertEqual(record["builder_runs"][0]["validation_declaration"], declaration)
        self.assertEqual(record["status"], "awaiting_independent_review")

    def test_rejected_review_never_invokes_application(self):
        self.fixture.campaign.create(self.fixture.payload("review-rejects"),
                                     authenticated_rider=True)
        defect = {"defect_id":"defect", "acceptance_condition_id":"tests-pass",
                  "evidence_reference":"review-evidence"}
        record = self.fixture.campaign.consume_review("review-rejects",
            self.fixture.review("review-rejects", "correction_required",
                defects=[defect], violated=["tests-pass"]),
            reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(record["iteration"], 2)
        self.assertEqual(self.fixture.applications, [])

    def test_iteration_cap_escalates_without_a_fourth_builder_call(self):
        record = self.fixture.campaign.create(self.fixture.payload("cap-test"), authenticated_rider=True)
        defect = {"defect_id": "repeat-defect", "acceptance_condition_id": "tests-pass",
                  "evidence_reference": "review-evidence"}
        for expected in (2, 3):
            review = self.fixture.review("cap-test", "correction_required", defects=[defect],
                                         violated=["tests-pass"])
            record = self.fixture.campaign.consume_review("cap-test", review,
                reviewer=REVIEWER, transport_verified=True)
            self.assertEqual(record["iteration"], expected)
        review = self.fixture.review("cap-test", "correction_required", defects=[defect],
                                     violated=["tests-pass"])
        record = self.fixture.campaign.consume_review("cap-test", review,
            reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(record["status"], "tanner_escalation")
        self.assertEqual(record["needs_tanner"]["reason"], "maximum_iterations_reached")
        self.assertEqual(len(self.fixture.builder_payloads), 3)

    def test_reviewer_identity_transport_and_acceptance_scope_fail_closed(self):
        self.fixture.campaign.create(self.fixture.payload("review-guards"), authenticated_rider=True)
        review = self.fixture.review("review-guards", "pass", satisfied=["tests-pass", "scope-held"])
        with self.assertRaises(PermissionError):
            self.fixture.campaign.consume_review("review-guards", review,
                reviewer={**REVIEWER, "worker_id": BUILDER_ID}, transport_verified=True)
        with self.assertRaises(PermissionError):
            self.fixture.campaign.consume_review("review-guards", review,
                reviewer=REVIEWER, transport_verified=False)
        with self.assertRaises(ValueError):
            self.fixture.campaign.consume_review("review-guards", {**review,
                "acceptance_condition_ids_satisfied": ["invented-scope"]},
                reviewer=REVIEWER, transport_verified=True)

        self.fixture.campaign.create(self.fixture.payload("different-candidate"), authenticated_rider=True)
        wrong_target = self.fixture.review("different-candidate", "pass",
                                           satisfied=["tests-pass", "scope-held"])
        with self.assertRaises(PermissionError):
            self.fixture.campaign.consume_review("review-guards", wrong_target,
                reviewer=REVIEWER, transport_verified=True)

    def test_rider_cancel_is_durable_idempotent_and_prevents_review_or_restart_replay(self):
        record = self.fixture.campaign.create(self.fixture.payload("cancel-test"), authenticated_rider=True)
        original_return = record["builder_runs"][0]["return_report_id"]
        cancelled = self.fixture.campaign.cancel("cancel-test", authenticated_rider=True)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["builder_runs"][0]["return_report_id"], original_return)
        self.assertEqual(self.fixture.campaign.cancel("cancel-test", authenticated_rider=True), cancelled)
        review = self.fixture.review("cancel-test", "pass", satisfied=["tests-pass", "scope-held"])
        with self.assertRaises(RuntimeError):
            self.fixture.campaign.consume_review("cancel-test", review,
                reviewer=REVIEWER, transport_verified=True)
        calls = []
        restarted = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "campaigns",
            exchange=self.fixture.exchange, builder_runner=lambda payload: calls.append(payload),
            builder_modes={"repository_write"})
        self.assertEqual(restarted.presentation("cancel-test")["status"], "cancelled")
        self.assertEqual(calls, [])

    def test_cancel_waits_for_canonical_protected_operation_boundary(self):
        self.fixture.campaign.create(self.fixture.payload("cancel-linearized"),
                                     authenticated_rider=True)
        entered=threading.Event();release=threading.Event();cancelled=threading.Event()
        def protected_stage():
            with self.fixture.campaign.store.protected("cancel-linearized"):
                entered.set();release.wait(2)
        def cancel_stage():
            self.fixture.campaign.cancel("cancel-linearized",authenticated_rider=True)
            cancelled.set()
        holder=threading.Thread(target=protected_stage);holder.start();self.assertTrue(entered.wait(2))
        waiter=threading.Thread(target=cancel_stage);waiter.start()
        self.assertFalse(cancelled.wait(0.05));release.set()
        holder.join(2);waiter.join(2);self.assertFalse(holder.is_alive());self.assertFalse(waiter.is_alive())
        self.assertTrue(cancelled.is_set())
        terminal=self.fixture.campaign.store.load("cancel-linearized")
        self.assertEqual("cancelled",terminal["status"])
        self.assertFalse(terminal["creates_continuing_authority"])

    def test_authority_scope_recovery_and_integrity_are_required(self):
        payload = self.fixture.payload("guard-test")
        with self.assertRaises(PermissionError):
            self.fixture.campaign.create(payload, authenticated_rider=False)
        for change, error in (({"instance_id": "other"}, PermissionError),
                              ({"target_builder": "windows_codex"}, ValueError),
                              ({"allowed_scope": ["../escape"]}, ValueError),
                              ({"recovery_references": []}, ValueError)):
            with self.subTest(change=change), self.assertRaises(error):
                self.fixture.campaign.create({**payload, **change,
                    "campaign_id": f"guard-{len(str(change))}"}, authenticated_rider=True)

    def test_campaign_identity_collision_and_record_tampering_fail_closed(self):
        self.fixture.campaign.create(self.fixture.payload("stable-id"), authenticated_rider=True)
        with self.assertRaises(RuntimeError):
            self.fixture.campaign.create(self.fixture.payload("stable-id"), authenticated_rider=True)
        path = self.fixture.campaign.store.path("stable-id")
        record = json.loads(path.read_text(encoding="utf-8"))
        record["maximum_iterations"] = 4
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.fixture.campaign.store.load("stable-id")

    def test_restart_observes_in_progress_state_without_blind_replay(self):
        record = self.fixture.campaign.create(self.fixture.payload("restart-in-progress"),
                                              authenticated_rider=True)
        record = self.fixture.campaign._update(record, event_kind="fixture_interruption",
            status="builder_in_progress", active_builder_task_scope_id="interrupted-task")
        calls = []
        restarted = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "campaigns",
            exchange=self.fixture.exchange, builder_runner=lambda payload: calls.append(payload),
            builder_modes={"repository_write"})
        view = restarted.presentation("restart-in-progress")
        self.assertEqual(view["status"], "builder_in_progress")
        self.assertEqual(calls, [])

    def test_periodic_progress_is_descriptive_nonblocking_and_separate_from_human_review(self):
        self.fixture.campaign.create(self.fixture.payload("progress-signals"),
                                     authenticated_rider=True)
        durable_path = self.fixture.campaign.store.path("progress-signals")
        durable_before = durable_path.read_bytes()

        progress = self.fixture.campaign.presentation("progress-signals")
        signals = progress["notification_signals"]
        # Lock the entire descriptive presentation contract so progress cannot silently
        # acquire a control, delivery-provider, or escalation side effect.
        self.assertEqual(signals, {
            "immediate_human_review": False,
            "periodic_progress_interval_seconds": 10800,
            "periodic_progress_pauses_campaign": False,
            "rider_inactivity_source_required": True,
        })
        self.assertTrue(progress["operational_learning_observations"]
                        ["observations_are_not_policy_or_authority"])
        self.assertFalse(progress["operational_learning_observations"]
                         ["tanner_escalation_required"])
        self.assertTrue(progress["derived_from_campaign_record"])
        durable_record = self.fixture.campaign.store.load("progress-signals")
        self.assertTrue(set(signals).isdisjoint(durable_record))
        self.assertNotIn("notification_signals", durable_record)
        self.assertNotIn("periodic_progress_interval_seconds", durable_record)
        self.assertFalse(progress["creates_authority"])
        self.assertIsNone(progress["needs_tanner"])
        self.assertFalse(signals["immediate_human_review"])
        self.assertEqual(progress["status"], "awaiting_independent_review")
        self.assertIsNone(durable_record["needs_tanner"])
        self.assertEqual(durable_record["status"], "awaiting_independent_review")
        provider_terms = ("sms", "twilio", "push_provider", "notification_daemon",
                          "delivery_provider")
        serialized_signals = json.dumps(signals, sort_keys=True).lower()
        for provider_term in provider_terms:
            with self.subTest(provider_term=provider_term):
                self.assertNotIn(provider_term, serialized_signals)

        repeated = self.fixture.campaign.presentation("progress-signals")
        self.assertEqual(durable_path.read_bytes(), durable_before)
        self.assertEqual(repeated["status"], "awaiting_independent_review")
        self.assertIsNone(repeated["needs_tanner"])
        self.assertEqual(repeated["notification_signals"], signals)
        self.assertEqual(repeated["last_builder_run"], progress["last_builder_run"])
        self.assertFalse(repeated["notification_signals"]["periodic_progress_pauses_campaign"])
        self.assertIsNone(repeated["needs_tanner"])

        review = self.fixture.review("progress-signals", "insufficient_evidence",
                                     correctable=False)
        self.fixture.campaign.consume_review("progress-signals", review,
                                             reviewer=REVIEWER, transport_verified=True)
        escalated = self.fixture.campaign.presentation("progress-signals")
        self.assertIsNotNone(escalated["needs_tanner"])
        self.assertEqual(escalated["status"], "tanner_escalation")
        self.assertTrue(escalated["notification_signals"]["immediate_human_review"])
        self.assertEqual(escalated["notification_signals"]["immediate_human_review"],
                         bool(escalated["needs_tanner"]))
        self.assertTrue(escalated["operational_learning_observations"]
                        ["tanner_escalation_required"])
        self.assertEqual(escalated["notification_signals"]
                         ["periodic_progress_interval_seconds"], 10800)
        self.assertFalse(escalated["notification_signals"]
                         ["periodic_progress_pauses_campaign"])

    def test_noncorrectable_insufficient_review_escalates_without_new_builder(self):
        self.fixture.campaign.create(self.fixture.payload("insufficient"), authenticated_rider=True)
        review = self.fixture.review("insufficient", "insufficient_evidence", correctable=False)
        record = self.fixture.campaign.consume_review("insufficient", review,
            reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(record["status"], "tanner_escalation")
        self.assertEqual(record["needs_tanner"]["reason"],
                         "insufficient_evidence_not_correctable_in_scope")
        self.assertEqual(len(self.fixture.builder_payloads), 1)


class StepwiseCampaignV01Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.fixture = CampaignFixture(Path(self.tmp.name))

    def payload(self, campaign_id):
        return {**self.fixture.payload(campaign_id), "execution_budget_v01": {
            "maximum_duration_seconds": 3600, "maximum_worker_turns": 2,
            "maximum_reviewer_turns": 4, "maximum_provider_turns": 6,
            "maximum_cost_units": 6, "maximum_correction_cycles": 2,
            "maximum_iterations": 3}}

    def test_canonical_stepwise_status_and_budget_projection_is_exact(self):
        record = self.fixture.campaign.create(
            self.payload("stepwise-contract-projection"),
            authenticated_rider=True, stepwise=True)
        self.assertEqual(stepwise_campaign_budget_limits(record), {
            "seconds": 3600, "provider_turns": 6,
            "correction_cycles": 2, "cost_units": 6, "iterations": 3,
        })
        for status in (
                "ready", "builder_in_progress", "awaiting_independent_review",
                "reviewer_native_action_approved",
                "review_accepted_application_pending",
                "reviewed_application_completed", "correction_pending"):
            self.assertEqual(stepwise_campaign_status_disposition(status), "active")
        for status in ("tanner_escalation", "ready_for_bounded_continuation"):
            self.assertEqual(stepwise_campaign_status_disposition(status), "paused")
        for status in ("succeeded", "cancelled", "failed_safe"):
            self.assertEqual(stepwise_campaign_status_disposition(status), "terminal")
        for status in ("denied", "expired", "accepted", None):
            with self.subTest(status=status), self.assertRaises(PermissionError):
                stepwise_campaign_status_disposition(status)

        tampered = json.loads(json.dumps(record))
        tampered["execution_budget_v01"]["maximum_provider_turns"] += 1
        with self.assertRaisesRegex(PermissionError, "budget binding"):
            stepwise_campaign_budget_limits(tampered)

    def test_accepted_review_checkpoints_once_without_fallthrough(self):
        campaign=self.fixture.campaign
        created=campaign.create(self.payload("stepwise-accepted"),
            authenticated_rider=True)
        awaiting=campaign._update(created,event_kind="fixture_stepwise_boundary",
            stepwise_v01=True)
        self.assertEqual("awaiting_independent_review",awaiting["status"])
        review=self.fixture.review(created["campaign_id"],"pass",
            satisfied=["tests-pass","scope-held"])
        accepted=campaign.consume_review(created["campaign_id"],review,
            reviewer=REVIEWER,transport_verified=True)
        self.assertEqual("review_accepted_application_pending",accepted["status"])
        self.assertIsNone(accepted.get("application_evidence"))
        self.assertEqual([],self.fixture.applications)

    def test_stepwise_creation_requires_explicit_external_git_state_root(self):
        campaign=CodexDevelopmentCampaign("fawkes",root=Path(self.tmp.name)/"no-runtime",
            exchange=self.fixture.exchange,builder_runner=lambda payload: payload,
            builder_modes={"repository_write"})
        with self.assertRaisesRegex(ValueError,"Git transaction state root"):
            campaign.create(self.payload("stepwise-no-git-root"),
                authenticated_rider=True,stepwise=True)

    def test_expired_git_stage_reconciles_first_but_never_starts_new_cas(self):
        campaign = self.fixture.campaign
        record = campaign.create(self.payload("stepwise-expired-git"),
            authenticated_rider=True, stepwise=True)
        budget = dict(record["execution_budget_v01"])
        budget["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        application = {
            "status": "applied_verified_after_review", "application_count": 1,
            "operation_id": "application-exact", "applied_paths": [],
            "review_acceptance_receipt_sha256": "a" * 64,
            "binding": {"expected_repository_head": "b" * 40,
                        "mutation_manifest_sha256": "c" * 64},
            "reviewed_commit_projection": {
                "expected_tree": "d" * 40, "expected_diff_sha256": "e" * 64,
                "message": "Exact reviewed fixture"},
        }
        record = campaign._update(record, event_kind="fixture_application_complete",
            status="reviewed_application_completed", execution_budget_v01=budget,
            application_evidence=application,
            reviews=[{"status": "pass", "reviewed_application_operation_id":
                      "application-exact"}])
        counts = {"reconcile": 0, "prepare": 0, "advance": 0}

        class Owner:
            def __init__(self, *args):
                pass

            def reconcile_campaign_reviewed_application(self, **kwargs):
                counts["reconcile"] += 1
                raise FileNotFoundError

            def prepare_reviewed_application(self, **kwargs):
                counts["prepare"] += 1
                return kwargs

            def advance_campaign_reviewed_application(self, *args, **kwargs):
                counts["advance"] += 1
                return {"status": "committed"}

        with patch.object(campaign, "_canonical_application_adapter",
                          return_value=SimpleNamespace(workspace=Path(self.tmp.name))), \
                patch("src.runtime.git_commit_transaction.GitCommitTransaction", Owner):
            result = campaign._complete_pending_reviewed_git_locked(record, object())
        self.assertEqual(result["status"], "failed_safe")
        self.assertEqual(result["needs_tanner"]["reason"], "campaign_duration_expired")
        self.assertEqual(counts, {"reconcile": 1, "prepare": 0, "advance": 0})
        self.assertFalse(result["creates_continuing_authority"])

    def _reserved(self, campaign_id="stepwise-ambiguous"):
        campaign = self.fixture.campaign
        record = campaign.create(self.payload(campaign_id), authenticated_rider=True,
                                 stepwise=True)
        scope = f"{campaign_id}-builder-1"
        record = campaign._update(record, event_kind="builder_invocation_started",
            status="builder_in_progress", iteration=1,
            active_builder_task_scope_id=scope)
        sender = {"worker_id":"fawkes-development", "role":"coordination",
            "identity_status":"verified", "charter_version":"1.0"}
        report = self.fixture.exchange.create_report(task_scope_id=scope, sender=sender,
            authority=authority("fawkes", scope, sender["worker_id"]),
            sections=[{"section_id":"approved-task", "title":"Task", "content":"Bounded."}])
        package = self.fixture.exchange.compose_package(report_id=report["report_id"],
            recipient={"worker_id":BUILDER_ID,"role":"repository_implementation",
                "identity_status":"verified","charter_version":"1.0"},
            authority=authority("fawkes", scope, sender["worker_id"], BUILDER_ID),
            included_section_ids=["approved-task"])
        campaign.reserve_worker_provider_action(campaign_id=campaign_id,
            task_scope_id=scope, package_id=package["package_id"],
            package_sha256=package["record_sha256"], invocation_id=scope+"-appserver")
        return campaign

    def test_ambiguous_provider_completion_consumes_reservation_without_retry(self):
        campaign = self._reserved()
        result = campaign.advance_once("stepwise-ambiguous")
        self.assertEqual(result["status"], "failed_safe")
        self.assertEqual(result["needs_tanner"]["reason"], "ambiguous_provider_completion")
        budget = result["execution_budget_v01"]
        self.assertEqual(budget["consumed_provider_turns"], 1)
        self.assertEqual(budget["consumed_cost_units"], 1)
        self.assertEqual(len(self.fixture.builder_payloads), 0)
        self.assertEqual(campaign.advance_once("stepwise-ambiguous")["status"], "failed_safe")

    def test_restart_before_provider_reservation_closes_failed_safe_without_retry(self):
        campaign = self.fixture.campaign
        record = campaign.create(self.payload("stepwise-before-reservation"),
            authenticated_rider=True, stepwise=True)
        record = campaign._update(record, event_kind="builder_invocation_started",
            status="builder_in_progress", iteration=1,
            active_builder_task_scope_id="stepwise-before-reservation-builder-1")
        result = campaign.advance_once(record["campaign_id"])
        self.assertEqual(result["status"], "failed_safe")
        self.assertEqual(result["needs_tanner"]["reason"], "ambiguous_provider_completion")
        self.assertFalse(result["needs_tanner"]["provider_contact_proven"])
        self.assertIsNone(result["execution_budget_v01"]["provider_action"])
        self.assertEqual(result["execution_budget_v01"]["consumed_provider_turns"], 0)
        self.assertEqual(len(self.fixture.builder_payloads), 0)
        replay = campaign.advance_once(record["campaign_id"])
        self.assertEqual(replay["record_sha256"], result["record_sha256"])
        self.assertEqual(len(self.fixture.builder_payloads), 0)

    def test_stepwise_configured_iteration_limit_blocks_next_worker(self):
        payload=self.fixture.payload("iteration-budget-v01")
        payload["stepwise_v01"]=True
        payload["execution_budget_v01"]={"maximum_duration_seconds":3600,
            "maximum_worker_turns":3,"maximum_reviewer_turns":4,
            "maximum_provider_turns":7,"maximum_cost_units":7,
            "maximum_correction_cycles":2,"maximum_iterations":1}
        record=self.fixture.campaign.create(payload,authenticated_rider=True,stepwise=True)
        record=self.fixture.campaign.store.load(record["campaign_id"])
        record=self.fixture.campaign._update(record,event_kind="fixture_iteration_limit",
            iteration=1,status="correction_pending",
            pending_correction={"task":"bounded correction"})
        before=len(record["builder_runs"])
        terminal=self.fixture.campaign.advance_once(record["campaign_id"])
        self.assertEqual(terminal["status"],"failed_safe")
        self.assertEqual(terminal["needs_tanner"]["reason"],"maximum_iterations_reached")
        self.assertEqual(len(terminal["builder_runs"]),before)

    def test_run_to_terminal_stalls_fail_closed_through_advance_once(self):
        payload=self.fixture.payload("stepwise-stall-v01")
        payload["stepwise_v01"]=True
        payload["execution_budget_v01"]={"maximum_duration_seconds":3600,
            "maximum_worker_turns":3,"maximum_reviewer_turns":4,
            "maximum_provider_turns":7,"maximum_cost_units":7,
            "maximum_correction_cycles":2,"maximum_iterations":1}
        record=self.fixture.campaign.create(payload,authenticated_rider=True,stepwise=True)
        self.fixture.campaign.advance_once=lambda *args,**kwargs: record
        terminal=self.fixture.campaign.run_to_terminal(record["campaign_id"])
        self.assertEqual(terminal["status"],"failed_safe")
        self.assertEqual(terminal["needs_tanner"]["reason"],"stepwise_progress_stalled")

    def test_every_provider_budget_exhaustion_is_durable_and_unreserved(self):
        cases=(("maximum_worker_turns","worker",1,1),
               ("maximum_reviewer_turns","reviewer",2,2),
               ("maximum_provider_turns","worker",1,1),
               ("maximum_cost_units","worker",1,1))
        for index,(limit,kind,turns,cost) in enumerate(cases):
            with self.subTest(limit=limit):
                payload=self.fixture.payload(f"exhaust-{index}")
                payload["execution_budget_v01"]={"maximum_duration_seconds":3600,
                    "maximum_worker_turns":2,"maximum_reviewer_turns":4,
                    "maximum_provider_turns":6,"maximum_cost_units":6,
                    "maximum_correction_cycles":2,"maximum_iterations":3}
                record=self.fixture.campaign.create(payload,authenticated_rider=True,stepwise=True)
                budget=dict(record["execution_budget_v01"])
                consumed={"maximum_worker_turns":"consumed_worker_turns",
                    "maximum_reviewer_turns":"consumed_reviewer_turns",
                    "maximum_provider_turns":"consumed_provider_turns",
                    "maximum_cost_units":"consumed_cost_units"}[limit]
                budget[consumed]=budget[limit]
                record=self.fixture.campaign._update(record,event_kind="fixture_budget_used",
                    execution_budget_v01=budget)
                with self.assertRaisesRegex(RuntimeError,limit):
                    self.fixture.campaign._reserve_provider(record,operation_type=kind,
                        package_id="package-test",package_sha256="0"*64,
                        invocation_id="invocation-test",task_scope_id="scope-test",
                        turns=turns,cost=cost)
                failed=self.fixture.campaign.store.load(record["campaign_id"])
                self.assertEqual(failed["status"],"failed_safe")
                self.assertEqual(failed["needs_tanner"]["exhausted_limit"],limit)
                self.assertIsNone(failed["execution_budget_v01"]["provider_action"])

    def test_reservation_rejects_neighboring_package_and_is_durable(self):
        campaign = self._reserved("stepwise-bound")
        record = campaign.store.load("stepwise-bound")
        action = record["execution_budget_v01"]["provider_action"]
        self.assertEqual(action["status"], "provider_action_reserved")
        self.assertEqual(action["scope_sha256"], _digest(record["allowed_scope"]))
        with self.assertRaises((KeyError, PermissionError)):
            campaign.reserve_worker_provider_action(campaign_id="stepwise-bound",
                task_scope_id=action["task_scope_id"], package_id="neighbor-package",
                package_sha256="0"*64, invocation_id="neighbor")


class CodexDevelopmentCampaignHTTPTests(unittest.TestCase):
    def test_status_create_and_cancel_require_authenticated_rider(self):
        if os.getenv("FAWKES_HTTP_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_HTTP_ACCEPTANCE=1 where loopback sockets are permitted")
        from src.app.server import FawkesAppServer

        class Service:
            def __init__(self): self.calls = []
            def create_codex_development_campaign(self, payload, *, authenticated_rider=False):
                self.calls.append(("create", authenticated_rider, payload)); return {"campaign": {"campaign_id": "one"}}
            def codex_development_campaign(self, campaign_id):
                self.calls.append(("get", campaign_id)); return {"campaign_id": campaign_id}
            def cancel_codex_development_campaign(self, campaign_id, *, authenticated_rider=False):
                self.calls.append(("cancel", authenticated_rider, campaign_id)); return {"campaign": {"status": "cancelled"}}

        service = Service(); server = FawkesAppServer(("127.0.0.1", 0), chat_service=service, app_token="token")
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_port}/api/development/codex-campaigns"
        body = json.dumps({"objective": "bounded"}).encode()
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(urllib.request.Request(base, data=body, method="POST",
                    headers={"Content-Type": "application/json"}), timeout=5)
            self.assertEqual(denied.exception.code, 401); denied.exception.close()
            headers = {"Content-Type": "application/json", "Authorization": "Bearer token"}
            self.assertEqual(urllib.request.urlopen(urllib.request.Request(base, data=body,
                method="POST", headers=headers), timeout=5).status, 201)
            get = urllib.request.urlopen(urllib.request.Request(base + "/one",
                headers={"Authorization": "Bearer token"}), timeout=5)
            self.assertEqual(json.load(get)["campaign_id"], "one")
            cancel = urllib.request.urlopen(urllib.request.Request(base + "/one/cancel", data=b"{}",
                method="POST", headers=headers), timeout=5)
            self.assertEqual(json.load(cancel)["campaign"]["status"], "cancelled")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
        self.assertEqual([item[0] for item in service.calls], ["create", "get", "cancel"])


if __name__ == "__main__":
    unittest.main()

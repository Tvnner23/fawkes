import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.runtime.codex_development_campaign import (
    CAMPAIGN_ACCEPTANCE_CONTRACT, CAMPAIGN_CONTRACT_VERSION, MAX_ITERATIONS,
    DEFAULT_REVIEWER_BINDING_ASSURANCE, DEFAULT_REVIEWER_ROLE, DEFAULT_REVIEWER_WORKER_ID,
    FORMAL_REVIEW_ROLE,
    ROOT,
    CodexDevelopmentCampaign,
    _cleanup_python_cache,
)
from src.runtime.codex_development_handoff import run_codex_development_handoff
from src.runtime.phase0_integrity import SCOPED_ROOTS
from src.runtime.worker_exchange import WorkerExchange, _digest
from src.runtime.development_attention import DevelopmentAttentionStore
from src.runtime.disposable_verifier import candidate_manifest


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
        self.campaign = CodexDevelopmentCampaign(self.instance_id, root=root / "campaigns",
            exchange=self.exchange, builder_runner=builder, builder_modes={"repository_write"},
            candidate_applier=apply_candidate)

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
                "review_report_id":returned["report_id"],
                "review_report_sha256":returned["record_sha256"],
                "review_invocation_id":f"fixture-review-{record['iteration']}",
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
                "creates_authority":False,"created_at":datetime.now(timezone.utc).isoformat()}
            receipt["record_sha256"]=_digest(receipt); review["review_acceptance_receipt"]=receipt
        return review


class CodexDevelopmentCampaignTests(unittest.TestCase):
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

    def test_correction_cycle_uses_exact_review_then_independent_pass_succeeds(self):
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
        self.assertEqual(record["status"], "succeeded")
        self.assertFalse(record["automatic_promotion"])
        self.assertEqual(len(record["builder_runs"]), 2)
        self.assertEqual(len(self.fixture.applications), 1)

    def test_end_to_end_transaction_orders_retention_review_and_one_shot_apply(self):
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
        self.assertEqual(terminal["status"], "succeeded")
        self.assertEqual(len(self.fixture.applications), 1)
        self.assertEqual(self.fixture.applications[0]["review_report_id"],
                         terminal["reviews"][-1]["review_report_id"])
        kinds = [item["kind"] for item in terminal["events"]]
        self.assertLess(kinds.index("builder_return_retained"),
                        kinds.index("independent_review_retained"))
        self.assertLess(kinds.index("independent_review_retained"),
                        kinds.index("campaign_succeeded"))
        with self.assertRaisesRegex(RuntimeError, "not awaiting"):
            self.fixture.campaign.consume_review("transaction-order", review,
                reviewer=REVIEWER, transport_verified=True)
        self.assertEqual(len(self.fixture.applications), 1)

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

import os
import tempfile
import threading
import unittest
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "src/runtime/langgraph_development_runner.py"
SPEC = importlib.util.spec_from_file_location("stage_b_candidate", MODULE)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
freeze_runner_plan = RUNNER.freeze_runner_plan


class LangGraphDevelopmentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        os.system(f"git -C {self.repo} init -q -b synthetic")
        (self.repo / "base.txt").write_text("base\n")
        os.system(f"git -C {self.repo} add base.txt")
        os.system(
            f"git -C {self.repo} -c user.name=Fixture -c user.email=f@invalid commit -qm base")

    def tearDown(self):
        self.temp.cleanup()

    def payload(self):
        return {
            "instance_id": "fawkes", "campaign_id": "pilot",
            "target_builder": "codex_repo", "objective_mode": "repository_write",
            "objective": "Synthetic bounded fixture.",
            "acceptance_condition_ids": ["tests"],
            "acceptance_conditions": {"tests": "Tests pass."},
            "allowed_scope": ["src/example.py", "tests/test_example.py"],
            "source_sections": [{"section_id": "task", "title": "Task",
                                 "content": "Synthetic fixture only."}],
            "rider_authorization_reference": "synthetic-plan",
            "validation_policy": "required",
            "validation_commands": [["python3", "-m", "unittest", "tests.test_example"]],
            "recovery_references": [{"reference_type": "working_checkpoint",
                                     "reference_id": "synthetic-start"}],
            "explicitly_authorized": True,
        }

    def limits(self):
        return {
            "seconds": 1800, "batches": 1, "provider_turns": 8,
            "correction_cycles": 2, "cost_units": 8, "iterations": 3,
            "files": 2,
        }

    @staticmethod
    def seal(record):
        value = {key: item for key, item in record.items() if key != "record_sha256"}
        value["record_sha256"] = RUNNER._digest(value)
        return value

    @staticmethod
    def seal_budget(record):
        budget = record["execution_budget_v01"]
        immutable = {key: budget[key] for key in (
            "maximum_duration_seconds", "maximum_worker_turns",
            "maximum_reviewer_turns", "maximum_provider_turns",
            "maximum_cost_units", "maximum_correction_cycles",
            "maximum_iterations", "created_at", "expires_at", "contract")}
        budget["budget_sha256"] = RUNNER._digest(immutable)
        return LangGraphDevelopmentRunnerTests.seal(record)

    def plan(self, campaign_record=None):
        campaign_record = campaign_record or self.record("ready")
        return freeze_runner_plan(
            self.repo, {"task_id": "task-a", "payload": self.payload()},
            campaign_id="pilot", limits=self.limits(),
            campaign_record=campaign_record)

    def canonical_budget(self):
        now = datetime.now(timezone.utc)
        limits = self.limits()
        immutable = {
            "maximum_duration_seconds": limits["seconds"],
            "maximum_worker_turns": limits["iterations"],
            "maximum_reviewer_turns": limits["iterations"] * 2,
            "maximum_provider_turns": limits["provider_turns"],
            "maximum_cost_units": limits["cost_units"],
            "maximum_correction_cycles": limits["correction_cycles"],
            "maximum_iterations": limits["iterations"],
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=limits["seconds"])).isoformat(),
            "contract": "conservative-provider-reservation-failed-safe-v0.1",
        }
        return {
            **immutable,
            "consumed_worker_turns": 0,
            "consumed_reviewer_turns": 0,
            "consumed_provider_turns": 0,
            "consumed_cost_units": 0,
            "consumed_correction_cycles": 0,
            "provider_action": None,
            "provider_actions": [],
            "budget_sha256": RUNNER._digest(immutable),
        }

    def record(self, status="ready", revision=1):
        budget = self.canonical_budget()
        payload = self.payload()
        record = {
            "schema_version": 1,
            "record_type": "codex_development_campaign",
            "contract_version": "codex-development-campaign-v0.1",
            "campaign_id": "pilot", "instance_id": "fawkes",
            "objective": payload["objective"],
            "objective_sha256": __import__("hashlib").sha256(
                payload["objective"].encode()).hexdigest(),
            "objective_mode": payload["objective_mode"],
            "acceptance_condition_ids": payload["acceptance_condition_ids"],
            "acceptance_conditions": payload["acceptance_conditions"],
            "allowed_scope": payload["allowed_scope"],
            "source_sections": payload["source_sections"],
            "validation_commands": payload["validation_commands"],
            "validation_policy": payload["validation_policy"],
            "validation_declaration": {"record_sha256": "v" * 64},
            "rider_authorization_reference": payload["rider_authorization_reference"],
            "recovery_references": payload["recovery_references"],
            "stepwise_v01": True, "maximum_iterations": 3,
            "status": status, "state_revision": revision, "iteration": 0,
            "execution_budget_v01": budget, "needs_tanner": None,
            "application_evidence": None, "git_commit_evidence": None,
        }
        if status == "builder_in_progress":
            budget["provider_action"] = {
                "status": "provider_action_reserved", "operation_id": "provider-op"}
        if status == "reviewed_application_completed":
            record["application_evidence"] = {
                "operation_id": "application-exact", "record_sha256": "a" * 64}
        if status == "succeeded":
            record["application_evidence"] = {
                "operation_id": "application-exact", "record_sha256": "a" * 64}
            record["git_commit_evidence"] = {
                "operation_id": "application-exact", "record_sha256": "c" * 64}
        if status in {"failed_safe", "tanner_escalation"}:
            record["needs_tanner"] = {"reason": "fixture_stop"}
        return self.seal(record)

    def runner_fixture(self, *, initial=None, genesis=None, crash_after=None,
                       runtime_name="runtime", before_plan=None):
        if before_plan is not None:
            before_plan()
        genesis = copy.deepcopy(genesis) if genesis is not None else self.record("ready")
        if initial is None:
            initial = genesis
        else:
            initial = copy.deepcopy(initial)
            initial["execution_budget_v01"] = copy.deepcopy(
                genesis["execution_budget_v01"])
            initial = self.seal(initial)
        shared = {
            "record": initial,
            "counts": {"create": 0, "advance": 0, "worker": 0, "reviewer": 0,
                       "review_native": 0, "application": 0, "git": 0,
                       "cancel": 0},
            "crash_after": crash_after,
            "crashed": False,
            "canonical_reject": None,
            "plan": self.plan(genesis),
        }

        outer = self

        class Store:
            def load(self, campaign_id):
                if shared["record"] is None:
                    raise KeyError(campaign_id)
                return shared["record"]

        class Campaign:
            def __init__(self, *args, **kwargs):
                self.store = Store()
                self.exchange = object()

            @staticmethod
            def _set(status, *, reason=None):
                prior = shared["record"] or outer.record()
                updated = outer.record(status, prior.get("state_revision", 0) + 1)
                updated["execution_budget_v01"] = prior["execution_budget_v01"]
                if status == "reviewed_application_completed":
                    updated["application_evidence"] = {
                        "operation_id": "application-exact", "record_sha256": "a" * 64}
                if status == "succeeded":
                    updated["application_evidence"] = {
                        "operation_id": "application-exact", "record_sha256": "a" * 64}
                    updated["git_commit_evidence"] = {
                        "operation_id": "application-exact", "record_sha256": "c" * 64}
                if reason:
                    updated["needs_tanner"] = {"reason": reason}
                shared["record"] = outer.seal(updated)
                return shared["record"]

            def create(self, payload, *, authenticated_rider, stepwise):
                shared["counts"]["create"] += 1
                raise AssertionError("LangGraph must not create or authenticate a campaign")

            def advance_once(self, campaign_id, *, reviewer_adapter):
                shared["counts"]["advance"] += 1
                if shared["canonical_reject"]:
                    raise PermissionError(shared["canonical_reject"])
                status = shared["record"]["status"]
                budget = shared["record"]["execution_budget_v01"]
                if (datetime.now(timezone.utc) >=
                        datetime.fromisoformat(budget["expires_at"])):
                    result = self._set(
                        "failed_safe", reason="campaign_duration_expired")
                    result["execution_budget_v01"] = budget
                    shared["record"] = outer.seal(result)
                    return shared["record"]
                if status == "ready":
                    shared["counts"]["worker"] += 1
                    result = self._set("awaiting_independent_review")
                elif status == "awaiting_independent_review":
                    shared["counts"]["reviewer"] += 1
                    result = self._set("review_accepted_application_pending")
                elif status == "reviewer_native_action_approved":
                    shared["counts"]["review_native"] += 1
                    result = self._set("awaiting_independent_review")
                elif status == "review_accepted_application_pending":
                    shared["counts"]["application"] += 1
                    result = self._set("reviewed_application_completed")
                elif status == "reviewed_application_completed":
                    shared["counts"]["git"] += 1
                    result = self._set("succeeded")
                elif status == "builder_in_progress":
                    budget = shared["record"]["execution_budget_v01"]
                    budget["consumed_worker_turns"] += 1
                    budget["consumed_provider_turns"] += 1
                    budget["consumed_cost_units"] += 1
                    budget["provider_action"] = None
                    result = self._set("failed_safe", reason="ambiguous_provider_completion")
                    result["execution_budget_v01"] = budget
                    shared["record"] = outer.seal(result)
                    result = shared["record"]
                else:
                    raise AssertionError("unexpected canonical step: " + status)
                if shared["crash_after"] == result["status"] and not shared["crashed"]:
                    shared["crashed"] = True
                    raise RuntimeError("injected graph checkpoint gap")
                return result

            def cancel(self, campaign_id, *, authenticated_rider):
                if authenticated_rider is not True:
                    raise PermissionError("authenticated rider required")
                shared["counts"]["cancel"] += 1
                return self._set("cancelled")

        class Reviewer:
            def __init__(self, *args, **kwargs):
                pass

        with patch.object(RUNNER, "CodexDevelopmentCampaign", Campaign), \
                patch.object(RUNNER, "WslCodexReviewAdapter", Reviewer):
            runner = RUNNER.BoundedLangGraphDevelopmentRunner(
                repository=self.repo, runtime_root=self.root / runtime_name,
                plan=shared["plan"], clock=lambda: 100.0)
        return runner, shared, Campaign, Reviewer

    def reopen(self, shared, campaign_type, reviewer_type, runtime_name="runtime"):
        with patch.object(RUNNER, "CodexDevelopmentCampaign", lambda *a, **k: campaign_type()), \
                patch.object(RUNNER, "WslCodexReviewAdapter", reviewer_type):
            runner = RUNNER.BoundedLangGraphDevelopmentRunner(
                repository=self.repo, runtime_root=self.root / runtime_name,
                plan=shared["plan"], clock=lambda: 100.0)
        return runner

    def test_plan_is_exact_immutable_pre_genesis_and_budget_bound(self):
        genesis = self.record("ready")
        plan = self.plan(genesis)
        self.assertFalse(plan["canonical_memory"])
        self.assertFalse(plan["creates_authority"])
        self.assertFalse(plan["creates_continuing_authority"])
        self.assertEqual(plan["limits"]["batches"], 1)
        self.assertNotIn("canonical_execution_budget", plan)
        self.assertEqual(plan["canonical_campaign_initial_record_sha256"],
                         genesis["record_sha256"])

    def test_scope_file_iteration_and_unbounded_limits_are_rejected(self):
        payload = self.payload()
        payload["allowed_scope"] = ["../escape"]
        with self.assertRaises(PermissionError):
            freeze_runner_plan(self.repo, {"task_id": "task-a", "payload": payload},
                               campaign_id="pilot", limits=self.limits(),
                               campaign_record=self.record("ready"))
        for field, value in (("batches", 2), ("correction_cycles", 3), ("files", 1)):
            with self.subTest(field=field):
                limits = self.limits()
                limits[field] = value
                with self.assertRaises(ValueError):
                    freeze_runner_plan(
                        self.repo, {"task_id": "task-a", "payload": self.payload()},
                        campaign_id="pilot", limits=limits,
                        campaign_record=self.record("ready"))

    def test_caller_cannot_supply_or_override_canonical_budget(self):
        payload = self.payload()
        payload["execution_budget_v01"] = self.canonical_budget()
        with self.assertRaises(ValueError):
            freeze_runner_plan(self.repo, {"task_id": "task-a", "payload": payload},
                               campaign_id="pilot", limits=self.limits(),
                               campaign_record=self.record("ready"))

    def test_every_supported_runner_limit_must_equal_canonical_budget(self):
        mappings = {
            "seconds": "maximum_duration_seconds",
            "provider_turns": "maximum_provider_turns",
            "correction_cycles": "maximum_correction_cycles",
            "cost_units": "maximum_cost_units",
            "iterations": "maximum_iterations",
        }
        for runner_key, canonical_key in mappings.items():
            with self.subTest(runner_key=runner_key):
                record = self.record("ready")
                record["execution_budget_v01"][canonical_key] += 1
                if canonical_key == "maximum_duration_seconds":
                    created = datetime.fromisoformat(
                        record["execution_budget_v01"]["created_at"])
                    record["execution_budget_v01"]["expires_at"] = (
                        created + timedelta(seconds=record["execution_budget_v01"][
                            "maximum_duration_seconds"])).isoformat()
                record = self.seal_budget(record)
                with self.assertRaisesRegex(PermissionError, "campaign budget"):
                    freeze_runner_plan(
                        self.repo, {"task_id": "task-a", "payload": self.payload()},
                        campaign_id="pilot", limits=self.limits(),
                        campaign_record=record)

    def test_resumed_campaign_rejects_changed_immutable_budget_but_not_consumption(self):
        runner, shared, _, _ = self.runner_fixture(runtime_name="budget-resume")
        consumed = copy.deepcopy(shared["record"])
        consumed["execution_budget_v01"]["consumed_provider_turns"] = 1
        consumed["execution_budget_v01"]["consumed_cost_units"] = 1
        shared["record"] = self.seal(consumed)
        projected = runner._project_record(
            {"plan_sha256": runner.plan["plan_sha256"]}, shared["record"])
        self.assertEqual(projected["provider_turns_consumed"], 1)

        changed = copy.deepcopy(shared["record"])
        budget = changed["execution_budget_v01"]
        budget["maximum_provider_turns"] += 1
        immutable = {key: budget[key] for key in (
            "maximum_duration_seconds", "maximum_worker_turns",
            "maximum_reviewer_turns", "maximum_provider_turns",
            "maximum_cost_units", "maximum_correction_cycles",
            "maximum_iterations", "created_at", "expires_at", "contract")}
        budget["budget_sha256"] = RUNNER._digest(immutable)
        shared["record"] = self.seal(changed)
        with self.assertRaisesRegex(PermissionError, "frozen runner plan"):
            runner._campaign(projected)
        self.assertEqual(shared["counts"]["advance"], 0)
        runner.close()

    def test_source_has_no_review_application_or_git_authority_path(self):
        source = MODULE.read_text()
        for forbidden in ("GitCommitTransaction", "prepare_reviewed_application",
                          "advance_reviewed_application", "reconcile_completed_application",
                          "update-ref", "verdict", "canonical_memory=True"):
            self.assertNotIn(forbidden, source)
        self.assertIn("advance_once", source)
        self.assertNotIn("reconcile_expired_once", source)
        self.assertNotIn("_assert_repository_current", source)
        self.assertNotIn("_assert_budget_binding", source)
        self.assertNotIn("_repository_neighbor_state", source)
        self.assertNotIn("self.campaign.create", source)
        self.assertNotIn("authenticated_rider=True, stepwise=True", source)

    def test_telemetry_is_not_enabled_and_dependencies_are_exactly_pinned(self):
        requirements = (MODULE.parents[2] / "requirements.txt").read_text().splitlines()
        self.assertIn("langgraph==1.2.11", requirements)
        self.assertIn("langgraph-checkpoint-sqlite==3.1.1", requirements)
        self.assertFalse(any(line.startswith("langmem") for line in requirements))
        with patch.dict(os.environ, {"LANGCHAIN_TRACING_V2": "true"}):
            with self.assertRaisesRegex(PermissionError, "tracing"):
                RUNNER.BoundedLangGraphDevelopmentRunner(
                    repository=self.repo, runtime_root=self.root / "tracing-runtime",
                    plan=self.plan(self.record("ready")), clock=lambda: 100.0)

    def test_each_graph_campaign_step_requests_exactly_one_canonical_transition(self):
        runner, shared, _, _ = self.runner_fixture()
        state = {"plan_sha256": runner.plan["plan_sha256"], "creates_authority": False,
                 "creates_continuing_authority": False}
        expected = ("worker", "reviewer", "application", "git")
        for index, operation in enumerate(expected, 1):
            before = dict(shared["counts"])
            state = runner._campaign(state)
            delta = {key: shared["counts"][key] - before[key] for key in shared["counts"]}
            self.assertEqual(sum(delta[key] for key in expected), 1)
            self.assertEqual(delta[operation], 1)
            self.assertEqual(delta["advance"], 1)
        self.assertEqual(shared["counts"]["create"], 0)
        runner.close()

    def test_native_reviewer_restart_requests_one_canonical_reconciliation(self):
        runner, shared, _, _ = self.runner_fixture(
            initial=self.record("reviewer_native_action_approved"),
            runtime_name="native-review-restart")
        state = {
            "plan_sha256": runner.plan["plan_sha256"],
            "creates_authority": False,
            "creates_continuing_authority": False,
        }
        projected = runner._campaign(state)
        self.assertEqual(projected["canonical_campaign_status"],
                         "awaiting_independent_review")
        self.assertEqual(shared["counts"]["advance"], 1)
        self.assertEqual(shared["counts"]["review_native"], 1)
        self.assertEqual((shared["counts"]["reviewer"],
                          shared["counts"]["application"],
                          shared["counts"]["git"]), (0, 0, 0))
        runner._validate_checkpoint_state(projected)
        runner.close()

    def test_real_campaign_native_review_restart_routes_one_canonical_transition(self):
        from tests.test_codex_development_campaign import (
            CampaignFixture, CodexDevelopmentCampaignTests, REVIEWER, authority)
        from src.runtime.codex_development_handoff import run_codex_development_handoff
        from src.runtime.development_attention import DevelopmentAttentionStore

        fixture_root = self.root / "real-campaign"
        fixture_root.mkdir()
        fixture = CampaignFixture(fixture_root)
        campaign = fixture.campaign
        campaign.attention_store = DevelopmentAttentionStore(
            self.root / "real-campaign-attention")

        def stepwise_builder(builder_payload):
            fixture.builder_payloads.append(builder_payload)
            return run_codex_development_handoff(
                instance_id="fawkes", payload=builder_payload,
                authenticated_rider=True, exchange=fixture.exchange,
                adapter=fixture.adapter, provider_reservation_owner=campaign)

        campaign.builder_runner = stepwise_builder
        payload = fixture.payload("pilot")
        payload["execution_budget_v01"] = {
            "maximum_duration_seconds": 1800,
            "maximum_worker_turns": 3,
            "maximum_reviewer_turns": 6,
            "maximum_provider_turns": 8,
            "maximum_cost_units": 8,
            "maximum_correction_cycles": 2,
            "maximum_iterations": 3,
        }
        genesis = campaign.create(payload, authenticated_rider=True, stepwise=True)
        awaiting = campaign.advance_once("pilot")
        self.assertEqual(awaiting["status"], "awaiting_independent_review")

        retention = awaiting["builder_runs"][-1]["candidate_retention_receipt"]
        sender = {"worker_id": "fawkes-development", "role": "coordination",
                  "identity_status": "verified", "charter_version": "1.0"}
        task_scope = "pilot-review-1"
        report = fixture.exchange.create_report(
            task_scope_id=task_scope, sender=sender,
            authority=authority("fawkes", task_scope, sender["worker_id"]),
            sections=[
                {"section_id": "review-target", "title": "Review target",
                 "content": "Review the exact retained candidate."},
                {"section_id": "candidate-snapshot", "title": "Candidate snapshot",
                 "content": __import__("json").dumps(
                     retention["candidate_snapshot"], sort_keys=True)},
                {"section_id": "candidate-retention-receipt",
                 "title": "Candidate retention receipt",
                 "content": __import__("json").dumps(retention, sort_keys=True)},
            ], claims=[])
        package_authority = authority(
            "fawkes", task_scope, sender["worker_id"], REVIEWER["worker_id"])
        package = fixture.exchange.compose_package(
            report_id=report["report_id"], recipient=REVIEWER,
            authority=package_authority, included_section_ids=[
                "review-target", "candidate-snapshot",
                "candidate-retention-receipt"])
        campaign._update(awaiting, event_kind="review_requested_fixture",
            review_requests=[{"iteration": awaiting["iteration"],
                              "package_id": package["package_id"]}])
        transport = {
            "candidate_snapshot_id": retention["candidate_snapshot"][
                "candidate_snapshot_id"],
            "candidate_record_sha256": retention["candidate_snapshot"][
                "record_sha256"],
            "mutation_manifest_sha256": retention["mutation_manifest_sha256"],
            "exact_change_evidence_sha256": retention[
                "exact_change_evidence_sha256"],
            "allowed_scope_sha256": retention["allowed_scope_sha256"],
            "candidate_retention_receipt_sha256": retention["record_sha256"],
        }
        reviewer = {"worker_id": REVIEWER["worker_id"], "role": REVIEWER["role"],
                    "environment_id": "fixture-review-read-only"}
        approval = CodexDevelopmentCampaignTests._typed_review_approval(
            "pilot", package, transport, reviewer,
            "real-runner-review-invocation", "real-runner-review-item")
        plan_payload = copy.deepcopy(payload)
        plan_payload.pop("execution_budget_v01")
        plan = freeze_runner_plan(
            self.repo, {"task_id": "real-native-review", "payload": plan_payload},
            campaign_id="pilot", limits=self.limits(), campaign_record=genesis)

        class Reviewer:
            def __init__(self, *args, **kwargs):
                pass

        with patch.object(RUNNER, "CodexDevelopmentCampaign",
                          lambda *args, **kwargs: campaign), \
                patch.object(RUNNER, "WslCodexReviewAdapter", Reviewer):
            runner = RUNNER.BoundedLangGraphDevelopmentRunner(
                repository=self.repo, runtime_root=self.root / "real-runner",
                plan=plan, clock=lambda: 100.0)
        result, failures = {}, []
        waiter = threading.Thread(
            target=lambda: CodexDevelopmentCampaignTests._capture_approval_result(
                campaign, approval, result, failures))
        waiter.start()
        for _ in range(200):
            events = campaign.attention_store.list(pending_only=True)
            if events:
                break
            threading.Event().wait(0.01)
        else:
            self.fail("real canonical Reviewer Attention event was not retained")
        event = events[0]
        with patch.object(campaign, "advance_once",
                          wraps=campaign.advance_once) as pending_advance:
            pending = runner._campaign({
                "plan_sha256": plan["plan_sha256"],
                "creates_authority": False,
                "creates_continuing_authority": False,
            })
        self.assertEqual(pending_advance.call_count, 0)
        self.assertTrue(pending["paused"])
        self.assertEqual(pending["canonical_campaign_status"], "tanner_escalation")
        campaign.decide_attention(
            "pilot", event["attention_id"], "approve_once",
            authenticated_rider=True,
            expected_identity=campaign.attention_store._authority_binding(event))
        waiter.join(2)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(failures, [])
        result["value"]["claim"]()
        with patch.object(campaign, "_finish_review_native_action",
                          side_effect=RuntimeError("checkpoint gap")):
            with self.assertRaisesRegex(RuntimeError, "checkpoint gap"):
                result["value"]["complete"]("completed")
        self.assertEqual(campaign.store.load("pilot")["status"],
                         "reviewer_native_action_approved")
        with patch.object(campaign, "advance_once",
                          wraps=campaign.advance_once) as advance:
            projected = runner._campaign({
                "plan_sha256": plan["plan_sha256"],
                "creates_authority": False,
                "creates_continuing_authority": False,
            })
        self.assertEqual(advance.call_count, 1)
        self.assertEqual(projected["canonical_campaign_status"],
                         "awaiting_independent_review")
        self.assertIsNone(campaign.store.load("pilot").get(
            "active_review_native_action"))
        self.assertEqual(len(fixture.builder_payloads), 1)
        self.assertEqual(fixture.applications, [])
        runner.close()

    def test_real_campaign_budget_exhaustion_stops_before_provider_delivery(self):
        from tests.test_codex_development_campaign import CampaignFixture
        from src.runtime.codex_development_handoff import run_codex_development_handoff

        fixture_root = self.root / "real-budget-campaign"
        fixture_root.mkdir()
        fixture = CampaignFixture(fixture_root)
        campaign = fixture.campaign

        def stepwise_builder(builder_payload):
            fixture.builder_payloads.append(builder_payload)
            return run_codex_development_handoff(
                instance_id="fawkes", payload=builder_payload,
                authenticated_rider=True, exchange=fixture.exchange,
                adapter=fixture.adapter, provider_reservation_owner=campaign)

        campaign.builder_runner = stepwise_builder
        payload = fixture.payload("pilot")
        payload["execution_budget_v01"] = {
            "maximum_duration_seconds": 1800,
            "maximum_worker_turns": 3,
            "maximum_reviewer_turns": 6,
            "maximum_provider_turns": 8,
            "maximum_cost_units": 8,
            "maximum_correction_cycles": 2,
            "maximum_iterations": 3,
        }
        genesis = campaign.create(payload, authenticated_rider=True, stepwise=True)
        exhausted_budget = copy.deepcopy(genesis["execution_budget_v01"])
        exhausted_budget["consumed_provider_turns"] = exhausted_budget[
            "maximum_provider_turns"]
        campaign._update(genesis, event_kind="fixture_provider_budget_consumed",
                         execution_budget_v01=exhausted_budget)
        plan_payload = copy.deepcopy(payload)
        plan_payload.pop("execution_budget_v01")
        plan = freeze_runner_plan(
            self.repo, {"task_id": "real-budget", "payload": plan_payload},
            campaign_id="pilot", limits=self.limits(), campaign_record=genesis)

        class Reviewer:
            def __init__(self, *args, **kwargs):
                pass

        with patch.object(RUNNER, "CodexDevelopmentCampaign",
                          lambda *args, **kwargs: campaign), \
                patch.object(RUNNER, "WslCodexReviewAdapter", Reviewer):
            runner = RUNNER.BoundedLangGraphDevelopmentRunner(
                repository=self.repo, runtime_root=self.root / "real-budget-runner",
                plan=plan, clock=lambda: 100.0)
        with patch.object(fixture.adapter, "deliver_production_once",
                          wraps=fixture.adapter.deliver_production_once) as deliver, \
                patch.object(campaign, "advance_once",
                             wraps=campaign.advance_once) as advance:
            projected = runner._campaign({
                "plan_sha256": plan["plan_sha256"],
                "creates_authority": False,
                "creates_continuing_authority": False,
            })
        self.assertEqual(advance.call_count, 1)
        self.assertEqual(deliver.call_count, 0)
        self.assertEqual(projected["terminal_status"], "failed_safe")
        retained = campaign.store.load("pilot")
        self.assertEqual(retained["needs_tanner"]["reason"],
                         "provider_budget_exhausted")
        self.assertEqual(retained["needs_tanner"]["exhausted_limit"],
                         "maximum_provider_turns")
        self.assertIsNone(retained["execution_budget_v01"]["provider_action"])
        self.assertEqual(fixture.applications, [])
        runner.close()

    def test_accepted_path_applies_and_commits_exactly_once_and_replay_is_inert(self):
        runner, shared, _, _ = self.runner_fixture()
        result = runner.run_or_resume()
        self.assertEqual(result["terminal_status"], "succeeded")
        self.assertEqual((shared["counts"]["application"], shared["counts"]["git"]), (1, 1))
        again = runner.run_or_resume()
        self.assertEqual(again["campaign_record_sha256"], result["campaign_record_sha256"])
        self.assertEqual((shared["counts"]["application"], shared["counts"]["git"]), (1, 1))
        runner.close()

    def test_crash_after_application_reconciles_without_duplicate_effect(self):
        runner, shared, campaign_type, reviewer_type = self.runner_fixture(
            crash_after="reviewed_application_completed")
        with self.assertRaisesRegex(RuntimeError, "checkpoint gap"):
            runner.run_or_resume()
        self.assertEqual((shared["counts"]["application"], shared["counts"]["git"]), (1, 0))
        runner.close()
        shared["crash_after"] = None
        resumed = self.reopen(shared, campaign_type, reviewer_type)
        result = resumed.run_or_resume()
        self.assertEqual(result["terminal_status"], "succeeded")
        self.assertEqual((shared["counts"]["application"], shared["counts"]["git"]), (1, 1))
        resumed.close()

    def test_crash_after_git_reconciles_without_duplicate_effect(self):
        runner, shared, campaign_type, reviewer_type = self.runner_fixture(crash_after="succeeded")
        with self.assertRaisesRegex(RuntimeError, "checkpoint gap"):
            runner.run_or_resume()
        self.assertEqual((shared["counts"]["application"], shared["counts"]["git"]), (1, 1))
        runner.close()
        shared["crash_after"] = None
        resumed = self.reopen(shared, campaign_type, reviewer_type)
        result = resumed.run_or_resume()
        self.assertEqual(result["terminal_status"], "succeeded")
        self.assertEqual((shared["counts"]["application"], shared["counts"]["git"]), (1, 1))
        resumed.close()

    def test_ambiguous_provider_completion_stops_without_retry_or_protected_effect(self):
        runner, shared, _, _ = self.runner_fixture(initial=self.record("builder_in_progress"))
        result = runner.run_or_resume()
        self.assertEqual(result["terminal_status"], "failed_safe")
        self.assertEqual(result["needs_tanner_reason"], "ambiguous_provider_completion")
        self.assertEqual(result["provider_turns_consumed"], 1)
        self.assertEqual((shared["counts"]["worker"], shared["counts"]["reviewer"],
                          shared["counts"]["application"], shared["counts"]["git"]),
                         (0, 0, 0, 0))
        runner.run_or_resume()
        self.assertEqual(shared["counts"]["advance"], 1)
        runner.close()

    def test_cancel_failed_safe_and_attention_pause_never_advance(self):
        for status in ("cancelled", "failed_safe", "tanner_escalation",
                       "ready_for_bounded_continuation"):
            with self.subTest(status=status):
                runner, shared, _, _ = self.runner_fixture(
                    initial=self.record(status), runtime_name="runtime-" + status)
                result = runner.run_or_resume()
                self.assertEqual(sum(shared["counts"].values()), 0)
                if status in {"tanner_escalation", "ready_for_bounded_continuation"}:
                    self.assertTrue(result["paused"])
                else:
                    self.assertEqual(result["terminal_status"], status)
                runner.close()

    def test_unknown_or_runner_invented_outcomes_fail_closed(self):
        for index, status in enumerate(("denied", "expired", "accepted", "unknown")):
            with self.subTest(status=status):
                runner, shared, _, _ = self.runner_fixture(
                    initial=self.record("ready"), runtime_name=f"unknown-{index}")
                changed = copy.deepcopy(shared["record"])
                changed["status"] = status
                changed["state_revision"] += 1
                shared["record"] = self.seal(changed)
                with self.assertRaisesRegex(PermissionError, "status is unknown"):
                    runner._campaign({
                        "plan_sha256": runner.plan["plan_sha256"],
                        "creates_authority": False,
                        "creates_continuing_authority": False,
                    })
                self.assertEqual(shared["counts"]["advance"], 0)
                runner.close()

    def test_cancel_and_end_campaign_use_only_authenticated_canonical_owner(self):
        runner, shared, _, _ = self.runner_fixture(initial=self.record("ready"))
        with self.assertRaises(PermissionError):
            runner.cancel(authenticated_rider=False)
        result = runner.end_campaign(authenticated_rider=True)
        self.assertEqual(result["terminal_status"], "cancelled")
        self.assertEqual(shared["counts"]["cancel"], 1)
        self.assertEqual((shared["counts"]["application"], shared["counts"]["git"]), (0, 0))
        runner.close()

    def test_forged_bare_result_and_checkpoint_authority_fail_before_any_action(self):
        runner, shared, _, _ = self.runner_fixture(initial=self.record("ready"))
        forged = {"plan_sha256": runner.plan["plan_sha256"], "verdict": "accepted",
                  "creates_authority": False, "creates_continuing_authority": False}
        with self.assertRaises(PermissionError):
            runner._validate_checkpoint_state(forged)
        forged = {"plan_sha256": runner.plan["plan_sha256"], "terminal": True,
                  "terminal_status": "succeeded", "campaign_record_sha256": "f" * 64,
                  "creates_authority": False, "creates_continuing_authority": False}
        with self.assertRaises(PermissionError):
            runner._validate_checkpoint_state(forged)
        malformed = {
            "plan_sha256": runner.plan["plan_sha256"],
            "provider_turns_consumed": "not-an-integer",
            "needs_tanner_reason": {"body": "x" * 100_000},
            "creates_authority": False,
            "creates_continuing_authority": False,
        }
        with self.assertRaises(PermissionError):
            runner._validate_checkpoint_state(malformed)
        display_only = {
            "plan_sha256": runner.plan["plan_sha256"],
            "provider_turns_consumed": self.limits()["provider_turns"] + 1,
            "creates_authority": False,
            "creates_continuing_authority": False,
        }
        runner._validate_checkpoint_state(display_only)
        self.assertEqual(sum(shared["counts"].values()), 0)
        runner.close()

    def test_canonical_campaign_rejects_neighboring_budget_before_effect(self):
        runner, shared, _, _ = self.runner_fixture(initial=self.record("ready"))
        shared["canonical_reject"] = "canonical budget binding changed"
        with self.assertRaisesRegex(PermissionError, "canonical budget"):
            runner.run_or_resume()
        self.assertEqual(shared["counts"]["advance"], 1)
        self.assertEqual((shared["counts"]["worker"], shared["counts"]["reviewer"],
                          shared["counts"]["application"], shared["counts"]["git"]),
                         (0, 0, 0, 0))
        runner.close()

    def test_neighboring_task_scope_or_campaign_lineage_fails_before_advance(self):
        for field, value in (
                ("objective_sha256", "f" * 64),
                ("allowed_scope", ["neighbor.py"]),
                ("rider_authorization_reference", "neighboring-rider-request")):
            with self.subTest(field=field):
                runner, shared, _, _ = self.runner_fixture(
                    initial=self.record("ready"), runtime_name="neighbor-" + field)
                shared["record"][field] = value
                shared["record"] = self.seal(shared["record"])
                with self.assertRaises(PermissionError):
                    runner.run_or_resume()
                self.assertEqual(shared["counts"]["advance"], 0)
                runner.close()

    def test_stale_runner_budget_counters_never_decide_canonical_eligibility(self):
        runner, shared, _, _ = self.runner_fixture(runtime_name="budget-authority")
        state = {"plan_sha256": runner.plan["plan_sha256"],
                 "provider_turns_consumed": 99, "cost_units_consumed": 99,
                 "correction_cycles_consumed": 99, "iterations_consumed": 99,
                 "creates_authority": False, "creates_continuing_authority": False}
        projected = runner._campaign(state)
        self.assertEqual(shared["counts"]["advance"], 1)
        self.assertEqual(projected["provider_turns_consumed"], 0)
        self.assertEqual(projected["cost_units_consumed"], 0)
        runner.close()

    def test_post_bind_repository_drift_is_rejected_by_canonical_owner(self):
        mutations = (
            (lambda: (self.repo / "existing-untracked.txt").write_text("one\n"),
             lambda: (self.repo / "existing-untracked.txt").write_text("two\n")),
            (lambda: (self.repo / "existing-mode.txt").write_text("mode\n"),
             lambda: os.chmod(self.repo / "existing-mode.txt", 0o755)),
            (lambda: ((self.repo / "target-a").write_text("a\n"),
                      (self.repo / "target-b").write_text("b\n"),
                      os.symlink("target-a", self.repo / "existing-link")),
             lambda: (os.unlink(self.repo / "existing-link"),
                      os.symlink("target-b", self.repo / "existing-link"))),
            (lambda: None,
             lambda: (self.repo / "base.txt").write_text("post-bind\n")),
        )
        for index, (before_plan, after_bind) in enumerate(mutations):
            with self.subTest(index=index):
                if index:
                    self.tearDown()
                    self.setUp()
                runner, shared, _, _ = self.runner_fixture(
                    runtime_name=f"post-bind-drift-{index}", before_plan=before_plan)
                state = {
                    "plan_sha256": runner.plan["plan_sha256"], "started_at": 100.0,
                    "creates_authority": False, "creates_continuing_authority": False,
                }
                state = runner._bind(state)
                after_bind()
                shared["canonical_reject"] = "canonical repository state drift"
                with self.assertRaisesRegex(PermissionError, "canonical repository"):
                    runner._campaign(state)
                self.assertEqual(shared["counts"]["advance"], 1)
                self.assertEqual((shared["counts"]["application"],
                                  shared["counts"]["git"]), (0, 0))
                runner.close()

    def test_post_bind_in_scope_drift_reaches_only_canonical_rejection(self):
        mutations = (
            lambda path: path.write_text("changed\n", encoding="utf-8"),
            lambda path: path.unlink(),
            lambda path: os.chmod(path, 0o755),
            lambda path: (path.unlink(), os.symlink("../base.txt", path)),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                if index:
                    self.tearDown()
                    self.setUp()
                target = self.repo / "src/example.py"
                target.parent.mkdir(parents=True)
                target.write_text("reviewed\n", encoding="utf-8")
                runner, shared, _, _ = self.runner_fixture(
                    runtime_name=f"in-scope-drift-{index}")
                state = runner._bind({
                    "plan_sha256": runner.plan["plan_sha256"],
                    "started_at": 100.0,
                    "creates_authority": False,
                    "creates_continuing_authority": False,
                })
                mutate(target)
                shared["canonical_reject"] = "canonical in-scope projection drift"
                with self.assertRaisesRegex(PermissionError, "canonical in-scope"):
                    runner._campaign(state)
                self.assertEqual(shared["counts"]["advance"], 1)
                self.assertEqual((shared["counts"]["application"],
                                  shared["counts"]["git"]), (0, 0))
                runner.close()

    def test_expired_application_checkpoint_closes_without_git_transition(self):
        genesis = self.record("ready")
        expires = datetime.now(timezone.utc) - timedelta(seconds=1)
        genesis["execution_budget_v01"]["expires_at"] = expires.isoformat()
        genesis["execution_budget_v01"]["created_at"] = (
            expires - timedelta(seconds=genesis["execution_budget_v01"][
                "maximum_duration_seconds"])).isoformat()
        genesis = self.seal_budget(genesis)
        initial = self.record("reviewed_application_completed")
        initial["execution_budget_v01"] = copy.deepcopy(
            genesis["execution_budget_v01"])
        initial = self.seal(initial)
        runner, shared, _, _ = self.runner_fixture(
            initial=initial, genesis=genesis, runtime_name="expired-before-git")
        result = runner.run_or_resume()
        self.assertEqual(result["terminal_status"], "failed_safe")
        self.assertEqual(result["needs_tanner_reason"], "campaign_duration_expired")
        self.assertEqual(shared["counts"]["advance"], 1)
        self.assertEqual(shared["counts"]["git"], 0)
        runner.close()

    def test_post_expiry_completed_commit_is_only_projected_not_reexecuted(self):
        genesis = self.record("ready")
        expires = datetime.now(timezone.utc) - timedelta(seconds=1)
        genesis["execution_budget_v01"]["expires_at"] = expires.isoformat()
        genesis["execution_budget_v01"]["created_at"] = (
            expires - timedelta(seconds=genesis["execution_budget_v01"][
                "maximum_duration_seconds"])).isoformat()
        genesis = self.seal_budget(genesis)
        initial = self.record("succeeded")
        initial["execution_budget_v01"] = copy.deepcopy(
            genesis["execution_budget_v01"])
        initial = self.seal(initial)
        runner, shared, _, _ = self.runner_fixture(
            initial=initial, genesis=genesis, runtime_name="expired-completed")
        result = runner.run_or_resume()
        self.assertEqual(result["terminal_status"], "succeeded")
        self.assertEqual(shared["counts"]["advance"], 0)
        self.assertEqual((shared["counts"]["application"],
                          shared["counts"]["git"]), (0, 0))
        runner.close()

    def test_fresh_checkpoint_cannot_reexecute_canonical_terminal_campaign(self):
        runner, shared, campaign_type, reviewer_type = self.runner_fixture(
            initial=self.record("succeeded"), runtime_name="terminal-first")
        result = runner.run_or_resume()
        self.assertEqual(result["terminal_status"], "succeeded")
        runner.close()
        reopened = self.reopen(
            shared, campaign_type, reviewer_type, runtime_name="terminal-fresh")
        again = reopened.run_or_resume()
        self.assertEqual(again["campaign_record_sha256"],
                         result["campaign_record_sha256"])
        self.assertEqual(shared["counts"]["advance"], 0)
        reopened.close()

    def test_missing_canonical_campaign_cannot_be_created_or_authorized_by_runner(self):
        genesis = self.record("ready")
        plan = self.plan(genesis)

        class MissingStore:
            def load(self, campaign_id):
                raise KeyError(campaign_id)

        class MissingCampaign:
            def __init__(self, *args, **kwargs):
                self.store = MissingStore()
                self.exchange = object()

        class Reviewer:
            def __init__(self, *args, **kwargs):
                pass

        with patch.object(RUNNER, "CodexDevelopmentCampaign", MissingCampaign), \
                patch.object(RUNNER, "WslCodexReviewAdapter", Reviewer):
            with self.assertRaisesRegex(PermissionError, "already-authorized"):
                RUNNER.BoundedLangGraphDevelopmentRunner(
                    repository=self.repo, runtime_root=self.root / "missing-campaign",
                    plan=plan, clock=lambda: 100.0)

    def test_repository_drift_never_becomes_runner_authority(self):
        mutations = (
            lambda: (self.repo / "base.txt").write_text("changed\n"),
            lambda: (self.repo / "neighbor.txt").write_text("new\n"),
            lambda: os.chmod(self.repo / "base.txt", 0o755),
            lambda: ((self.repo / "base.txt").write_text("staged\n"),
                     os.system(f"git -C {self.repo} add base.txt")),
            lambda: os.system(f"git -C {self.repo} checkout -qb neighbor"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                if index:
                    self.tearDown()
                    self.setUp()
                runner, shared, _, _ = self.runner_fixture(runtime_name=f"drift-{index}")
                mutate()
                state = {"plan_sha256": runner.plan["plan_sha256"], "started_at": 100.0,
                         "creates_authority": False, "creates_continuing_authority": False}
                bound = runner._bind(state)
                self.assertEqual(bound["stage"], "bound")
                shared["canonical_reject"] = "canonical repository state drift"
                with self.assertRaises(PermissionError):
                    runner._campaign(bound)
                self.assertEqual(shared["counts"]["advance"], 1)
                self.assertEqual((shared["counts"]["worker"],
                                  shared["counts"]["application"],
                                  shared["counts"]["git"]), (0, 0, 0))
                runner.close()

    def test_one_active_session_lock_and_external_checkpoint_location(self):
        runner, _, campaign_type, reviewer_type = self.runner_fixture()
        self.assertTrue((runner.runtime_root / "langgraph.sqlite").is_file())
        self.assertFalse((self.repo / "langgraph.sqlite").exists())
        with patch.object(RUNNER, "CodexDevelopmentCampaign", campaign_type), \
                patch.object(RUNNER, "WslCodexReviewAdapter", reviewer_type):
            with self.assertRaisesRegex(RuntimeError, "active session"):
                RUNNER.BoundedLangGraphDevelopmentRunner(
                    repository=self.repo, runtime_root=runner.runtime_root,
                    plan=runner.plan, clock=lambda: 100.0)
        runner.close()

    def test_progress_projection_is_body_free_and_canonical(self):
        runner, _, _, _ = self.runner_fixture(initial=self.record("failed_safe"))
        projection = runner.progress_projection()
        self.assertEqual(projection["canonical_campaign_status"], "failed_safe")
        self.assertNotIn("objective", projection)
        self.assertNotIn("prompt", projection)
        self.assertFalse(projection["creates_authority"])
        self.assertFalse(projection["creates_continuing_authority"])
        runner.close()


if __name__ == "__main__":
    unittest.main()

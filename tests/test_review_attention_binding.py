import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.runtime.codex_app_server import (
    CodexAppServerError,
    CodexAppServerTransport,
    PROTOCOL_VERSION,
    REVIEW_APPROVAL_BINDING_FIELDS,
    typed_approval,
)
from src.runtime.codex_development_campaign import CodexDevelopmentCampaign
from src.runtime.development_attention import DevelopmentAttentionStore, _digest
from src.runtime.wsl_codex_reviewer import _review_attention_binding


PARAMS = {
    "threadId": "thread-1",
    "turnId": "turn-1",
    "itemId": "item-1",
    "command": "printf ready",
    "cwd": "/synthetic/candidate",
    "reason": "bounded synthetic action",
    "availableDecisions": ["accept", "decline", "cancel"],
}


def review_worker(worker_id="reviewer-1"):
    return {"worker_id": worker_id, "role": "read_only_review",
            "environment_id": "synthetic-wsl"}


def review_binding(*, campaign_id="campaign-1", package_id="review-package-1",
                   snapshot_id="candidate-snapshot-1", invocation_id="review-invocation-1",
                   worker=None):
    worker = worker or review_worker()
    return {
        "approval_binding_kind": "independent_review_provider",
        "campaign_id": campaign_id,
        "review_package_id": package_id,
        "review_package_record_sha256": "1" * 64,
        "candidate_snapshot_id": snapshot_id,
        "candidate_record_sha256": "2" * 64,
        "mutation_digest_sha256": "3" * 64,
        "exact_change_evidence_sha256": "4" * 64,
        "authorized_scope_sha256": "5" * 64,
        "reviewer_worker_id": worker["worker_id"],
        "reviewer_identity_sha256": _digest(worker),
        "reviewer_invocation_id": invocation_id,
    }


def review_protocol(**changes):
    core = review_binding()
    core.update({key: value for key, value in changes.items() if key in core})
    protocol = {
        **core,
        "approval_binding_sha256": _digest(core),
        "method": "item/commandExecution/requestApproval",
        "process_id": 4242,
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "item-1",
        "blocked_action_sha256": "6" * 64,
        "approved_action_sha256": "7" * 64,
        "recipient_sha256": core["reviewer_identity_sha256"],
        "rider_id": "tanner",
        "version": PROTOCOL_VERSION,
    }
    return protocol


class ReviewAttentionBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.consumer_identities = {4242: "boot-and-start-4242"}
        self.store = DevelopmentAttentionStore(
            Path(self.temporary.name),
            consumer_probe=lambda pid: self.consumer_identities.get(pid),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def create_review(self, *, invocation_id="review-invocation-1",
                      protocol=None, expires_in_seconds=60):
        worker = review_worker()
        protocol = protocol or review_protocol(reviewer_invocation_id=invocation_id)
        return self.store.create(
            campaign_id="campaign-1",
            invocation_id=invocation_id,
            worker=worker,
            kind="native_codex_approval_required",
            blocked_action="bounded synthetic action",
            why_required="exact review action requires Tanner",
            requested_authority="one exact review action",
            protocol_binding=protocol,
            expires_in_seconds=expires_in_seconds,
            expiration_reason="the exact review action becomes stale",
            expiration_effect="no provider action occurs",
            can_request_again=True,
            work_lost=False,
        )

    def test_wsl_binding_is_derived_from_exact_retained_package_and_invocation(self):
        worker = review_worker()
        snapshot = {"candidate_snapshot_id": "candidate-snapshot-1",
                    "record_sha256": "2" * 64}
        retention = {
            "candidate_snapshot": snapshot,
            "mutation_manifest_sha256": "3" * 64,
            "exact_change_evidence_sha256": "4" * 64,
            "allowed_scope_sha256": "5" * 64,
        }
        retention["record_sha256"] = _digest(retention)
        package = {
            "package_id": "review-package-1",
            "record_sha256": "1" * 64,
            "included_sections": [
                {"section_id": "candidate-snapshot",
                 "content": json.dumps(snapshot)},
                {"section_id": "candidate-retention-receipt",
                 "content": json.dumps(retention)},
            ],
        }
        authority = {
            "candidate_record_sha256": snapshot["record_sha256"],
            "mutation_manifest_sha256": retention["mutation_manifest_sha256"],
            "exact_change_evidence_sha256": retention["exact_change_evidence_sha256"],
            "allowed_scope_sha256": retention["allowed_scope_sha256"],
            "candidate_retention_receipt_sha256": retention["record_sha256"],
        }
        binding = _review_attention_binding(
            package=package,
            transport_authority=authority,
            campaign_id="campaign-1",
            candidate_snapshot_id=snapshot["candidate_snapshot_id"],
            reviewer=worker,
            reviewer_invocation_id="review-invocation-1",
        )
        self.assertEqual(set(binding), set(REVIEW_APPROVAL_BINDING_FIELDS))
        self.assertEqual(binding["reviewer_invocation_id"], "review-invocation-1")
        self.assertEqual(binding["exact_change_evidence_sha256"], "4" * 64)
        for key in authority:
            with self.subTest(swapped=key):
                invalid = dict(authority)
                invalid[key] = "f" * 64
                with self.assertRaises(PermissionError):
                    _review_attention_binding(
                        package=package, transport_authority=invalid,
                        campaign_id="campaign-1",
                        candidate_snapshot_id="candidate-snapshot-1",
                        reviewer=worker,
                        reviewer_invocation_id="review-invocation-1")

    def test_app_server_rejects_every_missing_or_changed_review_identity_before_launch(self):
        worker = review_worker()
        binding = review_binding(worker=worker)
        for key in sorted(binding):
            with self.subTest(missing=key):
                invalid = dict(binding)
                invalid.pop(key)
                with self.assertRaises(CodexAppServerError):
                    typed_approval(
                        "item/commandExecution/requestApproval", PARAMS,
                        campaign_id="campaign-1", invocation_id="review-invocation-1",
                        worker=worker, process_id=42, approval_binding=invalid)
            with self.subTest(changed=key):
                invalid = dict(binding)
                invalid[key] = ("f" * 64 if key.endswith("sha256") else "neighbor")
                if key in {"approval_binding_kind", "campaign_id", "reviewer_worker_id",
                           "reviewer_identity_sha256", "reviewer_invocation_id"}:
                    with self.assertRaises(CodexAppServerError):
                        typed_approval(
                            "item/commandExecution/requestApproval", PARAMS,
                            campaign_id="campaign-1", invocation_id="review-invocation-1",
                            worker=worker, process_id=42, approval_binding=invalid)
                else:
                    # The app-server layer carries opaque canonical lineage. Its
                    # canonical producer and campaign consumer independently
                    # validate these exact values; this transport must not
                    # reinterpret them.
                    mapped = typed_approval(
                        "item/commandExecution/requestApproval", PARAMS,
                        campaign_id="campaign-1", invocation_id="review-invocation-1",
                        worker=worker, process_id=42, approval_binding=invalid)
                    self.assertEqual(mapped["protocol"][key], invalid[key])

        launched = []
        invalid = dict(binding)
        invalid.pop("reviewer_invocation_id")
        transport = CodexAppServerTransport(popen=lambda *_args, **_kwargs: launched.append(True))
        with self.assertRaises(CodexAppServerError):
            transport.run(
                cwd=self.temporary.name, prompt="body-free synthetic review",
                output_schema={"type": "object"},
                output_path=Path(self.temporary.name) / "last.json",
                sandbox="read-only", campaign_id="campaign-1",
                invocation_id="review-invocation-1", worker=worker,
                environment={}, approval_binding=invalid)
        self.assertEqual(launched, [])

    def test_transport_carries_exact_binding_to_attention_handler(self):
        frames = [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "thread-1"}}},
            {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            {"id": 90, "method": "item/commandExecution/requestApproval", "params": PARAMS},
            {"method": "item/completed", "params": {"item": {
                "id": "agent-1", "type": "agentMessage", "text": "{\"ok\":true}"}}},
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
        ]

        class Process:
            pid = 77
            returncode = None

            def __init__(self):
                self.stdin = io.StringIO()
                self.stdout = io.StringIO("".join(json.dumps(value) + "\n" for value in frames))
                self.stderr = io.StringIO()

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            def kill(self):
                self.returncode = -9

        class Transport(CodexAppServerTransport):
            def qualify(self, environment):
                return {"protocol_version": PROTOCOL_VERSION, "cli_version": "test",
                        "typed_approval_methods": [], "request_schema_sha256": {}}

        worker = review_worker()
        binding = review_binding(worker=worker)
        observed = []
        Transport(popen=lambda *_args, **_kwargs: Process()).run(
            cwd=self.temporary.name, prompt="test", output_schema={"type": "object"},
            output_path=Path(self.temporary.name) / "last.json",
            sandbox="workspace-write", campaign_id="campaign-1",
            invocation_id="review-invocation-1", worker=worker,
            environment={}, approval_binding=binding,
            approval_handler=lambda approval, **_kwargs: (
                observed.append(approval) or {"choice": "deny"}),
        )
        self.assertEqual(len(observed), 1)
        for key, value in binding.items():
            self.assertEqual(observed[0]["protocol"][key], value)

    def test_browser_must_return_complete_canonical_review_tuple(self):
        event = self.create_review()
        canonical = self.store._authority_binding(event)
        self.assertEqual(canonical["reviewer_invocation_id"], event["invocation_id"])
        self.assertEqual(canonical["decision_nonce"], event["decision_nonce"])
        self.assertEqual(canonical["exact_change_evidence_sha256"], "4" * 64)

        old_reduced_fields = (
            "attention_id", "campaign_id", "invocation_id", "rider_id",
            "recipient_sha256", "candidate_snapshot_id", "candidate_record_sha256",
            "mutation_digest_sha256", "authorized_scope_sha256", "method", "item_id",
            "action_digest", "protocol_binding_sha256", "expires_at",
        )
        reduced = {key: canonical[key] for key in old_reduced_fields}
        with self.assertRaises(PermissionError):
            self.store.decide(event["attention_id"], "deny", authenticated_rider=True,
                              expected_identity=reduced)
        self.assertEqual(self.store.get(event["attention_id"])["state"], "needs_tanner")

    def test_missing_changed_neighboring_and_cross_invocation_identities_fail_closed(self):
        required = (
            "attention_id", "campaign_id", "invocation_id", "rider_id",
            "recipient_sha256", "approval_binding_kind", "approval_binding_sha256",
            "review_package_id", "review_package_record_sha256", "reviewer_worker_id",
            "reviewer_identity_sha256", "reviewer_invocation_id",
            "candidate_snapshot_id", "candidate_record_sha256",
            "mutation_digest_sha256", "exact_change_evidence_sha256",
            "authorized_scope_sha256", "method", "item_id", "action_digest",
            "protocol_binding_sha256", "expires_at", "decision_nonce",
        )
        for index, key in enumerate(required):
            with self.subTest(missing=key):
                event = self.create_review(invocation_id=f"missing-{index}")
                identity = self.store._authority_binding(event)
                identity.pop(key)
                with self.assertRaises(PermissionError):
                    self.store.decide(event["attention_id"], "deny",
                        authenticated_rider=True, expected_identity=identity)
                self.assertEqual(self.store.get(event["attention_id"])["state"], "needs_tanner")
            with self.subTest(changed=key):
                event = self.create_review(invocation_id=f"changed-{index}")
                identity = self.store._authority_binding(event)
                identity[key] = "f" * 64 if key.endswith("sha256") else "neighbor"
                with self.assertRaises(PermissionError):
                    self.store.decide(event["attention_id"], "approve_once",
                        authenticated_rider=True, expected_identity=identity)
                self.assertEqual(self.store.get(event["attention_id"])["state"], "needs_tanner")

        first = self.create_review(invocation_id="cross-invocation-a")
        second = self.create_review(invocation_id="cross-invocation-b")
        with self.assertRaises(PermissionError):
            self.store.decide(first["attention_id"], "approve_once",
                authenticated_rider=True,
                expected_identity=self.store._authority_binding(second))

    def test_bound_deny_and_approve_once_have_exact_single_terminal_semantics(self):
        denied = self.create_review(invocation_id="review-deny")
        denied_result = self.store.decide(
            denied["attention_id"], "deny", authenticated_rider=True,
            expected_identity=self.store._authority_binding(denied))
        self.assertFalse(denied_result["decision"]["creates_authority"])
        self.assertFalse(denied_result["decision"]["creates_continuing_authority"])
        self.assertEqual(denied_result["decision"]["authority_binding"],
                         self.store._authority_binding(denied))
        with self.assertRaises(RuntimeError):
            self.store.decide(denied["attention_id"], "deny", authenticated_rider=True,
                              expected_identity=self.store._authority_binding(denied))

        approved = self.create_review(invocation_id="review-approve")
        approved_result = self.store.decide(
            approved["attention_id"], "approve_once", authenticated_rider=True,
            expected_identity=self.store._authority_binding(approved))
        decision = approved_result["decision"]
        self.assertFalse(decision["creates_authority"])
        self.assertFalse(decision["creates_continuing_authority"])
        self.assertEqual(decision["campaign_publication"]["state"], "pending")
        with self.assertRaises(PermissionError):
            self.store.consume_approve_once(
                decision["decision_id"], attention_id=approved["attention_id"],
                invocation_id=approved["invocation_id"],
                expected_binding=self.store._authority_binding(approved))
        decision = self.store.publish_review_decision(
            decision["decision_id"], attention_id=approved["attention_id"],
            campaign_id=approved["campaign_id"],
            campaign_record_sha256="a" * 64, campaign_state_revision=2)
        self.assertTrue(decision["creates_authority"])
        consumed = self.store.consume_approve_once(
            decision["decision_id"], attention_id=approved["attention_id"],
            invocation_id=approved["invocation_id"],
            expected_binding=self.store._authority_binding(approved))
        self.assertFalse(consumed["creates_authority"])
        self.assertFalse(consumed["creates_continuing_authority"])
        with self.assertRaises(PermissionError):
            self.store.consume_approve_once(
                decision["decision_id"], attention_id=approved["attention_id"],
                invocation_id=approved["invocation_id"])

    def test_expiry_restart_and_concurrent_decisions_fail_closed(self):
        pending = self.create_review(invocation_id="review-pending")
        restarted = DevelopmentAttentionStore(
            Path(self.temporary.name),
            consumer_probe=lambda pid: self.consumer_identities.get(pid))
        self.assertEqual(restarted.get(pending["attention_id"])["state"], "needs_tanner")

        expired = self.create_review(invocation_id="review-expired", expires_in_seconds=1)
        later = datetime.now(timezone.utc) + timedelta(seconds=2)
        restarted.refresh_expiration(expired["attention_id"], now=later)
        with self.assertRaises(RuntimeError):
            restarted.decide(expired["attention_id"], "approve_once",
                authenticated_rider=True,
                expected_identity=self.store._authority_binding(expired))

        event = self.create_review(invocation_id="review-concurrent")
        identity = self.store._authority_binding(event)
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(
                self.store.decide, event["attention_id"], choice,
                authenticated_rider=True, expected_identity=identity)
                for choice in ("approve_once", "deny")]
        terminal = []
        for attempt in attempts:
            try:
                terminal.append(attempt.result()["decision"])
            except RuntimeError:
                pass
        self.assertEqual(len(terminal), 1)
        self.assertFalse(terminal[0]["creates_continuing_authority"])

    def test_campaign_validates_exact_package_candidate_reviewer_and_invocation(self):
        worker = review_worker()
        package = {"package_id": "review-package-1", "record_sha256": "1" * 64,
                   "recipient": {"worker_id": worker["worker_id"],
                                 "role": worker["role"]}}

        class Exchange:
            def _load(self, kind, identity):
                if kind != "packages" or identity != package["package_id"]:
                    raise FileNotFoundError(identity)
                return package

        campaign = object.__new__(CodexDevelopmentCampaign)
        campaign.exchange = Exchange()
        record = {
            "campaign_id": "campaign-1", "status": "awaiting_independent_review",
            "iteration": 1,
            "review_requests": [{"iteration": 1, "package_id": "review-package-1"}],
            "builder_runs": [{"candidate_retention_receipt": {
                "candidate_snapshot": {"candidate_snapshot_id": "candidate-snapshot-1",
                                       "record_sha256": "2" * 64},
                "mutation_manifest_sha256": "3" * 64,
                "exact_change_evidence_sha256": "4" * 64,
                "allowed_scope_sha256": "5" * 64,
            }}],
        }
        core = review_binding(worker=worker)
        protocol = {**core, "recipient_sha256": core["reviewer_identity_sha256"],
                    "approval_binding_sha256": _digest(core)}
        self.assertEqual(
            campaign._validated_review_attention_binding(
                record, protocol, worker, "review-invocation-1"),
            protocol,
        )
        for key in sorted(core):
            with self.subTest(key=key):
                invalid = dict(protocol)
                invalid[key] = "f" * 64 if key.endswith("sha256") else "neighbor"
                with self.assertRaises(PermissionError):
                    campaign._validated_review_attention_binding(
                        record, invalid, worker, "review-invocation-1")

    def test_attention_evidence_is_body_free_and_decision_carries_terminal_digest(self):
        event = self.create_review(invocation_id="review-body-free")
        result = self.store.decide(
            event["attention_id"], "deny", authenticated_rider=True,
            expected_identity=self.store._authority_binding(event))
        serialized = json.dumps({"event": event, "decision": result["decision"]},
                                sort_keys=True).lower()
        for forbidden in ("prompt_body", "source_body", "credential", "api_key",
                          "model_response", "provider_response"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(result["decision"]["record_sha256"], _digest({
            key: value for key, value in result["decision"].items()
            if key != "record_sha256"}))


if __name__ == "__main__":
    unittest.main()

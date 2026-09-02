import json
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from src.runtime.development_attention import (
    ATTENTION_BASE_URL_ENV, REMOTE_AUTHENTICATED_ENV,
    DevelopmentAttentionStore, canonical_attention_detail_url,
    native_approval_from_jsonl, sanitize_action,
)
from src.runtime.component_supervision import ComponentReceiptStore
from scripts.fawkes_attention_events import project


class DevelopmentAttentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = DevelopmentAttentionStore(Path(self.temporary.name))
        self.worker = {"worker_id": "codex-repository-wsl-fawkes", "role": "software_repository"}

    def tearDown(self):
        self.temporary.cleanup()

    def create(self):
        return self.store.create(campaign_id="synthetic-attention-campaign",
            invocation_id="synthetic-worker-1", worker=self.worker,
            kind="native_codex_approval_required", blocked_action="touch harmless.txt",
            why_required="workspace write requires exact approval",
            requested_authority="write harmless.txt once", resources=["harmless.txt"],
            reversible=True, provider_code="tool.approval_required")

    def test_event_is_durable_deduplicated_and_zero_authority(self):
        first = self.create(); second = self.create()
        self.assertEqual(first["attention_id"], second["attention_id"])
        self.assertEqual(len(self.store.list()), 1)
        self.assertFalse(first["creates_authority"])
        self.assertEqual(first["state"], "needs_tanner")
        self.assertIsNone(first["expires_at"])
        self.assertEqual(first["urgency"], "normal")
        self.assertIn("section=attention&attention=" + first["attention_id"], first["detail_url"])

    def test_attention_detail_url_enforces_local_and_authenticated_remote_origins(self):
        attention_id = "attention-" + "a" * 64
        self.assertEqual(canonical_attention_detail_url(attention_id),
            "http://localhost:8787/?view=developer&section=attention&attention=" + attention_id)
        with self.assertRaisesRegex(ValueError, "requires HTTPS"):
            canonical_attention_detail_url(attention_id, environment={
                ATTENTION_BASE_URL_ENV: "http://fawkes.example"})
        with self.assertRaisesRegex(ValueError, "authenticated boundary"):
            canonical_attention_detail_url(attention_id, environment={
                ATTENTION_BASE_URL_ENV: "https://fawkes.example"})
        remote = canonical_attention_detail_url(attention_id, environment={
            ATTENTION_BASE_URL_ENV: "https://fawkes.example",
            REMOTE_AUTHENTICATED_ENV: "true"})
        self.assertEqual(remote,
            "https://fawkes.example/?view=developer&section=attention&attention=" + attention_id)
        credential_bearing_origin = "https://" + ":".join(("user", "placeholder")) + "@fawkes.example"
        with self.assertRaisesRegex(ValueError, "must not contain credentials"):
            canonical_attention_detail_url(attention_id, environment={
                ATTENTION_BASE_URL_ENV: credential_bearing_origin,
                REMOTE_AUTHENTICATED_ENV: "true"})

    def test_approve_once_is_bound_and_consumable_once(self):
        event = self.create()
        result = self.store.decide(event["attention_id"], "approve_once", authenticated_rider=True)
        decision = result["decision"]
        self.assertTrue(decision["one_time"])
        self.assertFalse(decision["creates_continuing_authority"])
        consumed = self.store.consume_approve_once(decision["decision_id"],
            attention_id=event["attention_id"], invocation_id="synthetic-worker-1")
        self.assertTrue(consumed["consumed"])
        self.assertEqual(consumed["lifecycle_state"], "consumed")
        lifecycle = self.store.lifecycle(event["attention_id"])
        self.assertEqual(lifecycle["event"]["approval_outcome"], "consumed")
        with self.assertRaises(PermissionError):
            self.store.consume_approve_once(decision["decision_id"],
                attention_id=event["attention_id"], invocation_id="synthetic-worker-1")

    def test_complete_decision_identity_tuple_rejects_cross_request_binding(self):
        event = self.store.create(campaign_id="campaign-a", invocation_id="invocation-a",
            worker=self.worker, kind="native_codex_approval_required",
            blocked_action="run exact noop", why_required="typed approval",
            requested_authority="one exact action", protocol_binding={
                "method": "item/commandExecution/requestApproval", "item_id": "item-a",
                "approved_action_sha256": "a" * 64})
        binding = event["protocol_binding"]
        identity = {"attention_id": event["attention_id"], "campaign_id": "campaign-a",
            "invocation_id": "invocation-a", "method": binding["method"],
            "item_id": binding["item_id"], "action_digest": binding["approved_action_sha256"],
            "protocol_binding_sha256": event["protocol_binding_sha256"]}
        with self.assertRaisesRegex(PermissionError, "identity tuple"):
            self.store.decide(event["attention_id"], "approve_once", authenticated_rider=True,
                              expected_identity={**identity, "campaign_id": "campaign-b"})
        self.assertEqual(self.store.get(event["attention_id"])["state"], "needs_tanner")
        accepted = self.store.decide(event["attention_id"], "approve_once",
                                     authenticated_rider=True, expected_identity=identity)
        self.assertEqual(accepted["decision"]["campaign_id"], "campaign-a")
        self.assertFalse(accepted["decision"]["creates_continuing_authority"])

    def test_v10_shaped_pending_event_projects_structured_qualification_choice(self):
        event = self.store.create(campaign_id="gate1-native-attention-20260902-v10-deny",
            invocation_id="gate1-native-attention-20260902-v10-deny-builder-1-appserver",
            worker=self.worker, kind="native_codex_approval_required",
            blocked_action="powershell.exe -NoProfile -NonInteractive -Command exit 0",
            why_required="Test B — DENY: exact harmless qualification action",
            requested_authority="one exact no-op", protocol_binding={
                "method": "item/commandExecution/requestApproval", "item_id": "item-v10-b",
                "approved_action_sha256": "b" * 64})
        annotated = self.store.set_qualification_instruction(event["attention_id"],
            campaign_id=event["campaign_id"], invocation_id=event["invocation_id"],
            choice="deny", label="Test B",
            expected_action_digest=event["protocol_binding"]["approved_action_sha256"])
        projected = self.store.lifecycle(event["attention_id"])["event"]
        self.assertEqual(projected["qualification_instruction"], {
            "choice": "deny", "label": "Test B", "creates_authority": False})
        self.assertEqual(projected["attention_id"], event["attention_id"])
        self.assertEqual(projected["protocol_binding_sha256"], event["protocol_binding_sha256"])
        self.assertEqual(annotated["state"], "needs_tanner")
        self.assertIsNone(annotated["decision_id"])

    def test_qualification_annotation_fails_closed_on_identity_or_action_mismatch(self):
        event = self.create()
        with self.assertRaisesRegex(PermissionError, "identity/state mismatch"):
            self.store.set_qualification_instruction(event["attention_id"],
                campaign_id=event["campaign_id"], invocation_id=event["invocation_id"],
                choice="deny", label="Test B", expected_action_digest="wrong")
        self.assertIsNone(self.store.get(event["attention_id"])["qualification_instruction"])

    def test_concurrent_paired_decisions_remain_isolated_in_reversed_order(self):
        events = {}
        identities = {}
        for suffix in ("a", "b"):
            event = self.store.create(campaign_id="campaign-" + suffix,
                invocation_id="invocation-" + suffix, worker=self.worker,
                kind="native_codex_approval_required", blocked_action="noop-" + suffix,
                why_required="paired qualification", requested_authority="one exact action",
                protocol_binding={"method": "item/commandExecution/requestApproval",
                    "item_id": "item-" + suffix, "approved_action_sha256": suffix * 64})
            binding = event["protocol_binding"]
            events[suffix] = event
            identities[suffix] = {"attention_id": event["attention_id"],
                "campaign_id": event["campaign_id"], "invocation_id": event["invocation_id"],
                "method": binding["method"], "item_id": binding["item_id"],
                "action_digest": binding["approved_action_sha256"],
                "protocol_binding_sha256": event["protocol_binding_sha256"]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            denied = pool.submit(self.store.decide, events["b"]["attention_id"], "deny",
                authenticated_rider=True, expected_identity=identities["b"])
            approved = pool.submit(self.store.decide, events["a"]["attention_id"], "approve_once",
                authenticated_rider=True, expected_identity=identities["a"])
        self.assertEqual(denied.result()["decision"]["choice"], "deny")
        decision_a = approved.result()["decision"]
        self.assertEqual(decision_a["choice"], "approve_once")
        consumed = self.store.consume_approve_once(decision_a["decision_id"],
            attention_id=events["a"]["attention_id"], invocation_id="invocation-a",
            protocol_binding_sha256=events["a"]["protocol_binding_sha256"],
            approved_action_sha256="a" * 64)
        self.assertTrue(consumed["consumed"])
        self.assertFalse(denied.result()["decision"]["consumed"])
        with self.assertRaises(PermissionError):
            self.store.consume_approve_once(decision_a["decision_id"],
                attention_id=events["b"]["attention_id"], invocation_id="invocation-b")

    def test_detached_unreconstructable_action_rejects_misleading_approval(self):
        event = self.store.create(campaign_id="synthetic-attention-campaign-2",
            invocation_id="synthetic-reviewer-1", worker=self.worker,
            kind="native_codex_approval_required", blocked_action="change candidate",
            why_required="write requested", requested_authority="one file change",
            protocol_binding={"method": "item/fileChange/requestApproval"})
        detached = self.store.mark_process_detached(event["attention_id"])
        self.assertEqual(detached["consumer_state"], "unavailable")
        with self.assertRaisesRegex(RuntimeError, "no longer live or durably resumable"):
            self.store.decide(event["attention_id"], "approve_once", authenticated_rider=True)
        self.assertEqual(self.store.get(event["attention_id"])["state"], "needs_tanner")

    def test_detached_exact_command_remains_boundedly_resumable(self):
        event = self.store.create(campaign_id="synthetic-attention-campaign-3",
            invocation_id="synthetic-worker-3", worker=self.worker,
            kind="native_codex_approval_required", blocked_action="echo harmless",
            why_required="protected boundary", requested_authority="one command",
            protocol_binding={"method": "item/commandExecution/requestApproval"},
            expires_in_seconds=3600, expiration_reason="candidate staleness",
            expiration_effect="request fails closed", can_request_again=True, work_lost=False)
        detached = self.store.mark_process_detached(event["attention_id"])
        self.assertEqual(detached["consumer_state"], "durably_resumable")
        result = self.store.decide(event["attention_id"], "approve_once", authenticated_rider=True)
        self.assertEqual(result["decision"]["lifecycle_state"], "recorded_pending_consumption")

    def test_expiration_requires_justification_and_silence_never_approves(self):
        with self.assertRaisesRegex(ValueError, "complete justification"):
            self.store.create(campaign_id="expiring", invocation_id="invocation",
                worker=self.worker, kind="native_codex_approval_required",
                blocked_action="noop", why_required="boundary",
                requested_authority="once", expires_in_seconds=60)
        event = self.store.create(campaign_id="expiring-valid", invocation_id="invocation",
            worker=self.worker, kind="native_codex_approval_required",
            blocked_action="noop", why_required="boundary", requested_authority="once",
            expires_in_seconds=60, expiration_reason="exact action staleness",
            expiration_effect="action remains unperformed", can_request_again=True,
            work_lost=False)
        self.assertEqual(event["urgency"], "urgent_expiring")
        self.assertEqual(event["approval_outcome"], "awaiting_decision")
        self.assertFalse(event["creates_authority"])
        expired = self.store.refresh_expiration(event["attention_id"],
            now=datetime.fromisoformat(event["expires_at"]) + timedelta(seconds=1))
        self.assertEqual(expired["state"], "expired")
        self.assertFalse(expired["creates_authority"])
        with self.assertRaisesRegex(RuntimeError, "no longer awaiting"):
            self.store.decide(event["attention_id"], "approve_once", authenticated_rider=True)
        replacement = self.store.create(campaign_id="expiring-valid",
            invocation_id="invocation-new", worker=self.worker,
            kind="native_codex_approval_required", blocked_action="noop",
            why_required="boundary", requested_authority="once", expires_in_seconds=60,
            expiration_reason="exact action staleness",
            expiration_effect="action remains unperformed", can_request_again=True,
            work_lost=False)
        self.assertNotEqual(replacement["attention_id"], event["attention_id"])

    def test_live_action_completion_is_visible_and_execute_at_most_once(self):
        event = self.create()
        decision = self.store.decide(event["attention_id"], "approve_once",
                                     authenticated_rider=True)["decision"]
        self.store.consume_approve_once(decision["decision_id"], attention_id=event["attention_id"],
                                        invocation_id="synthetic-worker-1")
        completed = self.store.finish_live_action(decision["decision_id"], status="completed")
        self.assertEqual(completed["lifecycle_state"], "completed")
        self.assertEqual(self.store.lifecycle(event["attention_id"])["event"]["approval_outcome"],
                         "completed")
        self.assertEqual(self.store.finish_live_action(decision["decision_id"], status="completed"),
                         completed)

    def test_deny_and_cancel_are_exact_choices(self):
        event = self.create()
        result = self.store.decide(event["attention_id"], "deny", authenticated_rider=True)
        self.assertEqual(result["event"]["state"], "deny")
        with self.assertRaises(RuntimeError):
            self.store.decide(event["attention_id"], "cancel_campaign", authenticated_rider=True)

    def test_unknown_or_unauthenticated_decision_fails_closed(self):
        event = self.create()
        with self.assertRaises(PermissionError):
            self.store.decide(event["attention_id"], "approve_once", authenticated_rider=False)
        with self.assertRaises(ValueError):
            self.store.decide(event["attention_id"], "approve_forever", authenticated_rider=True)

    def test_typed_codex_event_is_detected_but_agent_prose_is_not(self):
        typed = json.dumps({"type": "tool.approval_required", "item": {
            "command": "touch harmless.txt", "reason": "write protected", "permission": "workspace_write",
            "resources": ["harmless.txt"], "reversible": True}})
        value = native_approval_from_jsonl(typed)
        self.assertEqual(value["provider_code"], "tool.approval_required")
        self.assertIsNone(native_approval_from_jsonl(json.dumps({"type": "item.completed",
            "item": {"type": "agent_message", "text": "approval required"}})))

    def test_secrets_and_endpoints_are_redacted(self):
        safe = sanitize_action("token=abc https://example.invalid/private password=hunter2")
        self.assertNotIn("abc", safe); self.assertNotIn("hunter2", safe)
        self.assertNotIn("example.invalid", safe)

    def test_windows_projection_deduplicates_logical_attention_and_sanitizes_receipts(self):
        event = self.create()
        receipt_store = ComponentReceiptStore(Path(self.temporary.name) / "receipts")
        receipt, _ = receipt_store.failure(component="worker", stage="launch",
            category="provider_failure", process_exit_code=17, provider_code="E_PROVIDER",
            service_state="failed")
        projected = project(root=Path(self.temporary.name), attention_store=self.store,
                            receipt_store=receipt_store)
        self.assertEqual(len([item for item in projected if item["kind"] == "needs_tanner"]), 1)
        failure = next(item for item in projected if item["kind"] == "component_failed")
        self.assertIn("exit=17", failure["safe_message"])
        self.assertIn("provider=E_PROVIDER", failure["safe_message"])
        self.assertNotIn("blocked_action", failure["safe_message"])

    def test_typed_attention_suppresses_duplicate_component_popup_only(self):
        self.create()
        receipt_store = ComponentReceiptStore(Path(self.temporary.name) / "receipts")
        receipt_store.failure(component="development_coordinator",
            stage="tanner_attention_required", category="native_codex_approval_required",
            service_state="needs_tanner")
        projected = project(root=Path(self.temporary.name), attention_store=self.store,
                            receipt_store=receipt_store)
        self.assertEqual([item["kind"] for item in projected], ["needs_tanner"])

    def test_windows_pending_probe_excludes_resolved_attention(self):
        event = self.create()
        self.assertTrue(any(item["source_id"] == event["attention_id"]
                            for item in project(attention_store=self.store,
                                              receipt_store=ComponentReceiptStore(
                                                  Path(self.temporary.name) / "empty-receipts"))))
        self.store.decide(event["attention_id"], "deny", authenticated_rider=True)
        self.assertFalse(any(item["source_id"] == event["attention_id"]
                             for item in project(attention_store=self.store,
                                               receipt_store=ComponentReceiptStore(
                                                   Path(self.temporary.name) / "empty-receipts"))))

    def test_process_detachment_and_interface_reopen_preserve_one_pending_event(self):
        event = self.create()
        with self.assertRaises(TimeoutError):
            self.store.wait_for_decision(event["attention_id"], timeout_seconds=0.02,
                                         process_alive=lambda: False)
        reopened = DevelopmentAttentionStore(Path(self.temporary.name))
        retained = reopened.get(event["attention_id"])
        self.assertEqual(retained["state"], "needs_tanner")
        self.assertEqual(retained["process_state"], "detached")
        self.assertEqual([item["attention_id"] for item in reopened.list(pending_only=True)],
                         [event["attention_id"]])


if __name__ == "__main__":
    unittest.main()
    def test_synthetic_qualification_cancellation_records_no_rider_decision_or_authority(self):
        event = self._event()
        cancelled = self.store.cancel_unresolved_qualification(
            event["attention_id"], authorization_reference="tanner-cancelled-incomplete-test")
        self.assertEqual(cancelled["state"], "cancelled_qualification")
        self.assertEqual(cancelled["approval_outcome"], "cancelled_without_decision")
        self.assertIsNone(cancelled["decision_id"])
        self.assertFalse(cancelled["creates_authority"])
        self.assertFalse(self.store.decisions.exists())

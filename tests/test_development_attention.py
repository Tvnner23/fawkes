import json
import subprocess
import tempfile
import unittest
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
        with self.assertRaises(PermissionError):
            self.store.consume_approve_once(decision["decision_id"],
                attention_id=event["attention_id"], invocation_id="synthetic-worker-1")

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

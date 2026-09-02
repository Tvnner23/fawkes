import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from src.runtime.codex_app_server import (
    CodexAppServerError, PROTOCOL_VERSION, approval_response, typed_approval,
)
from src.runtime.development_attention import DevelopmentAttentionStore


PARAMS = {"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1",
          "command": "touch harmless.txt", "cwd": "/tmp/candidate",
          "reason": "write test artifact", "availableDecisions": ["accept", "decline", "cancel"]}


class CodexAppServerProtocolTests(unittest.TestCase):
    def test_exact_typed_mapping_and_decisions(self):
        item = typed_approval("item/commandExecution/requestApproval", PARAMS,
            campaign_id="campaign-1", invocation_id="invocation-1",
            worker={"worker_id": "worker-1", "role": "software_repository"}, process_id=42)
        self.assertEqual(item["protocol"]["version"], PROTOCOL_VERSION)
        self.assertEqual(approval_response("item/commandExecution/requestApproval", "approve_once", PARAMS),
                         {"decision": "accept"})
        self.assertEqual(approval_response("item/commandExecution/requestApproval", "deny", PARAMS),
                         {"decision": "decline"})
        self.assertEqual(approval_response("item/commandExecution/requestApproval", "cancel_campaign", PARAMS),
                         {"decision": "cancel"})

    def test_permissions_never_become_broad_authority(self):
        with self.assertRaisesRegex(CodexAppServerError, "one action"):
            approval_response("item/permissions/requestApproval", "approve_once", PARAMS)

    def test_legacy_approval_uses_exact_conversation_and_call_lineage(self):
        params = {"conversationId": "thread-1", "callId": "call-1",
                  "command": ["echo", "safe"], "cwd": "/tmp", "parsedCmd": []}
        item = typed_approval("execCommandApproval", params, campaign_id="campaign-1",
            invocation_id="invocation-1", worker={"worker_id": "worker-1"}, process_id=42,
            active_thread_id="thread-1", active_turn_id="turn-1")
        self.assertEqual(item["protocol"]["thread_id"], "thread-1")
        self.assertEqual(item["protocol"]["turn_id"], "turn-1")
        self.assertEqual(item["protocol"]["item_id"], "call-1")
        self.assertEqual(approval_response("execCommandApproval", "approve_once", params),
                         {"decision": "approved"})

    def test_unknown_or_unbound_request_fails_closed(self):
        with self.assertRaises(CodexAppServerError):
            typed_approval("made/up", PARAMS, campaign_id="campaign-1",
                invocation_id="invocation-1", worker={"worker_id": "worker-1"}, process_id=42)
        with self.assertRaisesRegex(CodexAppServerError, "lineage"):
            typed_approval("item/fileChange/requestApproval", {"itemId": "i"},
                campaign_id="campaign-1", invocation_id="invocation-1",
                worker={"worker_id": "worker-1"}, process_id=42)

    def test_wait_and_one_time_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DevelopmentAttentionStore(Path(directory))
            event = store.create(campaign_id="campaign-1", invocation_id="invocation-1",
                worker={"worker_id": "worker-1", "role": "builder"}, kind="native_codex_approval_required",
                blocked_action="touch harmless.txt", why_required="test",
                requested_authority="one command", protocol_binding={"thread_id": "thread-1",
                    "turn_id": "turn-1", "item_id": "item-1"})
            result = {}
            waiter = threading.Thread(target=lambda: result.update(store.wait_for_decision(
                event["attention_id"], timeout_seconds=3)))
            waiter.start(); time.sleep(.05)
            decided = store.decide(event["attention_id"], "approve_once", authenticated_rider=True)
            waiter.join(1)
            self.assertEqual(result["decision"]["decision_id"], decided["decision"]["decision_id"])
            self.assertEqual(result["decision"]["protocol_binding_sha256"],
                             event["protocol_binding_sha256"])
            store.consume_approve_once(decided["decision"]["decision_id"],
                attention_id=event["attention_id"], invocation_id="invocation-1")
            with self.assertRaises(PermissionError):
                store.consume_approve_once(decided["decision"]["decision_id"],
                    attention_id=event["attention_id"], invocation_id="invocation-1")


if __name__ == "__main__":
    unittest.main()

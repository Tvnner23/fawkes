import unittest
import base64
import json
import tempfile
from io import BytesIO
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.app.server import BrowserSessionStore, FawkesAppHandler, SESSION_COOKIE, bind_requires_token, default_bind_host
from src.runtime.chat_service import ChatServiceError, FawkesChatService
from src.memory.correction import CorrectionAssessment


class FawkesChatServiceTests(unittest.TestCase):
    def _service(self):
        runtime = Mock()
        runtime.model = "test-model"
        runtime.respond.return_value = {
            "text": "Still me.",
            "presentation": {"schema_version": 1, "text": "Still me.", "blocks": [], "citations": []},
            "memories": [{"memory_id": "memory-1"}],
            "archive_passages": [{"source_archive_id": "archive-old"}],
            "library_passages": [{"source_id": "library-1", "segment_id": "segment-1"}],
            "conversation_context": [{"message_id": "message-old"}],
        }
        phoenix = {"instance_id": "fawkes-1", "name": "Fawkes"}
        receipt_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(receipt_tmp.cleanup)
        with patch("src.runtime.chat_service.ensure_archive_index"):
            service = FawkesChatService(phoenix=phoenix, runtime=runtime,
                                        provider_receipt_dir=receipt_tmp.name)
        return service, runtime

    @patch("src.runtime.chat_service.record_live_flight")
    @patch("src.runtime.chat_service.save_context_receipt")
    @patch("src.runtime.chat_service.update_work_item")
    @patch("src.runtime.chat_service.discover_candidate")
    @patch("src.runtime.chat_service.persist_live_message")
    @patch("src.runtime.chat_service.get_latest_conversation")
    def test_app_turn_uses_existing_runtime_archive_ledger_and_receipt(
        self, latest, persist, discover, update, receipt, flight
    ):
        service, runtime = self._service()
        latest.return_value = {
            "conversation_id": "conversation-1",
            "instance_id": "fawkes-1",
            "title": "Fawkes Chat",
        }
        persist.side_effect = [
            {"archive_id": "archive-user", "created_at": "now"},
            {"archive_id": "archive-assistant", "created_at": "later"},
        ]
        discover.return_value = {"work_item_id": "work-1"}
        receipt.return_value = {"receipt_id": "message-receipt", "retrieval_audit": {
            "context_composition": {"allocation": {"selected_evidence_ids": []}}}}

        result = service.send("hello", conversation_id="conversation-1")

        self.assertEqual(result["message"]["content"], "Still me.")
        self.assertEqual(result["user_message_created_at"], "now")
        self.assertEqual(result["message"]["created_at"], "later")
        self.assertEqual(persist.call_count, 2)
        self.assertEqual(persist.call_args_list[0].kwargs["source"], "fawkes_app")
        self.assertEqual(persist.call_args_list[1].kwargs["role"], "assistant")
        runtime.respond.assert_called_once()
        self.assertEqual(runtime.respond.call_args.kwargs["instance_id"] if "instance_id" in runtime.respond.call_args.kwargs else "fawkes-1", "fawkes-1")
        update.assert_called_once_with("work-1", status="queued")
        self.assertEqual(receipt.call_args.kwargs["memories"][0]["memory_id"], "memory-1")
        self.assertEqual(receipt.call_args.kwargs["library_sources"][0]["segment_id"], "segment-1")
        self.assertEqual(flight.call_args.kwargs["request_text"], "hello")
        self.assertEqual(flight.call_args.kwargs["context_receipt_id"], "message-receipt")
        self.assertGreaterEqual(flight.call_args.kwargs["elapsed_ms"], 0)
        self.assertNotIn("memories", result)
        self.assertNotIn("archive_passages", result)
        self.assertEqual(result["message"]["presentation"]["schema_version"], 1)
        self.assertTrue(result["message"]["context_inspector_available"])

    @patch("src.runtime.chat_service.record_live_flight")
    @patch("src.runtime.chat_service.save_context_receipt")
    @patch("src.runtime.chat_service.update_work_item")
    @patch("src.runtime.chat_service.discover_candidate")
    @patch("src.runtime.chat_service.persist_live_message")
    @patch("src.runtime.chat_service.get_latest_conversation")
    def test_discord_source_preserves_exact_inbound_and_outbound_archive_turns(
        self, latest, persist, discover, update, receipt, flight
    ):
        service, runtime = self._service()
        latest.return_value = {"conversation_id": "conversation-1", "instance_id": "fawkes-1"}
        persist.side_effect = [
            {"archive_id": "archive-user", "created_at": "now"},
            {"archive_id": "archive-assistant", "created_at": "later"},
        ]
        discover.return_value = {"work_item_id": "work-1"}
        receipt.return_value = {"receipt_id": "receipt-1", "retrieval_audit": {
            "context_composition": {"allocation": {"selected_evidence_ids": []}}}}
        service.send("Exact Discord words", source="discord_dm")
        self.assertEqual(persist.call_args_list[0].kwargs["text"], "Exact Discord words")
        self.assertEqual(persist.call_args_list[0].kwargs["source"], "discord_dm")
        self.assertEqual(persist.call_args_list[1].kwargs["text"], "Still me.")
        self.assertEqual(persist.call_args_list[1].kwargs["source"], "discord_dm")

    @patch("src.runtime.chat_service.load_flight")
    @patch("src.runtime.chat_service.load_context_receipt")
    def test_context_inspector_requires_owned_receipt_and_matching_replay(self, receipt, flight):
        service, _ = self._service()
        with self.assertRaisesRegex(ChatServiceError, "invalid"):
            service.context_inspector("../foreign")
        receipt.return_value = {"receipt_id": "response-1", "response_message_id": "response-1",
            "instance_id": "fawkes-1", "retrieval_audit": {"context_composition": {
                "package_id": "package-1", "allocation": {"selected_evidence_ids": [],
                    "omitted_evidence_ids": []}, "source_summary": []}}}
        flight.return_value = {"instance_id": "fawkes-1", "response_message_id": "response-1",
                               "context_receipt_id": "response-1", "flight_id": "response-1",
                               "evidence_sha256": "digest"}
        value = service.context_inspector("response-1")
        self.assertEqual(value["composition_status"], "zero_retrieval")
        self.assertFalse(value["authority"]["creates_authority"])
        receipt.return_value["instance_id"] = "foreign"
        with self.assertRaisesRegex(ChatServiceError, "does not belong"):
            service.context_inspector("response-1")

    @patch("src.runtime.chat_service.record_context_retrieval_feedback")
    @patch.object(FawkesChatService, "context_inspector")
    def test_context_feedback_revalidates_exact_inspector_linkage_and_creates_no_authority(self, inspector, record):
        service, _ = self._service()
        inspector.return_value = {"response_message_id": "response-1", "context_receipt_id": "response-1",
            "package_id": "package-1", "allocation": {"decision_sha256": "allocation-1"},
            "transmission": {"manifest_id": "permit-1"}, "replay": {"flight_id": "response-1"}}
        record.return_value = {"feedback_id": "feedback-1", "authority": {"creates_authority": False}}
        payload = {"feedback_type": "context_helped", "context_receipt_id": "response-1",
            "package_id": "package-1", "allocation_decision_sha256": "allocation-1",
            "transmission_manifest_id": "permit-1", "replay_flight_id": "response-1"}
        result = service.context_feedback("response-1", payload)
        self.assertFalse(result["authority"]["creates_authority"])
        self.assertEqual(record.call_args.kwargs["rider_principal_id"], "authenticated-rider:fawkes-1")
        with self.assertRaisesRegex(ChatServiceError, "does not match"):
            service.context_feedback("response-1", {**payload, "package_id": "stale-package"})
        self.assertEqual(record.call_count, 1)
        inspector.return_value["allocation"] = {}
        with self.assertRaisesRegex(ChatServiceError, "complete recorded"):
            service.context_feedback("response-1", payload)

    @patch("src.runtime.chat_service.load_context_receipt")
    @patch("src.runtime.chat_service.build_archive_context")
    @patch("src.runtime.chat_service.get_latest_conversation")
    def test_restart_continuity_reads_latest_canonical_archive(self, latest, context, receipt):
        service, _ = self._service()
        latest.return_value = {
            "conversation_id": "persisted-conversation",
            "instance_id": "fawkes-1",
            "title": "Fawkes Chat",
        }
        context.return_value = (
            {"message_id": "m1", "role": "user", "content": "Earlier", "created_at": "2026-08-30T12:00:00+00:00"},
            {"message_id": "m2", "role": "assistant", "content": "I remember.", "created_at": "2026-08-30T12:01:00+00:00"},
        )
        receipt.side_effect = lambda message_id: (
            {"presentation": {"schema_version": 1, "text": "I remember.", "blocks": [], "citations": []}}
            if message_id == "m2" else None
        )

        restarted_service, _ = self._service()
        history = restarted_service.history()

        self.assertEqual(history["conversation"]["conversation_id"], "persisted-conversation")
        self.assertEqual([m["content"] for m in history["messages"]], ["Earlier", "I remember."])
        self.assertEqual(history["messages"][1]["presentation"]["schema_version"], 1)
        self.assertEqual(history["messages"][0]["created_at"], "2026-08-30T12:00:00+00:00")
        context.assert_called_once_with("persisted-conversation", max_messages=100)

    @patch("src.runtime.chat_service.create_development_observation")
    def test_observation_api_preserves_distinct_rider_development_dimensions(self, create):
        service, _ = self._service()
        create.return_value = {"observation_id": "observation-1"}

        service.create_observation({
            "category": "observed_response_pattern",
            "interpretation": "The response substantially paraphrased the rider.",
            "observed_pattern": "Conversational mirroring/paraphrasing",
            "rider_evaluation": "undesired",
            "rider_reason": "It felt robotic.",
            "development_signal": "discourage",
            "longitudinal_status": "isolated",
            "confidence_state": "tentative",
            "uncertainty": "One interaction.",
            "conversation_id": "conversation-1",
            "message_ids": ["user-1", "assistant-1"],
        })

        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["category"], "observed_response_pattern")
        self.assertEqual(kwargs["rider_evaluation"], "undesired")
        self.assertEqual(kwargs["development_signal"], "discourage")
        self.assertEqual(kwargs["longitudinal_status"], "isolated")
        self.assertNotIn("phoenix_interpretation", kwargs)
        self.assertNotIn("proposed_change", kwargs)

    def test_research_uses_server_resolved_phoenix_scope(self):
        capability = Mock()
        capability.run.return_value = {"research": {"research_id": "r1"}}
        service, _ = self._service()
        service._research_capability = capability

        result = service.research({
            "query": "What changed today?",
            "instance_id": "attempted-sibling-injection",
            "conversation_id": "conversation-1",
        })

        self.assertEqual(result["research"]["research_id"], "r1")
        self.assertEqual(capability.run.call_args.kwargs["instance_id"], "fawkes-1")
        self.assertNotEqual(
            capability.run.call_args.kwargs["instance_id"],
            "attempted-sibling-injection",
        )

    @patch("src.runtime.chat_service.record_provider_transmission")
    @patch("src.runtime.chat_service.save_context_receipt")
    @patch("src.runtime.chat_service.update_work_item")
    @patch("src.runtime.chat_service.discover_candidate")
    @patch("src.runtime.chat_service.persist_live_message")
    @patch("src.runtime.chat_service.get_latest_conversation")
    def test_temporary_media_crosses_chat_boundary_with_instance_artifact_and_receipt(
        self, latest, persist, discover, update, context_receipt, transmission_receipt
    ):
        service, runtime = self._service()
        latest.return_value = {"conversation_id": "c1", "instance_id": "fawkes-1", "title": "Chat"}
        persist.side_effect = [{"archive_id": "a1", "created_at": "now"},
                               {"archive_id": "a2", "created_at": "later"}]
        discover.return_value = {"work_item_id": "w1"}
        transmission_receipt.return_value = {"transmission_id": "tx-1"}
        png = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()

        result = service.send("Look at this", conversation_id="c1", attachments=[{
            "name": "screen.png", "mime_type": "image/png", "data": png,
            "privacy": "potentially_private",
        }])

        sent = runtime.respond.call_args.kwargs["media_attachments"][0]
        self.assertEqual(sent["artifact"]["instance_id"], "fawkes-1")
        self.assertEqual(sent["artifact"]["lifecycle"]["state"], "validated_temporary")
        self.assertFalse(sent["artifact"]["retention"]["automatic_library_retention"])
        media_statuses = [call.kwargs["status"] for call in transmission_receipt.call_args_list
                          if call.kwargs["capability_id"] == "media.chat_analyze"]
        chat_statuses = [call.kwargs["status"] for call in transmission_receipt.call_args_list
                         if call.kwargs["capability_id"] == "chat.respond"]
        self.assertEqual(media_statuses, ["authorized", "completed"])
        self.assertEqual(chat_statuses, ["authorized", "completed"])
        self.assertEqual(result["media"][0]["artifact"]["instance_id"], "fawkes-1")

    def test_capability_discovery_is_runtime_derived_and_provider_neutral(self):
        service, runtime = self._service()
        runtime.capability_context.return_value = [{
            "name": "presentation.visualize", "features": ["pie", "timeline"],
            "availability": "available",
        }]
        result = service.capabilities()
        self.assertEqual(result["capabilities"][0]["name"], "presentation.visualize")
        self.assertEqual(result["presentation"]["envelope_versions"], [1, 2])
        self.assertNotIn("provider", result["capabilities"][0])

    @patch("src.runtime.chat_service.update_work_item")
    @patch("src.runtime.chat_service.discover_candidate")
    @patch("src.runtime.chat_service.persist_live_message")
    @patch("src.runtime.chat_service.get_latest_conversation")
    def test_provider_error_is_clean_and_user_message_remains_archived(
        self, latest, persist, discover, update
    ):
        service, runtime = self._service()
        latest.return_value = {"conversation_id": "c1", "instance_id": "fawkes-1", "title": "Chat"}
        persist.return_value = {"archive_id": "a1", "created_at": "now"}
        discover.return_value = {"work_item_id": "w1"}
        runtime.respond.side_effect = RuntimeError("secret traceback detail")

        with self.assertRaises(ChatServiceError) as caught:
            service.send("keep this", conversation_id="c1")

        self.assertEqual(caught.exception.code, "provider_unavailable")
        self.assertNotIn("secret", str(caught.exception))
        persist.assert_called_once()
        update.assert_called_once_with("w1", status="queued")

    @patch("src.runtime.chat_service.create_development_observation")
    @patch("src.runtime.chat_service.save_context_receipt")
    @patch("src.runtime.chat_service.update_work_item")
    @patch("src.runtime.chat_service.discover_candidate")
    @patch("src.runtime.chat_service.persist_live_message")
    @patch("src.runtime.chat_service.get_latest_conversation")
    def test_recognized_correction_becomes_observation_not_personality_control(
        self, latest, persist, discover, update, receipt, create_observation
    ):
        service, runtime = self._service()
        latest.return_value = {"conversation_id": "c1", "instance_id": "fawkes-1", "title": "Chat"}
        persist.side_effect = [
            {"archive_id": "archive-user", "created_at": "now"},
            {"archive_id": "archive-answer", "created_at": "later"},
        ]
        discover.return_value = {"work_item_id": "w1"}
        runtime.respond.return_value.update(
            correction=CorrectionAssessment(is_correction=True, confidence=0.9),
            conversation_context=(
                {"message_id": "prior-answer", "role": "assistant", "content": "Incorrect answer"},
            ),
        )
        create_observation.return_value = {"observation_id": "observation-1"}

        result = service.send("That's wrong.", conversation_id="c1")

        self.assertEqual(result["message"]["content"], "Still me.")
        self.assertEqual(create_observation.call_args.kwargs["category"], "correction_signal")
        self.assertEqual(
            create_observation.call_args.kwargs["message_ids"][0], "prior-answer"
        )
        self.assertEqual(
            create_observation.call_args.kwargs["observed_by"],
            "runtime_correction_evaluator",
        )
        self.assertNotIn("proposed_change", create_observation.call_args.kwargs)
        self.assertIn("observation-1", receipt.call_args.kwargs["development_sources"])


class FawkesAppHTTPTests(unittest.TestCase):
    def _handler(self, authorization=None):
        handler = object.__new__(FawkesAppHandler)
        handler.server = SimpleNamespace(app_token="correct-token", app_session_store=Mock())
        handler.server.app_session_store.valid.return_value = False
        handler.headers = Message()
        if authorization:
            handler.headers["Authorization"] = authorization
        return handler

    def test_api_requires_authentication(self):
        self.assertFalse(self._handler()._authorized())
        self.assertFalse(self._handler("Bearer wrong-token")._authorized())
        self.assertTrue(self._handler("Bearer correct-token")._authorized())

    def test_revocable_httponly_session_authenticates_without_browser_stored_credential(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            handler = self._handler(); handler.server.app_session_store = BrowserSessionStore(directory)
            session = handler.server.app_session_store.create()
            handler.headers["Cookie"] = f"{SESSION_COOKIE}={session}"
            self.assertTrue(handler._authorized())
            self.assertTrue(handler.server.app_session_store.revoke(session))
            self.assertFalse(handler._authorized())
            self.assertFalse(BrowserSessionStore(directory).valid(session))
            handler.headers.replace_header("Cookie", f"{SESSION_COOKIE}=wrong")
            self.assertFalse(handler._authorized())

    def test_attention_decision_requires_session_bound_csrf_not_bearer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            handler = self._handler("Bearer correct-token")
            handler.server.app_session_store = BrowserSessionStore(directory)
            session, csrf = handler.server.app_session_store.create_bound()
            handler.headers["Cookie"] = f"{SESSION_COOKIE}={session}"
            handler.headers["X-Fawkes-CSRF-Token"] = csrf
            self.assertTrue(handler._require_attention_decision_auth())
            handler.headers.replace_header("X-Fawkes-CSRF-Token", "wrong")
            handler._json = Mock()
            self.assertFalse(handler._require_attention_decision_auth())
            handler._json.assert_called_once()
            handler.headers.replace_header("Cookie", f"{SESSION_COOKIE}=wrong")
            handler.headers.replace_header("X-Fawkes-CSRF-Token", csrf)
            self.assertFalse(handler._require_attention_decision_auth())

    def test_failed_attention_decision_returns_exact_canonical_lifecycle(self):
        handler = self._handler()
        handler.path = ("/api/development/codex-campaigns/campaign-a/attention/"
                        "attention-a/decision")
        handler._require_attention_decision_auth = Mock(return_value=True)
        handler.server.chat_service = Mock()
        handler.server.chat_service.decide_development_attention.side_effect = RuntimeError(
            "attention request is stale")
        handler.server.chat_service.development_attention_event.return_value = {
            "attention": {"attention_id": "attention-a", "campaign_id": "campaign-a",
                          "state": "expired", "decision_id": None,
                          "creates_authority": False,
                          "creates_continuing_authority": False},
            "decision": None, "creates_authority": False,
        }
        body = json.dumps({"choice": "approve_once", "identity": {
            "attention_id": "attention-a"}}).encode()
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = BytesIO(body)
        handler._json = Mock()

        handler.do_POST()

        status, payload = handler._json.call_args.args
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], {
            "code": "invalid_attention_decision",
            "message": "attention request is stale",
        })
        self.assertEqual(payload["attention"]["attention_id"], "attention-a")
        self.assertEqual(payload["attention"]["state"], "expired")
        self.assertIsNone(payload["decision"])
        self.assertFalse(payload["creates_authority"])
        self.assertFalse(payload["creates_continuing_authority"])

    def test_failed_attention_decision_never_projects_neighboring_lifecycle(self):
        handler = self._handler()
        handler.server.chat_service = Mock()
        handler.server.chat_service.development_attention_event.return_value = {
            "attention": {"attention_id": "attention-neighbor"}, "decision": None}
        handler._json = Mock()

        handler._attention_decision_failure(
            409, "attention_consumer_unavailable", "consumer unavailable", "attention-a")

        payload = handler._json.call_args.args[1]
        self.assertNotIn("attention", payload)
        self.assertNotIn("decision", payload)
        self.assertFalse(payload["creates_authority"])
        self.assertFalse(payload["creates_continuing_authority"])

    def test_post_logout_requires_csrf_and_durably_invalidates_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrowserSessionStore(directory)
            session, csrf = store.create_bound()
            handler = self._handler()
            handler.server.app_session_store = store
            handler.path = "/api/session/logout"
            handler.headers["Cookie"] = f"{SESSION_COOKIE}={session}"
            handler._json = Mock()
            handler.do_POST()
            handler._json.assert_called_once_with(403, unittest.mock.ANY)
            self.assertTrue(store.valid(session))

            handler.headers["X-Fawkes-CSRF-Token"] = csrf
            handler.send_response = Mock(); handler.send_header = Mock(); handler.end_headers = Mock()
            handler.wfile = BytesIO()
            handler.do_POST()
            handler.send_response.assert_called_once_with(200)
            self.assertFalse(store.valid(session))
            self.assertFalse(BrowserSessionStore(directory).valid(session))
            self.assertIn(b'"authenticated_rider": null', handler.wfile.getvalue())

    @patch("src.runtime.development_attention.DevelopmentAttentionStore.lifecycle")
    def test_exact_attention_api_shape_matches_decision_client(self, lifecycle):
        lifecycle.return_value = {"event": {"attention_id": "attention-test"}, "decision": None}
        service = object.__new__(FawkesChatService)
        result = service.development_attention_event("attention-test")
        self.assertEqual(result["attention"]["attention_id"], "attention-test")
        self.assertIsNone(result["decision"])
        self.assertNotIn("event", result)

    @patch("src.runtime.development_attention.DevelopmentAttentionStore.projection")
    def test_console_attention_projection_uses_side_effect_free_store_entrypoint(self, projection):
        projection.return_value = [{"attention_id": "attention-console",
                                    "actionable": False}]
        service = object.__new__(FawkesChatService)
        result = service.development_attention_projection(pending_only=True)
        projection.assert_called_once_with(pending_only=True)
        self.assertEqual(result["attention"][0]["attention_id"], "attention-console")
        self.assertFalse(result["creates_authority"])
        self.assertFalse(result["creates_continuing_authority"])

    def test_no_token_configuration_is_local_open_mode(self):
        handler = self._handler()
        handler.server.app_token = ""
        self.assertTrue(handler._authorized())

    def test_phone_bind_defaults_only_when_token_is_configured(self):
        self.assertEqual(default_bind_host(app_token=""), "127.0.0.1")
        self.assertEqual(default_bind_host(app_token="secret"), "0.0.0.0")
        self.assertTrue(bind_requires_token("0.0.0.0"))
        self.assertFalse(bind_requires_token("127.0.0.1"))


if __name__ == "__main__":
    unittest.main()

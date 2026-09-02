import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import bootstrap_fawkes_discord_dm, run_fawkes_discord_bot

from src.runtime.discord_bot import (
    DiscordBotConfiguration, DiscordBotConfigurationError, DiscordBotHttpClient,
    DiscordBotTransportError, DiscordConversationBridge,
    DiscordConversationProcessingError, DiscordGatewayRunner, DiscordIdentityError,
    DiscordOutboundAuthorization, DiscordOutboundBridge, DiscordReplyDeliveryError,
    TANNER_DM_BOOTSTRAP_MESSAGE, DiscordMessageCursorStore, bootstrap_tanner_dm,
)
from src.runtime.discord_webhook import DiscordWebhookConfiguration, DiscordWebhookSender
from src.runtime.chat import FawkesChatRuntime
from src.runtime.chat_service import FawkesChatService
from src.runtime.evidence_eligibility import POLICY_VERSION as ELIGIBILITY_POLICY_VERSION


TOKEN = "private-bot-token"
TANNER = "100000000000000001"
EMILY = "100000000000000002"


class Response:
    def __init__(self, payload=None, status=200):
        self.payload = payload or {}
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *arguments): return False
    def read(self): return json.dumps(self.payload).encode()


class Api:
    def __init__(self): self.requests = []
    def __call__(self, outbound, timeout):
        self.requests.append(outbound)
        if outbound.full_url.endswith("/users/@me/channels"):
            return Response({"id": "200000000000000001"})
        return Response({"id": "300000000000000001"})


class DiscordBotTests(unittest.TestCase):
    def configuration(self, **changes):
        values = dict(bot_token=TOKEN, tanner_user_id=TANNER,
                      emily_user_id=EMILY, emily_opted_in=False)
        values.update(changes)
        return DiscordBotConfiguration(**values)

    def test_tanner_inbound_dm_reaches_normal_chat_and_replies(self):
        chat = Mock()
        chat.send.return_value = {"message": {"content": "Hello from Fawkes."}}
        http = Mock()
        http.send_dm.return_value = {"provider": "discord_bot", "message_id": "3",
                                     "creates_authority": False}
        bridge = DiscordConversationBridge(self.configuration(), chat_service=chat, http_client=http)
        result = bridge.handle_dispatch({"op": 0, "t": "MESSAGE_CREATE", "d": {
            "id": "1", "channel_id": "2", "content": "Exact Tanner words",
            "author": {"id": TANNER, "bot": False}}})
        chat.send.assert_called_once_with("Exact Tanner words", source="discord_dm")
        http.send_dm.assert_called_once_with(TANNER, "Hello from Fawkes.")
        self.assertEqual(result["archive_source"], "discord_dm")
        self.assertFalse(result["development_authority"])

    def test_tanner_outbound_dm_uses_explicit_identity_and_disables_mentions(self):
        api = Api()
        receipt = DiscordBotHttpClient(self.configuration(), opener=api).send_dm(TANNER, "Safe reply")
        message = json.loads(api.requests[1].data)
        self.assertEqual(message["allowed_mentions"], {"parse": []})
        self.assertEqual(receipt["recipient_identity"], "tanner")
        self.assertFalse(receipt["creates_authority"])

    def test_bootstrap_resolves_only_configured_tanner_identity(self):
        client = Mock()
        client.send_dm.return_value = {
            "recipient_identity": "tanner", "creates_authority": False,
        }
        result = bootstrap_tanner_dm(self.configuration(), client)
        client.send_dm.assert_called_once_with(TANNER, TANNER_DM_BOOTSTRAP_MESSAGE)
        self.assertEqual(result["recipient_identity"], "tanner")
        self.assertFalse(result["creates_authority"])

    def test_bootstrap_command_rejects_arbitrary_recipient_argument(self):
        with self.assertRaises(SystemExit):
            bootstrap_fawkes_discord_dm.main(["999999999999999999"])

    @patch("scripts.run_fawkes_discord_bot.DiscordGatewayRunner")
    @patch("scripts.run_fawkes_discord_bot.DiscordConversationBridge")
    @patch("scripts.run_fawkes_discord_bot.FawkesChatService")
    @patch("scripts.run_fawkes_discord_bot.DiscordBotHttpClient")
    @patch("scripts.run_fawkes_discord_bot.DiscordBotConfiguration.from_environment")
    def test_normal_gateway_startup_does_not_send_bootstrap(
        self, from_environment, client_type, _chat_type, _bridge_type, runner_type,
    ):
        configuration = self.configuration()
        client = client_type.return_value
        from_environment.return_value = configuration
        with patch("scripts.run_fawkes_discord_bot.write_status"):
            run_fawkes_discord_bot.main()
        client.send_dm.assert_not_called()
        runner_type.return_value.run.assert_called_once_with()

    def test_gateway_ready_callback_is_the_authenticated_running_boundary(self):
        socket = Mock()
        socket.recv_data.side_effect = [
            (1, json.dumps({"op": 10, "d": {"heartbeat_interval": 45_000}})),
            (1, json.dumps({"op": 0, "t": "READY", "s": 1, "d": {}})),
        ]
        ready = Mock()
        runner = None

        def mark_ready():
            ready()
            runner.stop()

        runner = DiscordGatewayRunner(
            self.configuration(), Mock(),
            http_client=Mock(gateway_url=Mock(return_value="wss://gateway.example")),
            websocket_factory=Mock(return_value=socket), on_ready=mark_ready,
        )
        runner.run()
        ready.assert_called_once_with()

    def test_single_message_failure_is_reported_and_listener_accepts_later_message(self):
        socket = Mock()
        socket.recv_data.side_effect = [
            (1, json.dumps({"op": 10, "d": {"heartbeat_interval": 45_000}})),
            (1, json.dumps({"op": 0, "t": "READY", "s": 1, "d": {}})),
            (1, json.dumps({"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": {}})),
            (1, json.dumps({"op": 0, "t": "MESSAGE_CREATE", "s": 3, "d": {}})),
        ]
        bridge = Mock()
        failures = []
        runner = None
        original = Mock()
        original.side_effect = [DiscordConversationProcessingError("failed turn"),
                                {"status": "replied"}]

        def handle(event):
            try:
                return original(event)
            finally:
                if original.call_count == 2:
                    runner.stop()

        bridge.handle_dispatch.side_effect = handle
        runner = DiscordGatewayRunner(
            self.configuration(), bridge,
            http_client=Mock(gateway_url=Mock(return_value="wss://gateway.example")),
            websocket_factory=Mock(return_value=socket),
            on_message_failure=failures.append,
        )
        runner.run()
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], DiscordConversationProcessingError)
        self.assertEqual(original.call_count, 2)

    def test_gateway_local_failure_retains_stage_and_safe_type_without_secrets(self):
        runner = DiscordGatewayRunner(
            self.configuration(), Mock(),
            http_client=Mock(gateway_url=Mock(return_value="wss://gateway.example")),
            websocket_factory=Mock(side_effect=RuntimeError(
                f"socket failed {TOKEN} at https://credential-bearing.example/path?secret=yes"
            )),
        )
        with self.assertRaisesRegex(
            DiscordBotTransportError, r"stage=connect: RuntimeError: socket failed <redacted>"
        ) as caught:
            runner.run()
        rendered = str(caught.exception)
        self.assertNotIn(TOKEN, rendered)
        self.assertNotIn("credential-bearing", rendered)

    def test_chat_processing_and_reply_delivery_failures_are_distinct(self):
        config = self.configuration()
        failed_chat = Mock()
        failed_chat.send.side_effect = RuntimeError("provider unavailable")
        bridge = DiscordConversationBridge(config, chat_service=failed_chat, http_client=Mock())
        event = {"t": "MESSAGE_CREATE", "d": {
            "id": "1", "content": "hello", "author": {"id": TANNER, "bot": False},
        }}
        with self.assertRaisesRegex(
            DiscordConversationProcessingError, "ChatService failed.*RuntimeError"
        ):
            bridge.handle_dispatch(event)

        chat = Mock()
        chat.send.return_value = {"message": {"content": "reply"}}
        http = Mock()
        http.send_dm.side_effect = DiscordBotTransportError("status=403, code=50007")
        bridge = DiscordConversationBridge(config, chat_service=chat, http_client=http)
        with self.assertRaisesRegex(
            DiscordReplyDeliveryError, r"reply delivery failed.*status=403, code=50007"
        ):
            bridge.handle_dispatch(event)

    @patch("src.runtime.chat_service.record_live_flight")
    @patch("src.runtime.chat_service.save_context_receipt")
    @patch("src.runtime.chat_service.update_work_item")
    @patch("src.runtime.chat_service.discover_candidate")
    @patch("src.runtime.chat_service.persist_live_message")
    @patch("src.runtime.chat_service.get_latest_conversation")
    def test_real_discord_chat_boundary_preserves_interleaved_exact_evidence_order(
        self, latest, persist, discover, _update, receipt, _flight,
    ):
        route = {"provider_policy_id": "private-chat-policy",
                 "provider_class": "openai-compatible", "model": "test-model",
                 "route_version": "1"}

        def evidence(evidence_id, domain, body):
            return {"instance_id": "fawkes-1",
                    "owner_principal_id": "authenticated-rider:fawkes-1",
                    "evidence_id": evidence_id, "domain": domain,
                    "authority_class": f"{domain}_evidence", "text": body,
                    "content": body, "original_evidence_reference": {"id": evidence_id},
                    "adapter_version": f"{domain}-test-v1",
                    "eligibility": {"instance_id": "fawkes-1",
                        "policy_version": ELIGIBILITY_POLICY_VERSION,
                        "privacy_classification": "potentially_private",
                        "selected_for_context": True,
                        "provider_transmission": {"allowed": True,
                            "reason": "authorized", "provider_route": route}}}

        selected = [
            evidence("archive-1", "native_archive", "archive evidence"),
            evidence("memory-1", "memory", "memory evidence"),
            evidence("library-1", "library", "library evidence"),
        ]

        def builder(**_kwargs):
            return {"selected_evidence": selected,
                    "policy_version": "unified-retrieval-foundation-v1",
                    "evidence_eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
                    "adapter_versions": {"native_archive": "native_archive-test-v1",
                                         "memory": "memory-test-v1",
                                         "library": "library-test-v1"},
                    "candidates": selected, "exclusions": [],
                    "allocation": {"total_budget": 10_000}, "conversation": (),
                    "continuity": {"attempted": False, "status": "not_requested"},
                    "warnings": []}

        class Response:
            output_text = "private Discord path confirmed"
            usage = None

        class Responses:
            def create(self, **_kwargs):
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            runtime = FawkesChatRuntime(
                client=type("Client", (), {"responses": Responses()})(),
                model="test-model", instance_id="fawkes-1", research_enabled=False,
                retrieval_path="planner", planner_context_builder=builder,
                evidence_transmission_root=directory,
            )
            with patch("src.runtime.chat_service.ensure_archive_index"):
                service = FawkesChatService(
                    phoenix={"instance_id": "fawkes-1", "name": "Fawkes"},
                    runtime=runtime, provider_receipt_dir=directory,
                )
            latest.return_value = {"conversation_id": "conversation-1",
                                   "instance_id": "fawkes-1"}
            persist.side_effect = [
                {"archive_id": "archive-user", "created_at": "2026-09-01T00:00:00+00:00"},
                {"archive_id": "archive-assistant", "created_at": "2026-09-01T00:00:01+00:00"},
            ]
            discover.return_value = {"work_item_id": "work-1"}
            receipt.return_value = {"receipt_id": "receipt-1", "retrieval_audit": {
                "context_composition": {"allocation": {
                    "selected_evidence_ids": [item["evidence_id"] for item in selected]}}}}
            http = Mock()
            http.send_dm.return_value = {"provider": "discord_bot", "message_id": "3",
                                         "recipient_identity": "tanner",
                                         "creates_authority": False}
            result = DiscordConversationBridge(
                self.configuration(), chat_service=service, http_client=http,
            ).handle_dispatch({"t": "MESSAGE_CREATE", "d": {
                "id": "live-tanner-test", "content": "hello fawkes its tanner",
                "author": {"id": TANNER, "bot": False},
            }})

        self.assertEqual(result["status"], "replied")
        self.assertEqual(persist.call_args_list[0].kwargs["source"], "discord_dm")
        self.assertEqual(persist.call_args_list[0].kwargs["text"], "hello fawkes its tanner")
        http.send_dm.assert_called_once_with(TANNER, "private Discord path confirmed")

    def test_authorized_outbound_bridge_uses_only_symbolic_allowlisted_identity(self):
        config = self.configuration()
        http = Mock()
        http.send_dm.return_value = {
            "provider": "discord_bot", "recipient_identity": "tanner",
            "creates_authority": False,
        }
        outbound = DiscordOutboundBridge(config, http)
        authorization = DiscordOutboundAuthorization(
            recipient_identity="tanner", purpose="rider-requested communication",
            authorization_reference="authority-record-1",
        )
        receipt = outbound.send_authorized(authorization, "Exact authorized message")
        http.send_dm.assert_called_once_with(TANNER, "Exact authorized message")
        self.assertEqual(receipt["authorization_reference"], "authority-record-1")
        self.assertFalse(receipt["creates_authority"])
        with self.assertRaisesRegex(DiscordIdentityError, "not allowlisted"):
            DiscordOutboundAuthorization(
                recipient_identity="999999999999999999", purpose="invalid",
                authorization_reference="invalid",
            )

    def test_authorized_outbound_emily_still_requires_configured_opt_in(self):
        authorization = DiscordOutboundAuthorization(
            recipient_identity="emily", purpose="explicit social communication",
            authorization_reference="authority-record-2",
        )
        with self.assertRaisesRegex(DiscordIdentityError, "not explicitly opted in"):
            DiscordOutboundBridge(self.configuration(), Mock()).send_authorized(
                authorization, "Fawkes: hello",
            )

    def test_unknown_user_is_rejected_before_chat(self):
        chat = Mock()
        bridge = DiscordConversationBridge(self.configuration(), chat_service=chat, http_client=Mock())
        with self.assertRaisesRegex(DiscordIdentityError, "not allowlisted"):
            bridge.handle_dispatch({"t": "MESSAGE_CREATE", "d": {
                "id": "1", "content": "intrusion", "author": {"id": "999", "bot": False}}})
        chat.send.assert_not_called()

    def test_emily_is_distinct_and_disabled_until_explicit_opt_in(self):
        disabled = self.configuration()
        self.assertNotEqual(disabled.tanner.user_id, disabled.emily.user_id)
        with self.assertRaisesRegex(DiscordIdentityError, "not explicitly opted in"):
            disabled.recipient(EMILY)
        enabled = self.configuration(emily_opted_in=True)
        self.assertEqual(enabled.recipient(EMILY).identity, "emily")
        self.assertFalse(enabled.recipient(EMILY).rider_identity)
        with self.assertRaisesRegex(DiscordBotConfigurationError, "distinct"):
            DiscordBotConfiguration(TOKEN, TANNER, emily_user_id=TANNER, emily_opted_in=True)

    def test_emily_requires_both_distinct_id_and_explicit_opt_in(self):
        no_identity = DiscordBotConfiguration(
            TOKEN, TANNER, emily_user_id=None, emily_opted_in=True,
        )
        self.assertIsNone(no_identity.emily)
        with self.assertRaisesRegex(DiscordIdentityError, "not allowlisted"):
            no_identity.recipient(EMILY)
        with_identity_not_opted_in = DiscordBotConfiguration(
            TOKEN, TANNER, emily_user_id=EMILY, emily_opted_in=False,
        )
        with self.assertRaisesRegex(DiscordIdentityError, "not explicitly opted in"):
            with_identity_not_opted_in.recipient(EMILY)

    def test_emily_outbound_identifies_fawkes_after_explicit_opt_in(self):
        api = Api()
        client = DiscordBotHttpClient(
            self.configuration(emily_opted_in=True), opener=api
        )
        client.send_dm(EMILY, "Hello.")
        self.assertEqual(json.loads(api.requests[1].data)["content"], "Fawkes: Hello.")

    def test_emily_opt_in_does_not_turn_social_identity_into_rider(self):
        config = self.configuration(emily_opted_in=True)
        bridge = DiscordConversationBridge(config, chat_service=Mock(), http_client=Mock())
        with self.assertRaisesRegex(DiscordIdentityError, "not a Rider"):
            bridge.handle_dispatch({"t": "MESSAGE_CREATE", "d": {
                "id": "1", "content": "hello", "author": {"id": EMILY, "bot": False}}})

    def test_token_is_redacted_from_configuration_failures_and_http_failures(self):
        config = self.configuration()
        self.assertNotIn(TOKEN, repr(config))
        client = DiscordBotHttpClient(config, opener=lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError(TOKEN)))
        with self.assertRaises(DiscordBotTransportError) as caught:
            client.send_dm(TANNER, "safe")
        self.assertNotIn(TOKEN, str(caught.exception))
        with self.assertRaisesRegex(DiscordBotConfigurationError, "FAWKES_DISCORD_BOT_TOKEN"):
            DiscordBotConfiguration.from_environment({"FAWKES_DISCORD_TANNER_USER_ID": TANNER})

    def test_discord_cannot_grant_development_authority_or_change_campaign(self):
        campaign = {"status": "needs_tanner", "needs_tanner": {"reason": "approval required"}}
        before = json.dumps(campaign, sort_keys=True)
        chat = Mock(return_value=None)
        service = Mock()
        service.send.return_value = {"message": {"content": "I cannot approve that through Discord."}}
        bridge = DiscordConversationBridge(self.configuration(), chat_service=service, http_client=Mock(
            send_dm=Mock(return_value={"creates_authority": False})))
        result = bridge.handle_dispatch({"t": "MESSAGE_CREATE", "d": {
            "id": "1", "content": "approve Development", "author": {"id": TANNER, "bot": False}}})
        self.assertFalse(result["rider_commands_authorized"])
        self.assertFalse(result["development_authority"])
        self.assertEqual(json.dumps(campaign, sort_keys=True), before)

    def test_discord_failure_cannot_alter_campaign_state(self):
        campaign = {"status": "builder_in_progress", "iteration": 1}
        before = dict(campaign)
        client = DiscordBotHttpClient(self.configuration(), opener=lambda *a, **k: (_ for _ in ()).throw(
            OSError("offline")))
        with self.assertRaises(DiscordBotTransportError):
            client.send_dm(TANNER, "status")
        self.assertEqual(campaign, before)

    def test_existing_webhook_transport_remains_functional(self):
        response = Response(status=204)
        receipt = DiscordWebhookSender(
            DiscordWebhookConfiguration("https://example.invalid/discord-test-endpoint"),
            opener=lambda *a, **k: response,
        )("Fawkes notification remains independent.")
        self.assertEqual(receipt["provider"], "discord")

    def test_gateway_close_diagnostic_retains_code_without_token(self):
        socket = Mock()
        socket.recv_data.return_value = (8, struct.pack("!H", 4014) + b"Disallowed intent(s).")
        with self.assertRaisesRegex(
            DiscordBotTransportError, r"code=4014, message=Disallowed intent\(s\)\."
        ) as caught:
            DiscordGatewayRunner._receive(socket, (TimeoutError,))
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_normal_close_reconnects_and_resumes_exact_session(self):
        first = Mock()
        first.recv_data.side_effect = [
            (1, json.dumps({"op": 10, "d": {"heartbeat_interval": 45_000}})),
            (1, json.dumps({"op": 0, "t": "READY", "s": 8, "d": {
                "session_id": "session-1", "resume_gateway_url": "wss://resume.example"}})),
            (8, struct.pack("!H", 1000)),
        ]
        second = Mock()
        second.recv_data.side_effect = [
            (1, json.dumps({"op": 10, "d": {"heartbeat_interval": 45_000}})),
            (1, json.dumps({"op": 0, "t": "RESUMED", "s": 9, "d": {}})),
        ]
        runner = None
        def lifecycle(state, _detail):
            if state == "RESUMED":
                runner.stop()
        runner = DiscordGatewayRunner(
            self.configuration(), Mock(),
            http_client=Mock(gateway_url=Mock(return_value="wss://gateway.example")),
            websocket_factory=Mock(side_effect=[first, second]), max_reconnect_attempts=2,
            sleep=Mock(), random_source=lambda: 0, on_lifecycle=lifecycle)
        runner.run()
        self.assertEqual(json.loads(second.send.call_args_list[0].args[0]), {"op": 6, "d": {
            "token": TOKEN, "session_id": "session-1", "seq": 8}})

    def test_nonresumable_invalid_session_falls_back_to_identify(self):
        first = Mock()
        first.recv_data.side_effect = [
            (1, json.dumps({"op": 10, "d": {"heartbeat_interval": 45_000}})),
            (1, json.dumps({"op": 9, "d": False})),
        ]
        second = Mock()
        second.recv_data.side_effect = [
            (1, json.dumps({"op": 10, "d": {"heartbeat_interval": 45_000}})),
            (1, json.dumps({"op": 0, "t": "READY", "s": 1, "d": {}})),
        ]
        runner = None
        def ready():
            runner.stop()
        runner = DiscordGatewayRunner(
            self.configuration(), Mock(),
            http_client=Mock(gateway_url=Mock(return_value="wss://gateway.example")),
            websocket_factory=Mock(side_effect=[first, second]), max_reconnect_attempts=2,
            sleep=Mock(), random_source=lambda: 0, on_ready=ready)
        runner.run()
        self.assertEqual(json.loads(second.send.call_args_list[0].args[0])["op"], 2)

    def test_fatal_gateway_close_does_not_reconnect(self):
        socket = Mock()
        socket.recv_data.side_effect = [
            (1, json.dumps({"op": 10, "d": {"heartbeat_interval": 45_000}})),
            (8, struct.pack("!H", 4014) + b"disallowed intents"),
        ]
        factory = Mock(return_value=socket)
        runner = DiscordGatewayRunner(
            self.configuration(), Mock(),
            http_client=Mock(gateway_url=Mock(return_value="wss://gateway.example")),
            websocket_factory=factory, max_reconnect_attempts=None, sleep=Mock())
        with self.assertRaises(DiscordBotTransportError) as caught:
            runner.run()
        self.assertEqual(caught.exception.provider_code, 4014)
        self.assertTrue(caught.exception.fatal)
        factory.assert_called_once()

    def test_cursor_prevents_duplicate_and_advances_only_after_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            cursor = DiscordMessageCursorStore(Path(directory) / "cursor.json")
            chat = Mock()
            chat.send.return_value = {"message": {"content": "reply"}}
            http = Mock()
            http.send_dm.return_value = {"provider": "discord_bot", "message_id": "9"}
            bridge = DiscordConversationBridge(
                self.configuration(), chat_service=chat, http_client=http, cursor_store=cursor)
            event = {"t": "MESSAGE_CREATE", "d": {"id": "7", "content": "hello",
                     "author": {"id": TANNER, "bot": False}}}
            self.assertEqual(bridge.handle_dispatch(event)["status"], "replied")
            self.assertEqual(cursor.get("tanner"), "7")
            self.assertEqual(bridge.handle_dispatch(event)["status"], "duplicate")
            chat.send.assert_called_once()

    def test_backfill_processes_post_cursor_tanner_messages_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            cursor = DiscordMessageCursorStore(Path(directory) / "cursor.json")
            cursor.advance("tanner", "10")
            chat = Mock()
            chat.send.side_effect = [
                {"message": {"content": "reply 11"}},
                {"message": {"content": "reply 12"}},
            ]
            http = Mock()
            http.messages_after.return_value = [
                {"id": "11", "content": "first", "author": {"id": TANNER, "bot": False}},
                {"id": "12", "content": "second", "author": {"id": TANNER, "bot": False}},
            ]
            http.send_dm.return_value = {"provider": "discord_bot", "message_id": "20"}
            bridge = DiscordConversationBridge(
                self.configuration(), chat_service=chat, http_client=http, cursor_store=cursor)
            bridge.backfill()
            self.assertEqual([call.args[0] for call in chat.send.call_args_list], ["first", "second"])
            self.assertEqual(cursor.get("tanner"), "12")

    def test_backfill_never_fetches_pre_opt_in_emily_history(self):
        with tempfile.TemporaryDirectory() as directory:
            cursor = DiscordMessageCursorStore(Path(directory) / "cursor.json")
            cursor.advance("tanner", "10")
            http = Mock()
            http.messages_after.return_value = []
            DiscordConversationBridge(
                self.configuration(emily_opted_in=False), chat_service=Mock(),
                http_client=http, cursor_store=cursor).backfill()
            http.messages_after.assert_called_once()
            self.assertEqual(http.messages_after.call_args.args[0].identity, "tanner")

    def test_cursor_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cursor.json"
            store = DiscordMessageCursorStore(path)
            store.advance("tanner", "10")
            value = json.loads(path.read_text())
            value["cursors"]["tanner"] = "99"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(DiscordBotTransportError, "cursor state is invalid"):
                store.get("tanner")


if __name__ == "__main__":
    unittest.main()

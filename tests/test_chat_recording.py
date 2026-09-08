"""Synthetic policy enforcement tests: fake runtime, no live state/providers."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.runtime import chat_cli
from src.runtime.chat_service import ChatServiceError, FawkesChatService
from src.runtime.personal_recording import RecordingPolicyConflict, RecordingPolicyError, RecordingPolicyStore


class ChatRecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = RecordingPolicyStore("fawkes-test", root=self.root)
        self.runtime = Mock()
        self.runtime.model = "synthetic-model"
        self.runtime.semantic_retriever = None
        self.runtime.context_messages = 20
        self.answer = {"text": "PRIVATE_REPLY_SENTINEL", "memories": [],
                       "archive_passages": [], "library_passages": [],
                       "conversation_context": [], "correction": None}
        self.runtime.respond.return_value = self.answer
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.mocks = {}
        for name in ("ensure_archive_index", "persist_live_message", "discover_candidate",
                     "update_work_item", "save_context_receipt", "record_live_flight",
                     "create_development_observation", "get_latest_conversation",
                     "create_conversation", "build_archive_context"):
            self.mocks[name] = self.stack.enter_context(patch("src.runtime.chat_service." + name))
        self.mocks["get_latest_conversation"].return_value = {
            "conversation_id": "retained-conversation", "instance_id": "fawkes-test", "title": "Chat"}
        self.mocks["build_archive_context"].return_value = (
            {"role": "user", "content": "retained history", "message_id": "old"},)
        self.mocks["persist_live_message"].side_effect = lambda **kw: {
            "archive_id": "archive-" + kw["message_id"], "created_at": "synthetic-time"}
        self.mocks["discover_candidate"].return_value = {"work_item_id": "work-test"}
        self.mocks["save_context_receipt"].return_value = {"receipt_id": "receipt-test"}
        self.service = FawkesChatService(
            phoenix={"instance_id": "fawkes-test", "name": "Fawkes"}, runtime=self.runtime,
            recording_policy_store=self.store, provider_receipt_dir=self.root / "provider_receipts")
        self.schedule = self.stack.enter_context(patch.object(self.service, "_schedule_memory_queue"))

    def configure(self, changes):
        return self.store.update(changes, expected_revision=self.store.load().revision)

    def assert_no_personal_writers(self):
        for name in ("persist_live_message", "discover_candidate", "update_work_item",
                     "save_context_receipt", "record_live_flight", "create_development_observation"):
            self.mocks[name].assert_not_called()
        self.schedule.assert_not_called()

    def test_private_turn_skips_all_personal_sinks_but_keeps_body_free_provider_receipts(self):
        self.configure({"mode": "private"})
        self.answer["correction"] = SimpleNamespace(is_correction=True)
        self.answer["conversation_context"] = [{"role": "assistant", "message_id": "previous"}]
        result = self.service.send("PRIVATE_USER_SENTINEL")
        self.assert_no_personal_writers()
        self.mocks["get_latest_conversation"].assert_not_called()
        self.mocks["create_conversation"].assert_not_called()
        self.mocks["build_archive_context"].assert_not_called()
        self.assertTrue(result["conversation_id"].startswith("private-"))
        self.assertEqual(result["recording"]["mode"], "private")
        self.assertFalse(result["message"]["context_inspector_available"])
        self.assertEqual(self.runtime.respond.call_args.kwargs["ephemeral_context"], ())
        receipts = list((self.root / "provider_receipts").rglob("*.json"))
        self.assertEqual(len(receipts), 2)
        for path in receipts:
            body = path.read_text()
            self.assertNotIn("PRIVATE_USER_SENTINEL", body)
            self.assertNotIn("PRIVATE_REPLY_SENTINEL", body)
            self.assertFalse(json.loads(body)["payload_recorded"])

    def test_private_followup_and_history_use_only_bounded_volatile_messages(self):
        first = self.service.send("first private", recording_mode="private")
        second = self.service.send("follow up", conversation_id=first["conversation_id"])
        context = self.runtime.respond.call_args.kwargs["ephemeral_context"]
        self.assertEqual(context[0], {"role": "user", "content": "first private"})
        self.assertEqual(len(context), 2)
        history = self.service.history()
        self.assertEqual(len(history["messages"]), 4)
        self.assertEqual(history["recording"], second["recording"])
        self.assertEqual(self.service.history(limit=0)["messages"], [])
        for index in range(30):
            self.service._append_private_message({"role": "user", "content": "x" * 50_000})
        self.assertLessEqual(sum(len(item["content"]) for item in self.service._private_messages), 100_000)
        self.assertLessEqual(len(self.service._private_messages), 20)
        self.assert_no_personal_writers()

    def test_private_to_retained_discards_buffer_and_rejects_private_archive_identity(self):
        private = self.service.send("PRIVATE_USER_SENTINEL", recording_mode="private")
        with self.assertRaises(ChatServiceError):
            self.service.send("next", conversation_id=private["conversation_id"], recording_mode="retained")
        result = self.service.send("retained now", recording_mode="retained")
        self.assertEqual(result["conversation_id"], "retained-conversation")
        self.assertEqual(result["recording"]["mode"], "retained")
        self.assertEqual(self.service._private_messages, [])
        self.assertNotIn("ephemeral_context", self.runtime.respond.call_args.kwargs)
        self.assertEqual(self.mocks["persist_live_message"].call_count, 2)
        for call in self.mocks["persist_live_message"].call_args_list:
            self.assertNotIn("PRIVATE_USER_SENTINEL", call.kwargs["text"])
            self.assertFalse(call.kwargs["conversation_id"].startswith("private-"))

    def test_private_started_turn_stays_private_when_settings_change_during_provider(self):
        self.configure({"mode": "private"})
        def respond(**kwargs):
            self.configure({"mode": "retained"})
            return self.answer
        self.runtime.respond.side_effect = respond
        result = self.service.send("private turn")
        self.assertEqual(result["recording"]["mode"], "private")
        self.assertEqual(self.store.load().mode, "retained")
        self.assert_no_personal_writers()
        self.assertEqual(self.service.history()["recording"]["mode"], "retained")
        self.assertEqual(self.service._private_messages, [])

    def test_retained_turn_passes_identical_latch_to_both_archive_writes_and_runtime(self):
        def respond(**kwargs):
            self.configure({"mode": "private"})
            return self.answer
        self.runtime.respond.side_effect = respond
        result = self.service.send("retained started")
        latch = self.runtime.respond.call_args.kwargs["recording_policy"]
        self.assertEqual(result["recording"], latch.public())
        self.assertEqual(latch.mode, "retained")
        self.assertEqual(self.mocks["persist_live_message"].call_count, 2)
        for call in self.mocks["persist_live_message"].call_args_list:
            self.assertIs(call.kwargs["recording_policy"], latch)

    def test_memory_and_diagnostic_categories_gate_independent_personal_sinks(self):
        self.configure({"categories": {"memory_learning": False, "personal_diagnostics": False}})
        self.answer["correction"] = SimpleNamespace(is_correction=True)
        result = self.service.send("retained without learning")
        self.assertEqual(result["recording"]["mode"], "retained")
        self.assertEqual(self.mocks["persist_live_message"].call_count, 2)
        for name in ("discover_candidate", "update_work_item", "save_context_receipt",
                     "record_live_flight", "create_development_observation"):
            self.mocks[name].assert_not_called()
        self.schedule.assert_not_called()
        self.assertFalse(self.runtime.respond.call_args.kwargs["recording_policy"].memory_learning)

    def test_archive_off_forces_private_even_with_retained_override(self):
        self.configure({"categories": {"archive_recording": False}})
        result = self.service.send("not recorded", recording_mode="retained")
        self.assertEqual(result["recording"]["mode"], "private")
        self.assert_no_personal_writers()

    def test_private_failure_is_truthful_and_never_records_content(self):
        self.configure({"mode": "private"})
        self.runtime.respond.side_effect = RuntimeError("synthetic provider failure")
        with self.assertRaises(ChatServiceError) as failure:
            self.service.send("private failure sentinel")
        self.assertIn("not recorded", str(failure.exception))
        self.assertNotIn("preserved", str(failure.exception))
        self.assert_no_personal_writers()

    def test_invalid_or_foreign_policy_blocks_before_conversation_or_provider(self):
        self.store.path.parent.mkdir(parents=True)
        foreign = self.store.load().public()
        foreign["instance_id"] = "another-phoenix"
        for payload in ("not JSON", json.dumps(foreign)):
            self.store.path.write_text(payload)
            with self.assertRaises(ChatServiceError):
                self.service.send("must not write")
        self.runtime.respond.assert_not_called()
        self.mocks["get_latest_conversation"].assert_not_called()
        self.assert_no_personal_writers()

    def test_foreign_policy_store_is_rejected_at_service_construction(self):
        foreign = RecordingPolicyStore("another-phoenix", root=self.root)
        with self.assertRaises(RecordingPolicyError):
            FawkesChatService(phoenix={"instance_id": "fawkes-test"}, runtime=self.runtime,
                              recording_policy_store=foreign)

    def test_restarted_service_cannot_recover_private_content(self):
        self.configure({"mode": "private"})
        original = self.service.send("PRIVATE_RESTART_SENTINEL")
        restarted = FawkesChatService(
            phoenix={"instance_id": "fawkes-test", "name": "Fawkes"}, runtime=self.runtime,
            recording_policy_store=self.store, provider_receipt_dir=self.root / "provider_receipts")
        history = restarted.history()
        self.assertEqual(history["messages"], [])
        self.assertNotEqual(history["conversation"]["conversation_id"], original["conversation_id"])
        self.mocks["get_latest_conversation"].assert_not_called()

    def test_invalid_recording_mode_fails_before_policy_or_provider_work(self):
        for mode in (True, 1, "unknown", [], {}):
            with self.assertRaises(ChatServiceError) as failure:
                self.service.send("unused", recording_mode=mode)
            self.assertEqual(failure.exception.code, "invalid_recording_mode")
        self.runtime.respond.assert_not_called()
        self.assert_no_personal_writers()

    def test_policy_api_propagates_typed_errors_and_reports_configured_values(self):
        result = self.service.update_recording_policy({"mode": "private"}, expected_revision=0)
        self.assertEqual(result, self.service.get_recording_policy())
        with self.assertRaises(RecordingPolicyConflict):
            self.service.update_recording_policy({"mode": "retained"}, expected_revision=0)
        with self.assertRaises(RecordingPolicyError):
            self.service.update_recording_policy({"categories": {"sensor_retention": True}}, expected_revision=1)

    def test_private_media_clarification_social_and_retention_capabilities_are_bounded(self):
        self.configure({"mode": "private"})
        for kwargs in ({"attachments": [{"data": "ignored"}]},
                       {"retrieval_clarification": {}}, {"source": "discord_dm"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ChatServiceError):
                self.service.send("private", **kwargs)
        for call in (lambda: self.service.research({"query": "private query"}),
                     lambda: self.service.library_extract("source"),
                     lambda: self.service.context_feedback("response", {})):
            with self.assertRaises(ChatServiceError):
                call()
        self.runtime.respond.assert_not_called()
        self.assert_no_personal_writers()

    def test_social_off_and_library_keep_off_block_before_archive_or_provider(self):
        self.configure({"categories": {"social_archive": False, "library_retention": False}})
        with self.assertRaises(ChatServiceError):
            self.service.send("social text", source="discord_dm")
        with patch("src.runtime.chat_service.validate_chat_media",
                   return_value=({"keep_in_library": True},)):
            with self.assertRaises(ChatServiceError):
                self.service.send("keep this", attachments=[{}])
        self.assert_no_personal_writers()
        self.runtime.respond.assert_not_called()

    def test_current_policy_pauses_background_worker_without_claiming_or_deleting_queue(self):
        self.configure({"categories": {"memory_learning": False}})
        with patch("src.memory.ledger.list_work_items") as items, patch(
                "src.runtime.chat_service.evaluate_batch") as evaluate, patch(
                "src.runtime.chat_service.apply_accepted_batch") as apply:
            self.service._process_memory_queue()
        items.assert_not_called()
        evaluate.assert_not_called()
        apply.assert_not_called()

    def test_background_apply_rechecks_policy_after_started_evaluation(self):
        self.runtime.semantic_retriever = SimpleNamespace(provider=Mock())
        candidate = {"work_item_id": "work-old", "candidate_content": "old permitted text", "status": "queued"}
        with patch("src.memory.ledger.list_work_items", return_value=[candidate]), patch(
                "src.runtime.chat_service.evaluate_batch",
                side_effect=lambda **kw: self.configure({"categories": {"memory_learning": False}})), patch(
                "src.runtime.chat_service.apply_accepted_batch") as apply:
            self.service._process_memory_queue()
        apply.assert_not_called()
        self.mocks["update_work_item"].assert_not_called()


class CLIRecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = RecordingPolicyStore("cli-test", root=self.tmp.name)

    def run_cli(self, inputs, *, response_effect=None, estimated_cost=0):
        runtime = Mock()
        runtime.model = "synthetic-model"
        runtime.context_messages = 20
        runtime.paid_call_guard.estimate.return_value = SimpleNamespace(
            estimated_cost=estimated_cost, provider="synthetic", model="synthetic-model", estimated_calls=5)
        runtime.respond.return_value = {"text": "synthetic reply", "conversation_context": []}
        runtime.respond.side_effect = response_effect
        with ExitStack() as stack:
            stack.enter_context(patch.object(chat_cli, "RecordingPolicyStore", return_value=self.store))
            stack.enter_context(patch.object(chat_cli, "get_or_create_default_instance", return_value={"instance_id": "cli-test"}))
            stack.enter_context(patch.object(chat_cli, "FawkesChatRuntime", return_value=runtime))
            stack.enter_context(patch("builtins.input", side_effect=inputs))
            stack.enter_context(patch("builtins.print"))
            mocks = {name: stack.enter_context(patch.object(chat_cli, name)) for name in (
                "ensure_archive_index", "get_latest_conversation", "create_conversation", "build_archive_context",
                "persist_live_message", "discover_candidate", "update_work_item", "save_context_receipt")}
            mocks["get_latest_conversation"].return_value = {"conversation_id": "retained-cli"}
            mocks["build_archive_context"].return_value = ({"role": "user", "content": "old retained context"},)
            mocks["persist_live_message"].side_effect = lambda **kw: {"archive_id": "archive-" + kw["message_id"], "created_at": "now"}
            mocks["discover_candidate"].return_value = {"work_item_id": "cli-work"}
            chat_cli.main()
        return runtime, mocks

    def test_private_cli_skips_canonical_startup_and_personal_writes(self):
        self.store.update({"mode": "private"}, expected_revision=0)
        runtime, mocks = self.run_cli(["private one", "private two", "exit"])
        for name in mocks:
            mocks[name].assert_not_called()
        self.assertEqual(runtime.respond.call_count, 2)
        self.assertEqual(len(runtime.respond.call_args.kwargs["ephemeral_context"]), 2)
        self.assertEqual(runtime.respond.call_args.kwargs["conversation_history"], ())

    def test_private_to_retained_cli_reloads_archive_instead_of_promoting_buffer(self):
        runtime, mocks = self.run_cli(["/private", "PRIVATE_CLI_SENTINEL", "/retained", "retained next", "exit"])
        self.assertEqual(mocks["persist_live_message"].call_count, 2)
        self.assertNotIn("ephemeral_context", runtime.respond.call_args.kwargs)
        context = runtime.respond.call_args.kwargs["conversation_history"]
        self.assertNotIn("PRIVATE_CLI_SENTINEL", str(context))
        for call in mocks["persist_live_message"].call_args_list:
            self.assertEqual(call.kwargs["conversation_id"], "retained-cli")
            self.assertEqual(call.kwargs["recording_policy"].mode, "retained")

    def test_cli_retained_memory_off_has_policy_on_both_messages_without_queue(self):
        self.store.update({"categories": {"memory_learning": False, "personal_diagnostics": False}}, expected_revision=0)
        runtime, mocks = self.run_cli(["retained without learning", "exit"])
        self.assertEqual(mocks["persist_live_message"].call_count, 2)
        mocks["discover_candidate"].assert_not_called()
        mocks["update_work_item"].assert_not_called()
        mocks["save_context_receipt"].assert_not_called()
        latch = runtime.respond.call_args.kwargs["recording_policy"]
        for call in mocks["persist_live_message"].call_args_list:
            self.assertIs(call.kwargs["recording_policy"], latch)

    def test_cli_latched_private_turn_ignores_midturn_retained_setting_change(self):
        self.store.update({"mode": "private"}, expected_revision=0)
        def respond(**kwargs):
            self.store.update({"mode": "retained"}, expected_revision=1)
            return {"text": "private reply"}
        runtime, mocks = self.run_cli(["private started", "exit"], response_effect=respond)
        self.assertEqual(runtime.respond.call_args.kwargs["recording_policy"].mode, "private")
        mocks["persist_live_message"].assert_not_called()
        mocks["save_context_receipt"].assert_not_called()

    def test_cli_draft_started_private_stays_private_when_default_changes_during_input(self):
        self.store.update({"mode": "private"}, expected_revision=0)
        answers = iter(["PRIVATE_DRAFT_SENTINEL", "retained next", "exit"])
        def read(prompt):
            answer = next(answers)
            if answer == "PRIVATE_DRAFT_SENTINEL":
                self.store.update({"mode": "retained"}, expected_revision=1)
            return answer
        runtime, mocks = self.run_cli(read)
        first, second = runtime.respond.call_args_list
        self.assertEqual(first.kwargs["recording_policy"].mode, "private")
        self.assertEqual(first.kwargs["conversation_history"], ())
        self.assertEqual(first.kwargs["ephemeral_context"], ())
        self.assertEqual(second.kwargs["recording_policy"].mode, "retained")
        self.assertNotIn("PRIVATE_DRAFT_SENTINEL", str(second.kwargs["conversation_history"]))
        self.assertEqual(mocks["persist_live_message"].call_count, 2)
        self.assertEqual(mocks["discover_candidate"].call_count, 1)
        for call in mocks["persist_live_message"].call_args_list:
            self.assertNotIn("PRIVATE_DRAFT_SENTINEL", call.kwargs["text"])
            self.assertIs(call.kwargs["recording_policy"], second.kwargs["recording_policy"])

    def test_cli_draft_current_private_or_archive_off_applies_before_submission(self):
        for changes in ({"mode": "private"}, {"categories": {"archive_recording": False}}):
            with self.subTest(changes=changes):
                self.store.update({"mode": "retained", "categories": {"archive_recording": True}},
                                  expected_revision=self.store.load().revision)
                answers = iter(["draft before restriction", "exit"])
                def read(prompt):
                    answer = next(answers)
                    if answer != "exit":
                        self.store.update(changes, expected_revision=self.store.load().revision)
                    return answer
                runtime, mocks = self.run_cli(read)
                self.assertEqual(runtime.respond.call_args.kwargs["recording_policy"].mode, "private")
                self.assertEqual(runtime.respond.call_args.kwargs["ephemeral_context"], ())
                for name in ("persist_live_message", "discover_candidate", "update_work_item", "save_context_receipt"):
                    mocks[name].assert_not_called()

    def test_cli_draft_disabled_categories_never_enable_during_input_or_confirmation(self):
        categories = ("memory_learning", "personal_diagnostics", "research_records", "library_retention", "social_archive")
        for when in ("draft", "confirmation"):
            with self.subTest(when=when):
                self.store.update({"categories": dict.fromkeys(categories, False)},
                                  expected_revision=self.store.load().revision)
                answers = iter(["category-restricted draft", "yes", "exit"] if when == "confirmation"
                               else ["category-restricted draft", "exit"])
                def read(prompt):
                    answer = next(answers)
                    if (when == "draft" and answer == "category-restricted draft") or (
                            when == "confirmation" and answer == "yes"):
                        self.store.update({"categories": dict.fromkeys(categories, True)},
                                          expected_revision=self.store.load().revision)
                    return answer
                runtime, mocks = self.run_cli(read, estimated_cost=1 if when == "confirmation" else 0)
                policy = runtime.respond.call_args.kwargs["recording_policy"]
                self.assertEqual(policy.mode, "retained")
                for name in categories:
                    self.assertFalse(getattr(policy, name), name)
                self.assertEqual(mocks["persist_live_message"].call_count, 2)
                for call in mocks["persist_live_message"].call_args_list:
                    self.assertIs(call.kwargs["recording_policy"], policy)
                for name in ("discover_candidate", "update_work_item", "save_context_receipt"):
                    mocks[name].assert_not_called()

    def test_cli_draft_private_paid_confirmation_cannot_enable_retention(self):
        self.store.update({"mode": "private"}, expected_revision=0)
        answers = iter(["PRIVATE_PAID_DRAFT", "yes", "exit"])
        def read(prompt):
            answer = next(answers)
            if answer == "yes":
                self.store.update({"mode": "retained"}, expected_revision=1)
            return answer
        runtime, mocks = self.run_cli(read, estimated_cost=1)
        self.assertEqual(runtime.respond.call_args.kwargs["recording_policy"].mode, "private")
        self.assertEqual(runtime.respond.call_args.kwargs["ephemeral_context"], ())
        for name in mocks:
            mocks[name].assert_not_called()

    def test_cli_draft_paid_confirmation_rechecks_current_restrictions_and_context(self):
        for changes in ({"mode": "private"}, {"categories": {"memory_learning": False, "personal_diagnostics": False}}):
            with self.subTest(changes=changes):
                self.store.update({"mode": "retained", "categories": {"memory_learning": True, "personal_diagnostics": True}},
                                  expected_revision=self.store.load().revision)
                answers = iter(["draft awaiting approval", "yes", "exit"])
                def read(prompt):
                    answer = next(answers)
                    if answer == "yes":
                        self.store.update(changes, expected_revision=self.store.load().revision)
                    return answer
                runtime, mocks = self.run_cli(read, estimated_cost=1)
                policy = runtime.respond.call_args.kwargs["recording_policy"]
                self.assertFalse(policy.memory_learning)
                self.assertFalse(policy.personal_diagnostics)
                for name in ("discover_candidate", "update_work_item", "save_context_receipt"):
                    mocks[name].assert_not_called()
                if "mode" in changes:
                    self.assertEqual(policy.mode, "private")
                    self.assertEqual(runtime.respond.call_args.kwargs["ephemeral_context"], ())
                    self.assertEqual(runtime.respond.call_args.kwargs["conversation_history"], ())
                    mocks["persist_live_message"].assert_not_called()
                else:
                    self.assertEqual(mocks["persist_live_message"].call_count, 2)
                    for call in mocks["persist_live_message"].call_args_list:
                        self.assertIs(call.kwargs["recording_policy"], policy)

    def test_cli_draft_commands_apply_to_future_drafts_without_overriding_configured_private(self):
        runtime, mocks = self.run_cli(["/private", "private text", "/retained", "retained text", "exit"])
        self.assertEqual([call.kwargs["recording_policy"].mode for call in runtime.respond.call_args_list],
                         ["private", "retained"])
        self.assertEqual(mocks["persist_live_message"].call_count, 2)
        self.store.update({"mode": "private"}, expected_revision=0)
        runtime, mocks = self.run_cli(["/retained", "still private", "exit"])
        self.assertEqual(runtime.respond.call_args.kwargs["recording_policy"].mode, "private")
        for name in mocks:
            mocks[name].assert_not_called()

    def test_cli_draft_unavailable_settings_block_input_or_confirmation_submission(self):
        for when in ("draft", "confirmation"):
            with self.subTest(when=when):
                # Each variant gets a new synthetic owner; corrupt history is not repaired.
                self.store = RecordingPolicyStore("cli-test", root=Path(self.tmp.name) / when)
                answers = iter(["unsent draft", "yes", "exit"] if when == "confirmation"
                               else ["unsent draft", "exit"])
                def read(prompt):
                    answer = next(answers)
                    if (when == "draft" and answer == "unsent draft") or answer == "yes":
                        self.store.path.parent.mkdir(parents=True, exist_ok=True)
                        self.store.path.write_text("not JSON")
                    return answer
                runtime, mocks = self.run_cli(read, estimated_cost=1 if when == "confirmation" else 0)
                runtime.respond.assert_not_called()
                for name in ("persist_live_message", "discover_candidate", "update_work_item", "save_context_receipt"):
                    mocks[name].assert_not_called()

    def test_cli_draft_cancelled_paid_call_does_not_send_or_retain(self):
        runtime, mocks = self.run_cli(["unsent draft", "no", "exit"], estimated_cost=1)
        runtime.respond.assert_not_called()
        self.assertTrue(runtime.paid_call_guard.require_confirmation)
        for name in ("persist_live_message", "discover_candidate", "update_work_item", "save_context_receipt"):
            mocks[name].assert_not_called()

    def test_cli_draft_dispatched_turn_keeps_one_policy_during_provider_change(self):
        def respond(**kwargs):
            self.store.update({"mode": "private"}, expected_revision=0)
            return {"text": "retained response"}
        runtime, mocks = self.run_cli(["retained submitted", "exit"], response_effect=respond)
        policy = runtime.respond.call_args.kwargs["recording_policy"]
        self.assertEqual(policy.mode, "retained")
        self.assertEqual(mocks["persist_live_message"].call_count, 2)
        for call in mocks["persist_live_message"].call_args_list:
            self.assertIs(call.kwargs["recording_policy"], policy)


if __name__ == "__main__":
    unittest.main()

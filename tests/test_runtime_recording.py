"""Actual runtime response boundary with synthetic providers and private state."""

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.runtime.chat import FawkesChatRuntime
from src.runtime.context_composer import ProductionContextComposer
from src.runtime.evidence_transmission import EvidenceTransmissionAuthorizer
from src.runtime.personal_recording import RecordingPolicy, RecordingPolicyError, RecordingPolicyStore


class RuntimeRecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"FAWKES_RUNTIME_STATE_ROOT": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = Mock(return_value=SimpleNamespace(output_text="A private answer.", usage=None))
        self.runtime = object.__new__(FawkesChatRuntime)
        self.runtime.instance_id = "fawkes"
        self.runtime.model = "synthetic-model"
        self.runtime.context_messages = 20
        self.runtime.retrieval_path = "planner"
        self.runtime.planner_context_builder = Mock(side_effect=AssertionError("private planner called"))
        self.runtime.build_context = Mock(side_effect=AssertionError("private retrieval called"))
        self.runtime.paid_call_guard = Mock()
        self.runtime.client = SimpleNamespace(responses=SimpleNamespace(create=self.provider))
        self.runtime.context_composer = ProductionContextComposer()
        self.runtime.evidence_transmission_authorizer = EvidenceTransmissionAuthorizer(root=self.root / "permits")
        self.runtime.capability_context = lambda: [{"name": "web.research", "availability": "live"}]
        self.runtime.research_orchestrator = Mock()
        self.runtime._research_health = {}
        self.runtime.presentation_planner = Mock()
        self.runtime.correction_evaluator = Mock()
        self.runtime.development_evaluator = Mock()
        self.runtime.development_similarity = Mock()
        self.private = RecordingPolicy("fawkes", mode="private").effective()

    def run_private(self, **kwargs):
        return self.runtime.respond(user_message="PRIVATE SENTINEL current news",
            conversation_id="private-one", current_message_id="private-message",
            recording_policy=self.private, **kwargs)

    def retained_context(self):
        return {"memories": [], "archive_passages": [], "library_passages": [],
                "conversation": [], "continuity": {"attempted": False, "status": "not_requested"},
                "selected_evidence": [], "warnings": []}

    def assert_no_personal_bytes_saved(self):
        paths = [p for p in self.root.rglob("*") if p.is_file()]
        self.assertTrue(paths, "metadata-only permission evidence should remain")
        for path in paths:
            body = path.read_bytes()
            self.assertNotIn(b"PRIVATE SENTINEL", body, str(path))
            self.assertNotIn(b"A private answer.", body, str(path))
            self.assertNotIn(b"Earlier private context", body, str(path))

    def test_private_bypasses_personal_retrieval_and_learning_but_keeps_exact_permit(self):
        for path in ("planner", "legacy"):
            with self.subTest(path=path):
                self.runtime.retrieval_path = path
                with patch("src.runtime.chat.build_archive_context", side_effect=AssertionError("Archive read")), \
                     patch("src.runtime.chat.evaluate_correction", side_effect=AssertionError("learning")), \
                     patch("src.runtime.chat.process_user_correction", side_effect=AssertionError("development")):
                    result = self.run_private(ephemeral_context=[{"role": "user", "content": "Earlier private context"}])
                self.assertEqual(result["recording"]["mode"], "private")
                self.assertEqual(result["conversation_context"][0]["content"], "Earlier private context")
                self.assertEqual(result["memories"], [])
                self.assertIsNone(result["correction"])
                self.assertIsNone(result["development"])
                self.assertIsNone(result["research"])
                self.assertIn("manifest_id", result["retrieval_audit"]["transmission_authorization"])
                args = self.provider.call_args.kwargs
                self.assertFalse(args["store"])
                self.assertIn("You are Fawkes", args["input"][0]["content"])
                self.assertIn("Earlier private context", args["input"][1]["content"])
                self.assertIn("research is disabled", args["input"][1]["content"].lower())
        self.runtime.planner_context_builder.assert_not_called()
        self.runtime.build_context.assert_not_called()
        self.runtime.research_orchestrator.research_if_needed.assert_not_called()
        self.assertEqual(self.runtime.paid_call_guard.authorize.call_count, 2)
        self.assert_no_personal_bytes_saved()

    def test_direct_scoped_call_loads_current_private_policy_not_old_history(self):
        RecordingPolicyStore("fawkes").update({"mode": "private"}, expected_revision=0)
        result = self.runtime.respond(user_message="PRIVATE SENTINEL", conversation_id="old-retained",
            current_message_id="message-two", conversation_history=[{"role": "user", "content": "unrelated old history"}])
        self.assertEqual(result["recording"]["policy_revision"], 1)
        self.assertEqual(result["conversation_context"], [])
        self.assertNotIn("unrelated old history", self.provider.call_args.kwargs["input"][1]["content"])
        self.assert_no_personal_bytes_saved()

    def test_provider_failure_keeps_no_personal_record(self):
        self.provider.side_effect = RuntimeError("synthetic provider failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic provider"):
            self.run_private()
        self.assert_no_personal_bytes_saved()

    def test_corrupt_or_foreign_policy_fails_before_any_provider(self):
        store = RecordingPolicyStore("fawkes")
        store.path.parent.mkdir(parents=True)
        store.path.write_text("{bad-json")
        with self.assertRaises(RecordingPolicyError):
            self.runtime.respond(user_message="PRIVATE SENTINEL")
        with self.assertRaises(ValueError):
            self.runtime.respond(user_message="PRIVATE SENTINEL", recording_policy=RecordingPolicy("foreign").effective())
        self.provider.assert_not_called()
        self.runtime.paid_call_guard.authorize.assert_not_called()

    def test_private_media_and_stale_private_id_are_rejected_before_provider(self):
        with self.assertRaises(PermissionError):
            self.run_private(media_attachments=[{"modality": "image"}])
        with self.assertRaises(PermissionError):
            self.runtime.respond(user_message="PRIVATE SENTINEL", conversation_id="private-old",
                recording_policy=RecordingPolicy("fawkes").effective())
        self.provider.assert_not_called()
        self.runtime.paid_call_guard.authorize.assert_not_called()

    def test_research_off_and_learning_off_are_independent_retained_controls(self):
        self.runtime.retrieval_path = "legacy"
        self.runtime.build_context = Mock(return_value=self.retained_context())
        policy = RecordingPolicy("fawkes", research_records=False, memory_learning=False).effective()
        with patch("src.runtime.chat.evaluate_correction", side_effect=AssertionError("disabled learning")), \
             patch("src.runtime.chat.process_user_correction", side_effect=AssertionError("disabled learning")):
            result = self.runtime.respond(user_message="What is the current weather today?", recording_policy=policy)
        self.assertEqual(result["recording"]["mode"], "retained")
        self.assertTrue(result["recording"]["categories"]["archive_recording"])
        self.runtime.research_orchestrator.research_if_needed.assert_not_called()
        self.assertIn("research is disabled", self.provider.call_args.kwargs["input"][1]["content"].lower())

    def test_latched_private_policy_cannot_be_reenabled_by_settings_change(self):
        store = RecordingPolicyStore("fawkes")
        store.update({"mode": "private"}, expected_revision=0)
        latched = store.latch()
        store.update({"mode": "retained"}, expected_revision=1)
        result = self.runtime.respond(user_message="PRIVATE SENTINEL", conversation_id="private-latched",
            current_message_id="private-latched-message", recording_policy=latched)
        self.assertEqual(result["recording"]["mode"], "private")
        self.assertEqual(result["recording"]["policy_revision"], 1)
        self.runtime.planner_context_builder.assert_not_called()
        self.assert_no_personal_bytes_saved()

    def test_effective_policy_cannot_be_constructed_to_bypass_privacy(self):
        with self.assertRaises(RecordingPolicyError):
            replace(self.private, memory_learning=True)
        with self.assertRaises(RecordingPolicyError):
            replace(self.private, mode="retained", archive_recording=True)

    def test_direct_correction_entrypoint_filters_ineligible_history(self):
        from src.memory.development_runtime import process_user_correction
        context = ({"role": "user", "content": "DISABLED OLD CONTENT", "memory_learning_eligible": False},
                   {"role": "assistant", "content": "eligible old response", "memory_learning_eligible": True})
        with patch("src.memory.development_runtime.process_development_experience", return_value={}) as process:
            process_user_correction("Please correct this.", evaluator=object(), similarity=object(),
                                    instance_id="fawkes", conversation_context=context)
        experience = process.call_args.args[0]
        self.assertNotIn("DISABLED OLD CONTENT", experience)
        self.assertIn("eligible old response", experience)

    def test_direct_correction_entrypoint_respects_current_disabled_policy(self):
        from src.memory.development_runtime import process_user_correction
        RecordingPolicyStore("fawkes").update({"categories": {"memory_learning": False}}, expected_revision=0)
        with patch("src.memory.development_runtime.process_development_experience") as process:
            with self.assertRaises(PermissionError):
                process_user_correction("PRIVATE SENTINEL", evaluator=object(), similarity=object(),
                                        instance_id="fawkes")
        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Synthetic Archive/Memory regressions; no live sources or model providers."""

from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src import ingest
from src.capture import canonical
from src.memory import archive_retrieval, store, worker
from src.memory.archive_context import ArchiveContextReviewRequired, MemoryLearningPaused, build_archive_context
from src.memory.consolidate import consolidate_assessment
from src.memory.dry_run import dry_run_conversation
from src.memory.development import propose_development
from src.memory.development_runtime import process_development_experience, process_user_correction
from src.memory.extract import extract_memory_candidates
from src.memory.ledger import discover_candidate, get_work_item, list_work_items, update_work_item
from src.memory.pipeline import process_conversation, process_memory_candidate
from src.memory.runtime import process_memory_conversation
from src.memory.semantic import SemanticMemoryAssessment
from src.runtime.personal_recording import RecordingPolicy, RecordingPolicyError, RecordingPolicyStore
from src.runtime.persistence import persist_live_message


class RecordingMemoryEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"FAWKES_RUNTIME_STATE_ROOT": str(self.root)}))
        for module, name, path in (
            (ingest, "RAW_DIR", self.root / "archive/raw"),
            (ingest, "META_DIR", self.root / "archive/meta"),
            (canonical, "RAW_DIR", self.root / "archive/raw"),
            (canonical, "META_DIR", self.root / "archive/meta"),
            (archive_retrieval, "META_DIR", self.root / "archive/meta"),
            (archive_retrieval, "INDEX_PATH", self.root / "database/canonical.sqlite3"),
            (store, "MEMORY_RECORDS_DIR", self.root / "memory/records"),
            (store, "MEMORY_EVENTS_DIR", self.root / "memory/events"),
        ):
            self.stack.enter_context(patch.object(module, name, path))
        self.policy = RecordingPolicyStore("fawkes", root=self.root)
        self.ledger = self.root / "database/work.sqlite3"

    def _learning(self, enabled):
        self.policy.update({"categories": {"memory_learning": enabled}},
                           expected_revision=self.policy.load().revision)

    def _capture(self, message_id, *, role="user", legacy=False):
        return persist_live_message(
            instance_id="fawkes", conversation_id="conversation", message_id=message_id,
            role=role, text="I prefer concise technical explanations. " + message_id,
            recording_policy=None if legacy else self.policy.latch(),
        )

    def _raw_capture(self, message_id, marker, *, text="Synthetic retained revision."):
        payload = {"schema_version": 1, "conversation_id": "conversation",
                   "message_id": message_id, "role": "user", "text": text,
                   "recording_policy": marker}
        return ingest.ingest_bytes(
            json.dumps(payload, sort_keys=True).encode(), "Synthetic message",
            source="synthetic", capture_type="message_state", encoding="utf-8",
            conversation_id="conversation", instance_id="fawkes", emit_receipt=False,
        )

    def _message(self, message_id):
        return next(message for message in canonical.canonical_messages(
            "conversation", instance_id="fawkes") if message["message_id"] == message_id)

    def _queue(self, message_id):
        message = self._message(message_id)
        item = discover_candidate(
            instance_id="fawkes", conversation_id="conversation", message_id=message_id,
            canonical_revision=message["source_archive_id"],
            source_archive_ids=(message["source_archive_id"],), candidate_content=message["content"],
            path=self.ledger,
        )
        return update_work_item(item["work_item_id"], status="queued", path=self.ledger)

    def _assessment(self, message_id):
        return SemanticMemoryAssessment(
            should_remember=True, memory_type="preference",
            meaning="The rider prefers concise technical explanations.",
            confidence=0.99, importance=0.9, reasoning="Explicit durable preference.",
            supporting_message_ids=(message_id,),
            supporting_archive_ids=(self._message(message_id)["source_archive_id"],),
        )

    def _evaluator(self, message_id):
        evaluator = Mock()
        evaluator.evaluate.return_value = self._assessment(message_id)
        return evaluator

    def _accept(self, item):
        return update_work_item(item["work_item_id"], status="accepted", decision="accept",
            assessment={"semantic": asdict(self._assessment(item["message_id"]))}, path=self.ledger)

    def test_archive_keeps_both_roles_with_hashed_body_free_policy_and_search_provenance(self):
        self._learning(False)
        for role in ("user", "assistant"):
            metadata = self._capture(role, role=role)
            raw = ingest.read_archived_bytes(metadata)
            marker = json.loads(raw)["recording_policy"]
            self.assertEqual(marker, {"schema_version": 1, "policy_revision": 1,
                                     "mode": "retained", "memory_learning": False})
            self.assertEqual(metadata["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertFalse(self._message(role)["memory_learning_eligible"])
            results = archive_retrieval.retrieve_archive_passages(
                "concise technical", instance_id="fawkes", path=archive_retrieval.INDEX_PATH)
            self.assertIn(metadata["archive_id"], [entry["source_archive_id"] for entry in results])
        self.assertEqual(len(build_archive_context("conversation", instance_id="fawkes")), 2)
        self.assertEqual(build_archive_context("conversation", instance_id="fawkes",
                                               memory_learning_only=True), ())

    def test_persistence_rejects_private_foreign_and_invalid_policy_before_archive_write(self):
        for policy in (RecordingPolicy("fawkes", mode="private").effective(),
                       RecordingPolicy("other").effective(), {"memory_learning": True}):
            with self.subTest(policy=policy), patch("src.runtime.persistence.ingest_bytes") as archive:
                with self.assertRaises(RecordingPolicyError):
                    persist_live_message(instance_id="fawkes", conversation_id="conversation",
                        message_id="blocked", role="user", text="Synthetic private turn.",
                        recording_policy=policy)
                archive.assert_not_called()

    def test_legacy_payload_remains_eligible_and_is_not_rewritten(self):
        metadata = self._capture("legacy", legacy=True)
        before = ingest.read_archived_bytes(metadata)
        self.assertNotIn("recording_policy", json.loads(before))
        self.assertTrue(self._message("legacy")["memory_learning_eligible"])
        discovered = worker.discover_history(instance_id="fawkes", path=self.ledger)
        self.assertEqual([item["message_id"] for item in discovered], ["legacy"])
        self.assertEqual(ingest.read_archived_bytes(metadata), before)

    def test_present_malformed_markers_fail_closed_without_hiding_archive(self):
        valid = {"schema_version": 1, "policy_revision": 0, "mode": "retained", "memory_learning": True}
        invalid = [None, False, "true", {}, {"memory_learning": True},
                   {**valid, "schema_version": True}, {**valid, "schema_version": 2},
                   {**valid, "policy_revision": True}, {**valid, "policy_revision": -1},
                   {**valid, "mode": "private"}, {**valid, "memory_learning": 1},
                   {**valid, "memory_learning": "true"}, {**valid, "extra": "value"}]
        for index, marker in enumerate(invalid):
            with self.subTest(marker=marker):
                message_id = "malformed-" + str(index)
                self._raw_capture(message_id, marker)
                self.assertFalse(self._message(message_id)["memory_learning_eligible"])
        self.assertEqual(len(build_archive_context("conversation", instance_id="fawkes")), len(invalid))
        self.assertEqual(worker.discover_history(instance_id="fawkes", path=self.ledger), [])

    def test_off_on_rescan_never_discovers_disabled_messages_or_disabled_revisions(self):
        self._capture("old-eligible", legacy=True)
        self._learning(False)
        self._capture("off-user")
        self._capture("off-assistant", role="assistant")
        self.assertEqual(worker.discover_conversation("conversation", instance_id="fawkes", path=self.ledger), [])
        self.assertFalse(self.ledger.exists())
        self._learning(True)
        self._raw_capture("off-user", {"schema_version": 1, "policy_revision": 2,
                                      "mode": "retained", "memory_learning": True})
        self._capture("new-eligible")
        discovered = worker.discover_history(instance_id="fawkes", path=self.ledger)
        self.assertEqual({item["message_id"] for item in discovered}, {"old-eligible", "new-eligible"})
        self.assertFalse(self._message("off-user")["memory_learning_eligible"])
        self.assertEqual(self._message("off-user")["revision_count"], 2)
        self.assertEqual(worker.discover_history(instance_id="fawkes", path=self.ledger), [])

    def test_disabled_neighbor_content_is_excluded_from_evaluator_and_cannot_be_cited(self):
        self._learning(False)
        self._capture("off-user")
        self._capture("off-assistant", role="assistant")
        self._learning(True)
        self._capture("allowed")
        self._queue("allowed")
        evaluator = self._evaluator("allowed")
        result = worker.evaluate_next(instance_id="fawkes", evaluator=evaluator, path=self.ledger)
        self.assertEqual(result["status"], "accepted")
        context = evaluator.evaluate.call_args.kwargs["conversation_context"]
        self.assertEqual([entry["message_id"] for entry in context], ["allowed"])
        assessment = asdict(self._assessment("allowed"))
        assessment["supporting_message_ids"] = ("allowed", "off-user")
        assessment["supporting_archive_ids"] = (self._message("allowed")["source_archive_id"],
                                                self._message("off-user")["source_archive_id"])
        update_work_item(result["work_item_id"], status="queued", path=self.ledger)
        evaluator.evaluate.return_value = SemanticMemoryAssessment(**assessment)
        rejected = worker.evaluate_next(instance_id="fawkes", evaluator=evaluator, path=self.ledger)
        self.assertEqual(rejected["status"], "review")

    def test_direct_queued_disabled_candidate_cannot_evaluate_or_apply_after_reenable(self):
        self._learning(False)
        self._capture("disabled")
        queued = self._queue("disabled")
        self._learning(True)
        evaluator = self._evaluator("disabled")
        result = worker.evaluate_next(instance_id="fawkes", evaluator=evaluator, path=self.ledger)
        self.assertEqual(result["status"], "review")
        evaluator.evaluate.assert_not_called()
        self._accept(queued)
        with patch("src.memory.worker.consolidate_assessment") as consolidate:
            result = worker.apply_next_accepted(instance_id="fawkes", path=self.ledger)
        self.assertEqual(result["status"], "review")
        consolidate.assert_not_called()
        self.assertEqual(list((self.root / "memory/records").glob("*.json")), [])

    def test_current_off_preserves_queued_and_accepted_work_then_on_resumes(self):
        self._capture("queued")
        self._capture("accepted")
        queued = self._queue("queued")
        accepted = self._accept(self._queue("accepted"))
        before = list_work_items(instance_id="fawkes", path=self.ledger)
        self._learning(False)
        evaluator = self._evaluator("queued")
        self.assertEqual(worker.discover_history(instance_id="fawkes", path=self.ledger), [])
        self.assertIsNone(worker.evaluate_next(instance_id="fawkes", evaluator=evaluator, path=self.ledger))
        self.assertIsNone(worker.apply_next_accepted(instance_id="fawkes", path=self.ledger))
        self.assertEqual(list_work_items(instance_id="fawkes", path=self.ledger), before)
        evaluator.evaluate.assert_not_called()
        self._learning(True)
        evaluated = worker.evaluate_next(instance_id="fawkes", evaluator=evaluator, path=self.ledger)
        self.assertEqual(evaluated["work_item_id"], queued["work_item_id"])
        self.assertEqual(evaluated["status"], "accepted")
        applied = worker.apply_accepted_batch(instance_id="fawkes", path=self.ledger)
        self.assertEqual({item["work_item_id"] for item in applied},
                         {queued["work_item_id"], accepted["work_item_id"]})
        self.assertTrue(all(item["status"] == "consolidated" for item in applied))

    def test_setting_disabled_during_evaluation_preserves_queue_without_assessment(self):
        self._capture("candidate")
        queued = self._queue("candidate")
        assessment = self._assessment("candidate")
        evaluator = Mock()
        def evaluate(**kwargs):
            self._learning(False)
            return assessment
        evaluator.evaluate.side_effect = evaluate
        self.assertIsNone(worker.evaluate_next(instance_id="fawkes", evaluator=evaluator, path=self.ledger))
        saved = get_work_item(queued["work_item_id"], path=self.ledger)
        self.assertEqual(saved["status"], "queued")
        self.assertIsNone(saved["assessment"])

    def test_setting_disabled_during_matcher_blocks_mutation_and_preserves_accepted_queue(self):
        self._capture("candidate")
        accepted = self._accept(self._queue("candidate"))
        existing = {"instance_id": "fawkes", "memory_id": "existing", "status": "active",
                    "content": "Existing synthetic preference.", "memory_type": "preference"}
        matcher = Mock()
        def compare(**kwargs):
            self._learning(False)
            return SimpleNamespace(relation="supports")
        matcher.compare.side_effect = compare
        with patch("src.memory.worker.retrieve_memories", return_value=[existing]), patch(
            "src.memory.consolidate.strengthen_memory") as strengthen:
            self.assertIsNone(worker.apply_next_accepted(
                instance_id="fawkes", matcher=matcher, path=self.ledger))
        strengthen.assert_not_called()
        saved = get_work_item(accepted["work_item_id"], path=self.ledger)
        self.assertEqual(saved["status"], "accepted")
        self.assertEqual(saved["assessment"], accepted["assessment"])
        self.assertEqual(list((self.root / "memory/records").glob("*.json")), [])

    def test_legacy_learning_entrypoints_respect_current_policy_and_per_message_eligibility(self):
        self._learning(False)
        self._capture("disabled")
        evaluator = self._evaluator("disabled")
        self.assertEqual(extract_memory_candidates("conversation", instance_id="fawkes"), [])
        self.assertEqual(process_conversation("conversation", instance_id="fawkes", evaluator=evaluator), [])
        self.assertEqual(process_memory_conversation("conversation", instance_id="fawkes", evaluator=evaluator), [])
        self.assertEqual(dry_run_conversation("conversation", instance_id="fawkes", evaluator=evaluator)["evaluated_count"], 0)
        self._learning(True)
        self.assertEqual(extract_memory_candidates("conversation", instance_id="fawkes"), [])
        self.assertEqual(process_conversation("conversation", instance_id="fawkes", evaluator=evaluator), [])
        self.assertEqual(process_memory_conversation("conversation", instance_id="fawkes", evaluator=evaluator), [])
        self.assertEqual(dry_run_conversation("conversation", instance_id="fawkes", evaluator=evaluator)["evaluated_count"], 0)
        evaluator.evaluate.assert_not_called()

    def test_direct_pipeline_and_consolidation_reject_ineligible_candidate_or_cited_context(self):
        self._learning(False)
        self._capture("disabled")
        self._learning(True)
        message = self._message("disabled")
        evaluator = self._evaluator("disabled")
        with self.assertRaises(ArchiveContextReviewRequired):
            process_memory_candidate(message, instance_id="fawkes", evaluator=evaluator)
        evaluator.evaluate.assert_not_called()
        with patch("src.memory.consolidate.create_memory") as create:
            with self.assertRaises(ArchiveContextReviewRequired):
                consolidate_assessment(self._assessment("disabled"), instance_id="fawkes",
                    source_message_ids=("disabled",), source_archive_ids=(message["source_archive_id"],),
                    conversation_context=(message,))
        create.assert_not_called()

    def test_direct_legacy_candidate_and_assessment_pause_under_current_off_policy(self):
        self._capture("legacy", legacy=True)
        candidate = {"content": "Synthetic explicit preference."}
        evaluator = self._evaluator("legacy")
        assessment = self._assessment("legacy")
        self._learning(False)
        with self.assertRaises(MemoryLearningPaused):
            process_memory_candidate(candidate, instance_id="fawkes", evaluator=evaluator)
        evaluator.evaluate.assert_not_called()
        with patch("src.memory.consolidate.create_memory") as create:
            with self.assertRaises(MemoryLearningPaused):
                consolidate_assessment(assessment, instance_id="fawkes",
                    source_message_ids=assessment.supporting_message_ids,
                    source_archive_ids=assessment.supporting_archive_ids)
        create.assert_not_called()

    def test_each_matcher_mutation_branch_rechecks_current_setting(self):
        self._capture("candidate")
        assessment = self._assessment("candidate")
        existing = {"instance_id": "fawkes", "memory_id": "existing", "status": "active",
                    "content": "Different retained preference.", "memory_type": "preference"}
        for relation in ("duplicate", "supports", "revises", "supersedes", "unrelated"):
            with self.subTest(relation=relation):
                self._learning(True)
                matcher = Mock()
                def compare(**kwargs):
                    self._learning(False)
                    return SimpleNamespace(relation=relation)
                matcher.compare.side_effect = compare
                with ExitStack() as stack:
                    mutations = [stack.enter_context(patch("src.memory.consolidate." + name))
                                 for name in ("create_memory", "strengthen_memory", "revise_memory", "supersede_memory")]
                    with self.assertRaises(MemoryLearningPaused):
                        consolidate_assessment(assessment, instance_id="fawkes", matcher=matcher,
                            existing_memories=(existing,), source_message_ids=assessment.supporting_message_ids,
                            source_archive_ids=assessment.supporting_archive_ids)
                    for mutate in mutations:
                        mutate.assert_not_called()

    def test_unreadable_policy_fails_closed_before_queue_claim(self):
        self._capture("candidate")
        queued = self._queue("candidate")
        evaluator = self._evaluator("candidate")
        with patch.object(RecordingPolicyStore, "latch", side_effect=RecordingPolicyError("unavailable")):
            with self.assertRaises(RecordingPolicyError):
                worker.evaluate_next(instance_id="fawkes", evaluator=evaluator, path=self.ledger)
            with self.assertRaises(RecordingPolicyError):
                worker.apply_next_accepted(instance_id="fawkes", path=self.ledger)
        self.assertEqual(get_work_item(queued["work_item_id"], path=self.ledger), queued)
        evaluator.evaluate.assert_not_called()


class RecordingReviewCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RecordingMemoryEligibilityTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.policy = self.fixture.root, self.fixture.policy

    def denied(self, message_id="denied", *, role="user"):
        self.fixture._learning(False)
        metadata = self.fixture._capture(message_id, role=role)
        self.fixture._learning(True)
        self.assertFalse(self.fixture._message(message_id)["memory_learning_eligible"])
        return metadata

    @staticmethod
    def assessment(meaning="Synthetic durable preference."):
        return SemanticMemoryAssessment(True, "preference", meaning, .9, .8)

    def candidate(self, message_id, archive_id, *, references="both"):
        candidate = {"content": "Synthetic durable preference.", "instance_id": "fawkes"}
        if references in {"both", "message"}:
            candidate["source_message_ids"] = [message_id]
        if references in {"both", "archive"}:
            candidate["source_archive_ids"] = [archive_id]
        if references == "projection":
            candidate.update(message_id=message_id, source_archive_id=archive_id)
        return candidate

    def no_memory_writes(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        writers = [stack.enter_context(patch("src.memory.consolidate." + name)) for name in
                   ("create_memory", "strengthen_memory", "revise_memory", "supersede_memory")]
        return writers

    def test_R1_legacy_shaped_direct_candidate_resolves_sources_before_evaluator(self):
        for role in ("user", "assistant"):
            metadata = self.denied(role, role=role)
            for references in ("both", "message", "archive", "projection"):
                with self.subTest(role=role, references=references):
                    evaluator = Mock()
                    evaluator.evaluate.return_value = self.assessment()
                    candidate = self.candidate(role, metadata["archive_id"], references=references)
                    with patch("src.memory.pipeline.consolidate_assessment") as writer:
                        with self.assertRaises(ArchiveContextReviewRequired):
                            process_memory_candidate(candidate, instance_id="fawkes", evaluator=evaluator)
                        evaluator.evaluate.assert_not_called()
                        writer.assert_not_called()

    def test_R1_direct_assessment_without_optional_context_resolves_each_reference_form(self):
        metadata = self.denied()
        writers = self.no_memory_writes()
        for references in ("both", "message", "archive"):
            candidate = self.candidate("denied", metadata["archive_id"], references=references)
            with self.subTest(references=references), self.assertRaises(ArchiveContextReviewRequired):
                consolidate_assessment(self.assessment(), instance_id="fawkes",
                    source_message_ids=candidate.get("source_message_ids", ()),
                    source_archive_ids=candidate.get("source_archive_ids", ()))
        for writer in writers:
            writer.assert_not_called()

    def test_R1_allowed_projection_or_new_revision_cannot_override_an_older_denial(self):
        self.denied()
        latest = self.fixture._raw_capture("denied", {"schema_version": 1, "policy_revision": 2,
            "mode": "retained", "memory_learning": True})
        candidate = {**self.candidate("denied", latest["archive_id"]), "memory_learning_eligible": True}
        evaluator = Mock()
        evaluator.evaluate.return_value = self.assessment()
        with patch("src.memory.pipeline.consolidate_assessment") as writer:
            with self.assertRaises(ArchiveContextReviewRequired):
                process_memory_candidate(candidate, instance_id="fawkes", evaluator=evaluator)
            evaluator.evaluate.assert_not_called()
            writer.assert_not_called()

    def test_R1_malformed_stored_marker_is_not_legacy_eligibility(self):
        metadata = self.fixture._raw_capture("malformed", None)
        writers = self.no_memory_writes()
        with self.assertRaises(ArchiveContextReviewRequired):
            consolidate_assessment(self.assessment(), instance_id="fawkes",
                                    source_archive_ids=(metadata["archive_id"],))
        for writer in writers:
            writer.assert_not_called()

    def test_R1_missing_foreign_or_corrupt_sources_fail_closed(self):
        metadata = self.fixture._capture("owned")
        writers = self.no_memory_writes()
        for owner, archive_id in (("fawkes", "does-not-exist"), ("another-phoenix", metadata["archive_id"])):
            with self.subTest(owner=owner), self.assertRaises(ArchiveContextReviewRequired):
                consolidate_assessment(self.assessment(), instance_id=owner, source_archive_ids=(archive_id,))
        raw = self.root / "archive/raw" / metadata["raw_file"]
        raw.write_bytes(b"synthetic digest mismatch")
        with self.assertRaises(ArchiveContextReviewRequired):
            consolidate_assessment(self.assessment(), instance_id="fawkes", source_archive_ids=(metadata["archive_id"],))
        for writer in writers:
            writer.assert_not_called()

    def test_R1_genuine_stored_marker_absent_sources_still_evaluate_and_write(self):
        metadata = self.fixture._capture("legacy", legacy=True)
        original = ingest.read_archived_bytes(metadata)
        self.assertNotIn("recording_policy", json.loads(original))
        evaluator = Mock()
        evaluator.evaluate.return_value = self.assessment()
        result = process_memory_candidate(self.candidate("legacy", metadata["archive_id"]),
                                          instance_id="fawkes", evaluator=evaluator)
        self.assertEqual(result.action, "created")
        evaluator.evaluate.assert_called_once()
        direct = consolidate_assessment(self.assessment("Another synthetic durable preference."),
            instance_id="fawkes", source_message_ids=("legacy",), source_archive_ids=(metadata["archive_id"],))
        self.assertEqual(direct.action, "created")
        self.assertEqual(ingest.read_archived_bytes(metadata), original)

    def test_R1_rechecks_archive_after_evaluation_before_direct_publication(self):
        metadata = self.fixture._capture("changed")
        def evaluate(**kwargs):
            self.fixture._raw_capture("changed", {"schema_version": 1, "policy_revision": 0,
                "mode": "retained", "memory_learning": False})
            return self.assessment()
        evaluator = Mock()
        evaluator.evaluate.side_effect = evaluate
        writers = self.no_memory_writes()
        with self.assertRaises(ArchiveContextReviewRequired):
            process_memory_candidate(self.candidate("changed", metadata["archive_id"]),
                                      instance_id="fawkes", evaluator=evaluator)
        evaluator.evaluate.assert_called_once()
        for writer in writers:
            writer.assert_not_called()

    def test_R1_every_matcher_mutation_rechecks_new_denied_revision(self):
        writers = self.no_memory_writes()
        for relation in ("duplicate", "supports", "revises", "supersedes", "unrelated"):
            message_id = "changed-" + relation
            metadata = self.fixture._capture(message_id)
            def compare(**kwargs):
                self.fixture._raw_capture(message_id, {"schema_version": 1, "policy_revision": 0,
                    "mode": "retained", "memory_learning": False})
                return SimpleNamespace(relation=relation)
            matcher = Mock()
            matcher.compare.side_effect = compare
            with self.subTest(relation=relation), self.assertRaises(ArchiveContextReviewRequired):
                consolidate_assessment(self.assessment(), instance_id="fawkes", matcher=matcher,
                    source_message_ids=(message_id,), source_archive_ids=(metadata["archive_id"],),
                    existing_memories=({"memory_id": "synthetic-existing", "instance_id": "fawkes",
                        "content": "Other synthetic preference.", "memory_type": "preference"},))
            matcher.compare.assert_called_once()
        for writer in writers:
            writer.assert_not_called()

    def development_evaluator(self, action=None):
        proposal = propose_development(observation="Synthetic correction.", proposed_change="Synthetic proposal only.",
                                       rationale="Unit-test evidence only.", confidence=.7)
        evaluator = Mock()
        def evaluate(**kwargs):
            if action:
                action()
            return proposal
        evaluator.evaluate.side_effect = evaluate
        return evaluator

    def test_R2_correction_policy_is_rechecked_after_evaluator_before_save(self):
        for category in ("memory_learning", "personal_diagnostics"):
            self.policy.update({"categories": {"memory_learning": True, "personal_diagnostics": True}},
                               expected_revision=self.policy.load().revision)
            evaluator = self.development_evaluator(lambda: self.policy.update({"categories": {category: False}},
                                                    expected_revision=self.policy.load().revision))
            with self.subTest(category=category), \
                 patch("src.memory.development_cycle.retrieve_relevant_development", return_value=()), \
                 patch("src.memory.development_runtime.save_development_proposal") as save:
                with self.assertRaises(PermissionError):
                    process_user_correction("Synthetic explicit correction.", instance_id="fawkes",
                                             evaluator=evaluator, similarity=Mock())
                evaluator.evaluate.assert_called_once()
                save.assert_not_called()

    def test_R2_direct_correction_origin_cannot_skip_the_entry_guard(self):
        self.fixture._learning(False)
        evaluator = self.development_evaluator()
        with patch("src.memory.development_cycle.retrieve_relevant_development", return_value=()), \
             patch("src.memory.development_runtime.save_development_proposal") as save:
            with self.assertRaises(PermissionError):
                process_development_experience("Synthetic correction.", instance_id="fawkes", origin="user_correction",
                                               evaluator=evaluator, similarity=Mock())
            evaluator.evaluate.assert_not_called()
            save.assert_not_called()

    def test_R2_correction_source_cannot_reactivate_after_learning_is_reenabled(self):
        self.denied("correction-source")
        evaluator = self.development_evaluator()
        with patch("src.memory.development_cycle.retrieve_relevant_development", return_value=()), \
             patch("src.memory.development_runtime.save_development_proposal") as save:
            with self.assertRaises(ArchiveContextReviewRequired):
                process_user_correction("Synthetic correction.", instance_id="fawkes", evaluator=evaluator,
                                        similarity=Mock(), source_message_ids=("correction-source",))
            evaluator.evaluate.assert_not_called()
            save.assert_not_called()

    def test_R2_separately_authorized_development_evidence_is_not_disabled(self):
        self.fixture._learning(False)
        evaluator = self.development_evaluator()
        with patch("src.memory.development_cycle.retrieve_relevant_development", return_value=()), \
             patch("src.memory.development_runtime.save_development_proposal", return_value={"status": "proposed"}) as save:
            result = process_development_experience("Separately authorized synthetic Development evidence.",
                instance_id="fawkes", evaluator=evaluator, similarity=Mock(), origin="development_experience")
            self.assertEqual(result["record"], {"status": "proposed"})
            evaluator.evaluate.assert_called_once()
            save.assert_called_once()

    def legacy_shaped_context(self):
        self.denied("off-neighbor-user")
        self.denied("off-neighbor-assistant", role="assistant")
        self.fixture._capture("legacy-neighbor", legacy=True)
        # Simulate an older projected shape, including a misleading true flag.
        rows = [dict(self.fixture._message(identity)) for identity in
                ("off-neighbor-user", "off-neighbor-assistant", "legacy-neighbor")]
        for row in rows:
            row.pop("memory_learning_eligible")
        rows[1]["memory_learning_eligible"] = True
        return tuple(rows)

    def test_current_policy_is_last_check_after_authoritative_resolution(self):
        metadata = self.fixture._capture("resolution-source")
        original = canonical.load_message_states
        writers = self.no_memory_writes()
        for boundary in ("evaluate", "write"):
            self.fixture._learning(True)
            def turn_off(*args, **kwargs):
                states = original(*args, **kwargs)
                self.fixture._learning(False)
                return states
            evaluator = Mock()
            evaluator.evaluate.return_value = self.assessment()
            with self.subTest(boundary=boundary), patch.object(canonical, "load_message_states", side_effect=turn_off) as resolve:
                with self.assertRaises(MemoryLearningPaused):
                    if boundary == "evaluate":
                        process_memory_candidate(self.candidate("resolution-source", metadata["archive_id"]),
                                                  instance_id="fawkes", evaluator=evaluator)
                    else:
                        consolidate_assessment(self.assessment(), instance_id="fawkes",
                                                source_archive_ids=(metadata["archive_id"],))
                self.assertTrue(resolve.called)
                evaluator.evaluate.assert_not_called()
        for writer in writers:
            writer.assert_not_called()

    def test_direct_pipeline_filters_legacy_shaped_denied_neighbors_in_one_context_read(self):
        context = self.legacy_shaped_context()
        metadata = self.fixture._capture("candidate")
        evaluator = Mock()
        original = canonical.load_message_states
        with patch.object(canonical, "load_message_states", wraps=original) as resolve:
            observed_reads = []
            def evaluate(**kwargs):
                observed_reads.append(resolve.call_count)
                return SemanticMemoryAssessment(False, None, None, .9, .1)
            evaluator.evaluate.side_effect = evaluate
            process_memory_candidate(self.candidate("candidate", metadata["archive_id"]), instance_id="fawkes",
                                      evaluator=evaluator, conversation_context=context)
        sent = evaluator.evaluate.call_args.kwargs["conversation_context"]
        self.assertEqual([message["message_id"] for message in sent], ["legacy-neighbor"])
        # One candidate source resolution plus one shared context resolution,
        # not one metadata/raw-history scan per neighboring message.
        self.assertEqual(observed_reads, [2])

    def test_direct_matcher_filters_legacy_shaped_denied_neighbors(self):
        context = self.legacy_shaped_context()
        metadata = self.fixture._capture("candidate")
        matcher = Mock()
        matcher.compare.return_value = SimpleNamespace(relation="contradicts")
        result = consolidate_assessment(self.assessment(), instance_id="fawkes", matcher=matcher,
            source_archive_ids=(metadata["archive_id"],), conversation_context=context,
            existing_memories=({"memory_id": "existing", "instance_id": "fawkes",
                               "content": "Other preference.", "memory_type": "preference"},))
        self.assertEqual(result.action, "conflict_detected")
        sent = matcher.compare.call_args.kwargs["conversation_context"]
        self.assertEqual([message["message_id"] for message in sent], ["legacy-neighbor"])

    def test_missing_neighbor_is_review_not_silent_legacy_or_disabled_context(self):
        metadata = self.fixture._capture("candidate")
        evaluator = Mock()
        evaluator.evaluate.return_value = self.assessment()
        with patch("src.memory.pipeline.consolidate_assessment") as writer:
            with self.assertRaises(ArchiveContextReviewRequired):
                process_memory_candidate(self.candidate("candidate", metadata["archive_id"]), instance_id="fawkes",
                    evaluator=evaluator, conversation_context=({"role": "user", "content": "Unresolved context.",
                        "message_id": "missing", "source_archive_id": "missing"},))
            evaluator.evaluate.assert_not_called()
            writer.assert_not_called()

    def test_neighbor_denied_during_matcher_blocks_publication(self):
        metadata = self.fixture._capture("candidate")
        self.fixture._capture("neighbor")
        context = (self.fixture._message("neighbor"),)
        def compare(**kwargs):
            self.fixture._raw_capture("neighbor", {"schema_version": 1, "policy_revision": 0,
                "mode": "retained", "memory_learning": False})
            return SimpleNamespace(relation="supports")
        matcher = Mock()
        matcher.compare.side_effect = compare
        writers = self.no_memory_writes()
        with self.assertRaises(ArchiveContextReviewRequired):
            consolidate_assessment(self.assessment(), instance_id="fawkes", matcher=matcher,
                source_archive_ids=(metadata["archive_id"],), conversation_context=context,
                existing_memories=({"memory_id": "existing", "instance_id": "fawkes",
                                   "content": "Other preference.", "memory_type": "preference"},))
        matcher.compare.assert_called_once()
        for writer in writers:
            writer.assert_not_called()

    def test_correction_filters_legacy_shaped_denied_neighbors(self):
        context = self.legacy_shaped_context()
        evaluator = self.development_evaluator()
        with patch("src.memory.development_cycle.retrieve_relevant_development", return_value=()), \
             patch("src.memory.development_runtime.save_development_proposal") as save:
            process_user_correction("Synthetic correction.", instance_id="fawkes", evaluator=evaluator,
                                    similarity=Mock(), conversation_context=context)
            sent = evaluator.evaluate.call_args.kwargs["experience"]
            self.assertIn("legacy-neighbor", sent)
            self.assertNotIn("off-neighbor-user", sent)
            self.assertNotIn("off-neighbor-assistant", sent)
            save.assert_called_once()

    def test_correction_neighbor_revalidated_after_evaluator_before_publication(self):
        self.fixture._capture("neighbor")
        context = (self.fixture._message("neighbor"),)
        evaluator = self.development_evaluator(lambda: self.fixture._raw_capture("neighbor", {
            "schema_version": 1, "policy_revision": 0, "mode": "retained", "memory_learning": False}))
        with patch("src.memory.development_cycle.retrieve_relevant_development", return_value=()), \
             patch("src.memory.development_runtime.save_development_proposal") as save:
            with self.assertRaises(ArchiveContextReviewRequired):
                process_user_correction("Synthetic correction.", instance_id="fawkes", evaluator=evaluator,
                                        similarity=Mock(), conversation_context=context)
            evaluator.evaluate.assert_called_once()
            save.assert_not_called()



if __name__ == "__main__":
    unittest.main()

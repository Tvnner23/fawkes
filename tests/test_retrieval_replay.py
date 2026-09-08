import json
import tempfile
import unittest
from pathlib import Path

from src.runtime.retrieval_replay import (
    load_flight, promote_regression, record_live_flight, replay_flight,
)


class RetrievalReplayTests(unittest.TestCase):
    def _result(self):
        return {
            "text": "Use the retained evidence.",
            "memories": [{"memory_id": "memory-1", "memory_type": "preference",
                          "source_archive_ids": ["archive-source"]}],
            "archive_passages": [{"message_id": "old-message", "conversation_id": "old-conversation",
                                   "source_archive_id": "old-archive", "retrieval_score": 2.0}],
            "library_passages": [{"source_id": "source-1", "extraction_id": "extract-1",
                                   "segment_id": "segment-1", "retrieval_score": 1.0}],
            "conversation_context": [{"message_id": "near-message", "conversation_id": "conversation-1",
                                      "source_archive_id": "near-archive"}],
            "continuity": {"attempted": True, "status": "matched"},
            "retrieval_trace": {"capability_selection": ["continuity.retrieve"],
                                "retrieval_plan": {"version": "test-v1"},
                                "queries": [{"domain": "archive", "text": "why"}],
                                "exclusions": [{"kind": "message_ids", "values": ["request-1"]}],
                                "context_allocation": {"archive": 1},
                                "context_composition": {"package_id":"package-1",
                                    "composer_version":"production-context-composer-v1",
                                    "contains_source_bodies":False}},
            "usage": {"input_tokens": 10, "output_tokens": 4}, "warnings": [],
        }

    def _record(self, root, owner="fawkes", response="response-1"):
        return record_live_flight(instance_id=owner, conversation_id="conversation-1",
            request_message_id="request-1", response_message_id=response,
            response_archive_id="response-archive", request_text="why", model="fixture",
            result=self._result(), context_receipt_id=response, elapsed_ms=12.5, root=root)

    def test_flight_is_immutable_scoped_and_preserves_decision_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self._record(tmp)
            second = self._record(tmp)
            loaded = load_flight("fawkes", "response-1", root=tmp)
            self.assertEqual(first, second)
            self.assertEqual(first, loaded)
            self.assertEqual({item["domain"] for item in loaded["selected_evidence"]},
                             {"memory", "archive", "library", "conversation"})
            self.assertEqual(loaded["execution"]["latency_ms"], 12.5)
            self.assertFalse(loaded["ordinary_history_mutated_by_recording"])
            self.assertEqual(loaded["context_composition"]["package_id"],"package-1")
            self.assertFalse((Path(tmp) / "other" / "flights" / "response-1.json").exists())

    def test_replay_receives_detached_input_and_writes_only_replay_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            flight = self._record(tmp)
            original = json.loads(json.dumps(flight))

            def candidate(detached):
                detached["request"]["text"] = "mutated detached copy"
                return {"selected_evidence": list(reversed(detached["selected_evidence"])),
                        "response_text": "candidate response", "latency_ms": 3}

            replay = replay_flight(instance_id="fawkes", flight_id="response-1",
                candidate_id="lexical", candidate_version="2", runner=candidate, root=tmp)
            self.assertTrue(replay["evidence_diff"]["order_changed"])
            self.assertFalse(replay["ordinary_history_mutated"])
            self.assertFalse(replay["response_diff"]["semantic_quality_assessed"])
            self.assertEqual(load_flight("fawkes", "response-1", root=tmp), original)
            self.assertFalse((Path(tmp) / "archive").exists())
            self.assertFalse((Path(tmp) / "memory").exists())

    def test_regression_requires_explicit_review_and_is_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._record(tmp)
            replay = replay_flight(instance_id="fawkes", flight_id="response-1",
                candidate_id="candidate", candidate_version="1", root=tmp,
                runner=lambda value: {"selected_evidence": []})
            with self.assertRaises(ValueError):
                promote_regression(instance_id="fawkes", replay_id=replay["replay_id"],
                    reviewer_principal_id="rider:fawkes", failure_statement=" ",
                    expected_evidence=[], root=tmp)
            case = promote_regression(instance_id="fawkes", replay_id=replay["replay_id"],
                reviewer_principal_id="rider:fawkes", failure_statement="lost required evidence",
                expected_evidence=self._result()["archive_passages"], root=tmp)
            self.assertFalse(case["automatic_promotion"])
            self.assertEqual(case["reviewer_principal_id"], "rider:fawkes")

    def test_other_phoenix_cannot_load_or_replay_flight(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._record(tmp, owner="fawkes")
            self.assertIsNone(load_flight("other", "response-1", root=tmp))
            with self.assertRaises(ValueError):
                replay_flight(instance_id="other", flight_id="response-1", candidate_id="x",
                              candidate_version="1", runner=lambda value: {}, root=tmp)


if __name__ == "__main__":
    unittest.main()

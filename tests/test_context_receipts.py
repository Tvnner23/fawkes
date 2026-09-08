import tempfile
import unittest
from pathlib import Path

from src.runtime.context_receipts import build_context_inspector, load_context_receipt, save_context_receipt


class FawkesContextReceiptTests(unittest.TestCase):
    def _kwargs(self):
        return {
            "instance_id": "fawkes",
            "conversation_id": "conversation-1",
            "request_message_id": "message-user",
            "response_message_id": "message-fawkes",
            "response_archive_id": "archive-response",
            "model": "test-model",
            "memories": (
                {
                    "memory_id": "memory-1",
                    "memory_type": "preference",
                    "content": "The rider prefers concise explanations.",
                    "source_message_ids": ["evidence-message"],
                    "source_archive_ids": ["evidence-archive"],
                    "source_work_item_ids": ["work-1"],
                },
            ),
            "archive_passages": (
                {
                    "conversation_id": "historical-conversation",
                    "message_id": "historical-message",
                    "role": "user",
                    "content": "A historical statement.",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "source_archive_id": "historical-archive",
                    "canonicalizer_version": "structured-v1",
                    "retrieval_score": -2.0,
                    "matched_terms": ["historical"],
                },
            ),
            "conversation_context": (
                {
                    "conversation_id": "conversation-1",
                    "message_id": "previous-message",
                    "role": "assistant",
                    "content": "Previous response.",
                    "source_archive_id": "previous-archive",
                },
            ),
            "development_sources": ("proposal-1",),
            "research_sources": ({
                "research_session_id": "research-session-1",
                "research_ids": ["research-1"],
                "capability_receipt_ids": ["receipt-1"],
            },),
            "library_sources": ({
                "source_id": "source-1",
                "source_title": "Networking Fundamentals",
                "source_sha256": "abc",
                "extraction_id": "extraction-1",
                "extractor": "fixture",
                "extractor_version": "1",
                "segment_id": "segment-1",
                "text": "ARP resolves IPv4 addresses.",
                "location": {"page_number": 142, "page_label": "128"},
                "matched_terms": ["arp"],
                "retrieval_score": 1.0,
                "trust": "untrusted_library_content",
            },),
            "presentation": {
                "schema_version": 1,
                "text": "A clearer answer.",
                "blocks": [],
                "citations": [],
            },
        }

    def test_receipt_preserves_exact_context_source_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / "message-fawkes.json"
            saved = save_context_receipt(**self._kwargs(), path=path)
            loaded = load_context_receipt(
                "message-fawkes", directory=directory
            )

        self.assertEqual(saved, loaded)
        self.assertEqual(loaded["memory_sources"][0]["memory_id"], "memory-1")
        self.assertEqual(
            loaded["memory_sources"][0]["source_archive_ids"],
            ["evidence-archive"],
        )
        self.assertEqual(
            loaded["archive_sources"][0]["source_archive_id"],
            "historical-archive",
        )
        self.assertEqual(loaded["development_sources"], ["proposal-1"])
        self.assertEqual(
            loaded["research_sources"][0]["research_session_id"],
            "research-session-1",
        )
        self.assertEqual(loaded["schema_version"], 7)
        self.assertEqual(loaded["library_sources"][0]["segment_id"], "segment-1")
        self.assertEqual(loaded["presentation"]["text"], "A clearer answer.")

    def test_receipt_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            first = save_context_receipt(**self._kwargs(), path=path)
            second = save_context_receipt(**self._kwargs(), path=path)

        self.assertEqual(first, second)

    def test_receipt_id_cannot_be_reused_for_different_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            save_context_receipt(**self._kwargs(), path=path)
            changed = self._kwargs()
            changed["memories"] = ()
            with self.assertRaises(ValueError):
                save_context_receipt(**changed, path=path)

    def test_context_inspector_is_body_free_and_links_matching_replay(self):
        receipt = {"receipt_id": "response-1", "response_message_id": "response-1",
                   "instance_id": "fawkes", "retrieval_audit": {
            "context_composition": {"package_id": "package-1", "contains_source_bodies": False,
                "purpose_profile": {"purpose": "response_model_context", "profile_version": "1"},
                "allocation": {"policy_version": "allocation-v1", "input_evidence_ids": ["e1", "e2"],
                    "selected_evidence_ids": ["e1"], "omitted_evidence_ids": ["e2"],
                    "per_domain_selected": {"memory": 1}, "warnings": ["bounded"]},
                "source_summary": [{"evidence_id": "e1", "domain": "memory",
                    "body_sha256": "body-digest", "uncertainty": {"kind": "bounded"},
                    "contradiction_group_ids": ["cg-1"], "ambiguity_set_ids": ["ag-1"]}],
                "transmission_manifest_id": "permit-1"},
            "transmission_authorization": {"status": "authorized", "manifest_id": "permit-1",
                                             "authorized_evidence_ids": ["e1"]},
            "exclusions": [{"evidence_id": "e2", "domain": "library", "reason": "budget"}]}}
        flight = {"instance_id": "fawkes", "response_message_id": "response-1",
                  "context_receipt_id": "response-1", "flight_id": "response-1",
                  "evidence_sha256": "flight-digest", "request": {"text": "private query"},
                  "response": {"text": "private response"}}
        value = build_context_inspector(receipt, flight=flight)
        encoded = str(value)
        self.assertEqual(value["composition_status"], "retrieved_context_used")
        self.assertEqual(value["source_domains"], {"memory": 1})
        self.assertEqual(value["transmission"]["manifest_id"], "permit-1")
        self.assertEqual(value["replay"]["evidence_sha256"], "flight-digest")
        self.assertFalse(value["contains_source_bodies"])
        self.assertFalse(value["authority"]["creates_authority"])
        self.assertNotIn("private query", encoded); self.assertNotIn("private response", encoded)

    def test_context_inspector_zero_retrieval_and_mismatch_fail_closed(self):
        receipt = {"receipt_id": "response-1", "response_message_id": "response-1",
                   "instance_id": "fawkes", "retrieval_audit": {
                       "context_composition": {"allocation": {"selected_evidence_ids": [],
                           "omitted_evidence_ids": ["e1"]}, "source_summary": []}}}
        value = build_context_inspector(receipt)
        self.assertEqual(value["composition_status"], "zero_retrieval")
        self.assertEqual(value["transmission"]["status"], "no_retrieved_evidence")
        with self.assertRaisesRegex(ValueError, "do not match"):
            build_context_inspector(receipt, flight={"instance_id": "foreign",
                "response_message_id": "response-1", "context_receipt_id": "response-1"})


if __name__ == "__main__":
    unittest.main()

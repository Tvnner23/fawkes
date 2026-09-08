import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.history_staging import ChatGPTExportAdapter, InheritedHistoryStore
from src.history_validation import (
    HISTORICAL_CORPUS_VALIDATION_DEFINITION, HistoricalCorpusValidator,
)
from src.runtime.chat import FawkesChatRuntime
from src.runtime.chat_service import FawkesChatService


def fixture():
    payload = [{"id": "duplicate", "title": "First", "current_node": "answer", "mapping": {
        "empty": {"parent": None, "children": ["question"], "message": None},
        "question": {"parent": "empty", "children": ["answer"], "message": {"id": "same-message",
            "author": {"role": "user"}, "create_time": 1,
            "content": {"content_type": "text", "parts": ["What is Fawkes?"]}}},
        "answer": {"parent": "question", "children": [], "message": {"id": "answer-message",
            "author": {"role": "assistant", "name": "ChatGPT"}, "create_time": 2,
            "content": {"content_type": "text", "parts": ["Founding evidence only."]}}}}},
        {"id": "duplicate", "title": "Second", "mapping": {"other": {"parent": None, "children": [],
            "message": {"id": "same-message", "author": {"role": "user"}, "create_time": 3,
            "content": {"content_type": "text", "parts": ["Fawkes duplicate identity test"]}}}}},
        {"title": "malformed"}]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("conversations.json", json.dumps(payload))
    return output.getvalue()


def authority(owner):
    return {"actor_principal": f"rider:{owner}", "authorization": {
        "authorization_id": f"authorization:{owner}", "mode": "explicit_confirmation",
        "scope": "stage_inherited_history_export", "instance_id": owner,
        "principal_id": f"rider:{owner}"}}


class HistoricalCorpusValidationTests(unittest.TestCase):
    def stage(self, root, owner="phoenix-one"):
        store = InheritedHistoryStore(owner, root=root / "database/inherited_history",
                                      processing_root=root / "database/processing")
        manifest = store.stage(fixture(), adapter=ChatGPTExportAdapter(), **authority(owner))
        return store, manifest

    def test_contract_is_explicit_read_only_and_partial_in_runtime(self):
        public = HISTORICAL_CORPUS_VALIDATION_DEFINITION.public_manifest()
        self.assertEqual(public["authorization_mode"], "task_request")
        self.assertEqual(public["authority_actions"], ["read", "analyze"])
        self.assertIn("Memory absorption", public["inappropriate_use"])
        runtime = FawkesChatRuntime(client=object(), instance_id="phoenix-one")
        manifest = next(item for item in runtime.capability_context()
                        if item["name"] == "history.validate_corpus")
        self.assertEqual(manifest["availability"], "partial")

    def test_reconciles_original_projection_branches_duplicates_and_exact_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, staged = self.stage(Path(tmp))
            report = HistoricalCorpusValidator(store).validate(staged["export_id"],
                known_queries=({"query": "Fawkes", "minimum_results": 2},))
        self.assertEqual(report["status"], "qualified_with_source_warnings")
        self.assertFalse(report["failed_checks"])
        self.assertTrue(all(item["status"] == "pass" for item in report["checks"]))
        self.assertEqual(report["identity_attribution"], "unassessed")
        self.assertEqual(report["native_boundary_status"], "boundary_unknown")
        self.assertFalse(report["automatic_chat_context"])
        self.assertEqual(report["memory_promotion"], "prohibited")

    def test_validation_is_idempotent_and_two_phoenix_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store, staged = self.stage(root)
            validator = HistoricalCorpusValidator(store)
            first = validator.validate(staged["export_id"], known_queries=("Fawkes",))
            second = validator.validate(staged["export_id"], known_queries=("Fawkes",))
            other = InheritedHistoryStore("phoenix-two", root=root / "database/inherited_history",
                                          processing_root=root / "database/processing")
            with self.assertRaises(LookupError):
                HistoricalCorpusValidator(other).validate(staged["export_id"])
        self.assertEqual(first, second)

    def test_tampered_projection_fails_without_mutating_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store, staged = self.stage(root)
            original = store.root / store.get_export(staged["export_id"])["original_evidence_reference"]
            before = original.read_bytes()
            db = store._connect()
            try:
                row = db.execute("SELECT message_id,record_json FROM staged_messages LIMIT 1").fetchone()
                record = json.loads(row[1]); record["text"] = "tampered projection"
                db.execute("UPDATE staged_messages SET text=?,record_json=? WHERE message_id=?",
                           (record["text"], json.dumps(record), row[0])); db.commit()
            finally: db.close()
            report = HistoricalCorpusValidator(store).validate(staged["export_id"])
            self.assertEqual(before, original.read_bytes())
        self.assertEqual(report["status"], "failed")
        self.assertIn("message_fields_and_exact_text", report["failed_checks"])

    def test_known_query_absence_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, staged = self.stage(Path(tmp))
            report = HistoricalCorpusValidator(store).validate(staged["export_id"],
                known_queries=({"query": "definitely absent", "minimum_results": 1},))
        self.assertEqual(report["status"], "failed")
        self.assertIn("known_queries", report["failed_checks"])

    def test_authenticated_service_capability_path_does_not_put_query_text_in_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store, staged = self.stage(root)
            service = object.__new__(FawkesChatService)
            service.instance_id = "phoenix-one"
            service._inherited_history_root = root / "database/inherited_history"
            service._capability_receipt_dir = root / "database/capability_receipts"
            report = service.historical_corpus_validation({
                "export_id": staged["export_id"], "known_queries": ("Fawkes",)})
            receipts = list(service._capability_receipt_dir.rglob("*.json"))
            encoded = receipts[0].read_text(encoding="utf-8")
        self.assertEqual(report["status"], "qualified_with_source_warnings")
        self.assertNotIn('"Fawkes"', encoded)
        self.assertIn('"argument_sha256"', encoded)


if __name__ == "__main__":
    unittest.main()

import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.history_staging import (
    ChatGPTExportAdapter, ExportAdapter, InheritedHistoryStore,
    INHERITED_HISTORY_STAGING_DEFINITION, stage_authorized_export,
)
from src.runtime.phase0_integrity import (
    audit_phoenix_state, create_complete_state_backup, restore_complete_state_backup,
)


def export_bytes(*, partial=False):
    mapping = {
        "node-user": {"id": "node-user", "parent": None, "children": ["node-assistant"],
            "message": {"id": "message-user", "author": {"role": "user"},
                "create_time": 10, "content": {"content_type": "text", "parts": ["We are designing Fawkes."]}}},
        "node-assistant": {"id": "node-assistant", "parent": "node-user", "children": [],
            "message": {"id": "message-assistant", "author": {"role": "assistant", "name": "ChatGPT"},
                "create_time": 11, "content": {"content_type": "text", "parts": ["My Memory will preserve evidence."]}}},
    }
    payload = [{"id": "conversation-source-1", "title": "Founding discussion",
                "create_time": 9, "update_time": 12, "current_node": "node-assistant", "mapping": mapping}]
    if partial: payload.append({"title": "missing id"})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("conversations.json", json.dumps(payload))
    return output.getvalue()


def stage_args(owner):
    principal = f"rider:{owner}"
    return {"actor_principal": principal, "authorization": {
        "authorization_id": f"authorization:{owner}", "mode": "explicit_confirmation",
        "scope": "stage_inherited_history_export", "instance_id": owner, "principal_id": principal}}


class InheritedHistoryStagingTests(unittest.TestCase):
    def store(self, root, owner="phoenix-one"):
        return InheritedHistoryStore(owner, root=root / "database/inherited_history",
            processing_root=root / "database/processing")

    def test_provider_neutral_adapter_and_capability_are_explicit(self):
        self.assertTrue(issubclass(ChatGPTExportAdapter, ExportAdapter))
        manifest = INHERITED_HISTORY_STAGING_DEFINITION.public_manifest()
        self.assertEqual(manifest["authorization_mode"], "explicit_confirmation")
        self.assertIn("create autobiographical Memory", manifest["inappropriate_use"])
        self.assertIn("only ChatGPT export ZIP is currently supported", manifest["limitations"])

    def test_staging_requires_explicit_matching_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(Path(tmp)); raw = export_bytes()
            with self.assertRaises(TypeError):
                store.stage(raw, adapter=ChatGPTExportAdapter())
            bad = stage_args("phoenix-one"); bad["authorization"]["instance_id"] = "phoenix-two"
            with self.assertRaises(PermissionError):
                store.stage(raw, adapter=ChatGPTExportAdapter(), **bad)
            with patch("src.history_staging.MAX_EXPORT_BYTES", 2):
                with self.assertRaisesRegex(ValueError, "intake size"):
                    store.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            self.assertFalse((store.root / "originals").exists())

    def test_official_import_boundary_enforces_capability_permission_and_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); arguments = stage_args("phoenix-one")
            common = dict(instance_id="phoenix-one", adapter=ChatGPTExportAdapter(),
                actor_principal=arguments["actor_principal"], authorization=arguments["authorization"],
                root=root / "database/inherited_history", processing_root=root / "database/processing",
                capability_receipt_dir=root / "database/capability_receipts")
            with self.assertRaises(PermissionError):
                stage_authorized_export(export_bytes(), explicitly_confirmed=False, **common)
            with self.assertRaises(PermissionError):
                stage_authorized_export(export_bytes(), explicitly_confirmed=True, granted_permissions=(), **common)
            result = stage_authorized_export(export_bytes(), explicitly_confirmed=True, **common)
            self.assertTrue(result["capability_receipt_id"])
            self.assertEqual(result["authorization_reference"], "authorization:phoenix-one")

    def test_exact_identity_hierarchy_and_inert_provenance_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = export_bytes(); store = self.store(root)
            result = store.stage(raw, adapter=ChatGPTExportAdapter(), filename="chatgpt-export.zip", **stage_args("phoenix-one"))
            hits = store.search("Memory")
            self.assertEqual(result["conversation_count"], 1)
            self.assertEqual(result["message_count"], 2)
            self.assertEqual(len(hits), 1)
            record = hits[0]
            self.assertEqual(record["source_conversation_id"], "conversation-source-1")
            self.assertEqual(record["source_node_id"], "node-assistant")
            self.assertEqual(record["source_parent_node_id"], "node-user")
            self.assertEqual(record["source_message_id"], "message-assistant")
            self.assertEqual(record["history_era"], "inherited_history")
            self.assertEqual(record["relationship_provenance"], "founding_developmental")
            self.assertEqual(record["identity_attribution"], "unassessed")
            self.assertEqual(record["native_boundary_status"], "boundary_unknown")
            self.assertNotEqual(record["native_boundary_status"], "proven_native")
            original = store.root / result["original_evidence_reference"]
            self.assertEqual(original.read_bytes(), raw)

    def test_reimport_is_idempotent_and_processing_lifecycle_completes_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = self.store(root); raw = export_bytes()
            first = store.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            replay = store.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            self.assertFalse(first["idempotent_replay"]); self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(first["export_id"], replay["export_id"])
            db = sqlite3.connect(root / "database/processing/phoenix-one/ledger.sqlite3")
            self.assertEqual(db.execute("SELECT count(*) FROM processing_work_items").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT status FROM processing_work_items").fetchone()[0], "completed")
            db.close()

    def test_two_phoenixes_are_physically_and_logically_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = export_bytes()
            one = self.store(root, "phoenix-one"); two = self.store(root, "phoenix-two")
            first = one.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            self.assertEqual(two.search("Fawkes"), [])
            self.assertIsNone(two.get_export(first["export_id"]))
            second = two.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-two"))
            self.assertEqual(second["instance_id"], "phoenix-two")
            self.assertNotEqual(one.index_path, two.index_path)

    def test_partial_and_malformed_exports_are_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = self.store(root)
            partial = store.stage(export_bytes(partial=True), adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            self.assertEqual(partial["staging_status"], "partial")
            self.assertEqual(partial["warnings"][0]["code"], "malformed_conversation")
            with self.assertRaisesRegex(ValueError, "valid ZIP"):
                store.stage(b"not zip", adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            failed_originals = list((store.root / "originals").glob("*.zip"))
            failed_receipts = list((store.root / "receipts").glob("*.json"))
            self.assertEqual(len(failed_originals), 2)
            self.assertEqual(len(failed_receipts), 2)
            malformed_receipt = next(json.loads(path.read_text()) for path in failed_receipts
                                     if json.loads(path.read_text())["size_bytes"] == len(b"not zip"))
            self.assertEqual(malformed_receipt["identity_attribution"], "unassessed")
            self.assertEqual(malformed_receipt["native_boundary_status"], "boundary_unknown")
            db = sqlite3.connect(root / "database/processing/phoenix-one/ledger.sqlite3")
            statuses = dict(db.execute("SELECT idempotency_key,status FROM processing_work_items"))
            db.close()
            self.assertIn("failed_terminal", statuses.values())

    def test_message_less_nodes_and_duplicate_source_ids_remain_distinct(self):
        payload = [
            {"id": "duplicate-conversation", "mapping": {
                "root": {"parent": None, "children": ["message-node"], "message": None},
                "message-node": {"parent": "root", "children": [], "message": {"id": "duplicate-message",
                    "author": {"role": "user"}, "content": {"content_type": "text", "parts": ["first duplicate"]}}}}},
            {"id": "duplicate-conversation", "mapping": {
                "message-node": {"parent": None, "children": [], "message": {"id": "duplicate-message",
                    "author": {"role": "user"}, "content": {"content_type": "text", "parts": ["second duplicate"]}}}}},
        ]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive: archive.writestr("conversations.json", json.dumps(payload))
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(Path(tmp)); store.stage(buffer.getvalue(), adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            db = sqlite3.connect(store.index_path)
            self.assertEqual(db.execute("SELECT count(*) FROM staged_conversations").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM staged_nodes").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT count(*) FROM staged_messages").fetchone()[0], 2)
            db.close()
            first = store.search("first duplicate")[0]; second = store.search("second duplicate")[0]
            self.assertNotEqual(first["message_id"], second["message_id"])
            self.assertEqual(store.original_message(first["message_id"])["exact_original_text"], "first duplicate")
            self.assertEqual(store.original_message(second["message_id"])["exact_original_text"], "second duplicate")

    def test_unexpected_parser_failure_is_retryable_and_never_strands_running_work(self):
        class BrokenAdapter(ExportAdapter):
            provider_id = "broken_test"; format_id = "broken"; version = "1"
            def parse(self, raw_export): raise RuntimeError("synthetic parser crash")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = self.store(root)
            with self.assertRaises(RuntimeError):
                store.stage(export_bytes(), adapter=BrokenAdapter(), **stage_args("phoenix-one"))
            db = sqlite3.connect(root / "database/processing/phoenix-one/ledger.sqlite3")
            status = db.execute("SELECT status FROM processing_work_items").fetchone()[0]; db.close()
            self.assertEqual(status, "failed_retryable")
            self.assertTrue(any((store.root / "originals").glob("*.zip")))

    def test_uncatchable_interruption_requires_explicit_recovery_before_resume(self):
        class InterruptOnceAdapter(ChatGPTExportAdapter):
            provider_id = "interrupt_test"
            def __init__(self): self.interrupt = True
            def parse(self, raw_export):
                if self.interrupt:
                    self.interrupt = False
                    raise KeyboardInterrupt()
                return super().parse(raw_export)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = self.store(root); adapter = InterruptOnceAdapter()
            arguments = stage_args("phoenix-one")
            with self.assertRaises(KeyboardInterrupt):
                store.stage(export_bytes(), adapter=adapter, **arguments)
            with self.assertRaisesRegex(RuntimeError, "confirm the prior worker"):
                store.stage(export_bytes(), adapter=adapter, **arguments)
            result = store.stage(export_bytes(), adapter=adapter,
                                 resume_confirmed_interruption=True, **arguments)
            self.assertEqual(result["staging_status"], "complete")
            db = sqlite3.connect(root / "database/processing/phoenix-one/ledger.sqlite3")
            events = [json.loads(row[0]) for row in db.execute(
                "SELECT event_json FROM processing_events ORDER BY occurred_at,event_id")]
            db.close()
            self.assertTrue(any(event["operation_id"].startswith("confirmed-interruption")
                                for event in events))

    def test_retryable_write_failure_resumes_same_work_item(self):
        class FailOnceStore(InheritedHistoryStore):
            failed = False
            def _persist(self, *args, **kwargs):
                if not self.failed:
                    self.failed = True
                    raise OSError("synthetic disk interruption")
                return super()._persist(*args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = export_bytes()
            store = FailOnceStore("phoenix-one", root=root / "database/inherited_history",
                                  processing_root=root / "database/processing")
            with self.assertRaises(OSError): store.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            completed = store.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            self.assertEqual(completed["staging_status"], "complete")
            db = sqlite3.connect(root / "database/processing/phoenix-one/ledger.sqlite3")
            item = db.execute("SELECT status,attempt_count FROM processing_work_items").fetchone()
            db.close()
            self.assertEqual(item[0], "completed"); self.assertEqual(item[1], 2)

    def test_staging_does_not_create_memory_archive_or_continuity_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.store(root).stage(export_bytes(), adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            self.assertFalse((root / "memory").exists())
            self.assertFalse((root / "archive").exists())
            self.assertFalse((root / "database/canonical_archive.sqlite3").exists())
            self.assertFalse((root / "conversations").exists())

    def test_complete_backup_and_isolated_restore_preserve_exact_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "live"
            (root / "instances").mkdir(parents=True)
            (root / "instances/registry.json").write_text(json.dumps({"schema_version": 1, "instances": [
                {"instance_id": "phoenix-one", "name": "One"}, {"instance_id": "phoenix-two", "name": "Two"}]}) + "\n")
            raw = export_bytes(); one = self.store(root, "phoenix-one"); two = self.store(root, "phoenix-two")
            one_result = one.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            two.stage(raw, adapter=ChatGPTExportAdapter(), **stage_args("phoenix-two"))
            self.assertTrue(audit_phoenix_state("phoenix-one", root=root)["gate_satisfied"])
            backup, _ = create_complete_state_backup("phoenix-one", Path(tmp) / "backups", source_root=root)
            restored = Path(tmp) / "restored"
            restore_complete_state_backup(backup, restored, instance_id="phoenix-one")
            restored_store = self.store(restored, "phoenix-one")
            restored_manifest = restored_store.get_export(one_result["export_id"])
            self.assertEqual(restored_manifest["export_id"], one_result["export_id"])
            self.assertEqual((restored_store.root / restored_manifest["original_evidence_reference"]).read_bytes(), raw)
            self.assertFalse((restored / "database/inherited_history/phoenix-two").exists())


if __name__ == "__main__": unittest.main()

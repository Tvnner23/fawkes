import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.runtime.phase0_integrity import (
    audit_phoenix_state, create_complete_state_backup,
    restore_complete_state_backup, verify_complete_state_backup,
)


class PhaseZeroIntegrityTests(unittest.TestCase):
    def _state(self, root):
        for directory in ("instances", "conversations", "database/context_receipts",
                          "database/preferences/one", "archive/meta", "archive/raw",
                          "memory/records"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "instances/registry.json").write_text(json.dumps({"schema_version": 1, "instances": [
            {"instance_id": "one", "name": "One"}, {"instance_id": "two", "name": "Two"}]}))
        (root / "conversations/registry.json").write_text(json.dumps({"schema_version": 1, "conversations": [
            {"conversation_id": "c1", "instance_id": "one"},
            {"conversation_id": "legacy", "instance_id": None},
            {"conversation_id": "c2", "instance_id": "two"}]}))
        (root / "database/preferences/one/event_sounds.json").write_text(json.dumps({"schema_version": 1}))
        (root / "database/context_receipts/one.json").write_text(json.dumps({"instance_id": "one"}))
        (root / "database/context_receipts/two.json").write_text(json.dumps({"instance_id": "two"}))
        (root / "memory/records/legacy.json").write_text(json.dumps({"memory_id": "legacy"}))
        for owner in ("one", "two"):
            (root / f"archive/meta/{owner}.json").write_text(json.dumps({"instance_id": owner, "archive_id": owner}))
            (root / f"archive/raw/{owner}.txt").write_bytes(f"{owner} exact".encode())
        connection = sqlite3.connect(root / "database/memory_processing.sqlite3")
        connection.execute("CREATE TABLE memory_work_items (work_item_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL)")
        connection.executemany("INSERT INTO memory_work_items VALUES (?, ?)", (("w1", "one"), ("w2", "two")))
        connection.commit(); connection.close()

    def test_audit_reports_legacy_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self._state(root)
            legacy = root / "memory/records/legacy.json"; before = legacy.read_bytes()
            report = audit_phoenix_state("one", root=root); after = legacy.read_bytes()
        self.assertTrue(report["gate_satisfied"])
        self.assertGreaterEqual(report["summary"]["legacy_unscoped"], 2)
        self.assertGreaterEqual(report["summary"]["legacy_path_scoped"], 1)
        self.assertEqual(before, after)

    def test_mismatch_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self._state(root)
            path = root / "database/research/one/bad.json"
            path.parent.mkdir(parents=True); path.write_text(json.dumps({"instance_id": "two"}))
            report = audit_phoenix_state("one", root=root)
        self.assertFalse(report["gate_satisfied"])
        self.assertEqual(report["summary"]["ownership_mismatch"], 1)

    def test_backup_restore_isolated_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"; self._state(root)
            backup, manifest = create_complete_state_backup("one", Path(tmp) / "backups", source_root=root)
            self.assertGreater(len(manifest["files"]), 3)
            restored = Path(tmp) / "restored"
            restore_complete_state_backup(backup, restored, instance_id="one")
            self.assertEqual((restored / "archive/raw/one.txt").read_bytes(), b"one exact")
            self.assertFalse((restored / "archive/raw/two.txt").exists())
            registry = json.loads((restored / "instances/registry.json").read_text())
            self.assertEqual([item["instance_id"] for item in registry["instances"]], ["one"])
            db = sqlite3.connect(restored / "database/memory_processing.sqlite3")
            self.assertEqual(db.execute("SELECT instance_id FROM memory_work_items").fetchall(), [("one",)])
            db.close()
            target = next((backup / "files").rglob("one.txt")); target.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "integrity"):
                verify_complete_state_backup(backup, expected_instance_id="one")

    def test_restore_rejects_wrong_phoenix_and_nonempty_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"; self._state(root)
            backup, _ = create_complete_state_backup("one", Path(tmp) / "backups", source_root=root)
            with self.assertRaisesRegex(ValueError, "different Phoenix"):
                restore_complete_state_backup(backup, Path(tmp) / "wrong", instance_id="two")
            occupied = Path(tmp) / "occupied"; occupied.mkdir(); (occupied / "x").write_text("x")
            with self.assertRaisesRegex(ValueError, "empty"):
                restore_complete_state_backup(backup, occupied, instance_id="one")

    def test_live_write_boundaries_require_explicit_phoenix_scope(self):
        from src.memory.store import create_memory
        from src.conversations import create_conversation
        from src.memory.ledger import discover_candidate
        with self.assertRaisesRegex(ValueError, "instance_id"):
            create_memory("goal", "must not be written")
        with self.assertRaisesRegex(ValueError, "instance_id"):
            create_conversation("must not be written")
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, "instance_id"):
            discover_candidate(instance_id="", conversation_id="c", message_id="m",
                canonical_revision="a", path=Path(tmp) / "ledger.sqlite3")

    def test_new_preferences_embed_scope_while_legacy_preferences_stay_readable(self):
        from src.capabilities.event_audio import SoundPreferenceStore
        with tempfile.TemporaryDirectory() as tmp:
            store = SoundPreferenceStore("one", root=tmp)
            saved = store.update({"master_enabled": False})
            raw = json.loads((Path(tmp) / "one/event_sounds.json").read_text())
        self.assertEqual(saved["instance_id"], "one")
        self.assertEqual(raw["instance_id"], "one")

    def test_worker_exchange_revocation_is_in_complete_state_recovery(self):
        from src.runtime.worker_exchange import WorkerExchange
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"state"; self._state(root)
            exchange=WorkerExchange("one",root=root/"database/worker_exchange")
            sender={"worker_id":"sender","role":"software","identity_status":"verified","charter_version":"1.0"}
            recipient={"worker_id":"recipient","role":"verification","identity_status":"rider_attested","charter_version":"1.0"}
            expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
            target={"decision":"authorized","instance_id":"one","task_scope_id":"task",
                "sender_worker_id":"sender","recipient_worker_id":"recipient",
                "authorization_reference":"grant","expires_at":expiry}
            report=exchange.create_report(task_scope_id="task",sender=sender,
                authority={key:value for key,value in target.items() if key!="recipient_worker_id"},
                sections=[{"section_id":"one","title":"One","content":"exact"}])
            package=exchange.compose_package(report_id=report["report_id"],recipient=recipient,
                authority=target,included_section_ids=["one"])
            valid=exchange.validate_transport_authorization(package_id=package["package_id"],authority=target)
            rider={"decision":"authorized","operation":"worker_exchange.transport_authorization.revoke",
                "authority_class":"rider","instance_id":"one","task_scope_id":"task",
                "target_authorization_id":valid["authorization_id"],
                "target_authorization_reference":"grant","revoking_principal_id":"tanner",
                "authorization_reference":"rider-approval","expires_at":expiry}
            revocation=exchange.revoke_transport_authorization(package_id=package["package_id"],
                target_authorization=target,revocation_authority=rider)
            backup,_=create_complete_state_backup("one",Path(tmp)/"backups",source_root=root)
            restored=Path(tmp)/"restored"
            restore_complete_state_backup(backup,restored,instance_id="one")
            restored_record=restored/"database/worker_exchange/one/authorization_revocations"/f"{revocation['revocation_id']}.json"
            self.assertTrue(restored_record.exists())
            self.assertEqual(json.loads(restored_record.read_text())["record_sha256"],revocation["record_sha256"])

    def test_development_campaign_state_is_in_complete_state_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"; self._state(root)
            path = root / "database/development_campaigns/one/campaign.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"instance_id": "one", "campaign_id": "campaign"}))
            backup, _ = create_complete_state_backup("one", Path(tmp) / "backups", source_root=root)
            restored = Path(tmp) / "restored"
            restore_complete_state_backup(backup, restored, instance_id="one")
            restored_record = restored / "database/development_campaigns/one/campaign.json"
            self.assertEqual(json.loads(restored_record.read_text())["campaign_id"], "campaign")


if __name__ == "__main__":
    unittest.main()

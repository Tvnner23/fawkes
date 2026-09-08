import hashlib
import inspect
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.historical_search import (
    FederatedHistoricalSearch, HistoricalSearchDomain, InheritedHistoryDomain,
    MANUAL_HISTORY_SEARCH_DEFINITION, NativeArchiveDomain,
)
from src.history_staging import ChatGPTExportAdapter, InheritedHistoryStore
from src.memory.archive_retrieval import index_canonical_message
from src.runtime.phase0_integrity import create_complete_state_backup, restore_complete_state_backup
from src.runtime.chat import FawkesChatRuntime


def stage_args(owner):
    principal = f"rider:{owner}"
    return {"actor_principal": principal, "authorization": {
        "authorization_id": f"authorization:{owner}", "mode": "explicit_confirmation",
        "scope": "stage_inherited_history_export", "instance_id": owner, "principal_id": principal}}


def inherited_zip(text="The shared phrase belongs to inherited founding evidence."):
    payload = [{"id": "inherited-conversation", "title": "Founding", "mapping": {
        "node-1": {"id": "node-1", "parent": None, "children": [], "message": {
            "id": "inherited-message", "author": {"role": "user"}, "create_time": 10,
            "content": {"content_type": "text", "parts": [text]}}}}}]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive: archive.writestr("conversations.json", json.dumps(payload))
    return output.getvalue()


def native_fixture(root, index_path, *, owner="phoenix-one", text="The shared phrase belongs to native evidence."):
    archive_id = f"archive-{owner}"
    raw = json.dumps({"message_id": f"native-message-{owner}", "role": "user", "text": text}).encode()
    (root / "archive/raw").mkdir(parents=True, exist_ok=True); (root / "archive/meta").mkdir(parents=True, exist_ok=True)
    (root / f"archive/raw/{archive_id}.json").write_bytes(raw)
    (root / f"archive/meta/{archive_id}.json").write_text(json.dumps({
        "schema_version": 1, "archive_id": archive_id, "instance_id": owner,
        "conversation_id": f"native-conversation-{owner}", "capture_type": "message_state",
        "created_at": "2026-08-31T12:00:00+00:00", "raw_file": f"{archive_id}.json",
        "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "encoding": "utf-8"}) + "\n")
    index_canonical_message(instance_id=owner, conversation_id=f"native-conversation-{owner}",
        message_id=f"native-message-{owner}", role="user", content=text,
        created_at="2026-08-31T12:00:00+00:00", source_archive_id=archive_id, path=index_path)
    return archive_id, raw


class HistoricalSearchTests(unittest.TestCase):
    def setup_domains(self, root, owner="phoenix-one"):
        index = root / "database/native-index.sqlite3"
        archive_id, native_raw = native_fixture(root, index, owner=owner)
        inherited_root = root / "database/inherited_history"
        store = InheritedHistoryStore(owner, root=inherited_root, processing_root=root / "database/processing")
        staged = store.stage(inherited_zip(), adapter=ChatGPTExportAdapter(), **stage_args(owner))
        native = NativeArchiveDomain(owner, index_path=index, meta_dir=root / "archive/meta", raw_dir=root / "archive/raw")
        inherited = InheritedHistoryDomain(owner, root=inherited_root)
        return FederatedHistoricalSearch(owner, domains=(native, inherited)), store, staged, archive_id, native_raw

    def test_contract_is_explicit_read_only_and_not_automatic_chat(self):
        self.assertTrue(issubclass(NativeArchiveDomain, HistoricalSearchDomain))
        manifest = MANUAL_HISTORY_SEARCH_DEFINITION.public_manifest()
        self.assertEqual(manifest["authority_actions"], ["read"])
        self.assertEqual(manifest["authorization_mode"], "task_request")
        self.assertIn("automatic Chat context", manifest["inappropriate_use"])
        context_source = inspect.getsource(FawkesChatRuntime.build_context)
        self.assertNotIn("InheritedHistoryStore", context_source)
        self.assertNotIn("FederatedHistoricalSearch", context_source)
        self.assertNotIn("history.search_manual", context_source)

    def test_native_only_inherited_only_and_federated_results_remain_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            search, *_ = self.setup_domains(Path(tmp))
            native = search.search("shared phrase", requested_domains=("native_archive",))
            inherited = search.search("shared phrase", requested_domains=("inherited_history",))
            both = search.search("shared phrase")
        self.assertEqual([item["domain"] for item in native["results"]], ["native_archive"])
        self.assertEqual([item["domain"] for item in inherited["results"]], ["inherited_history"])
        self.assertEqual({item["domain"] for item in both["results"]}, {"native_archive", "inherited_history"})
        self.assertEqual(both["ranking_policy"], "round_robin_domain_neutral_no_cross_domain_authority_score")
        self.assertFalse(both["automatic_chat_context"])

    def test_inherited_provenance_unknowns_survive_search_and_exact_navigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            search, _, _, _, _ = self.setup_domains(Path(tmp))
            result = search.search("founding evidence", requested_domains=("inherited_history",))["results"][0]
            evidence = search.evidence("inherited_history", result["evidence_reference"]["evidence_id"])
        for record in (result, evidence):
            self.assertEqual(record["history_era"], "inherited_history")
            self.assertEqual(record["relationship_provenance"], "founding_developmental")
            self.assertEqual(record["identity_attribution"], "unassessed")
            self.assertEqual(record["native_boundary_status"], "boundary_unknown")
            self.assertNotIn("proven_native", json.dumps(record))
        self.assertEqual(evidence["exact_original_text"], "The shared phrase belongs to inherited founding evidence.")
        self.assertFalse(evidence["navigation_projection_authoritative"])

    def test_native_navigation_resolves_owned_hash_verified_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            search, _, _, archive_id, native_raw = self.setup_domains(Path(tmp))
            result = search.search("native evidence", requested_domains=("native_archive",))["results"][0]
            evidence = search.evidence("native_archive", result["evidence_reference"]["evidence_id"])
        self.assertEqual(result["evidence_reference"]["archive_id"], archive_id)
        self.assertEqual(evidence["original_record"], json.loads(native_raw))
        self.assertEqual(evidence["exact_original_text"], "The shared phrase belongs to native evidence.")
        self.assertEqual(evidence["native_boundary_status"], "boundary_unknown")

    def test_search_is_idempotent_and_does_not_mutate_any_authority_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); search, store, _, archive_id, _ = self.setup_domains(root)
            native = root / f"archive/raw/{archive_id}.json"
            inherited = next((store.root / "originals").glob("*.zip"))
            before = (native.read_bytes(), inherited.read_bytes())
            first = search.search("shared phrase"); second = search.search("shared phrase")
            self.assertEqual(first, second)
            self.assertEqual(before, (native.read_bytes(), inherited.read_bytes()))
            self.assertFalse((root / "memory").exists())

    def test_two_phoenix_isolation_and_foreign_evidence_navigation_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); index = root / "database/native.sqlite3"
            one_archive, _ = native_fixture(root, index, owner="phoenix-one", text="isolation token")
            native_fixture(root, index, owner="phoenix-two", text="isolation token")
            one = FederatedHistoricalSearch("phoenix-one", domains=(NativeArchiveDomain(
                "phoenix-one", index_path=index, meta_dir=root / "archive/meta", raw_dir=root / "archive/raw"),))
            two = FederatedHistoricalSearch("phoenix-two", domains=(NativeArchiveDomain(
                "phoenix-two", index_path=index, meta_dir=root / "archive/meta", raw_dir=root / "archive/raw"),))
            self.assertEqual({x["instance_id"] for x in one.search("isolation token", requested_domains=("native_archive",))["results"]}, {"phoenix-one"})
            self.assertEqual({x["instance_id"] for x in two.search("isolation token", requested_domains=("native_archive",))["results"]}, {"phoenix-two"})
            with self.assertRaises(PermissionError): two.evidence("native_archive", one_archive)

    def test_unavailable_or_malformed_domain_does_not_break_other_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inherited_root = root / "database/inherited_history"
            InheritedHistoryStore("phoenix-one", root=inherited_root, processing_root=root / "database/processing").stage(inherited_zip(), adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            missing = NativeArchiveDomain("phoenix-one", index_path=root / "missing.sqlite3", meta_dir=root / "archive/meta", raw_dir=root / "archive/raw")
            search = FederatedHistoricalSearch("phoenix-one", domains=(missing, InheritedHistoryDomain("phoenix-one", root=inherited_root)))
            result = search.search("shared phrase")
            self.assertEqual(result["domain_status"]["native_archive"]["status"], "unavailable")
            self.assertEqual([x["domain"] for x in result["results"]], ["inherited_history"])
            broken = root / "broken.sqlite3"; broken.write_text("not sqlite")
            result = FederatedHistoricalSearch("phoenix-one", domains=(NativeArchiveDomain(
                "phoenix-one", index_path=broken, meta_dir=root / "archive/meta", raw_dir=root / "archive/raw"),)).search(
                    "shared", requested_domains=("native_archive",))
            self.assertEqual(result["domain_status"]["native_archive"]["status"], "degraded")

    def test_inherited_search_survives_isolated_complete_state_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "live"; (root / "instances").mkdir(parents=True)
            (root / "instances/registry.json").write_text(json.dumps({"schema_version": 1, "instances": [
                {"instance_id": "phoenix-one", "name": "One"}]}) + "\n")
            store = InheritedHistoryStore("phoenix-one", root=root / "database/inherited_history", processing_root=root / "database/processing")
            store.stage(inherited_zip(), adapter=ChatGPTExportAdapter(), **stage_args("phoenix-one"))
            backup, _ = create_complete_state_backup("phoenix-one", Path(tmp) / "backups", source_root=root)
            restored = Path(tmp) / "restored"; restore_complete_state_backup(backup, restored, instance_id="phoenix-one")
            search = FederatedHistoricalSearch("phoenix-one", domains=(InheritedHistoryDomain(
                "phoenix-one", root=restored / "database/inherited_history"),))
            result = search.search("founding evidence", requested_domains=("inherited_history",))
            self.assertEqual(len(result["results"]), 1)


if __name__ == "__main__": unittest.main()

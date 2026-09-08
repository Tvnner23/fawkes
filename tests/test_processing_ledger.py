import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.runtime.processing_ledger import PROCESSING_LEDGER_DEFINITION, ProcessingLedger
from src.runtime.phase0_integrity import (
    audit_phoenix_state, create_complete_state_backup,
    restore_complete_state_backup, verify_complete_state_backup,
)


def source(revision="revision-1", *, era="inherited_history"):
    return {
        "source_id": "source-1", "object_id": "conversation-1",
        "content_id": "message-1", "revision_id": revision,
        "source_domain": "synthetic-test-source", "evidence_era": era,
    }


class FixedClock:
    kind = "simulation"
    domain_id = "simulation:test-run"

    def __init__(self): self.tick = 0
    def now(self):
        self.tick += 1
        return f"simulated:{self.tick:04d}"


class ProcessingLedgerTests(unittest.TestCase):
    def register(self, ledger, **changes):
        payload = {
            "domain": "history_import", "work_kind": "parse_conversation",
            "source": source(), "processor_id": "chat-export-adapter",
            "processor_version": "1.0", "idempotency_key": "import-conversation-1",
            "actor": {"actor_type": "import", "principal_id": "importer:local"},
        }
        payload.update(changes)
        return ledger.register(**payload)

    def test_capability_contract_is_internal_and_does_not_claim_domain_authority(self):
        manifest = PROCESSING_LEDGER_DEFINITION.public_manifest()
        self.assertEqual(manifest["name"], "system.processing_ledger")
        self.assertEqual(manifest["execution_boundary"], "internal")
        self.assertIn("replace Archive or Library evidence", manifest["inappropriate_use"])
        self.assertIn("existing Memory work remains in its domain ledger until an explicit migration", manifest["limitations"])

    def test_registration_is_stable_idempotent_and_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ProcessingLedger("phoenix-one", root=tmp)
            first = self.register(ledger); replay = self.register(ledger)
            self.assertEqual(first["work_item_id"], replay["work_item_id"])
            self.assertEqual(len(ledger.list()), 1)
            self.assertEqual([event["event_type"] for event in ledger.events(first["work_item_id"])], ["work.registered"])
            with self.assertRaises(ValueError):
                self.register(ledger, source=source("different-revision"))

    def test_dependency_and_correlation_metadata_are_explicit_but_inert(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ProcessingLedger("phoenix-one", root=tmp)
            parent = self.register(ledger)
            child = self.register(ledger, idempotency_key="child-1",
                dependency_work_item_ids=[parent["work_item_id"]],
                correlation_id="correlation-1", causation_id="request-1")
            self.assertEqual(child["dependency_work_item_ids"], [parent["work_item_id"]])
            self.assertEqual(child["correlation_id"], "correlation-1")
            self.assertEqual(child["status"], "discovered")

    def test_lifecycle_replay_recovery_and_results_are_inspectable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ProcessingLedger("phoenix-one", root=tmp); item = self.register(ledger)
            queued = ledger.transition(item["work_item_id"], to_status="queued", operation_id="queue-1")
            running = ledger.transition(item["work_item_id"], to_status="running", operation_id="claim-1", increment_attempt=True)
            failed = ledger.transition(item["work_item_id"], to_status="failed_retryable", operation_id="failure-1",
                error={"code": "provider_unavailable", "stage": "parse"})
            recovered = ledger.transition(item["work_item_id"], to_status="queued", operation_id="recover-1")
            replay = ledger.transition(item["work_item_id"], to_status="queued", operation_id="recover-1")
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(running["attempt_count"], 1)
            self.assertEqual(failed["error"]["stage"], "parse")
            self.assertEqual(recovered, replay)
            self.assertEqual(len(ledger.events(item["work_item_id"])), 5)
            with self.assertRaises(ValueError):
                ledger.transition(item["work_item_id"], to_status="cancelled", operation_id="recover-1")

    def test_claim_is_atomic_instance_scoped_and_counts_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ProcessingLedger("phoenix-one", root=tmp); item = self.register(ledger)
            ledger.transition(item["work_item_id"], to_status="queued", operation_id="queue")
            claimed = ledger.claim_next(domain="history_import")
            self.assertEqual(claimed["status"], "running")
            self.assertEqual(claimed["attempt_count"], 1)
            self.assertIsNone(ledger.claim_next())
            self.assertEqual(ledger.events(item["work_item_id"])[-1]["event_type"], "work.claimed")

    def test_phoenix_ownership_is_physical_and_query_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = ProcessingLedger("phoenix-one", root=tmp); two = ProcessingLedger("phoenix-two", root=tmp)
            item = self.register(one)
            self.assertNotEqual(one.path, two.path)
            self.assertIsNone(two.get(item["work_item_id"]))
            with self.assertRaises(KeyError): two.events(item["work_item_id"])
            self.assertEqual(two.list(), [])

    def test_reserved_extensions_are_inert_and_simulation_cannot_label_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ProcessingLedger("synthetic-phoenix", root=tmp, clock=FixedClock())
            item = self.register(ledger, reality_scope="synthetic_experiment",
                extensions={
                    "experiment_run": {"experiment_id": "experiment-1", "run_id": "run-1", "cohort_id": "cohort-1"},
                    "continuity_lineage": {"continuity_lineage_id": "lineage-1", "checkpoint_id": "checkpoint-1"},
                    "historical_provenance": {"founding_relationship_provenance_id": "founding-1", "identity_attribution": "ambiguous"},
                    "validated_progression": {"validity_finding_id": "finding-1"},
                    "independent_reference": {"expected_claim_id": "claim-1", "detector_id": "detector-1"},
                    "development_run": {"development_run_id": "development-1", "sandbox_id": "sandbox-1"},
                })
            self.assertEqual(item["time_domain"]["kind"], "simulation")
            self.assertEqual(item["extensions"]["historical_provenance"]["identity_attribution"], "ambiguous")
            self.assertIsNone(item["decision"])
            with self.assertRaises(ValueError):
                self.register(ledger, idempotency_key="invalid-production-time", reality_scope="production")

    def test_coverage_is_bounded_projection_not_source_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ProcessingLedger("phoenix-one", root=tmp)
            self.assertEqual(ledger.coverage()["blind_spots"], ["no_registered_processing_work"])
            item = self.register(ledger)
            ledger.transition(item["work_item_id"], to_status="queued", operation_id="queue")
            coverage = ledger.coverage()
            self.assertEqual(coverage["total"], 1)
            self.assertEqual(coverage["incomplete"], 1)
            self.assertEqual(coverage["by_domain"], {"history_import": 1})

    def test_complete_backup_restores_only_owning_processing_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "live"
            (root / "instances").mkdir(parents=True)
            (root / "instances/registry.json").write_text(json.dumps({
                "schema_version": 1, "instances": [
                    {"instance_id": "phoenix-one", "name": "One", "instance_type": "phoenix"},
                    {"instance_id": "phoenix-two", "name": "Two", "instance_type": "phoenix"},
                ]}) + "\n")
            self.register(ProcessingLedger("phoenix-one", root=root / "database/processing"))
            self.register(ProcessingLedger("phoenix-two", root=root / "database/processing"))
            audit = audit_phoenix_state("phoenix-one", root=root)
            self.assertTrue(audit["gate_satisfied"])
            backup, _ = create_complete_state_backup("phoenix-one", Path(tmp) / "backups", source_root=root)
            verify_complete_state_backup(backup, expected_instance_id="phoenix-one")
            restored = Path(tmp) / "restored"
            restore_complete_state_backup(backup, restored, instance_id="phoenix-one")
            one = restored / "database/processing/phoenix-one/ledger.sqlite3"
            two = restored / "database/processing/phoenix-two/ledger.sqlite3"
            self.assertTrue(one.is_file()); self.assertFalse(two.exists())
            connection = sqlite3.connect(one)
            owners = {row[0] for row in connection.execute("SELECT DISTINCT instance_id FROM processing_work_items")}
            connection.close()
            self.assertEqual(owners, {"phoenix-one"})


if __name__ == "__main__": unittest.main()

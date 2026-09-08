"""Synthetic isolated Workshop evidence tests; no provider or live fixtures."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from src.memory.workshop import WorkshopConflict, WorkshopError, WorkshopStateError, WorkshopStore
from src.runtime.personal_recording import RecordingPolicyStore
from src.runtime.worker_exchange import WorkerExchange


BUILDER = {"worker_id": "synthetic-builder", "role": "builder", "identity_status": "rider_attested",
           "charter_version": "fixture-v1"}
VERIFIER = {"worker_id": "synthetic-verifier", "role": "verifier", "identity_status": "rider_attested",
            "charter_version": "fixture-v1"}


class WorkshopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fawkes-workshop-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        from src.memory import development_store
        from src.runtime import worker_exchange
        for owner, name, path in ((development_store, 'DEVELOPMENT_DIR', self.root / 'memory' / 'development'),
                                  (worker_exchange, 'EXCHANGE_ROOT', self.root / 'database' / 'worker_exchange')):
            binding = patch.object(owner, name, path)
            binding.start(); self.addCleanup(binding.stop)
        self.store = WorkshopStore("fixture-phoenix", root=self.root)
        self.policy = RecordingPolicyStore("fixture-phoenix", root=self.root)
        self.exchange = WorkerExchange("fixture-phoenix", root=self.root / "database" / "worker_exchange")
        self.record = None

    def authority(self, sender=BUILDER, *, task="fixture-workshop"):
        return {"decision": "authorized", "instance_id": "fixture-phoenix", "task_scope_id": task,
                "sender_worker_id": sender["worker_id"], "authorization_reference": "synthetic-test-only"}

    def report(self, section_id="synthetic-evidence", payload=None, *, sender=BUILDER, task="fixture-workshop"):
        return self.exchange.create_report(task_scope_id=task, sender=sender, authority=self.authority(sender, task=task),
            sections=[{"section_id": section_id, "title": "Synthetic isolated test evidence",
                       "content": json.dumps(payload if payload is not None else {"test": "fixture-only"}, sort_keys=True)}])

    def ref(self, report):
        return self.store.report_reference(report)

    def create(self, *, evidence=None):
        self.record = self.store.create({"classification": "retrieval_context_failure",
            "observation": "A synthetic fixture failed to retrieve an expected source.",
            "interpretation": "Possibly an evidence ranking defect.",
            "uncertainty": "Synthetic fixture only; no real rider outcome is claimed.",
            "evidence": [] if evidence is None else evidence}, actor=BUILDER)
        return self.record

    def append(self, action, payload):
        self.record = self.store.append(self.record["proposal_id"], expected_revision=self.record["revision"],
                                        action=action, payload=payload, actor=BUILDER)
        return self.record

    @staticmethod
    def investigation():
        return {"investigation": "Inspected the synthetic trace.", "knowledge": "The exact title should rank first.",
                "hypothesis": "Tie-breaking is unstable.", "evidence": [], "cost": {"status": "unknown"}}

    @staticmethod
    def contract(tier=2):
        return {"intended_behavior": "Stable exact-title ordering in the isolated fixture.",
            "forbidden_behavior": "No ordinary Archive or Memory mutation.",
            "rider_expectation": "No live change from this proposal.", "hard_invariants": ["same Phoenix", "isolated only"],
            "failure_behavior": "Fail closed on missing ownership.", "regression_boundary": "Synthetic source ranking fixture.",
            "rollback_requirement": "Discard isolated candidate; no live rollback needed.",
            "evidence_required": ["exact fixture report", "independent scope inspection"], "assurance_tier": tier,
            "limitations": ["No real rider/provider evaluation."],
            "criteria": [{"criterion_id": "exact-source", "expectation": "Exact source ranks first.", "mandatory": True},
                         {"criterion_id": "no-live-write", "expectation": "Ordinary state is unchanged.", "mandatory": True}]}

    def declared(self, tier=2):
        self.create()
        self.append("investigate", self.investigation())
        self.append("design", {"proposed_change": "Use a deterministic tie-breaker in a detached candidate.",
            "affected_systems": ["isolated retrieval"], "permissions": [], "risks": ["Fixture does not prove semantic quality."],
            "rollback": "Discard isolated fixture."})
        self.append("declare_acceptance", self.contract(tier))
        return self.record

    def evaluation_payload(self, *, verdict="pass", candidate_id="synthetic-candidate-1"):
        contract = self.record["acceptance_contracts"][-1]
        source = self.ref(self.report(payload={"candidate_id": candidate_id, "verdict": verdict,
                                              "note": "Synthetic fixture evidence, not real qualification."}))
        return {"proposal_id": self.record["proposal_id"], "contract_version": contract["contract_version"],
            "contract_sha256": contract["contract_sha256"],
            "candidate": {"candidate_id": candidate_id, "revision": "fixture-revision-1",
                          "sha256": hashlib.sha256(candidate_id.encode()).hexdigest(),
                          "instance_id": "fixture-phoenix", "reality_scope": "isolated"},
            "started_at": datetime.now(timezone.utc).isoformat(), "isolated": True, "ordinary_history_mutated": False,
            "results": [{"criterion_id": item["criterion_id"], "verdict": verdict,
                         "observed": "Synthetic fixture result: " + verdict, "evidence": [source]}
                        for item in contract["criteria"]],
            "tests": ["synthetic-exact-title", "synthetic-no-live-write"], "sandbox_results": ["Temporary fixture root only."],
            "cost": {"provider_calls": 0, "source": "synthetic fixture"}, "limitations": ["Synthetic scope only."]}

    def evaluated(self, *, verdict="pass", candidate_id="synthetic-candidate-1", sender=BUILDER):
        payload = self.evaluation_payload(verdict=verdict, candidate_id=candidate_id)
        reference = self.ref(self.report("workshop-evaluation-v1", payload, sender=sender))
        self.append("record_evaluation", {"report_reference": reference})
        return reference

    def requested(self, verifier=VERIFIER):
        result = self.store.export_report(self.record["proposal_id"], expected_revision=self.record["revision"],
            task_scope_id="fixture-workshop", sender=BUILDER, authority=self.authority(),
            purpose="verifier_request", verifier=verifier)
        self.record = result["proposal"]
        return result["report_reference"]

    def assurance_payload(self, evaluation, request, *, verdict="pass", verifier=VERIFIER):
        contract = self.record["acceptance_contracts"][-1]
        return {"proposal_id": self.record["proposal_id"], "contract_version": contract["contract_version"],
            "contract_sha256": contract["contract_sha256"], "candidate": self.record["evaluations"][-1]["candidate"],
            "evaluation_report": evaluation, "verifier_request": request, "verdict": verdict,
            "observed": "Synthetic independent role inspected the fixture report.",
            "coverage": [item["criterion_id"] for item in contract["criteria"]],
            "limitations": ["Synthetic source assertions, not production acceptance."], "disagreements": [],
            "authority_check": "No live authority; fixture root only.", "rider_impact": "No applied change.",
            "recommendation": "prototype only", "cost": {"provider_calls": 0, "status": "synthetic"},
            "independence": {"builder_worker_id": BUILDER["worker_id"], "verifier_worker_id": verifier["worker_id"],
                             "context_separation": "Separate synthetic role, not actual independent review.",
                             "common_mode_dependencies": ["Same unit-test fixture."]}}

    def assured(self, *, verdict="pass", candidate_id="synthetic-candidate-1"):
        evaluation = self.evaluated(verdict=verdict, candidate_id=candidate_id)
        request = self.requested()
        payload = self.assurance_payload(evaluation, request, verdict=verdict)
        report = self.report("workshop-assurance-v1", payload, sender=VERIFIER)
        self.append("record_assurance", {"report_reference": self.ref(report)})
        return self.record

    def test_full_flow_is_versioned_attributed_and_inert(self):
        self.declared()
        self.assured()
        self.assertEqual(self.record["verdict"], "pass")
        self.append("submit", {})
        revision = self.record["revision"]
        self.record = self.store.review(self.record["proposal_id"], expected_revision=revision, decision="approve",
            note="Approve only a future separately authorized action.", rider_principal_id="fixture-rider", authenticated_rider=True)
        self.assertEqual(self.record["status"], "approved_for_future_action")
        self.assertIsNone(self.record["applied_revision"])
        self.assertEqual(self.record["outcome"], "not_applied")
        self.assertFalse(self.record["execution_allowed"])
        self.assertFalse(self.record["creates_authority"])
        self.assertEqual(self.record["reviews"][0]["effect"], "recorded_only_no_automatic_application")
        history = self.store.history(self.record["proposal_id"])
        self.assertEqual(len(history), self.record["revision"])
        self.assertEqual(history[0]["investigations"], [])
        for earlier, later in zip(history, history[1:]):
            self.assertEqual(later["previous_sha256"], earlier["record_sha256"])
        self.assertEqual(self.record["assurance"][0]["verifier"]["worker_id"], VERIFIER["worker_id"])
        self.assertEqual(self.record["evaluations"][0]["cost"]["provider_calls"], 0)
        # Human approval does not create a campaign, Memory, Archive, or active task.
        self.assertEqual({path.name for path in self.root.iterdir()}, {"memory", "database"})
        self.assertEqual({path.name for path in (self.root / "database").iterdir()}, {"worker_exchange"})
        exported = self.store.export_report(self.record["proposal_id"], expected_revision=self.record["revision"],
            task_scope_id="fixture-workshop", sender=BUILDER, authority=self.authority())
        report = self.exchange._load("reports", exported["report_reference"]["report_id"])
        content = json.loads(report["sections"][0]["content"])
        self.assertEqual(content["proposal"]["reviews"], self.record["reviews"])
        self.assertFalse(content["creates_authority"])

    def test_tier_two_missing_independent_assurance_is_not_pass(self):
        self.declared()
        self.evaluated()
        self.assertEqual(self.record["evaluations"][0]["verdict"], "pass")
        self.assertEqual(self.record["verdict"], "inconclusive")

    def test_new_evaluation_requires_its_own_assurance_for_identical_candidate(self):
        for tier in (2, 3):
            with self.subTest(tier=tier):
                self.declared(tier)
                self.assured()
                first = deepcopy(self.record)
                self.assertEqual(first["verdict"], "pass")
                evaluation = self.evaluated()
                self.assertEqual(first["evaluations"][-1]["candidate"], self.record["evaluations"][-1]["candidate"])
                self.assertNotEqual(first["evaluations"][-1]["report_reference"], evaluation)
                self.assertEqual(self.record["verdict"], "inconclusive")
                self.assertEqual(self.record["assurance"], first["assurance"])
                self.assertEqual(self.store.get(first["proposal_id"], revision=first["revision"])["verdict"], "pass")
                restarted = WorkshopStore("fixture-phoenix", root=self.root)
                self.assertEqual(restarted.get(first["proposal_id"])["verdict"], "inconclusive")
                request = self.requested()
                payload = self.assurance_payload(evaluation, request)
                self.append("record_assurance", {"report_reference": self.ref(self.report(
                    "workshop-assurance-v1", payload, sender=VERIFIER))})
                self.assertEqual(self.record["verdict"], "pass")
                self.assertEqual(len(self.record["assurance"]), 2)
                self.assertEqual(self.record["assurance"][0], first["assurance"][0])

    def test_assurance_request_cannot_be_reused_for_another_evaluation(self):
        self.declared()
        self.evaluated()
        first_request = self.requested()
        second_evaluation = self.evaluated()
        prior = deepcopy(self.record)
        files_before = {p: p.read_bytes() for p in self.store.path.rglob('*.json')}
        payload = self.assurance_payload(second_evaluation, first_request)
        reference = self.ref(self.report("workshop-assurance-v1", payload, sender=VERIFIER))
        with self.assertRaisesRegex(WorkshopError, "exact recorded evaluation and verifier request"):
            self.append("record_assurance", {"report_reference": reference})
        self.assertEqual(self.store.get(prior["proposal_id"]), prior)
        self.assertEqual(len(self.store.history(prior["proposal_id"])), prior["revision"])
        self.assertEqual({p: p.read_bytes() for p in self.store.path.rglob('*.json')}, files_before)
        second_request = self.requested()
        payload = self.assurance_payload(second_evaluation, second_request)
        self.append("record_assurance", {"report_reference": self.ref(self.report(
            "workshop-assurance-v1", payload, sender=VERIFIER))})
        self.assertEqual(self.record["verdict"], "pass")

    def test_missing_results_do_not_become_pass(self):
        self.declared(0)
        payload = self.evaluation_payload()
        payload["results"] = []
        self.append("record_evaluation", {"report_reference": self.ref(self.report("workshop-evaluation-v1", payload))})
        self.assertEqual(self.record["verdict"], "inconclusive")

    def test_pass_requires_resolving_exact_criterion_evidence(self):
        self.declared(0)
        for modification in ("empty", "missing", "wrong-owner", "wrong-digest"):
            with self.subTest(modification=modification):
                payload = self.evaluation_payload()
                reference = payload["results"][0]["evidence"][0]
                if modification == "empty":
                    payload["results"][0]["evidence"] = []
                elif modification == "missing":
                    reference["report_id"] = "worker-report-missing"
                elif modification == "wrong-owner":
                    reference["instance_id"] = "other-phoenix"
                else:
                    reference["record_sha256"] = "0" * 64
                with self.assertRaises(WorkshopError):
                    self.append("record_evaluation", {"report_reference": self.ref(self.report("workshop-evaluation-v1", payload))})

    def test_unverified_evaluator_is_inconclusive(self):
        self.declared(0)
        self.evaluated(sender={**BUILDER, "identity_status": "unverified"})
        self.assertEqual(self.record["verdict"], "inconclusive")

    def test_exact_binding_predeclaration_and_isolation_are_required(self):
        self.declared()
        for key, value in (("contract_sha256", "0" * 64), ("proposal_id", "other-proposal"),
                           ("started_at", "2000-01-01T00:00:00Z"), ("isolated", False), ("ordinary_history_mutated", True)):
            with self.subTest(key=key):
                payload = self.evaluation_payload()
                payload[key] = value
                with self.assertRaises(WorkshopError):
                    self.append("record_evaluation", {"report_reference": self.ref(self.report("workshop-evaluation-v1", payload))})

    def test_changed_candidate_requires_new_identity(self):
        self.declared(0)
        self.evaluated(verdict="fail")
        payload = self.evaluation_payload()
        payload["candidate"]["sha256"] = "0" * 64
        with self.assertRaises(WorkshopError):
            self.append("record_evaluation", {"report_reference": self.ref(self.report("workshop-evaluation-v1", payload))})
        self.evaluated(candidate_id="synthetic-candidate-2")
        self.assertEqual(self.record["verdict"], "pass")
        self.assertEqual([item["verdict"] for item in self.record["evaluations"]], ["fail", "pass"])

    def test_contract_revisions_preserve_failures_and_cannot_erase_criteria(self):
        self.declared()
        self.evaluated(verdict="fail")
        for change in ({"criteria": [self.contract()["criteria"][0]]}, {"assurance_tier": 1}, {"hard_invariants": []}):
            with self.subTest(change=change):
                with self.assertRaises(WorkshopError):
                    self.append("declare_acceptance", {**self.contract(), **change})
        amended = self.contract()
        amended["criteria"].append({"criterion_id": "new-regression", "expectation": "A newly found failure remains covered.", "mandatory": True})
        self.append("declare_acceptance", amended)
        self.assertEqual(len(self.record["acceptance_contracts"]), 2)
        self.assertEqual(self.record["evaluations"][0]["verdict"], "fail")
        self.assertEqual(self.record["verdict"], "inconclusive")
        with self.assertRaises(WorkshopError):
            self.append("submit", {})

    def test_verifier_cannot_be_builder_or_evaluator(self):
        self.declared()
        self.evaluated()
        with self.assertRaises(WorkshopError):
            self.requested(BUILDER)

    def test_assurance_requires_exact_request_identity_scope_and_coverage(self):
        self.declared()
        evaluation = self.evaluated()
        request = self.requested()
        for modification in ("scope", "identity", "coverage", "disagreement", "unverified"):
            with self.subTest(modification=modification):
                payload = self.assurance_payload(evaluation, request)
                sender, task = VERIFIER, "fixture-workshop"
                if modification == "scope":
                    task = "other-task"
                elif modification == "identity":
                    sender = {**VERIFIER, "worker_id": "unrequested-verifier"}
                elif modification == "coverage":
                    payload["coverage"] = []
                elif modification == "disagreement":
                    payload["disagreements"] = ["Unresolved contradictory output."]
                else:
                    sender = {**VERIFIER, "identity_status": "unverified"}
                with self.assertRaises(WorkshopError):
                    self.append("record_assurance", {"report_reference": self.ref(self.report("workshop-assurance-v1", payload, sender=sender, task=task))})

    def test_disagreement_and_all_verdicts_remain_visible(self):
        self.declared()
        self.assured()
        evaluation = self.record["evaluations"][-1]["report_reference"]
        request = self.record["verifier_requests"][-1]["report_reference"]
        for verdict in ("fail", "partial", "inconclusive"):
            payload = self.assurance_payload(evaluation, request, verdict=verdict)
            payload["disagreements"] = ["Earlier pass omitted a relevant synthetic failure."]
            self.append("record_assurance", {"report_reference": self.ref(self.report("workshop-assurance-v1", payload, sender=VERIFIER))})
        self.assertEqual([item["verdict"] for item in self.record["assurance"]], ["pass", "fail", "partial", "inconclusive"])
        self.assertEqual(self.record["verdict"], "fail")
        self.assertTrue(self.record["assurance"][-1]["disagreements"])

    def test_rider_review_requires_submission_authentication_and_exact_revision(self):
        self.declared(0)
        args = {"expected_revision": self.record["revision"], "decision": "approve", "note": "", "rider_principal_id": "fixture-rider"}
        with self.assertRaises(PermissionError):
            self.store.review(self.record["proposal_id"], **args, authenticated_rider=False)
        with self.assertRaises(WorkshopError):
            self.store.review(self.record["proposal_id"], **args, authenticated_rider=True)
        self.evaluated(verdict="fail")
        self.append("submit", {})
        with self.assertRaises(WorkshopConflict):
            self.store.review(self.record["proposal_id"], **args, authenticated_rider=True)
        self.record = self.store.review(self.record["proposal_id"], **{**args, "expected_revision": self.record["revision"]}, authenticated_rider=True)
        self.assertEqual(self.record["reviews"][0]["verdict_at_review"], "fail")
        self.assertEqual(self.record["verdict"], "fail")
        with self.assertRaises(WorkshopError):
            self.append("investigate", self.investigation())

    def test_exchange_export_requires_real_upstream_authority(self):
        self.create()
        with self.assertRaises(PermissionError):
            self.store.export_report(self.record["proposal_id"], expected_revision=self.record["revision"],
                                     task_scope_id="fixture-workshop", sender=BUILDER, authority={})
        self.assertEqual(self.store.get(self.record["proposal_id"])["revision"], 1)
        self.assertEqual(list((self.exchange.root / "reports").iterdir()), [])

    def test_private_and_category_off_block_writes_without_deleting_history(self):
        self.create()
        first = self.record["record_sha256"]
        self.policy.update({"categories": {"personal_diagnostics": False}}, expected_revision=0)
        off = self.policy.latch()
        with self.assertRaises(PermissionError):
            self.append("investigate", self.investigation())
        self.assertEqual(self.store.get(self.record["proposal_id"])["record_sha256"], first)
        self.assertEqual(len(self.store.list()), 1)
        self.policy.update({"categories": {"personal_diagnostics": True}}, expected_revision=1)
        with self.assertRaises(PermissionError):
            self.store.append(self.record["proposal_id"], expected_revision=1, action="investigate",
                              payload=self.investigation(), actor=BUILDER, recording_policy=off)
        self.append("investigate", self.investigation())
        self.policy.update({"mode": "private"}, expected_revision=2)
        with self.assertRaises(PermissionError):
            self.create()
        self.assertEqual(len(self.store.history(self.record["proposal_id"])), 2)

    def test_policy_rechecked_at_final_publication(self):
        self.declared(0)
        payload = self.evaluation_payload()
        reference = self.ref(self.report("workshop-evaluation-v1", payload))
        original = self.store._evaluation
        def turn_off(record, ref):
            original(record, ref)
            self.policy.update({"categories": {"personal_diagnostics": False}}, expected_revision=0)
        with patch.object(self.store, "_evaluation", side_effect=turn_off):
            with self.assertRaises(PermissionError):
                self.append("record_evaluation", {"report_reference": reference})
        self.assertEqual(self.store.get(self.record["proposal_id"])["revision"], self.record["revision"])
        self.assertEqual(self.store.get(self.record["proposal_id"])["evaluations"], [])

    def test_private_empty_store_reads_do_not_create_workshop_state(self):
        self.policy.update({"mode": "private"}, expected_revision=0)
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(PermissionError):
            self.create()
        self.assertFalse(self.store.path.exists())

    def test_instance_isolation_and_legacy_records_untouched(self):
        legacy = self.root / "memory" / "development" / "legacy-proposal.json"
        legacy.parent.mkdir(parents=True)
        original = '{"legacy":"must remain byte-identical","status":"proposed"}\n'
        legacy.write_text(original)
        self.create()
        other = WorkshopStore("other-phoenix", root=self.root)
        self.assertEqual(other.list(), [])
        with self.assertRaises(KeyError):
            other.get(self.record["proposal_id"])
        self.assertEqual(legacy.read_text(), original)

    def test_concurrent_compare_and_swap_has_one_winner(self):
        self.create()
        proposal_id = self.record["proposal_id"]
        def write(_):
            try:
                WorkshopStore("fixture-phoenix", root=self.root).append(proposal_id, expected_revision=1,
                    action="investigate", payload=self.investigation(), actor=BUILDER)
                return "committed"
            except WorkshopConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(executor.map(write, range(2)), ["committed", "conflict"])
        self.assertEqual(len(self.store.history(proposal_id)), 2)

    def test_tampered_history_and_missing_revision_fail_closed(self):
        self.create()
        self.append("investigate", self.investigation())
        first = self.store.path / f"{self.record['proposal_id']}.000001.json"
        value = json.loads(first.read_text())
        value["interpretation"] = "tampered"
        first.write_text(json.dumps(value))
        with self.assertRaises(WorkshopError):
            self.store.get(self.record["proposal_id"])
        first.unlink()
        with self.assertRaises(WorkshopError):
            self.store.get(self.record["proposal_id"])

    def test_missing_or_changed_report_keeps_history_but_removes_passing_projection(self):
        self.declared()
        self.assured()
        reference = self.record["assurance"][0]["report_reference"]
        path = self.exchange.root / "reports" / (reference["report_id"] + ".json")
        path.write_text('{"corrupt":true}')
        read = self.store.get(self.record["proposal_id"])
        self.assertEqual(read["assurance"][0]["verdict"], "pass")
        self.assertEqual(read["verdict"], "inconclusive")
        self.assertEqual(read["evidence_status"]["missing_report_ids"], [reference["report_id"]])

    def test_symlinks_hardlinks_and_traversal_are_rejected(self):
        for identity in ("../other", ".", "..", "/tmp/other"):
            with self.subTest(identity=identity), self.assertRaises(WorkshopError):
                WorkshopStore(identity, root=self.root)
        self.create()
        path = self.store.path / f"{self.record['proposal_id']}.000001.json"
        linked = self.root / "linked.json"
        os.link(path, linked)
        with self.assertRaises(WorkshopError):
            self.store.get(self.record["proposal_id"])
        linked.unlink()
        alternate = self.root / "alternate"
        alternate.mkdir()
        bad_root = self.root / "linked-root"
        bad_root.symlink_to(alternate, target_is_directory=True)
        with self.assertRaises((WorkshopError, OSError)):
            WorkshopStore("fixture-phoenix", root=bad_root).list()

    def test_directory_fsync_uncertainty_requires_reload_not_blind_retry(self):
        self.create()
        target = self.store.path / f"{self.record['proposal_id']}.000002.json"
        original = os.fsync
        def uncertain(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode) and target.exists():
                raise OSError("synthetic directory durability failure")
            return original(fd)
        with patch("src.memory.workshop.os.fsync", side_effect=uncertain):
            with self.assertRaisesRegex(WorkshopError, "durability is unconfirmed"):
                self.append("investigate", self.investigation())
        self.assertEqual(self.store.get(self.record["proposal_id"])["revision"], 2)
        with self.assertRaises(WorkshopConflict):
            self.append("investigate", self.investigation())

    def test_structured_report_duplicate_fields_are_rejected(self):
        self.declared(0)
        payload = self.evaluation_payload()
        content = json.dumps(payload)
        content = content[:-1] + ', "isolated": false, "isolated": true}'
        report = self.exchange.create_report(task_scope_id="fixture-workshop", sender=BUILDER,
            authority=self.authority(), sections=[{"section_id": "workshop-evaluation-v1", "title": "Duplicate fixture",
                                                  "content": content}])
        with self.assertRaises(WorkshopError):
            self.append("record_evaluation", {"report_reference": self.ref(report)})
        self.assertEqual(self.store.get(self.record["proposal_id"])["evaluations"], [])

    def test_directory_replacement_before_publication_does_not_write_detached_tree(self):
        self.declared(0)
        reference = self.ref(self.report("workshop-evaluation-v1", self.evaluation_payload()))
        detached = self.root / "detached-workshop"
        original = self.store._evaluation
        def replace_directory(record, ref):
            original(record, ref)
            self.store.path.rename(detached)
            self.store.path.mkdir()
            (self.store.path / ".workshop.lock").write_bytes(b"")
        with patch.object(self.store, "_evaluation", side_effect=replace_directory):
            with self.assertRaises(WorkshopStateError):
                self.append("record_evaluation", {"report_reference": reference})
        self.assertEqual(len(list(detached.glob("*.json"))), self.record["revision"])
        self.assertEqual(list(self.store.path.glob("*.json")), [])
        self.assertEqual(list(detached.glob(".*.tmp")), [])

    def test_replaced_or_hardlinked_lock_is_rejected_before_publication(self):
        self.declared(0)
        reference = self.ref(self.report("workshop-evaluation-v1", self.evaluation_payload()))
        original = self.store._evaluation
        def replace_lock(record, ref):
            original(record, ref)
            lock = self.store.path / ".workshop.lock"
            lock.rename(self.store.path / ".old-lock")
            lock.write_bytes(b"")
        with patch.object(self.store, "_evaluation", side_effect=replace_lock):
            with self.assertRaises(WorkshopStateError):
                self.append("record_evaluation", {"report_reference": reference})
        self.assertEqual(self.store.get(self.record["proposal_id"])["evaluations"], [])
        os.link(self.store.path / ".workshop.lock", self.root / "foreign-lock-link")
        with self.assertRaises(WorkshopStateError):
            self.store.get(self.record["proposal_id"])

    def test_real_process_exit_after_atomic_publication_leaves_single_link_readable_revision(self):
        from src.memory import workshop
        self.create()
        original = workshop._rename_once
        def child():
            def stop_after_publish(*args):
                original(*args)
                os._exit(91)
            with patch.object(workshop, "_rename_once", side_effect=stop_after_publish):
                self.append("investigate", self.investigation())
        process = multiprocessing.get_context("fork").Process(target=child)
        process.start()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(5)
            self.fail("synthetic publication child did not finish")
        self.assertEqual(process.exitcode, 91)
        reopened = self.store.get(self.record["proposal_id"])
        self.assertEqual(reopened["revision"], 2)
        self.assertEqual(len(reopened["investigations"]), 1)
        self.assertTrue(all(path.stat().st_nlink == 1 for path in self.store.path.glob("*.json")))
        self.assertEqual(list(self.store.path.glob(".*.tmp")), [])

    def test_atomic_publication_never_overwrites_an_existing_name(self):
        from src.memory.workshop import _rename_once
        self.create()
        target = f"{self.record['proposal_id']}.000001.json"
        before = (self.store.path / target).read_bytes()
        (self.store.path / ".synthetic-conflict.tmp").write_text("must not replace history")
        directory = os.open(self.store.path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(FileExistsError):
                _rename_once(directory, ".synthetic-conflict.tmp", target)
        finally:
            os.close(directory)
        self.assertEqual((self.store.path / target).read_bytes(), before)

    def test_exchange_write_rechecks_policy_after_report_preparation(self):
        from src.memory.workshop import _PinnedReportExchange
        self.create()
        original = _PinnedReportExchange._write_once
        def turn_off(exchange, kind, record):
            self.policy.update({"categories": {"personal_diagnostics": False}}, expected_revision=0)
            return original(exchange, kind, record)
        with patch.object(_PinnedReportExchange, "_write_once", new=turn_off):
            with self.assertRaises(PermissionError):
                self.store.export_report(self.record["proposal_id"], expected_revision=1,
                    task_scope_id="fixture-workshop", sender=BUILDER, authority=self.authority())
        self.assertEqual(list((self.exchange.root / "reports").iterdir()), [])
        self.assertEqual(self.store.get(self.record["proposal_id"])["revision"], 1)

    def legacy_proposal(self):
        from src.memory.development import DevelopmentProposal
        from src.memory import development_store
        with patch.object(development_store, "DEVELOPMENT_DIR", self.root / "memory" / "development"):
            return development_store.save_development_proposal(
                DevelopmentProposal(category="workflow", observation="Synthetic Phoenix-generated observation.",
                    proposed_change="Investigate synthetic workflow.", rationale="An attributed source proposal, not proof.",
                    confidence=0.5, source_memory_ids=("synthetic-memory",), source_message_ids=("synthetic-message",)),
                instance_id="fixture-phoenix", origin="development_experience")

    def test_existing_phoenix_development_intake_preserves_exact_source_and_unknown_identity(self):
        source = self.legacy_proposal()
        path = self.root / "memory" / "development" / (source["proposal_id"] + ".json")
        before = path.read_bytes()
        reference = self.store.development_source(source["proposal_id"])
        self.assertEqual(reference["expected_source_sha256"], hashlib.sha256(before).hexdigest())
        intake_actor = {**BUILDER, "worker_id": "synthetic-rider", "role": "rider_submission"}
        record = self.store.intake_development(source["proposal_id"],
            expected_source_sha256=reference["expected_source_sha256"], classification="development_observation", actor=intake_actor)
        self.assertEqual(record["origin"]["source_record"], source)
        self.assertEqual(record["origin"]["producer_identity"], "not_recorded_by_legacy_owner")
        self.assertEqual(record["builder"]["worker_id"], "synthetic-rider")
        self.assertEqual(record["investigations"], [])
        self.assertEqual(record["evaluations"], [])
        self.assertEqual(record["verdict"], "inconclusive")
        self.assertEqual(path.read_bytes(), before)

    def test_development_intake_rejects_changed_unscoped_foreign_and_private_sources(self):
        source = self.legacy_proposal()
        reference = self.store.development_source(source["proposal_id"])
        args = {"expected_source_sha256": reference["expected_source_sha256"],
                "classification": "development_observation", "actor": BUILDER}
        with self.assertRaises(WorkshopConflict):
            self.store.intake_development(source["proposal_id"], **{**args, "expected_source_sha256": "0" * 64})
        path = self.root / "memory" / "development" / (source["proposal_id"] + ".json")
        for owner in (None, "other-phoenix"):
            path.write_text(json.dumps({**source, "instance_id": owner}))
            with self.assertRaises(WorkshopError):
                self.store.intake_development(source["proposal_id"], **args)
        path.write_text(json.dumps(source))
        self.policy.update({"mode": "private"}, expected_revision=0)
        with self.assertRaises(PermissionError):
            self.store.intake_development(source["proposal_id"], **args)
        self.assertFalse(self.store.path.exists())

    def test_existing_complete_state_backup_restores_exact_revision_chain_and_exchange_refs(self):
        from src.runtime.phase0_integrity import create_complete_state_backup, restore_complete_state_backup
        self.declared()
        self.assured()
        self.append("submit", {})
        (self.root / "instances").mkdir()
        (self.root / "instances" / "registry.json").write_text(json.dumps({"schema_version": 1, "instances": [
            {"instance_id": "fixture-phoenix", "name": "Synthetic Phoenix"}]}))
        before = self.store.history(self.record["proposal_id"])
        with tempfile.TemporaryDirectory(prefix="fawkes-workshop-backup-test-") as temporary:
            backup, manifest = create_complete_state_backup("fixture-phoenix", Path(temporary) / "backups", source_root=self.root)
            revisions = [item for item in manifest["files"] if "/workshop/" in item["path"]]
            self.assertEqual(len(revisions), self.record["revision"])
            restored = Path(temporary) / "isolated-restored"
            restore_complete_state_backup(backup, restored, instance_id="fixture-phoenix")
            owner = WorkshopStore("fixture-phoenix", root=restored,
                development_root=restored / 'memory' / 'development',
                exchange_root=restored / 'database' / 'worker_exchange')
            self.assertFalse((owner.path / ".workshop.lock").exists())
            self.assertEqual(owner.history(self.record["proposal_id"]), before)
            self.assertTrue((owner.path / ".workshop.lock").exists())
            self.assertEqual(owner.get(self.record["proposal_id"])["verdict"], "pass")
            self.assertEqual(self.store.history(self.record["proposal_id"]), before)

    def test_existing_source_owners_are_independent_of_recording_root(self):
        from src.memory import development_store
        from src.runtime import worker_exchange
        source = self.legacy_proposal()
        report = self.report()
        before = (self.root / 'memory' / 'development' / (source['proposal_id'] + '.json')).read_bytes()
        runtime = self.root / 'separate-runtime'
        owner = WorkshopStore('fixture-phoenix', root=runtime)
        self.assertEqual(owner.development_root, development_store.DEVELOPMENT_DIR)
        self.assertEqual(owner.exchange.root, self.exchange.root)
        reference = owner.development_source(source['proposal_id'])
        proposal = owner.intake_development(source['proposal_id'], expected_source_sha256=reference['expected_source_sha256'],
            classification='development_observation', actor=BUILDER)
        exported = owner.export_report(proposal['proposal_id'], expected_revision=1,
            task_scope_id='fixture-workshop', sender=BUILDER, authority=self.authority())
        self.assertEqual(self.exchange._load('reports', exported['report_reference']['report_id'])['instance_id'], 'fixture-phoenix')
        self.assertEqual(owner._resolve(owner.report_reference(report))['report_id'], report['report_id'])
        self.assertFalse((runtime / 'database').exists())
        self.assertEqual((self.root / 'memory' / 'development' / (source['proposal_id'] + '.json')).read_bytes(), before)

    def test_export_file_and_directory_sync_precede_workshop_reference(self):
        from src.memory import workshop
        self.create(); events=[]
        sync=os.fsync; rename=workshop._rename_once
        def observed_sync(fd):
            name=os.readlink('/proc/self/fd/' + str(fd))
            sync(fd); events.append(('sync', name))
        def observed_rename(directory, temporary, filename):
            events.append(('publish', filename)); return rename(directory, temporary, filename)
        with patch.object(workshop.os, 'fsync', observed_sync), patch.object(workshop, '_rename_once', observed_rename):
            result=self.store.export_report(self.record['proposal_id'], expected_revision=1,
                task_scope_id='fixture-workshop', sender=BUILDER, authority=self.authority())
        report_id=result['report_reference']['report_id']
        report_publish=events.index(('publish', report_id + '.json'))
        report_file_sync=next(i for i,e in enumerate(events) if e[0]=='sync' and report_id in e[1] and e[1].endswith('.tmp'))
        report_dir_sync=next(i for i,e in enumerate(events) if i>report_publish and e==('sync',str(self.exchange.root/'reports')))
        revision_publish=next(i for i,e in enumerate(events) if i>report_publish and e[0]=='publish')
        self.assertLess(report_file_sync, report_publish);self.assertLess(report_publish, report_dir_sync)
        self.assertLess(report_dir_sync, revision_publish)

    def test_uncertain_report_directory_sync_leaves_no_workshop_reference_and_retry_is_exact(self):
        from src.memory import workshop
        self.create(); sync=os.fsync
        def fail_report_directory(fd):
            if os.readlink('/proc/self/fd/' + str(fd))==str(self.exchange.root/'reports'):
                raise OSError('synthetic report directory sync failure')
            return sync(fd)
        with patch.object(workshop.os, 'fsync', fail_report_directory):
            with self.assertRaises(workshop.WorkshopDurabilityError):
                self.store.export_report(self.record['proposal_id'], expected_revision=1,
                    task_scope_id='fixture-workshop', sender=BUILDER, authority=self.authority())
        retained=list((self.exchange.root/'reports').glob('worker-report-*.json'))
        self.assertEqual(len(retained),1);before=retained[0].read_bytes()
        self.assertEqual(self.store.get(self.record['proposal_id'])['revision'],1)
        result=self.store.export_report(self.record['proposal_id'], expected_revision=1,
            task_scope_id='fixture-workshop', sender=BUILDER, authority=self.authority())
        self.assertEqual(result['proposal']['revision'],2)
        self.assertEqual(retained[0].read_bytes(),before)
        self.assertEqual(len(list((self.exchange.root/'reports').glob('worker-report-*.json'))),1)

    def test_report_file_sync_failure_does_not_publish_either_record(self):
        from src.memory import workshop
        self.create();sync=os.fsync
        def fail_file(fd):
            path=os.readlink('/proc/self/fd/' + str(fd))
            if '/reports/' in path and path.endswith('.tmp'):raise OSError('synthetic file sync failure')
            return sync(fd)
        with patch.object(workshop.os,'fsync',fail_file):
            with self.assertRaises(WorkshopStateError):
                self.store.export_report(self.record['proposal_id'], expected_revision=1,
                    task_scope_id='fixture-workshop', sender=BUILDER, authority=self.authority())
        self.assertEqual(list((self.exchange.root/'reports').iterdir()),[])
        self.assertEqual(self.store.get(self.record['proposal_id'])['revision'],1)

    def test_report_publication_race_never_replaces_existing_identity(self):
        from src.memory import workshop
        self.create();rename=workshop._rename_once;retained=[]
        def race(directory, temporary, filename):
            if filename.startswith('worker-report-'):
                path=self.exchange.root/'reports'/filename
                with path.open('x') as stream:stream.write('{"unrelated":"existing identity"}')
                retained.append(path)
            return rename(directory,temporary,filename)
        with patch.object(workshop,'_rename_once',race):
            with self.assertRaises(WorkshopStateError):
                self.store.export_report(self.record['proposal_id'],expected_revision=1,
                    task_scope_id='fixture-workshop',sender=BUILDER,authority=self.authority())
        self.assertEqual(retained[0].read_text(),'{"unrelated":"existing identity"}')
        self.assertEqual(self.store.get(self.record['proposal_id'])['revision'],1)

    def test_new_contract_or_new_label_cannot_launder_same_candidate_failure(self):
        self.declared(0)
        self.evaluated(verdict="fail")
        self.append("declare_acceptance", self.contract(0))
        self.evaluated()
        self.assertEqual(self.record["verdict"], "fail")
        payload = self.evaluation_payload()
        payload["candidate"]["candidate_id"] = "relabeled-same-candidate"
        self.append("record_evaluation", {"report_reference": self.ref(self.report("workshop-evaluation-v1", payload))})
        self.assertEqual(self.record["verdict"], "fail")
        self.evaluated(candidate_id="actually-different-candidate")
        self.assertEqual(self.record["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()

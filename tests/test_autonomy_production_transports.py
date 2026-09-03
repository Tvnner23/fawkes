import hashlib
import json
import re
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from src.runtime.codex_development_campaign import WINDOWS_REVIEWER_ROLE, WINDOWS_REVIEWER_WORKER_ID
from src.runtime.codex_worker_adapter import ADAPTER_ID, PROMOTION_RECORD
from src.runtime.disposable_verifier import DisposableVerifierWorkspace, candidate_manifest
from src.runtime.codex_write_builder_adapter import (
    MAX_TRACKED_FILES, WRITE_ADAPTER_ID, WRITE_ADAPTER_VERSION, WRITE_ADAPTER_QUALIFIED, WRITE_ADAPTER_PROMOTED,
    WRITE_PROMOTION_RECORD,
    WRITE_QUALIFICATION_CONTRACT, CodexWriteBuilderAdapter, _exact_return_schema,
    _canonical_node_evidence, _capture_frozen_tree, _diff, _exact_change_evidence, _relative_scopes,
    _scope_contract, _validate_candidate_changes, _workspace_snapshot,
)
from src.runtime.windows_codex_reviewer import (
    WINDOWS_ADAPTER_ID, WINDOWS_ADAPTER_QUALIFIED, WINDOWS_ADAPTER_PROMOTED,
    WINDOWS_CODEX_WORKER_REFERENCE, WINDOWS_ENVIRONMENT_ID,
    WINDOWS_PROMOTION_RECORD, WINDOWS_REVIEW_SNAPSHOT_PARENT, WINDOWS_TRANSPORT_CONFORMANCE, WindowsCodexReviewAdapter,
    materialize_standing_windows_snapshot, prepare_windows_review_package,
    validate_windows_review_return, verify_standing_windows_snapshot,
)
from src.runtime.worker_exchange import WorkerExchange, _digest


def authority(instance, task, sender, recipient=None, **extra):
    result = {"decision": "authorized", "instance_id": instance, "task_scope_id": task,
        "sender_worker_id": sender, "authorization_reference": f"auth-{task}",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), **extra}
    if recipient:
        result["recipient_worker_id"] = recipient
    return result


class FakeWriteCodex:
    def __init__(self, workspace, changed_path="src/allowed.py", *, malformed=False):
        self.workspace = workspace; self.changed_path = changed_path; self.malformed = malformed

    def __call__(self, command, *, prompt, environment, timeout):
        if command[-1:] != ["-"]:
            text = "codex-cli 0.0-fixture" if "--version" in command else "Logged in using fixture"
            return SimpleNamespace(returncode=0, stdout=text, stderr="")
        self.environment = environment
        execution_workspace = Path(command[command.index("--cd") + 1])
        target = execution_workspace / self.changed_path
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text("changed\n", encoding="utf-8")
        package_path = Path(prompt.split("Package file: ", 1)[1].splitlines()[0])
        package = json.loads(package_path.read_text(encoding="utf-8"))
        output = Path(command[command.index("--output-last-message") + 1])
        response = {"schema_version": 1, "package_id": package["package_id"],
            "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
            "source_report_id": package["source_report_id"], "task_scope_id": package["task_scope_id"],
            "recipient": {"worker_id": package["recipient"]["worker_id"],
                "role": package["recipient"]["role"],
                "environment_id": f"codex-cli:{self.workspace.resolve()}"},
            "source_summary_distinction_confirmed": True,
            "sections": [{"section_id": "result", "title": "Result", "content": "Exact result"}],
            "verification": {"status": "accepted", "checked_claim_ids": ["done"],
                "evidence_references": [], "method": "fixture write and tests",
                "material_reliance": True, "relied_source_section_ids": ["task"],
                "caveats": [], "counterclaim": None}}
        output.write_text("{" if self.malformed else json.dumps(response), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class EnvironmentRecordingWriteCodex(FakeWriteCodex):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.calls = []

    def __call__(self, command, *, prompt, environment, timeout):
        self.calls.append({"command": list(command), "environment": dict(environment),
                           "timeout": timeout})
        return super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)


class RuntimeDatabaseWriteCodex(FakeWriteCodex):
    def __call__(self, command, *, prompt, environment, timeout):
        completed = super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)
        if command[-1:] == ["-"]:
            database = Path(environment["FAWKES_MEMORY_LEDGER_PATH"])
            database.parent.mkdir(parents=True, exist_ok=True)
            database.write_bytes(b"disposable runtime state")
        return completed


class SymlinkWriteCodex(FakeWriteCodex):
    def __call__(self, command, *, prompt, environment, timeout):
        completed = super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)
        if command[-1:] == ["-"]:
            target = Path(command[command.index("--cd") + 1]) / self.changed_path
            target.unlink(); target.symlink_to("../outside-target")
        return completed


class DeleteWriteCodex(FakeWriteCodex):
    def __call__(self, command, *, prompt, environment, timeout):
        completed = super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)
        if command[-1:] == ["-"]:
            (Path(command[command.index("--cd") + 1]) / self.changed_path).unlink()
        return completed


class ConcurrentAuthoritativeWriteCodex(FakeWriteCodex):
    def __init__(self, workspace, *, target=False):
        super().__init__(workspace)
        self.target = target

    def __call__(self, command, *, prompt, environment, timeout):
        completed = super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)
        if command[-1:] == ["-"]:
            target = (self.workspace / "src/allowed.py" if self.target
                      else self.workspace / "archive/meta/concurrent.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("concurrent\n", encoding="utf-8")
        return completed


class MultiWriteCodex(FakeWriteCodex):
    def __call__(self, command, *, prompt, environment, timeout):
        completed = super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)
        if command[-1:] == ["-"]:
            root = Path(command[command.index("--cd") + 1])
            (root / "src/second.py").write_text("second changed\n", encoding="utf-8")
        return completed


class UnknownClaimWriteCodex(FakeWriteCodex):
    def __call__(self, command, *, prompt, environment, timeout):
        completed = super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)
        if command[-1:] == ["-"]:
            output = Path(command[command.index("--output-last-message") + 1])
            response = json.loads(output.read_text(encoding="utf-8"))
            response["verification"]["checked_claim_ids"] = ["unknown"]
            output.write_text(json.dumps(response), encoding="utf-8")
        return completed


class FakeWindowsCodex:
    def __init__(self): self.prompt = None
    @staticmethod
    def _path(value):
        prefix = "\\\\wsl.localhost\\Ubuntu"
        return Path("/" + value[len(prefix):].replace("\\", "/").lstrip("/"))
    def __call__(self, command, *, prompt, environment, timeout):
        if "--version" in command:
            return SimpleNamespace(returncode=0, stdout="codex-cli 0.151.0-alpha.7.2\n", stderr="")
        if command[1:3] == ["login", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        self.prompt = prompt
        output = self._path(command[command.index("--output-last-message") + 1])
        package_text = prompt.split("----- BEGIN EXACT WORKER EXCHANGE PACKAGE (UTF-8) -----\n", 1)[1].split(
            "\n----- END EXACT WORKER EXCHANGE PACKAGE -----", 1)[0]
        package = json.loads(package_text); package_bytes = package_text.encode()
        invocation = re.search(r"Exact review invocation: ([^\n]+)", prompt).group(1)
        snapshot = re.search(r"Frozen read-only candidate snapshot: ([^\n]+)", prompt).group(1)
        response = {"schema_version": 1, "review_invocation_id": invocation,
            "candidate_snapshot_id": snapshot,
            "package_id": package["package_id"],
            "package_sha256": hashlib.sha256(package_bytes).hexdigest(),
            "source_report_id": package["source_report_id"], "task_scope_id": package["task_scope_id"],
            "recipient": {"worker_id": package["recipient"]["worker_id"],
                "role": package["recipient"]["role"], "environment_id": WINDOWS_ENVIRONMENT_ID},
            "source_summary_distinction_confirmed": True, "review_status": "pass",
            "acceptance_condition_ids_satisfied": ["done"], "violated_acceptance_condition_ids": [],
            "defects": [], "correctable_within_scope": False,
            "sections": [{"section_id": "verdict", "title": "Verdict", "content": "Exact evidence passes."}],
            "verification": {"status": "accepted", "checked_claim_ids": ["done"],
                "evidence_references": package["evidence_references"], "method": "exact supplied evidence review",
                "material_reliance": True, "relied_source_section_ids": ["exact-builder-return"],
                "caveats": [], "counterclaim": None}}
        output.write_text(json.dumps(response), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="json event body", stderr="")


class ContradictoryInsufficientWindowsCodex(FakeWindowsCodex):
    def __call__(self, command, *, prompt, environment, timeout):
        completed = super().__call__(command, prompt=prompt, environment=environment, timeout=timeout)
        if command[-1:] == ["-"]:
            output = self._path(command[command.index("--output-last-message") + 1])
            response = json.loads(output.read_text(encoding="utf-8"))
            response["review_status"] = "insufficient_evidence"
            output.write_text(json.dumps(response), encoding="utf-8")
        return completed


class AutonomyProductionTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.workspace = root / "repo"; self.workspace.mkdir()
        (self.workspace / ".git").mkdir(); (self.workspace / "src").mkdir()
        (self.workspace / "src/allowed.py").write_text("before\n")
        self.exchange = WorkerExchange("fawkes", root=root / "exchange")
        self.sender = {"worker_id": "fawkes-development", "role": "coordination",
                       "identity_status": "verified", "charter_version": "1.0"}
        self.recipient = {"worker_id": "codex-repository-wsl-fawkes", "role": "software_repository",
                          "identity_status": "rider_attested", "charter_version": "1.0"}
        self.task = "write-task"; self.campaign = "campaign"; self.iteration = 1
        self.report = self.exchange.create_report(task_scope_id=self.task, sender=self.sender,
            authority=authority("fawkes", self.task, self.sender["worker_id"]),
            sections=[{"section_id": "task", "title": "Task", "content": "Change only allowed.py"}],
            claims=[{"claim_id": "done", "area": "development", "statement": "change done",
                     "maturity": "in_development", "change_class": "software_system"}])
        self.base_transport = authority("fawkes", self.task, self.sender["worker_id"],
            self.recipient["worker_id"])
        self.package = self.exchange.compose_package(report_id=self.report["report_id"],
            recipient=self.recipient, authority=self.base_transport, included_section_ids=["task"])
        self.environment = f"codex-cli:{self.workspace.resolve()}"
        self.scopes = ["src/allowed.py"]
        self.recovery = [{"reference_type": "working_checkpoint", "reference_id": "before-write"}]
        self.write_task = "Modify only src/allowed.py and report the result."

    def transport(self):
        return {**self.base_transport, "adapter_id": WRITE_ADAPTER_ID,
            "package_id": self.package["package_id"], "recipient_environment_id": self.environment,
            "write_task_sha256": hashlib.sha256(self.write_task.encode()).hexdigest(),
            "campaign_id": self.campaign, "iteration": self.iteration,
            "allowed_scope_sha256": _digest(self.scopes),
            "acceptance_condition_ids_sha256": _digest(["done"]),
            "recovery_references_sha256": _digest(self.recovery)}

    def invoke(self, fake=None, **adapter_options):
        timeout_seconds = adapter_options.pop("timeout_seconds", 5)
        adapter = CodexWriteBuilderAdapter(self.exchange, workspace=self.workspace,
            run_process=fake or FakeWriteCodex(self.workspace), timeout_seconds=timeout_seconds,
            **adapter_options)
        return adapter.deliver_candidate_once(package_id=self.package["package_id"],
            transport_authority=self.transport(),
            return_authority=authority("fawkes", self.task, self.recipient["worker_id"]),
            recipient_environment_id=self.environment, write_task=self.write_task,
            campaign_id=self.campaign, iteration=self.iteration, allowed_scope=self.scopes,
            acceptance_condition_ids=["done"], recovery_references=self.recovery)

    def test_read_only_and_write_modes_have_independent_exact_promotions(self):
        self.assertEqual(ADAPTER_ID, "codex-cli-exec-local")
        self.assertEqual(PROMOTION_RECORD["scope"], "bounded_ephemeral_read_only_codex_cli_transport")
        self.assertTrue(WRITE_ADAPTER_QUALIFIED)
        self.assertTrue(WRITE_ADAPTER_PROMOTED)
        self.assertEqual(WRITE_ADAPTER_VERSION, "0.5")
        self.assertNotEqual(PROMOTION_RECORD["promotion_id"], WRITE_PROMOTION_RECORD["promotion_id"])
        self.assertEqual(WRITE_PROMOTION_RECORD["snapshot_identity_policy_version"],
                         "phoenix-portable-snapshot-identity-v2")
        self.assertTrue(WRITE_QUALIFICATION_CONTRACT["independent_assurance_required"])

    def test_write_return_schema_binds_exact_lineage_recipient_and_claims(self):
        package_sha = "a" * 64
        bound_recipient = {"worker_id": self.recipient["worker_id"],
                           "role": self.recipient["role"],
                           "environment_id": self.environment}
        schema = _exact_return_schema(package=self.package, package_sha=package_sha,
                                      recipient=bound_recipient)
        properties = schema["properties"]
        self.assertEqual(properties["package_id"]["const"], self.package["package_id"])
        self.assertEqual(properties["package_sha256"]["const"], package_sha)
        self.assertEqual(properties["source_report_id"]["const"], self.package["source_report_id"])
        self.assertEqual(properties["task_scope_id"]["const"], self.package["task_scope_id"])
        for key, value in bound_recipient.items():
            self.assertEqual(properties["recipient"]["properties"][key]["const"], value)
        self.assertEqual(properties["verification"]["properties"]["checked_claim_ids"]
                         ["items"]["enum"], ["done"])

    def test_capacity_revision_is_bounded_and_over_limit_failure_is_durable(self):
        self.assertEqual(MAX_TRACKED_FILES, 30_000)
        (self.workspace / "second.py").write_text("two\n", encoding="utf-8")
        with patch("src.runtime.codex_write_builder_adapter.MAX_TRACKED_FILES", 1):
            result = self.invoke()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "workspace_snapshot_capacity_exceeded")
        self.assertEqual(result["workspace_changes"], [])
        self.assertFalse(result["recovery_required"])
        self.assertEqual(result["failure_detail"],
                         "workspace exceeds bounded write snapshot file limit")

    @unittest.skipUnless(os.environ.get("FAWKES_WRITE_CAPACITY_ACCEPTANCE") == "1",
                         "set FAWKES_WRITE_CAPACITY_ACCEPTANCE=1 for real workspace capacity evidence")
    def test_real_cumulative_workspace_exceeds_old_limit_and_fits_new_bound(self):
        snapshot = _workspace_snapshot(Path(__file__).resolve().parents[1])
        self.assertGreater(len(snapshot), 20_000)
        self.assertLessEqual(len(snapshot), MAX_TRACKED_FILES)

    def test_production_write_requires_and_records_exact_promotion_binding(self):
        transport = {**self.transport(),
            "adapter_promotion_reference": WRITE_PROMOTION_RECORD["promotion_id"]}
        adapter = CodexWriteBuilderAdapter(self.exchange, workspace=self.workspace,
            run_process=FakeWriteCodex(self.workspace), timeout_seconds=5)
        arguments = dict(
                package_id=self.package["package_id"], transport_authority=transport,
                return_authority=authority("fawkes", self.task, self.recipient["worker_id"]),
                recipient_environment_id=self.environment, write_task=self.write_task,
                campaign_id=self.campaign, iteration=1, allowed_scope=self.scopes,
                acceptance_condition_ids=["done"], recovery_references=self.recovery)
        if not WRITE_ADAPTER_PROMOTED:
            with self.assertRaises(PermissionError):
                adapter.deliver_production_once(**arguments)
            return
        result = adapter.deliver_production_once(**arguments)
        self.assertTrue(result["candidate_qualified"])
        self.assertTrue(result["adapter_promoted"])
        self.assertEqual(result["adapter_promotion_reference"], WRITE_PROMOTION_RECORD["promotion_id"])

    def test_exact_in_scope_write_returns_diff_and_zero_authority_evidence(self):
        fake = FakeWriteCodex(self.workspace); result = self.invoke(fake)
        self.assertEqual(result["status"], "delivered")
        self.assertEqual([item["path"] for item in result["workspace_changes"]], ["src/allowed.py"])
        self.assertEqual(result["out_of_scope_changes"], [])
        self.assertFalse(result["candidate_qualified"]); self.assertFalse(result["adapter_promoted"])
        returned = self.exchange._load("reports", result["return_report_id"])
        self.assertFalse(returned["creates_authority"])
        self.assertEqual(fake.environment["PYTHONDONTWRITEBYTECODE"], "1")

    def test_batch_e_directory_scope_captures_nested_modify_add_remove_exactly(self):
        baseline = Path(self.tmp.name) / "frozen"; candidate = Path(self.tmp.name) / "mutable"
        for root in (baseline, candidate):
            (root / "src/tree").mkdir(parents=True)
            (root / "src/tree/kept.py").write_text("old\n")
            (root / "src/tree/removed.py").write_text("remove\n")
        before = _workspace_snapshot(baseline)
        contract = _scope_contract(["src/tree"], before)
        frozen = _capture_frozen_tree(baseline, before, contract)
        (candidate / "src/tree/kept.py").write_text("new\n")
        (candidate / "src/tree/removed.py").unlink()
        (candidate / "src/tree/nested").mkdir()
        (candidate / "src/tree/nested/added.py").write_text("added\n")
        changes = _diff(before, _workspace_snapshot(candidate))
        evidence, digest = _exact_change_evidence(candidate, changes, frozen)
        self.assertEqual([item["path"] for item in changes], sorted(item["path"] for item in changes))
        self.assertEqual({item["path"] for item in evidence}, {item["path"] for item in changes})
        removed = next(item for item in evidence if item["path"].endswith("removed.py"))
        self.assertIsNotNone(removed["before_base64"]); self.assertIsNone(removed["after_base64"])
        self.assertEqual(digest, _digest(evidence))
        with self.assertRaisesRegex(PermissionError, "deletion"):
            _validate_candidate_changes(changes, contract)

    def test_batch_e_exact_file_scope_rejects_nested_neighbor_and_traversal(self):
        baseline = _workspace_snapshot(self.workspace)
        contract = _scope_contract(["src/allowed.py"], baseline)
        neighbor = {"path": "src/allowed.py/neighbor", "status": "added", "before": None,
            "after": {"file_type": "regular", "sha256": "0" * 64,
                      "byte_length": 0, "mode": 0o644}}
        with self.assertRaisesRegex(PermissionError, "out-of-scope"):
            _validate_candidate_changes([neighbor], contract)
        for scope in ("../escape", "src/../../escape", "/absolute"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                _relative_scopes([scope])

    def test_batch_e_mode_symlink_and_type_replacements_are_evidenced_then_closed(self):
        baseline = Path(self.tmp.name) / "frozen-types"; candidate = Path(self.tmp.name) / "mutable-types"
        for root in (baseline, candidate):
            root.mkdir(); (root / "mode.py").write_text("same\n"); (root / "kind.py").write_text("old\n")
        before = _workspace_snapshot(baseline)
        contract = _scope_contract(["mode.py", "kind.py"], before)
        frozen = _capture_frozen_tree(baseline, before, contract)
        (candidate / "mode.py").chmod(0o755)
        (candidate / "kind.py").unlink(); (candidate / "kind.py").symlink_to("mode.py")
        changes = _diff(before, _workspace_snapshot(candidate))
        evidence, _ = _exact_change_evidence(candidate, changes, frozen)
        self.assertEqual(next(item for item in evidence if item["path"] == "mode.py")["after_mode"], 0o755)
        kind = next(item for item in evidence if item["path"] == "kind.py")
        self.assertEqual(kind["after_type"], "symlink")
        self.assertEqual(kind["after_symlink_target"], "mode.py")
        with self.assertRaises(PermissionError):
            _validate_candidate_changes(changes, contract)

    def test_batch_e_symlink_add_change_remove_targets_are_exact(self):
        baseline = Path(self.tmp.name) / "frozen-links"
        candidate = Path(self.tmp.name) / "mutable-links"
        for root in (baseline, candidate):
            root.mkdir()
            (root / "target-a").write_text("a\n")
            (root / "target-b").write_text("b\n")
        (baseline / "changed").symlink_to("target-a")
        (baseline / "removed").symlink_to("target-a")
        (candidate / "changed").symlink_to("target-b")
        (candidate / "added").symlink_to("target-a")
        before = _workspace_snapshot(baseline)
        contract = _scope_contract(["changed", "removed", "added"], before)
        frozen = _capture_frozen_tree(baseline, before, contract)
        evidence, _ = _exact_change_evidence(
            candidate, _diff(before, _workspace_snapshot(candidate)), frozen)
        by_path = {item["path"]: item for item in evidence}
        self.assertEqual((by_path["changed"]["before_symlink_target"],
                          by_path["changed"]["after_symlink_target"]),
                         ("target-a", "target-b"))
        self.assertEqual(by_path["removed"]["before_symlink_target"], "target-a")
        self.assertIsNone(by_path["removed"]["after_symlink_target"])
        self.assertIsNone(by_path["added"]["before_symlink_target"])
        self.assertEqual(by_path["added"]["after_symlink_target"], "target-a")
        self.assertNotEqual(by_path["changed"]["eligibility_receipt"]["before"]["sha256"],
                            by_path["changed"]["eligibility_receipt"]["after"]["sha256"])
        self.assertEqual(by_path["changed"]["before_node_binding"]["body_sha256"],
                         hashlib.sha256(b"target-a").hexdigest())
        self.assertEqual(by_path["changed"]["after_node_binding"]["body_sha256"],
                         hashlib.sha256(b"target-b").hexdigest())

    def test_batch_e_node_binding_distinguishes_presence_type_and_mode(self):
        absent, _ = _canonical_node_evidence(None, None)
        regular, _ = _canonical_node_evidence(
            {"file_type": "regular", "mode": 0o644}, b"")
        directory, _ = _canonical_node_evidence(
            {"file_type": "directory", "mode": 0o644}, None)
        symlink, _ = _canonical_node_evidence(
            {"file_type": "symlink", "mode": 0o777, "target": ""}, None)
        executable, _ = _canonical_node_evidence(
            {"file_type": "regular", "mode": 0o755}, b"")
        bindings = {hashlib.sha256(item).hexdigest()
                    for item in (absent, regular, directory, symlink, executable)}
        self.assertEqual(len(bindings), 5)
        self.assertEqual(regular, _canonical_node_evidence(
            {"file_type": "regular", "mode": 0o644}, b"")[0])

    def test_batch_e_node_binding_leaves_source_bytes_visible_to_classifier(self):
        marker = b"synthetic-visible-source-marker"
        encoded, binding = _canonical_node_evidence(
            {"file_type": "regular", "mode": 0o600}, marker)
        self.assertTrue(encoded.endswith(marker))
        self.assertEqual(binding["body_sha256"], hashlib.sha256(marker).hexdigest())

    def test_batch_e_frozen_preimage_determinism_and_classification_precedes_bodies(self):
        baseline = Path(self.tmp.name) / "frozen-proof"; candidate = Path(self.tmp.name) / "mutable-proof"
        baseline.mkdir(); candidate.mkdir()
        (baseline / "one.py").write_text("baseline\n"); (candidate / "one.py").write_text("after\n")
        before = _workspace_snapshot(baseline); contract = _scope_contract(["one.py"], before)
        frozen = _capture_frozen_tree(baseline, before, contract)
        # Later authoritative drift cannot alter the already frozen preimage.
        (self.workspace / "src/allowed.py").write_text("concurrent unrelated\n")
        changes = _diff(before, _workspace_snapshot(candidate))
        first, first_digest = _exact_change_evidence(candidate, changes, frozen)
        second, second_digest = _exact_change_evidence(candidate, list(reversed(changes)), frozen)
        self.assertEqual(first, second); self.assertEqual(first_digest, second_digest)
        self.assertIn("YmFzZWxpbmUK", first[0]["before_base64"])
        denied = {"classification": "blocked_fixture", "disclosure_allowed": False}
        with patch("src.runtime.codex_write_builder_adapter.classify_reviewer_source_evidence",
                   return_value=denied) as classify:
            with self.assertRaisesRegex(PermissionError, "blocked_fixture"):
                _exact_change_evidence(candidate, changes, frozen)
        classify.assert_called_once()

    def test_external_runtime_root_reaches_every_adapter_subprocess_without_secrets(self):
        external = Path(self.tmp.name) / "external-state"
        external.mkdir()
        fake = EnvironmentRecordingWriteCodex(self.workspace)
        with patch.dict(os.environ, {
                "FAWKES_DISCORD_WEBHOOK_URL": "not-forwarded",
                "FAWKES_APP_TOKEN": "not-forwarded",
                "UNRELATED_HOST_SETTING": "not-forwarded"}, clear=False):
            result = self.invoke(fake, runtime_state_root=external, timeout_seconds=1800)
        self.assertEqual(result["status"], "delivered")
        self.assertGreaterEqual(len(fake.calls), 3)
        self.assertTrue(any("--version" in item["command"] for item in fake.calls))
        self.assertTrue(any("login" in item["command"] for item in fake.calls))
        self.assertTrue(any(item["command"][-1:] == ["-"] for item in fake.calls))
        self.assertEqual(next(item["timeout"] for item in fake.calls
                              if item["command"][-1:] == ["-"]), 1800)
        for item in fake.calls:
            self.assertEqual(item["environment"]["FAWKES_RUNTIME_STATE_ROOT"],
                             str(external.resolve()))
            self.assertNotIn("FAWKES_DISCORD_WEBHOOK_URL", item["environment"])
            self.assertNotIn("FAWKES_APP_TOKEN", item["environment"])
            self.assertNotIn("UNRELATED_HOST_SETTING", item["environment"])

    def test_runtime_root_is_optional_and_invalid_roots_fail_closed(self):
        fake = EnvironmentRecordingWriteCodex(self.workspace)
        self.assertEqual(self.invoke(fake)["status"], "delivered")
        self.assertTrue(all("FAWKES_RUNTIME_STATE_ROOT" not in item["environment"]
                            for item in fake.calls))
        invalid = ["relative", self.workspace, Path(self.tmp.name) / "missing"]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                CodexWriteBuilderAdapter(self.exchange, workspace=self.workspace,
                    run_process=FakeWriteCodex(self.workspace), runtime_state_root=value)

    def test_private_memory_database_is_outside_candidate_but_not_globally_excluded(self):
        fake = RuntimeDatabaseWriteCodex(self.workspace)
        result = self.invoke(fake)
        self.assertEqual(result["status"], "delivered")
        self.assertEqual([item["path"] for item in result["workspace_changes"]], ["src/allowed.py"])
        configured = Path(fake.environment["FAWKES_MEMORY_LEDGER_PATH"])
        self.assertNotEqual(configured, self.workspace / "database/memory_processing.sqlite3")
        self.assertFalse((self.workspace / "database/memory_processing.sqlite3").exists())
        self.assertNotIn(".sqlite", json.dumps(result))

    def test_exact_review_evidence_is_idempotent_and_stale_artifact_fails_closed(self):
        result = self.invoke()
        returned = self.exchange._load("reports", result["return_report_id"])
        campaign = {"instance_id": "fawkes", "campaign_id": self.campaign,
            "status": "awaiting_independent_review", "iteration": 1,
            "objective": "Review the exact bounded candidate.",
            "acceptance_condition_ids": ["done"],
            "acceptance_conditions": {"done": "The bounded change is exact."},
            "allowed_scope": ["src/allowed.py"], "recovery_references": self.recovery,
            "contract_version": "fixture-campaign-v1",
            "builder_runs": [{"iteration": 1, "package_id": self.package["package_id"],
                "return_report_id": returned["report_id"],
                "transport_result_reference": {"workspace_changes_sha256":
                    result["workspace_changes_sha256"]}, "validation_evidence": [{"argv": ["python3", "-m", "unittest"],
                    "exit_status": 0, "stdout": "OK\n", "stdout_sha256": hashlib.sha256(b"OK\n").hexdigest(),
                    "stderr": "", "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                    "bytecode_prevention": True}], "cache_cleanup": {"removed": [],
                    "absence_verified": True}, "completed_at": datetime.now(timezone.utc).isoformat()}]}
        snapshot = candidate_manifest(self.workspace)
        first = prepare_windows_review_package(exchange=self.exchange, campaign_record=campaign,
            candidate_snapshot={**snapshot, "record_sha256": _digest(snapshot),
                "file_count": len(snapshot["files"]),
                "total_byte_length": sum(item["byte_length"] for item in snapshot["files"])},
            workspace=self.workspace)
        second = prepare_windows_review_package(exchange=self.exchange, campaign_record=campaign,
            candidate_snapshot={**snapshot, "record_sha256": _digest(snapshot),
                "file_count": len(snapshot["files"]),
                "total_byte_length": sum(item["byte_length"] for item in snapshot["files"])},
            workspace=self.workspace)
        self.assertEqual(first["source_report_id"], second["source_report_id"])
        self.assertEqual(first["package_id"], second["package_id"])
        package = self.exchange._load("packages", first["package_id"])
        section_ids = {item["section_id"] for item in package["included_sections"]}
        self.assertTrue({"mutation-manifest", "validation-evidence", "candidate-snapshot",
                         "changed-artifact-1"} <= section_ids)
        (self.workspace / "src/allowed.py").write_text("stale\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            prepare_windows_review_package(exchange=self.exchange, campaign_record=campaign,
                candidate_snapshot={**snapshot, "record_sha256": _digest(snapshot),
                    "file_count": len(snapshot["files"]), "total_byte_length": 0},
                workspace=self.workspace)

    def test_out_of_scope_disposable_write_fails_without_authoritative_recovery(self):
        result = self.invoke(FakeWriteCodex(self.workspace, "outside.py"))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "unauthorized_file_mutation")
        self.assertEqual(result["out_of_scope_changes"], ["outside.py"])
        self.assertFalse(result["recovery_required"])

    def test_authorized_new_file_applies_but_deletion_fails_closed(self):
        self.scopes = ["src/new.py"]
        result = self.invoke(FakeWriteCodex(self.workspace, "src/new.py"))
        self.assertEqual(result["status"], "delivered")
        self.assertEqual((self.workspace / "src/new.py").read_text(), "changed\n")

        # A distinct package/attempt is required for a second consequential use.
        self.setUp()
        result = self.invoke(DeleteWriteCodex(self.workspace))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "validated_apply_failed")
        self.assertIn("deletion was not explicitly authorized", result["failure_detail"])
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "before\n")

    def test_unrelated_concurrent_archive_is_preserved_and_target_drift_fails_closed(self):
        result = self.invoke(ConcurrentAuthoritativeWriteCodex(self.workspace))
        self.assertEqual(result["status"], "delivered")
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "changed\n")
        self.assertEqual((self.workspace / "archive/meta/concurrent.json").read_text(), "concurrent\n")
        self.assertTrue(result["application_evidence"]["unrelated_authoritative_changes_ignored"])

        self.setUp()
        result = self.invoke(ConcurrentAuthoritativeWriteCodex(self.workspace, target=True))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "validated_apply_failed")
        self.assertIn("target_file_drift", result["failure_detail"])
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "concurrent\n")

    def test_partial_apply_failure_rolls_back_all_applied_paths(self):
        (self.workspace / "src/second.py").write_text("second before\n", encoding="utf-8")
        self.scopes = ["src/allowed.py", "src/second.py"]
        calls = {"count": 0}

        def fail_second_replace(source, target):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected second replace failure")
            return os.replace(source, target)

        result = self.invoke(MultiWriteCodex(self.workspace), apply_replace=fail_second_replace)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "validated_apply_failed")
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "before\n")
        self.assertEqual((self.workspace / "src/second.py").read_text(), "second before\n")

    def test_partial_apply_failure_preserves_drifted_applied_target(self):
        (self.workspace / "src/second.py").write_text("second before\n", encoding="utf-8")
        self.scopes = ["src/allowed.py", "src/second.py"]
        calls = {"count": 0}

        def drift_then_fail_second(source, target):
            calls["count"] += 1
            if calls["count"] == 2:
                (self.workspace / "src/allowed.py").write_text("concurrent\n", encoding="utf-8")
                raise OSError("injected second replace failure")
            return os.replace(source, target)

        result = self.invoke(MultiWriteCodex(self.workspace), apply_replace=drift_then_fail_second)
        evidence = result["application_evidence"]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(evidence["status"], "rollback_failed_recovery_required")
        self.assertFalse(evidence["rollback_performed"])
        self.assertTrue(evidence["recovery_required"])
        self.assertIn("rollback_target_drift", result["failure_detail"])
        self.assertIn(hashlib.sha256(b"concurrent\n").hexdigest(), result["failure_detail"])
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "concurrent\n")
        self.assertEqual((self.workspace / "src/second.py").read_text(), "second before\n")

    def test_unknown_claim_fails_before_apply_and_preserves_authoritative_target(self):
        result = self.invoke(UnknownClaimWriteCodex(self.workspace))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "malformed_or_unbound_response")
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "before\n")
        self.assertFalse(result["recovery_required"])

    def test_exchange_recording_failure_after_apply_restores_target(self):
        with patch.object(self.exchange, "record_verification", side_effect=ValueError("injected evidence failure")):
            result = self.invoke()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "exchange_evidence_recording_failed_after_apply")
        self.assertTrue(result["application_evidence"]["rollback_performed"])
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "before\n")

    def test_exchange_failure_rollback_preserves_concurrent_existing_target_drift(self):
        def drift_then_fail(*args, **kwargs):
            (self.workspace / "src/allowed.py").write_text("concurrent\n", encoding="utf-8")
            raise ValueError("injected evidence failure")

        with patch.object(self.exchange, "record_verification", side_effect=drift_then_fail):
            result = self.invoke()
        evidence = result["application_evidence"]
        self.assertEqual(result["status"], "failed")
        self.assertFalse(evidence["rollback_performed"])
        self.assertTrue(evidence["recovery_required"])
        self.assertIn("rollback_target_drift", evidence["rollback_error_detail"])
        self.assertIn(hashlib.sha256(b"concurrent\n").hexdigest(),
                      evidence["rollback_error_detail"])
        self.assertEqual((self.workspace / "src/allowed.py").read_text(), "concurrent\n")

    def test_exchange_failure_rollback_preserves_concurrent_new_target_drift(self):
        self.scopes = ["src/new.py"]

        def drift_then_fail(*args, **kwargs):
            (self.workspace / "src/new.py").write_text("concurrent\n", encoding="utf-8")
            raise ValueError("injected evidence failure")

        with patch.object(self.exchange, "record_verification", side_effect=drift_then_fail):
            result = self.invoke(FakeWriteCodex(self.workspace, "src/new.py"))
        evidence = result["application_evidence"]
        self.assertFalse(evidence["rollback_performed"])
        self.assertTrue(evidence["recovery_required"])
        self.assertIn('\"disposition\": \"preserved\"', evidence["rollback_error_detail"])
        self.assertEqual((self.workspace / "src/new.py").read_text(), "concurrent\n")

    def test_bytecode_cache_is_disposable_but_not_an_invisible_write_surface(self):
        result = self.invoke(FakeWriteCodex(self.workspace, "src/__pycache__/hidden.pyc"))
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(result["workspace_changes"], [])
        self.assertEqual(result["cache_cleanup"]["removed"][0]["path"],
                         "src/__pycache__/hidden.pyc")
        self.assertTrue(result["cache_cleanup"]["absence_verified"])
        self.assertFalse((self.workspace / "src/__pycache__/hidden.pyc").exists())

    def test_symlink_candidate_fails_without_authoritative_recovery_need(self):
        result = self.invoke(SymlinkWriteCodex(self.workspace))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "symlink_mutation_forbidden")
        self.assertFalse(result["recovery_required"])
        self.assertEqual(result["workspace_changes"][0]["after"]["file_type"], "symlink")

    def test_preexisting_workspace_symlink_blocks_before_invocation(self):
        link = self.workspace / "src/link.py"; link.symlink_to("../../outside")
        fake = FakeWriteCodex(self.workspace)
        self.scopes = ["src/link.py"]
        result = self.invoke(fake)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "preexisting_symlink_forbidden")

    def test_wrong_binding_missing_recovery_and_malformed_return_fail_closed(self):
        adapter = CodexWriteBuilderAdapter(self.exchange, workspace=self.workspace,
            run_process=FakeWriteCodex(self.workspace), timeout_seconds=5)
        with self.assertRaises(PermissionError):
            adapter.deliver_candidate_once(package_id=self.package["package_id"],
                transport_authority={**self.transport(), "campaign_id": "other"},
                return_authority=authority("fawkes", self.task, self.recipient["worker_id"]),
                recipient_environment_id=self.environment, write_task=self.write_task,
                campaign_id=self.campaign, iteration=1, allowed_scope=self.scopes,
                acceptance_condition_ids=["done"], recovery_references=self.recovery)
        with self.assertRaises(ValueError):
            adapter.deliver_candidate_once(package_id=self.package["package_id"],
                transport_authority=self.transport(),
                return_authority=authority("fawkes", self.task, self.recipient["worker_id"]),
                recipient_environment_id=self.environment, write_task=self.write_task,
                campaign_id=self.campaign, iteration=1, allowed_scope=self.scopes,
                acceptance_condition_ids=["done"], recovery_references=[])
        with self.assertRaises(ValueError):
            adapter.deliver_candidate_once(package_id=self.package["package_id"],
                transport_authority=self.transport(),
                return_authority=authority("fawkes", self.task, self.recipient["worker_id"]),
                recipient_environment_id=self.environment, write_task=self.write_task,
                campaign_id=self.campaign, iteration=True, allowed_scope=self.scopes,
                acceptance_condition_ids=["done"], recovery_references=self.recovery)
        with self.assertRaises(PermissionError):
            adapter.deliver_candidate_once(package_id=self.package["package_id"],
                transport_authority=self.transport(),
                return_authority=authority("fawkes", self.task, self.recipient["worker_id"]),
                recipient_environment_id=self.environment, write_task=self.write_task,
                campaign_id=self.campaign, iteration=1, allowed_scope=self.scopes,
                acceptance_condition_ids=["different"], recovery_references=self.recovery)

    def test_standing_windows_snapshot_is_exact_frozen_and_no_writeback(self):
        source = Path(self.tmp.name) / "standing-source"
        parent = Path(self.tmp.name) / "windows-local"
        for relative, content in (("src/core.py", "one\n"),
                                  ("tests/test_core.py", "test\n"),
                                  ("docs/architecture.md", "design\n")):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (source / ".env").write_text("SECRET=excluded\n", encoding="utf-8")
        (source / "database").mkdir()
        (source / "database/private.sqlite3").write_bytes(b"private")

        first = materialize_standing_windows_snapshot(source, parent=parent)
        snapshot = Path(first["snapshot_root"])
        repository = snapshot / "repository"
        self.assertTrue(first["created"])
        self.assertTrue(first["integrity_verified"])
        self.assertTrue(first["matches_current_source"])
        self.assertNotIn(".materializing-", first["repository_path_windows"])
        self.assertIn(first["candidate_snapshot_id"], first["repository_path_windows"])
        self.assertTrue((repository / "src/core.py").is_file())
        self.assertTrue((repository / "tests/test_core.py").is_file())
        self.assertTrue((repository / "docs/architecture.md").is_file())
        self.assertFalse((repository / ".env").exists())
        self.assertFalse((repository / "database").exists())
        self.assertNotEqual(repository.resolve(), source.resolve())

        # Even deliberate local snapshot mutation cannot write back to source,
        # and integrity verification makes the altered copy unusable as truth.
        copied = repository / "src/core.py"
        copied.chmod(0o644)
        copied.write_text("snapshot-only\n", encoding="utf-8")
        self.assertEqual((source / "src/core.py").read_text(encoding="utf-8"), "one\n")
        with self.assertRaises(ValueError):
            verify_standing_windows_snapshot(snapshot)
        copied.write_text("one\n", encoding="utf-8")
        copied.chmod(0o444)
        self.assertTrue(verify_standing_windows_snapshot(snapshot)["integrity_verified"])

        unchanged = materialize_standing_windows_snapshot(source, parent=parent)
        self.assertFalse(unchanged["created"])
        self.assertEqual(unchanged["candidate_snapshot_id"], first["candidate_snapshot_id"])
        (source / "src/core.py").write_text("two\n", encoding="utf-8")
        refreshed = materialize_standing_windows_snapshot(source, parent=parent)
        self.assertTrue(refreshed["created"])
        self.assertNotEqual(refreshed["candidate_snapshot_id"], first["candidate_snapshot_id"])
        self.assertEqual((repository / "src/core.py").read_text(encoding="utf-8"), "one\n")
        current = json.loads((parent / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertEqual(current["candidate_snapshot_id"], refreshed["candidate_snapshot_id"])
        for directory in parent.rglob("*"):
            if directory.is_dir():
                directory.chmod(0o755)

    def test_windows_reference_is_distinct_and_non_authorizing(self):
        self.assertEqual(WINDOWS_CODEX_WORKER_REFERENCE["worker_id"], WINDOWS_REVIEWER_WORKER_ID)
        self.assertEqual(WINDOWS_CODEX_WORKER_REFERENCE["role"], WINDOWS_REVIEWER_ROLE)
        self.assertFalse(WINDOWS_CODEX_WORKER_REFERENCE["identified_is_authorized"])
        expected_status = ("promoted_bounded_read_only" if WINDOWS_ADAPTER_PROMOTED
                           else "qualified_unpromoted" if WINDOWS_ADAPTER_QUALIFIED
                           else "candidate_under_requalification")
        self.assertEqual(WINDOWS_CODEX_WORKER_REFERENCE["transport_status"], expected_status)
        self.assertTrue(WINDOWS_ADAPTER_QUALIFIED)
        self.assertTrue(WINDOWS_ADAPTER_PROMOTED)
        self.assertEqual(WINDOWS_PROMOTION_RECORD["snapshot_identity_policy_version"],
                         "phoenix-portable-snapshot-identity-v2")
        self.assertEqual(WINDOWS_TRANSPORT_CONFORMANCE["qualified"], WINDOWS_ADAPTER_QUALIFIED)
        self.assertEqual(WINDOWS_TRANSPORT_CONFORMANCE["promoted"], WINDOWS_ADAPTER_PROMOTED)
        self.assertNotEqual(WINDOWS_CODEX_WORKER_REFERENCE["worker_id"], self.recipient["worker_id"])

    def windows_fixture(self):
        builder = self.exchange.create_return_report(source_package_id=self.package["package_id"],
            task_scope_id=self.task, sender=self.recipient,
            authority=authority("fawkes", self.task, self.recipient["worker_id"]),
            sections=[{"section_id": "result", "title": "Builder result", "content": "Exact mutation and tests."}])
        review_task = "review-task"
        review_sender = self.sender
        review_recipient = {key: WINDOWS_CODEX_WORKER_REFERENCE[key]
                            for key in ("worker_id", "role", "identity_status", "charter_version")}
        source = self.exchange.create_report(task_scope_id=review_task, sender=review_sender,
            authority=authority("fawkes", review_task, review_sender["worker_id"]),
            sections=[{"section_id": "exact-builder-return", "title": "Exact builder return",
                "content": json.dumps(builder, sort_keys=True, ensure_ascii=False)}],
            claims=[{"claim_id": "done", "area": "development", "statement": "Candidate satisfies scope.",
                "maturity": "in_development", "change_class": "software_system"}],
            evidence_references=[{"reference_type": "worker_exchange_report",
                "reference_id": builder["report_id"], "sha256": builder["record_sha256"]}])
        base = authority("fawkes", review_task, review_sender["worker_id"], review_recipient["worker_id"])
        package = self.exchange.compose_package(report_id=source["report_id"], recipient=review_recipient,
            authority=base, included_section_ids=["exact-builder-return"])
        snapshot_id = candidate_manifest(self.workspace)["candidate_snapshot_id"]
        transport = {**base, "adapter_id": WINDOWS_ADAPTER_ID, "package_id": package["package_id"],
            "recipient_environment_id": WINDOWS_ENVIRONMENT_ID, "campaign_id": self.campaign,
            "builder_return_report_id": builder["report_id"], "builder_return_sha256": builder["record_sha256"],
            "candidate_snapshot_id": snapshot_id}
        return builder, package, transport, snapshot_id

    def test_windows_exact_package_stdin_return_lineage_and_zero_authority(self):
        builder, package, transport, snapshot_id = self.windows_fixture(); fake = FakeWindowsCodex()
        result = WindowsCodexReviewAdapter(self.exchange, run_process=fake, timeout_seconds=5).deliver_candidate_once(
            package_id=package["package_id"], transport_authority=transport,
            return_authority=authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
            campaign_id=self.campaign, builder_return_report_id=builder["report_id"],
            candidate_snapshot_id=snapshot_id, candidate_snapshot_root=self.workspace)
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(result["review_status"], "pass")
        self.assertFalse(result["candidate_qualified"]); self.assertFalse(result["adapter_promoted"])
        self.assertIn(self.exchange.export_package(package["package_id"]).decode(), fake.prompt)
        self.assertFalse(self.exchange._load("reports", result["return_report_id"])["creates_authority"])
        self.assertEqual(len(result["review_response_sha256"]), 64)

    def test_windows_response_invocation_and_cached_replay_are_exact(self):
        builder, package, transport, snapshot_id = self.windows_fixture()
        adapter = WindowsCodexReviewAdapter(
            self.exchange, run_process=FakeWindowsCodex(), timeout_seconds=5)
        arguments = {"package_id": package["package_id"], "transport_authority": transport,
            "return_authority": authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
            "campaign_id": self.campaign, "builder_return_report_id": builder["report_id"],
            "candidate_snapshot_id": snapshot_id, "candidate_snapshot_root": self.workspace,
            "invocation_id": "windows-review-exact"}
        first = adapter.deliver_candidate_once(**arguments)
        replay = adapter.deliver_candidate_once(**arguments)
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(first["record_sha256"], replay["record_sha256"])
        with self.assertRaises(PermissionError):
            adapter.deliver_candidate_once(**{**arguments, "invocation_id": "windows-review-neighbor"})

    def test_windows_insufficient_evidence_cannot_claim_accepted_complete_review(self):
        builder, package, transport, snapshot_id = self.windows_fixture()
        result = WindowsCodexReviewAdapter(self.exchange,
            run_process=ContradictoryInsufficientWindowsCodex(), timeout_seconds=5).deliver_candidate_once(
                package_id=package["package_id"], transport_authority=transport,
                return_authority=authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
                campaign_id=self.campaign, builder_return_report_id=builder["report_id"],
                candidate_snapshot_id=snapshot_id, candidate_snapshot_root=self.workspace)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "malformed_or_unbound_response")

    def test_windows_production_review_requires_exact_promotion_and_remains_read_only(self):
        builder, package, transport, snapshot_id = self.windows_fixture(); fake = FakeWindowsCodex()
        adapter = WindowsCodexReviewAdapter(self.exchange, run_process=fake, timeout_seconds=5)
        with self.assertRaises(PermissionError):
            adapter.deliver_production_once(package_id=package["package_id"], transport_authority=transport,
                return_authority=authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
                campaign_id=self.campaign, builder_return_report_id=builder["report_id"],
                candidate_snapshot_id=snapshot_id, candidate_snapshot_root=self.workspace)
        if not WINDOWS_ADAPTER_PROMOTED:
            return
        result = adapter.deliver_production_once(package_id=package["package_id"],
            transport_authority={**transport,
                "adapter_promotion_reference": WINDOWS_PROMOTION_RECORD["promotion_id"]},
            return_authority=authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
            campaign_id=self.campaign, builder_return_report_id=builder["report_id"],
            candidate_snapshot_id=snapshot_id, candidate_snapshot_root=self.workspace)
        self.assertTrue(result["candidate_qualified"]); self.assertTrue(result["adapter_promoted"])
        self.assertEqual(result["adapter_promotion_reference"], WINDOWS_PROMOTION_RECORD["promotion_id"])

    def test_windows_wrong_campaign_digest_and_revocation_fail_closed(self):
        builder, package, transport, snapshot_id = self.windows_fixture()
        adapter = WindowsCodexReviewAdapter(self.exchange, run_process=FakeWindowsCodex(), timeout_seconds=5)
        with self.assertRaises(PermissionError):
            adapter.deliver_candidate_once(package_id=package["package_id"],
                transport_authority={**transport, "campaign_id": "other"},
                return_authority=authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
                campaign_id=self.campaign, builder_return_report_id=builder["report_id"],
                candidate_snapshot_id=snapshot_id, candidate_snapshot_root=self.workspace)
        status = self.exchange.transport_authorization_status(package_id=package["package_id"], authority=transport)
        self.exchange.revoke_transport_authorization(package_id=package["package_id"],
            target_authorization=transport, revocation_authority={
                "decision": "authorized", "operation": "worker_exchange.transport_authorization.revoke",
                "authority_class": "rider", "instance_id": "fawkes",
                "task_scope_id": package["task_scope_id"],
                "target_authorization_id": status["authorization_id"],
                "target_authorization_reference": transport["authorization_reference"],
                "revoking_principal_id": "tanner", "authorization_reference": "tanner-revoke-review",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
        with self.assertRaises(PermissionError):
            adapter.deliver_candidate_once(package_id=package["package_id"], transport_authority=transport,
                return_authority=authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
                campaign_id=self.campaign, builder_return_report_id=builder["report_id"],
                candidate_snapshot_id=snapshot_id, candidate_snapshot_root=self.workspace)

    def test_real_authenticated_windows_exact_evidence_review_route(self):
        if os.getenv("FAWKES_WINDOWS_CODEX_QUALIFICATION") != "1":
            self.skipTest("set FAWKES_WINDOWS_CODEX_QUALIFICATION=1 for the real Windows review route")
        builder, package, transport, _ = self.windows_fixture()
        with DisposableVerifierWorkspace(Path(__file__).resolve().parents[1],
                                         parent=WINDOWS_REVIEW_SNAPSHOT_PARENT) as snapshot:
            transport = {**transport, "candidate_snapshot_id": snapshot.provenance["candidate_snapshot_id"]}
            result = WindowsCodexReviewAdapter(self.exchange, timeout_seconds=420).deliver_candidate_once(
                package_id=package["package_id"], transport_authority=transport,
                return_authority=authority("fawkes", package["task_scope_id"], WINDOWS_REVIEWER_WORKER_ID),
                campaign_id=self.campaign, builder_return_report_id=builder["report_id"],
                candidate_snapshot_id=snapshot.provenance["candidate_snapshot_id"],
                candidate_snapshot_root=snapshot.root)
        self.assertEqual(result["status"], "delivered", result)
        self.assertTrue(result["real_client_exercised"])
        self.assertIn(result["review_status"], {"pass", "pass_with_caveats", "correction_required",
                                                "insufficient_evidence", "blocked"})
        self.assertFalse(result["candidate_qualified"])
        self.assertFalse(result["adapter_promoted"])

    def test_real_codex_write_route_in_exact_disposable_candidate(self):
        if os.getenv("FAWKES_CODEX_WRITE_QUALIFICATION") != "1":
            self.skipTest("set FAWKES_CODEX_WRITE_QUALIFICATION=1 for the real disposable write route")
        repository = Path(__file__).resolve().parents[1]
        with DisposableVerifierWorkspace(repository, parent="/tmp") as fixture:
            exchange = WorkerExchange("fawkes", root=fixture.root / "database/worker_exchange")
            sender = self.sender; recipient = self.recipient
            task = "write-real-route"; campaign = "write-qualification-campaign"
            base = authority("fawkes", task, sender["worker_id"], recipient["worker_id"])
            report = exchange.create_report(task_scope_id=task, sender=sender,
                authority=authority("fawkes", task, sender["worker_id"]),
                sections=[{"section_id": "task", "title": "Exact qualification task",
                    "content": "Create assurance-output/write-target.txt containing exactly: bounded-write-pass\\n"}],
                claims=[{"claim_id": "exact-file", "area": "development",
                    "statement": "The exact bounded file is created.", "maturity": "experimental",
                    "change_class": "software_system"}])
            package = exchange.compose_package(report_id=report["report_id"], recipient=recipient,
                authority=base, included_section_ids=["task"])
            environment = f"codex-cli:{fixture.root.resolve()}"
            task_text = "Create only assurance-output/write-target.txt with exact UTF-8 bytes bounded-write-pass followed by one newline. Do not change any other file."
            scopes = ["assurance-output/write-target.txt"]
            recovery = [{"reference_type": "candidate_snapshot",
                "reference_id": fixture.provenance["candidate_snapshot_id"],
                "sha256": fixture.provenance["record_sha256"]}]
            transport = {**base, "adapter_id": WRITE_ADAPTER_ID, "package_id": package["package_id"],
                "recipient_environment_id": environment,
                "write_task_sha256": hashlib.sha256(task_text.encode()).hexdigest(),
                "campaign_id": campaign, "iteration": 1,
                "allowed_scope_sha256": _digest(scopes),
                "acceptance_condition_ids_sha256": _digest(["exact-file"]),
                "recovery_references_sha256": _digest(recovery)}
            result = CodexWriteBuilderAdapter(exchange, workspace=fixture.root,
                timeout_seconds=420).deliver_candidate_once(package_id=package["package_id"],
                    transport_authority=transport,
                    return_authority=authority("fawkes", task, recipient["worker_id"]),
                    recipient_environment_id=environment, write_task=task_text,
                    campaign_id=campaign, iteration=1, allowed_scope=scopes,
                    acceptance_condition_ids=["exact-file"], recovery_references=recovery)
            self.assertEqual(result["status"], "delivered", result)
            self.assertEqual((fixture.root / scopes[0]).read_bytes(), b"bounded-write-pass\n")
            self.assertEqual([item["path"] for item in result["workspace_changes"]], scopes)
            self.assertFalse(result["candidate_qualified"])
            fixture.verify_source_unchanged()

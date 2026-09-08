import base64
import hashlib
import copy
import json
import os
import subprocess
import tempfile
import unittest
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_autonomy_production_transports import FakeWriteCodex, authority
from src.runtime.codex_write_builder_adapter import CodexWriteBuilderAdapter
from src.runtime.disposable_verifier import DisposableVerifierWorkspace, candidate_manifest
from src.runtime.codex_development_campaign import (
    CAMPAIGN_CONTRACT_VERSION, DEFAULT_REVIEWER_ROLE, DEFAULT_REVIEWER_WORKER_ID,
    FORMAL_REVIEW_ROLE, MAX_ITERATIONS, CodexDevelopmentCampaign,
)
from src.runtime.codex_development_handoff import CODEX_REPO_WORKER_REFERENCE
from src.runtime.worker_exchange import WorkerExchange, _digest
from src.runtime.windows_codex_reviewer import (
    MAX_CHANGED_ARTIFACT_BYTES, MAX_REVIEW_PACKAGE_BYTES,
    _read_exact_changed_artifact,
    canonical_review_evidence_reference_ids, exact_review_schema,
    validate_windows_structured_response,
)
from src.runtime.wsl_codex_reviewer import (
    FORMAL_REVIEW_ROLE, MAX_PROVIDER_REVIEW_EVIDENCE_BYTES, WSL_ADAPTER_ID, WSL_ADAPTER_QUALIFIED, WSL_ADAPTER_PROMOTED, WSL_ENVIRONMENT_ID,
    WSL_QUALIFICATION_CONTRACT, WSL_REVIEWER_REFERENCE, WSL_REVIEWER_ROLE,
    WSL_REVIEWER_WORKER_ID, WslCodexReviewAdapter, _provider_review_projection,
    _resolve_provider_review_projection, prepare_wsl_review_package,
)


class FakeWslReviewer:
    def __init__(self, *, status="pass", malformed=False, mutate=False):
        self.status, self.malformed, self.mutate = status, malformed, mutate
        self.provider_turns = 0
        self.last_package = None
        self.last_package_sha = None
        self.prompts = []

    def __call__(self, command, *, prompt, environment, timeout):
        self.prompts.append(prompt)
        if "--version" in command: return SimpleNamespace(returncode=0, stdout="codex-cli 0.151.0\n", stderr="")
        if command[1:3] == ["login", "status"]: return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        self.provider_turns += 1
        output = Path(command[command.index("--output-last-message") + 1])
        start = "----- BEGIN EXACT WORKER EXCHANGE PACKAGE -----\n"
        if start in prompt:
            package_text = prompt.split(start, 1)[1].split("\n----- END EXACT WORKER EXCHANGE PACKAGE -----", 1)[0]
            package = json.loads(package_text); self.last_package = package
            self.last_package_sha = hashlib.sha256(package_text.encode()).hexdigest()
        else:
            package = self.last_package
            package_text = json.dumps(package, sort_keys=True, separators=(",", ":"))
        if self.mutate:
            (Path(command[command.index("--cd") + 1]) / "src/allowed.py").write_text("reviewer mutation\n")
        violated = ["done"] if self.status == "correction_required" else []
        satisfied = ["done"] if self.status == "pass" else []
        invocation_match = re.search(r"(?:Review invocation: |review_invocation_id=)([^\n]+)", prompt)
        snapshot_match = re.search(r"(?:Frozen candidate: |candidate_snapshot_id=)([^\n]+)", prompt)
        invocation = invocation_match.group(1); snapshot = snapshot_match.group(1)
        response = {"schema_version": 1, "review_invocation_id": invocation,
            "candidate_snapshot_id": snapshot,
            "package_id": package["package_id"],
            "package_sha256": self.last_package_sha,
            "source_report_id": package["source_report_id"], "task_scope_id": package["task_scope_id"],
            "recipient": {"worker_id": WSL_REVIEWER_WORKER_ID, "role": WSL_REVIEWER_ROLE,
                          "environment_id": WSL_ENVIRONMENT_ID},
            "source_summary_distinction_confirmed": True, "review_status": self.status,
            "acceptance_condition_ids_satisfied": satisfied,
            "violated_acceptance_condition_ids": violated,
            "defects": ([{"defect_id": "defect", "acceptance_condition_id": "done",
                          "evidence_reference": "exact-builder-return"}]
                        if self.status == "correction_required" else []),
            "correctable_within_scope": self.status == "correction_required",
            "sections": [{"section_id": "verdict", "title": "Verdict", "content": self.status}],
            "verification": {"status": ("accepted" if self.status == "pass" else
                "disputed" if self.status == "correction_required" else "insufficient"),
                "checked_claim_ids": ["done"], "evidence_references": package["evidence_references"],
                "method": "exact frozen candidate review", "material_reliance": True,
                "relied_source_section_ids": ["exact-builder-return"],
                "caveats": (["missing test receipt"] if self.status == "insufficient_evidence" else []),
                "counterclaim": ({"claim": "Acceptance condition is not met",
                    "evidence_reference": "exact-builder-return"}
                    if self.status == "correction_required" else None)}}
        output.write_text("{" if self.malformed else json.dumps(response), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="event", stderr="")


class RepairSequenceReviewer(FakeWslReviewer):
    def __init__(self, failures, *, after_first=None):
        super().__init__(); self.failures=list(failures); self.after_first=after_first

    def __call__(self, command, **kwargs):
        completed=super().__call__(command, **kwargs)
        if "--output-last-message" not in command: return completed
        output=Path(command[command.index("--output-last-message")+1])
        response=json.loads(output.read_text())
        failure=self.failures[self.provider_turns-1] if self.provider_turns <= len(self.failures) else None
        if failure == "lineage": response["package_id"]="neighbor-package"
        elif failure == "material_without_claims":
            response["verification"]["checked_claim_ids"] = []
        elif failure == "semantic":
            response["review_status"]="correction_required"
            response["violated_acceptance_condition_ids"]=["done"]
            response["defects"]=[]
            response["verification"]["status"]="disputed"
            response["acceptance_condition_ids_satisfied"]=[]
        elif failure is not None:
            response["review_status"]="correction_required"
            response["violated_acceptance_condition_ids"]=["done"]
            response["acceptance_condition_ids_satisfied"]=[]
            response["defects"]=[{"defect_id":"defect", "acceptance_condition_id":"done",
                                  "evidence_reference":failure}]
            response["verification"]["status"]="disputed"
        output.write_text(json.dumps(response))
        if self.provider_turns == 1 and self.after_first: self.after_first()
        return completed


class WslFormalReviewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.workspace = root / "repo"; self.workspace.mkdir()
        (self.workspace / ".git").mkdir(); (self.workspace / "src").mkdir()
        (self.workspace / "src/allowed.py").write_text("before\n")
        self.exchange = WorkerExchange("fawkes", root=root / "exchange")
        sender = {"worker_id": "fawkes-development", "role": "coordination",
                  "identity_status": "verified", "charter_version": "1.0"}
        worker = {"worker_id": "codex-repository-wsl-fawkes", "role": "software_repository",
                  "identity_status": "rider_attested", "charter_version": "1.0"}
        report = self.exchange.create_report(task_scope_id="write-task", sender=sender,
            authority=authority("fawkes", "write-task", sender["worker_id"]),
            sections=[{"section_id": "task", "title": "Task", "content": "bounded change"}],
            claims=[{"claim_id": "done", "area": "development", "statement": "change done",
                     "maturity": "in_development", "change_class": "software_system"}])
        base = authority("fawkes", "write-task", sender["worker_id"], worker["worker_id"])
        package = self.exchange.compose_package(report_id=report["report_id"], recipient=worker,
            authority=base, included_section_ids=["task"])
        scopes = ["src/allowed.py"]; recovery = [{"reference_type": "working_checkpoint", "reference_id": "before"}]
        write_task = "Modify only src/allowed.py."
        transport = {**base, "adapter_id": "codex-cli-exec-local-write", "package_id": package["package_id"],
            "recipient_environment_id": f"codex-cli:{self.workspace.resolve()}",
            "write_task_sha256": hashlib.sha256(write_task.encode()).hexdigest(), "campaign_id": "campaign",
            "iteration": 1, "allowed_scope_sha256": _digest(scopes),
            "acceptance_condition_ids_sha256": _digest(["done"]), "recovery_references_sha256": _digest(recovery)}
        result = CodexWriteBuilderAdapter(self.exchange, workspace=self.workspace,
            run_process=FakeWriteCodex(self.workspace), timeout_seconds=5).deliver_candidate_once(
            package_id=package["package_id"], transport_authority=transport,
            return_authority=authority("fawkes", "write-task", worker["worker_id"]),
            recipient_environment_id=f"codex-cli:{self.workspace.resolve()}", write_task=write_task,
            campaign_id="campaign", iteration=1, allowed_scope=scopes,
            acceptance_condition_ids=["done"], recovery_references=recovery)
        self.workspace = Path(result["candidate_workspace"])
        returned = self.exchange._load("reports", result["return_report_id"])
        validation_declaration = {"policy_version": "development-campaign-validation-v1",
            "status": "required", "creates_authority": False}
        validation_declaration["record_sha256"] = _digest(validation_declaration)
        validation_evidence = [{"argv": ["test"], "exit_status": 0}]
        self.campaign = {"instance_id": "fawkes", "campaign_id": "campaign",
            "status": "awaiting_independent_review", "iteration": 1, "objective": "Review exact change.",
            "acceptance_condition_ids": ["done"], "acceptance_conditions": {"done": "Change is exact."},
            "allowed_scope": scopes, "recovery_references": recovery, "contract_version": "fixture-v1",
            "validation_policy": "required", "validation_declaration": validation_declaration,
            "builder_runs": [{"iteration": 1, "return_report_id": returned["report_id"],
                "package_id": package["package_id"],
                "transport_result_reference": {"workspace_changes_sha256": result["workspace_changes_sha256"]},
                "validation_evidence": validation_evidence,
                "completed_at": datetime.now(timezone.utc).isoformat()}]}
        manifest = candidate_manifest(self.workspace)
        self.provenance = {**manifest, "record_sha256": _digest(manifest),
            "file_count": len(manifest["files"]),
            "total_byte_length": sum(x["byte_length"] for x in manifest["files"])}
        application = result["application_evidence"]
        retention = {"schema_version": 1,
            "record_type": "codex_candidate_retention_receipt",
            "status": "awaiting_independent_review", "applied_paths": [],
            "campaign_id": "campaign", "package_id": package["package_id"], "iteration": 1,
            "worker_invocation_id": result["invocation_id"],
            "allowed_scope_sha256": _digest(scopes),
            "mutation_manifest_sha256": result["workspace_changes_sha256"],
            "exact_change_evidence_sha256": result["exact_change_evidence_sha256"],
            "candidate_snapshot": result["candidate_snapshot"], "validation_policy": "required",
            "validation_declaration_sha256": validation_declaration["record_sha256"],
            "validation_evidence_sha256": _digest(validation_evidence),
            "recovery_references_sha256": _digest(recovery),
            "retention_intent_sha256": application["application_record_sha256"],
            "creates_authority": False, "created_at": datetime.now(timezone.utc).isoformat()}
        retention["record_sha256"] = _digest(retention)
        self.campaign["builder_runs"][-1]["candidate_retention_receipt"] = retention
        self.prepared = prepare_wsl_review_package(exchange=self.exchange, campaign_record=self.campaign,
            candidate_snapshot=self.provenance, workspace=self.workspace)

    def invoke(self, fake=None, **changes):
        kwargs = {"package_id": self.prepared["package_id"],
            "transport_authority": {**self.prepared["transport_authority"], **changes.pop("authority", {})},
            "return_authority": self.prepared["return_authority"], "campaign_id": "campaign",
            "builder_return_report_id": self.campaign["builder_runs"][-1]["return_report_id"],
            "candidate_snapshot_id": self.provenance["candidate_snapshot_id"],
            "candidate_snapshot_root": self.workspace, **changes}
        return WslCodexReviewAdapter(self.exchange, run_process=fake or FakeWslReviewer(),
            timeout_seconds=5).deliver_candidate_once(**kwargs)

    def test_changed_artifact_capacity_is_lossless_bounded_and_digest_checked(self):
        paths = []
        sizes = (100_000, 100_000, 105_801)
        total = 0
        artifacts = []
        for index, size in enumerate(sizes):
            path = Path(self.tmp.name) / f"large-{index}.py"
            body = (chr(97 + index) * size).encode("utf-8")
            path.write_bytes(body); paths.append(path)
            artifact, total = _read_exact_changed_artifact(
                path=path, relative=f"src/large-{index}.py",
                expected_sha256=hashlib.sha256(body).hexdigest(),
                consumed_bytes=total)
            artifacts.append(artifact)
        self.assertEqual(total, 305_801)
        self.assertLess(total, MAX_CHANGED_ARTIFACT_BYTES)
        self.assertEqual(b"".join(item["content"].encode() for item in artifacts),
                         b"".join(path.read_bytes() for path in paths))
        self.assertEqual(sum(item["byte_length"] for item in artifacts), 305_801)

        paths[-1].write_bytes(b"stale")
        with self.assertRaisesRegex(ValueError, "stale or digest-mismatched"):
            _read_exact_changed_artifact(
                path=paths[-1], relative="src/large-2.py",
                expected_sha256=artifacts[-1]["sha256"], consumed_bytes=200_000)

        oversized = Path(self.tmp.name) / "oversized.py"
        oversized.write_bytes(b"x" * (MAX_CHANGED_ARTIFACT_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "exceed"):
            _read_exact_changed_artifact(
                path=oversized, relative="src/oversized.py",
                expected_sha256=hashlib.sha256(oversized.read_bytes()).hexdigest(),
                consumed_bytes=0)

    def test_exact_package_rejects_out_of_scope_and_overall_transport_remains_bounded(self):
        changed = copy.deepcopy(self.campaign)
        changed["allowed_scope"] = []
        with self.assertRaises((PermissionError, ValueError)):
            prepare_wsl_review_package(exchange=self.exchange, campaign_record=changed,
                candidate_snapshot=self.provenance, workspace=self.workspace)

        with patch("src.runtime.wsl_codex_reviewer.MAX_REVIEW_PACKAGE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "transported"):
                self.invoke()
        self.assertEqual(MAX_REVIEW_PACKAGE_BYTES, 512_000)

    def test_provider_projection_preserves_typed_nonregular_artifacts_and_round_trips(self):
        def node(kind, body, mode):
            return {"schema": "fawkes.filesystem_node.v1",
                    "state": "absent" if kind is None else "present",
                    "file_type": kind, "mode": mode,
                    "body_length": len(body),
                    "body_sha256": hashlib.sha256(body).hexdigest()}

        def change(path, kind, *, body=None, mode=0o644, target=None):
            if kind == "regular":
                encoded = base64.b64encode(body).decode("ascii")
                binding_body = body
            elif kind == "symlink":
                encoded = None; binding_body = target.encode("utf-8")
            else:
                encoded = None; binding_body = b""; mode = None if kind is None else mode
            return {"path": path, "status": "added" if kind is not None else "deleted",
                    "after_type": kind, "after_mode": mode,
                    "after_symlink_target": target, "after_base64": encoded,
                    "after_node_binding": node(kind, binding_body, mode)}

        def artifact(section_id, path, body):
            return {"section_id": section_id, "content": json.dumps(
                {"path": path, "sha256": hashlib.sha256(body).hexdigest(),
                 "byte_length": len(body)}, sort_keys=True, separators=(",", ":"))
                + "\n----- BEGIN EXACT UTF-8 ARTIFACT -----\n" + body.decode("utf-8")
                + "\n----- END EXACT UTF-8 ARTIFACT -----"}

        def package(changes, artifacts):
            value = {"record_type": "worker_exchange_package", "included_sections": [
                {"section_id": "exact-change-evidence", "content": json.dumps(
                    changes, sort_keys=True, separators=(",", ":"))}, *artifacts]}
            return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

        large_body = b"z" * 600_000
        changes = [
            change("src/large.py", "regular", body=large_body),
            change("src/empty.py", "regular", body=b""),
            change("src/assets", "directory", mode=0o755),
            change("src/current", "symlink", target="assets/current"),
            change("src/removed.py", None),
        ]
        logical = package(changes, [
            artifact("changed-artifact-1", "src/large.py", large_body),
            artifact("changed-artifact-2", "src/empty.py", b""),
        ])
        self.assertGreater(len(logical), 950_000)
        binding = {"expected_canonical_sha256": hashlib.sha256(logical).hexdigest(),
                   "expected_canonical_byte_length": len(logical)}
        projection = _provider_review_projection(logical)
        self.assertLess(len(projection), len(logical))
        self.assertEqual(_resolve_provider_review_projection(projection, **binding), logical)
        projected = json.loads(projection)
        projected_changes = {item["path"]: item for item in json.loads(
            projected["package"]["included_sections"][0]["content"])}
        self.assertIsNone(projected_changes["src/assets"]["after_base64"])
        self.assertNotIn("after_body_reference", projected_changes["src/assets"])
        self.assertIsNone(projected_changes["src/current"]["after_base64"])
        self.assertNotIn("after_body_reference", projected_changes["src/removed.py"])
        self.assertEqual(projected_changes["src/empty.py"]["after_body_reference"]["byte_length"], 0)

        small = package(changes[1:], [artifact("changed-artifact-1", "src/empty.py", b"")])
        small_binding = {"expected_canonical_sha256": hashlib.sha256(small).hexdigest(),
                         "expected_canonical_byte_length": len(small)}
        self.assertEqual(_provider_review_projection(small), small)
        self.assertEqual(_resolve_provider_review_projection(small, **small_binding), small)

        missing = copy.deepcopy(changes); missing[0].pop("after_base64")
        with self.assertRaisesRegex(ValueError, "regular postimage body"):
            _provider_review_projection(package(missing, [
                artifact("changed-artifact-1", "src/large.py", large_body),
                artifact("changed-artifact-2", "src/empty.py", b""),
            ]))
        nonregular = copy.deepcopy(changes); nonregular[2]["after_base64"] = "eA=="
        with self.assertRaisesRegex(ValueError, "nonregular postimage"):
            _provider_review_projection(package(nonregular, [
                artifact("changed-artifact-1", "src/large.py", large_body),
                artifact("changed-artifact-2", "src/empty.py", b""),
            ]))
        type_mismatch = copy.deepcopy(changes)
        type_mismatch[0]["after_node_binding"]["file_type"] = "directory"
        with self.assertRaisesRegex(ValueError, "node binding"):
            _provider_review_projection(package(type_mismatch, [
                artifact("changed-artifact-1", "src/large.py", large_body),
                artifact("changed-artifact-2", "src/empty.py", b""),
            ]))

        def encoded_projection(value):
            value["record_sha256"] = _digest(
                {key: item for key, item in value.items() if key != "record_sha256"})
            return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

        corrupt = json.loads(projection)
        corrupt["package"]["included_sections"][1]["content"] += "x"
        with self.assertRaisesRegex(ValueError, "identity mismatch|mismatches|malformed"):
            _resolve_provider_review_projection(encoded_projection(corrupt), **binding)
        dangling = json.loads(projection)
        exact = json.loads(dangling["package"]["included_sections"][0]["content"])
        exact[0]["after_body_reference"]["section_id"] = "changed-artifact-neighbor"
        dangling["package"]["included_sections"][0]["content"] = json.dumps(
            exact, sort_keys=True, separators=(",", ":"))
        with self.assertRaisesRegex(ValueError, "dangling"):
            _resolve_provider_review_projection(encoded_projection(dangling), **binding)
        directory_reference = json.loads(projection)
        exact = json.loads(directory_reference["package"]["included_sections"][0]["content"])
        for item in exact:
            if item["path"] == "src/assets":
                item["after_body_reference"] = dict(projected_changes["src/empty.py"]["after_body_reference"])
        directory_reference["package"]["included_sections"][0]["content"] = json.dumps(
            exact, sort_keys=True, separators=(",", ":"))
        with self.assertRaisesRegex(ValueError, "nonregular projection"):
            _resolve_provider_review_projection(encoded_projection(directory_reference), **binding)

        substituted = json.loads(logical)
        substituted["task_scope_id"] = "worker-exchange-scope-substituted"
        substituted_bytes = (json.dumps(substituted, sort_keys=True, separators=(",", ":")) + "\n").encode()
        internally_valid = _provider_review_projection(substituted_bytes)
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            _resolve_provider_review_projection(internally_valid, **binding)
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            _resolve_provider_review_projection(projection,
                expected_canonical_sha256="0" * 64,
                expected_canonical_byte_length=len(logical))
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            _resolve_provider_review_projection(projection,
                expected_canonical_sha256=binding["expected_canonical_sha256"],
                expected_canonical_byte_length=len(logical) + 1)
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            _resolve_provider_review_projection(projection[:-1], **binding)
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            _resolve_provider_review_projection(projection + b"{}", **binding)
        with self.assertRaisesRegex(ValueError, "independent canonical package binding"):
            _resolve_provider_review_projection(projection,
                expected_canonical_sha256=None,
                expected_canonical_byte_length=len(logical))

    def test_provider_projection_preserves_legacy_small_raw_package_byte_identically(self):
        body = b"legacy raw fixture"
        body_sha = hashlib.sha256(body).hexdigest()
        package = {"record_type": "worker_exchange_package", "included_sections": [
            {"section_id": "exact-change-evidence", "content": json.dumps([{
                "path": "tests/legacy_raw_fixture.py",
                "after_base64": base64.b64encode(body).decode("ascii"),
                "text_diff": "+ legacy raw fixture\n",
            }], sort_keys=True, separators=(",", ":"))},
            {"section_id": "changed-artifact-1", "content": json.dumps({
                "path": "tests/legacy_raw_fixture.py", "sha256": body_sha,
                "byte_length": len(body),
            }, sort_keys=True, separators=(",", ":"))
             + "\n----- BEGIN EXACT UTF-8 ARTIFACT -----\n"
             + body.decode("utf-8")
             + "\n----- END EXACT UTF-8 ARTIFACT -----"},
        ]}
        logical = (json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n").encode()
        binding = {"expected_canonical_sha256": hashlib.sha256(logical).hexdigest(),
                   "expected_canonical_byte_length": len(logical)}
        self.assertLess(len(logical), 950_000)
        self.assertEqual(_provider_review_projection(logical), logical)
        self.assertEqual(_resolve_provider_review_projection(logical, **binding), logical)

    def test_provider_projection_classifies_typed_and_legacy_raw_routes_before_size_selection(self):
        """Typed evidence cannot fall through to the legacy small/raw route."""
        def node(body):
            return {"schema": "fawkes.filesystem_node.v1", "state": "present",
                    "file_type": "regular", "mode": 0o644,
                    "body_length": len(body),
                    "body_sha256": hashlib.sha256(body).hexdigest()}

        def artifact(path, body):
            return {"section_id": "changed-artifact-" + path.rsplit("/", 1)[-1],
                    "content": json.dumps({"path": path,
                                           "sha256": hashlib.sha256(body).hexdigest(),
                                           "byte_length": len(body)},
                                          sort_keys=True, separators=(",", ":"))
                    + "\n----- BEGIN EXACT UTF-8 ARTIFACT -----\n"
                    + body.decode("utf-8")
                    + "\n----- END EXACT UTF-8 ARTIFACT -----"}

        def encode(changes, artifacts):
            package = {"record_type": "worker_exchange_package", "included_sections": [
                {"section_id": "exact-change-evidence",
                 "content": json.dumps(changes, sort_keys=True, separators=(",", ":"))},
                *artifacts,
            ]}
            return (json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n").encode()

        def binding(logical):
            return {"expected_canonical_sha256": hashlib.sha256(logical).hexdigest(),
                    "expected_canonical_byte_length": len(logical)}

        body = b"typed small fixture"
        typed = {"path": "tests/typed_small_fixture.py", "status": "added",
                 "after_type": "regular", "after_mode": 0o644,
                 "after_symlink_target": None,
                 "after_base64": base64.b64encode(body).decode("ascii"),
                 "after_node_binding": node(body)}
        valid = encode([typed], [artifact(typed["path"], body)])
        self.assertLess(len(valid), MAX_PROVIDER_REVIEW_EVIDENCE_BYTES)
        self.assertEqual(_provider_review_projection(valid), valid)
        self.assertEqual(_resolve_provider_review_projection(valid, **binding(valid)), valid)

        for missing in ("after_type", "after_mode", "after_node_binding",
                        "after_symlink_target", "after_base64"):
            malformed = copy.deepcopy(typed)
            malformed.pop(missing)
            logical = encode([malformed], [artifact(typed["path"], body)])
            with self.subTest(missing=missing):
                with self.assertRaises(ValueError):
                    _provider_review_projection(logical)
                with self.assertRaises(ValueError):
                    _resolve_provider_review_projection(logical, **binding(logical))

        malformed_node = copy.deepcopy(typed)
        malformed_node["after_node_binding"]["body_sha256"] = "0" * 64
        malformed_node_bytes = encode([malformed_node], [artifact(typed["path"], body)])
        with self.assertRaisesRegex(ValueError, "node binding|does not match"):
            _provider_review_projection(malformed_node_bytes)
        with self.assertRaises(ValueError):
            _resolve_provider_review_projection(malformed_node_bytes,
                                                **binding(malformed_node_bytes))

        legacy_body = b"legacy companion"
        legacy = {"path": "tests/legacy_companion.py",
                  "after_base64": base64.b64encode(legacy_body).decode("ascii")}
        mixed = encode([typed, legacy], [artifact(typed["path"], body),
                                         artifact(legacy["path"], legacy_body)])
        with self.assertRaisesRegex(ValueError, "mixes typed and legacy"):
            _provider_review_projection(mixed)
        with self.assertRaises(ValueError):
            _resolve_provider_review_projection(mixed, **binding(mixed))

        def legacy_without_exact_change_evidence(size):
            package = {"record_type": "worker_exchange_package", "included_sections": [
                {"section_id": "summary", "content": ""},
            ]}
            initial = (json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n").encode()
            self.assertGreaterEqual(size, len(initial))
            package["included_sections"][0]["content"] = "x" * (size - len(initial))
            logical = (json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n").encode()
            self.assertEqual(len(logical), size)
            return logical

        for size in (MAX_PROVIDER_REVIEW_EVIDENCE_BYTES - 1,
                     MAX_PROVIDER_REVIEW_EVIDENCE_BYTES):
            logical = legacy_without_exact_change_evidence(size)
            with self.subTest(legacy_size=size):
                self.assertEqual(_provider_review_projection(logical), logical)
                self.assertEqual(_resolve_provider_review_projection(logical, **binding(logical)),
                                 logical)

        oversized = legacy_without_exact_change_evidence(MAX_PROVIDER_REVIEW_EVIDENCE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "lacks exact change evidence"):
            _provider_review_projection(oversized)
        with self.assertRaisesRegex(ValueError, "exceeds byte limit"):
            _resolve_provider_review_projection(oversized, **binding(oversized))

    def test_identity_functional_role_and_zero_authority_are_distinct(self):
        self.assertEqual(WSL_REVIEWER_REFERENCE["functional_role"], FORMAL_REVIEW_ROLE)
        self.assertNotEqual(WSL_REVIEWER_WORKER_ID, "codex-repository-wsl-fawkes")
        self.assertFalse(WSL_REVIEWER_REFERENCE["identified_is_authorized"])
        self.assertTrue(WSL_ADAPTER_QUALIFIED)
        self.assertTrue(WSL_ADAPTER_PROMOTED)
        self.assertEqual(WSL_REVIEWER_REFERENCE["transport_status"], "promoted_bounded_read_only")
        self.assertEqual(len(WSL_QUALIFICATION_CONTRACT["hard_invariants"]), 16)

    def test_wsl_package_carries_exact_candidate_retention_receipt(self):
        package = self.exchange._load("packages", self.prepared["package_id"])
        sections = {item["section_id"]: item for item in package["included_sections"]}
        self.assertIn("candidate-retention-receipt", sections)
        expected = self.campaign["builder_runs"][-1]["candidate_retention_receipt"]
        self.assertEqual(json.loads(sections["candidate-retention-receipt"]["content"]), expected)
        self.assertEqual(self.prepared["transport_authority"]
                         ["candidate_retention_receipt_sha256"], expected["record_sha256"])

    def test_wsl_package_rejects_missing_and_mismatched_retention_lineage(self):
        def rejected(change):
            campaign = copy.deepcopy(self.campaign)
            change(campaign["builder_runs"][-1])
            with self.assertRaises((KeyError, ValueError, PermissionError)):
                prepare_wsl_review_package(exchange=self.exchange, campaign_record=campaign,
                    candidate_snapshot=self.provenance, workspace=self.workspace)

        rejected(lambda run: run.pop("candidate_retention_receipt"))
        for field, value in (("campaign_id", "neighbor-campaign"),
                             ("package_id", "worker-package-neighbor"),
                             ("allowed_scope_sha256", "1" * 64),
                             ("mutation_manifest_sha256", "2" * 64)):
            def alter(run, field=field, value=value):
                receipt = run["candidate_retention_receipt"]
                receipt[field] = value
                receipt["record_sha256"] = _digest(
                    {key: item for key, item in receipt.items() if key != "record_sha256"})
            rejected(alter)
        def candidate_neighbor(run):
            receipt = run["candidate_retention_receipt"]
            receipt["candidate_snapshot"] = {**receipt["candidate_snapshot"],
                "candidate_snapshot_id": "candidate-snapshot-neighbor"}
            receipt["record_sha256"] = _digest(
                {key: item for key, item in receipt.items() if key != "record_sha256"})
        rejected(candidate_neighbor)

    def test_provider_schema_uses_historical_keywords_while_semantics_bind_exact_lineage(self):
        package = self.exchange._load("packages", self.prepared["package_id"])
        recipient = package["recipient"]
        schema = exact_review_schema(package=package, package_sha256="a" * 64,
            recipient=recipient, invocation_id="review-invocation-current",
            candidate_snapshot_id=self.provenance["candidate_snapshot_id"])
        self.assertEqual(len(schema["required"]), 16)
        for key in ("review_invocation_id", "candidate_snapshot_id", "package_id",
                    "package_sha256", "source_report_id", "task_scope_id"):
            self.assertEqual(schema["properties"][key], {"type": "string"})
            self.assertNotIn("const", schema["properties"][key])
        for key in ("worker_id", "role", "environment_id"):
            field = schema["properties"]["recipient"]["properties"][key]
            self.assertEqual(field, {"type": "string"})
            self.assertNotIn("const", field)
        historical_keywords = {"type", "additionalProperties", "required", "properties",
            "const", "enum", "items", "minItems", "anyOf"}
        observed = set()
        def collect(node):
            if not isinstance(node, dict): return
            for key in historical_keywords | {"minLength", "pattern", "format", "uniqueItems"}:
                if key in node: observed.add(key)
            properties = node.get("properties")
            if isinstance(properties, dict):
                for child in properties.values(): collect(child)
            if isinstance(node.get("items"), dict): collect(node["items"])
            for child in node.get("anyOf", []): collect(child)
        collect(schema)
        self.assertTrue(observed <= historical_keywords)
        self.assertFalse({"minLength", "pattern", "format", "uniqueItems"} & observed)
        response = FakeWslReviewer()( ["codex", "--output-last-message", str(Path(self.tmp.name) / "response.json"), "--cd", str(self.workspace)], prompt="Review invocation: review-invocation-current\nFrozen candidate: " + self.provenance["candidate_snapshot_id"] + "\n----- BEGIN EXACT WORKER EXCHANGE PACKAGE -----\n" + json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n----- END EXACT WORKER EXCHANGE PACKAGE -----", environment={}, timeout=1)
        self.assertEqual(response.returncode, 0)
        parsed = json.loads((Path(self.tmp.name) / "response.json").read_text())
        parsed["package_id"] = "neighbor-package"
        with self.assertRaises(PermissionError):
            validate_windows_structured_response(parsed, package,
                hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                recipient, "review-invocation-current", self.provenance["candidate_snapshot_id"])
        exact = FakeWslReviewer()( ["codex", "--output-last-message", str(Path(self.tmp.name) / "response-2.json"), "--cd", str(self.workspace)], prompt="Review invocation: review-invocation-current\nFrozen candidate: " + self.provenance["candidate_snapshot_id"] + "\n----- BEGIN EXACT WORKER EXCHANGE PACKAGE -----\n" + json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n----- END EXACT WORKER EXCHANGE PACKAGE -----", environment={}, timeout=1)
        self.assertEqual(exact.returncode, 0)
        exact_response = json.loads((Path(self.tmp.name) / "response-2.json").read_text())
        package_sha = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for key in ("review_invocation_id", "candidate_snapshot_id", "package_id",
                    "package_sha256", "source_report_id", "task_scope_id"):
            invalid = dict(exact_response); invalid[key] = ""
            with self.assertRaises(PermissionError):
                validate_windows_structured_response(invalid, package, package_sha,
                    recipient, "review-invocation-current", self.provenance["candidate_snapshot_id"])
        for key in ("worker_id", "role", "environment_id"):
            invalid = json.loads(json.dumps(exact_response)); invalid["recipient"][key] = ""
            with self.assertRaises(PermissionError):
                validate_windows_structured_response(invalid, package, package_sha,
                    recipient, "review-invocation-current", self.provenance["candidate_snapshot_id"])

    def test_exact_frozen_package_pass_retains_lineage_and_no_authority(self):
        result = self.invoke()
        self.assertEqual((result["status"], result["review_status"]), ("delivered", "pass"))
        self.assertFalse(result["creates_authority"])
        self.assertEqual(result["candidate_snapshot_id"], self.provenance["candidate_snapshot_id"])
        self.assertEqual(result["builder_return_reference"], self.prepared["builder_return_reference"])

    def test_wrong_candidate_worker_campaign_and_write_authority_fail_closed(self):
        with self.assertRaises(PermissionError): self.invoke(candidate_snapshot_id="candidate-snapshot-wrong")
        with self.assertRaises(PermissionError): self.invoke(authority={"campaign_id": "wrong"})
        package = self.exchange._load("packages", self.prepared["package_id"])
        package["recipient"]["worker_id"] = "codex-repository-wsl-fawkes"
        with unittest.mock.patch.object(self.exchange, "_load", return_value=package):
            with self.assertRaises(PermissionError): self.invoke()

    def test_structured_correction_insufficient_and_malformed(self):
        correction = self.invoke(FakeWslReviewer(status="correction_required"))
        self.assertEqual(correction["review_status"], "correction_required")
        self.setUp(); insufficient = self.invoke(FakeWslReviewer(status="insufficient_evidence"))
        self.assertEqual(insufficient["review_status"], "insufficient_evidence")
        self.setUp(); malformed = self.invoke(FakeWslReviewer(malformed=True))
        self.assertEqual(malformed["failure_reason"], "malformed_or_unbound_response")

    def test_response_invocation_freshness_fails_closed(self):
        class WrongInvocation(FakeWslReviewer):
            def __call__(self, command, **kwargs):
                completed = super().__call__(command, **kwargs)
                if "--output-last-message" in command:
                    output = Path(command[command.index("--output-last-message") + 1])
                    response = json.loads(output.read_text())
                    response["review_invocation_id"] = "wsl-review-stale-neighbor"
                    output.write_text(json.dumps(response))
                return completed
        result = self.invoke(WrongInvocation(), invocation_id="wsl-review-current")
        self.assertEqual(result["failure_reason"], "semantic_repair_failed")
        self.assertNotIn("review_status", result)

    def test_semantic_repair_is_single_fresh_bound_turn_without_premature_success(self):
        valid=FakeWslReviewer(); result=self.invoke(valid,invocation_id="review-original")
        self.assertEqual((result["status"],valid.provider_turns),("delivered",1))
        self.setUp(); lineage=RepairSequenceReviewer(["lineage",None])
        repaired=self.invoke(lineage,invocation_id="review-original")
        self.assertEqual((repaired["status"],lineage.provider_turns),("delivered",2))
        self.assertEqual(repaired["original_invocation_id"],"review-original")
        self.assertRegex(repaired["invocation_id"],r"^review-original-repair-[0-9a-f]{32}$")
        failure_path=self.exchange.root/"wsl_codex_review_adapter"/self.prepared["package_id"]/"attempt-1-failure.json"
        failure=json.loads(failure_path.read_text())
        self.assertEqual(failure["failure_category"],"lineage_identity_or_semantic_validation")
        self.assertNotIn("response",failure); self.assertFalse(failure["creates_authority"])
        deliveries=[json.loads(p.read_text()) for p in (self.exchange.root/"delivery_receipts").glob("*.json")]
        reviewer=[x for x in deliveries if x.get("adapter_id")==WSL_ADAPTER_ID]
        self.assertEqual([x["status"] for x in reviewer],["delivered"])
        self.assertEqual(repaired["client_process_evidence"]["attempt_count"],2)
        self.assertNotEqual(repaired["client_process_evidence"]["repair_nonce_sha256"],"0"*64)
        repair_prompt=lineage.prompts[-1]
        self.assertIn("a nonempty\n  evidence_reference",repair_prompt)
        self.assertIn("verification.evidence_references must copy",repair_prompt)
        self.assertIn("correction_required requires at least one concrete defect",repair_prompt)
        self.assertIn(json.dumps(canonical_review_evidence_reference_ids(lineage.last_package)),
                      repair_prompt)

    def test_semantic_invalid_response_repairs_and_two_invalid_responses_fail_closed(self):
        semantic=RepairSequenceReviewer(["semantic",None])
        self.assertEqual(self.invoke(semantic)["status"],"delivered")
        self.assertEqual(semantic.provider_turns,2)
        self.setUp(); twice=RepairSequenceReviewer(["lineage","lineage"])
        failed=self.invoke(twice)
        self.assertEqual((failed["status"],failed["failure_reason"],twice.provider_turns),
                         ("failed","semantic_repair_failed",2))
        self.assertNotIn("review_status",failed)
        reports=[json.loads(p.read_text()) for p in (self.exchange.root/"reports").glob("*.json")]
        self.assertFalse(any(x.get("sender",{}).get("worker_id")==WSL_REVIEWER_WORKER_ID for x in reports))

    def test_material_reliance_requires_claims_and_uses_one_bounded_repair(self):
        repaired = RepairSequenceReviewer(["material_without_claims", None])
        result = self.invoke(repaired)
        self.assertEqual((result["status"], repaired.provider_turns), ("delivered", 2))
        self.assertEqual(result["review_status"], "pass")

        self.setUp()
        rejected = RepairSequenceReviewer(
            ["material_without_claims", "material_without_claims"])
        failed = self.invoke(rejected)
        self.assertEqual((failed["status"], failed["failure_reason"], rejected.provider_turns),
                         ("failed", "semantic_repair_failed", 2))
        reports = [json.loads(path.read_text())
                   for path in (self.exchange.root / "reports").glob("*.json")]
        self.assertFalse(any(item.get("sender", {}).get("worker_id") == WSL_REVIEWER_WORKER_ID
                             for item in reports))
        verifications = [json.loads(path.read_text()) for path in
                         (self.exchange.root / "verification_receipts").glob("*.json")]
        self.assertFalse(any(item.get("recipient", {}).get("worker_id") == WSL_REVIEWER_WORKER_ID
                             for item in verifications))

    def test_defect_evidence_reference_uses_canonical_id_and_bounded_repair(self):
        canonical=FakeWslReviewer(status="correction_required")
        delivered=self.invoke(canonical)
        self.assertEqual((delivered["status"],canonical.provider_turns),("delivered",1))
        self.assertEqual(delivered["defects"][0]["evidence_reference"],"exact-builder-return")

        self.setUp(); repaired=RepairSequenceReviewer(["builder output line 12",None])
        repaired_result=self.invoke(repaired)
        self.assertEqual((repaired_result["status"],repaired.provider_turns),("delivered",2))

        self.setUp(); invalid=RepairSequenceReviewer(["builder output line 12","   "])
        failed=self.invoke(invalid)
        self.assertEqual((failed["status"],failed["failure_reason"],invalid.provider_turns),
                         ("failed","semantic_repair_failed",2))
        self.assertNotIn("review_status",failed)
        self.assertNotIn("verification_receipt_id",failed)
        self.assertNotIn("return_report_id",failed)
        self.assertFalse(failed["creates_authority"])
        deliveries=[json.loads(p.read_text()) for p in
                    (self.exchange.root/"delivery_receipts").glob("*.json")]
        reviewer=[item for item in deliveries if item.get("adapter_id")==WSL_ADAPTER_ID]
        self.assertEqual([item["status"] for item in reviewer],["failed"])
        verifications=[json.loads(path.read_text()) for path in
                       (self.exchange.root/"verification_receipts").glob("*.json")]
        self.assertFalse(any(item.get("recipient",{}).get("worker_id")==WSL_REVIEWER_WORKER_ID
                             for item in verifications))
        reports=[json.loads(p.read_text()) for p in (self.exchange.root/"reports").glob("*.json")]
        self.assertFalse(any(item.get("sender",{}).get("worker_id")==WSL_REVIEWER_WORKER_ID
                             for item in reports))

        self.setUp(); unknown=RepairSequenceReviewer(["neighbor-evidence", "neighbor-evidence"])
        rejected=self.invoke(unknown)
        self.assertEqual((rejected["failure_reason"],unknown.provider_turns),
                         ("semantic_repair_failed",2))

    def test_repair_stops_on_candidate_or_package_scope_drift(self):
        mutate=RepairSequenceReviewer(["lineage"],after_first=lambda:
            (self.workspace/"src/allowed.py").write_text("concurrent\n"))
        changed=self.invoke(mutate)
        self.assertEqual((changed["failure_reason"],mutate.provider_turns),
                         ("candidate_snapshot_changed",1))
        self.setUp()
        def change_package():
            path=self.exchange._path("packages",self.prepared["package_id"])
            package=json.loads(path.read_text()); package["task_scope_id"]="changed-scope"
            package["record_sha256"]=_digest({k:v for k,v in package.items() if k!="record_sha256"})
            path.write_text(json.dumps(package))
        drift=RepairSequenceReviewer(["lineage"],after_first=change_package)
        failed=self.invoke(drift)
        self.assertEqual((failed["failure_reason"],drift.provider_turns),("repair_binding_changed",1))

    def test_dynamic_candidate_is_exact_and_qualification_fixture_cannot_substitute(self):
        from src.runtime.wsl_codex_reviewer import WSL_QUALIFIED_SNAPSHOT_ID
        self.assertNotEqual(self.provenance["candidate_snapshot_id"], WSL_QUALIFIED_SNAPSHOT_ID)
        self.assertEqual(self.invoke()["status"], "delivered")
        self.setUp()
        with self.assertRaises(PermissionError):
            self.invoke(candidate_snapshot_id=WSL_QUALIFIED_SNAPSHOT_ID)

    def test_read_only_mutation_timeout_replay_and_production_gate_fail_closed(self):
        changed = self.invoke(FakeWslReviewer(mutate=True))
        self.assertEqual(changed["failure_reason"], "candidate_snapshot_changed")
        deliveries = list((self.exchange.root / "delivery_receipts").glob("*.json"))
        delivery_records = [json.loads(path.read_text()) for path in deliveries]
        reviewer_deliveries = [item for item in delivery_records
                               if item.get("adapter_id") == WSL_ADAPTER_ID]
        self.assertEqual([item["status"] for item in reviewer_deliveries], ["failed"])
        verifications = ([json.loads(path.read_text()) for path in
                          (self.exchange.root / "verification_receipts").glob("*.json")]
                         if (self.exchange.root / "verification_receipts").exists() else [])
        self.assertFalse(any(item.get("recipient", {}).get("worker_id") == WSL_REVIEWER_WORKER_ID
                             for item in verifications))
        reports = [json.loads(path.read_text()) for path in
                   (self.exchange.root / "reports").glob("*.json")]
        self.assertFalse(any(item.get("sender", {}).get("worker_id") == WSL_REVIEWER_WORKER_ID
                             for item in reports))
        self.assertNotIn("review_status", changed)
        self.setUp()
        def timeout(*args, **kwargs): raise subprocess.TimeoutExpired("codex", 1)
        failed = self.invoke(timeout); self.assertEqual(failed["failure_reason"], "preflight_failure")
        self.setUp(); self.invoke()
        with self.assertRaises(RuntimeError): self.invoke()
        with self.assertRaises(PermissionError):
            WslCodexReviewAdapter(self.exchange).deliver_production_once(
                package_id=self.prepared["package_id"],
                transport_authority={k: v for k, v in self.prepared["transport_authority"].items()
                                     if k != "adapter_promotion_reference"},
                return_authority=self.prepared["return_authority"], campaign_id="campaign",
                builder_return_report_id=self.campaign["builder_runs"][-1]["return_report_id"],
                candidate_snapshot_id=self.provenance["candidate_snapshot_id"],
                candidate_snapshot_root=self.workspace)

    def _formal_campaign(self):
        coordinator = CodexDevelopmentCampaign("fawkes", root=Path(self.tmp.name) / "campaigns",
            exchange=self.exchange, candidate_applier=lambda **kwargs:
                {"status":"applied_verified_after_review", "applied_paths":[], **kwargs})
        now = datetime.now(timezone.utc).isoformat()
        record = {"schema_version": 1, "record_type": "codex_development_campaign",
            "contract_version": CAMPAIGN_CONTRACT_VERSION, "campaign_id": "campaign",
            "instance_id": "fawkes", "objective": self.campaign["objective"],
            "objective_sha256": hashlib.sha256(self.campaign["objective"].encode()).hexdigest(),
            "objective_mode": "repository_write", "acceptance_condition_ids": ["done"],
            "acceptance_conditions": self.campaign["acceptance_conditions"],
            "allowed_scope": self.campaign["allowed_scope"], "source_sections": [],
            "validation_commands": [], "validation_policy": self.campaign["validation_policy"],
            "validation_declaration": self.campaign["validation_declaration"],
            "rider_authorization_reference": "test-rider-authority",
            "recovery_references": self.campaign["recovery_references"],
            "builder": {**CODEX_REPO_WORKER_REFERENCE, "target": "codex_repo",
                        "execution_mode_required": "repository_write", "identified_is_authorized": False},
            "reviewer_requirement": {"functional_role": FORMAL_REVIEW_ROLE,
                "role": DEFAULT_REVIEWER_ROLE, "worker_id": DEFAULT_REVIEWER_WORKER_ID,
                "transport_binding": "wsl-codex-exec-exact-review-v0.1",
                "must_differ_from_builder": True, "identity_is_authority": False},
            "maximum_iterations": MAX_ITERATIONS, "iteration": 1,
            "status": "awaiting_independent_review", "active_builder_task_scope_id": None,
            "builder_runs": [{**item, "candidate_workspace": str(self.workspace),
                "candidate_snapshot": {key:self.provenance[key] for key in
                    ("candidate_snapshot_id", "record_sha256", "file_count", "total_byte_length")}}
                for item in self.campaign["builder_runs"]],
            "reviews": [], "review_requests": [],
            "review_transport_attempts": [], "cache_lifecycle_events": [], "acceptance_satisfied": [],
            "needs_tanner": None, "cancelled": False, "automatic_promotion": False,
            "creates_authority": False, "state_revision": 1, "created_at": now, "updated_at": now,
            "events": []}
        coordinator.store.write(record)
        return coordinator

    def test_campaign_review_pass_cannot_promote_noncanonical_application_callback(self):
        coordinator = self._formal_campaign()
        with patch("src.runtime.codex_development_campaign.ROOT", self.workspace):
            terminal = coordinator.run_to_terminal("campaign", reviewer_adapter=WslCodexReviewAdapter(
                self.exchange, run_process=FakeWslReviewer(), timeout_seconds=5))
        self.assertEqual(terminal["status"], "failed_safe")
        self.assertEqual(terminal["needs_tanner"]["reason"],
                         "reviewed_candidate_apply_failed")
        self.assertEqual(terminal["reviews"][-1]["reviewer"]["worker_id"], WSL_REVIEWER_WORKER_ID)
        self.assertEqual(terminal["maximum_iterations"], 3)
        self.assertFalse(terminal["creates_authority"])

    @unittest.skipUnless(os.environ.get("FAWKES_WSL_CAMPAIGN_ACCEPTANCE") == "1",
                         "set FAWKES_WSL_CAMPAIGN_ACCEPTANCE=1 for real production review path")
    def test_real_campaign_default_wsl_review_reaches_terminal_decision(self):
        coordinator = self._formal_campaign()
        with patch("src.runtime.codex_development_campaign.ROOT", self.workspace):
            terminal = coordinator.run_to_terminal("campaign")
        self.assertIn(terminal["status"], {"succeeded", "tanner_escalation"})
        self.assertEqual(terminal["reviewer_requirement"]["worker_id"], WSL_REVIEWER_WORKER_ID)
        self.assertEqual(terminal["maximum_iterations"], 3)

    @unittest.skipUnless(os.environ.get("FAWKES_WSL_CODEX_QUALIFICATION") == "1",
                         "set FAWKES_WSL_CODEX_QUALIFICATION=1 for real WSL route")
    def test_real_authenticated_wsl_formal_review_route(self):
        with DisposableVerifierWorkspace(self.workspace) as frozen:
            prepared = prepare_wsl_review_package(exchange=self.exchange, campaign_record=self.campaign,
                candidate_snapshot=frozen.provenance, workspace=self.workspace)
            route_run_id = os.environ.get("FAWKES_WSL_ROUTE_RUN_ID", "wsl-real-route-test")
            invocation_id = f"{route_run_id}-invocation"
            result = WslCodexReviewAdapter(self.exchange, timeout_seconds=420).deliver_candidate_once(
                package_id=prepared["package_id"], transport_authority=prepared["transport_authority"],
                return_authority=prepared["return_authority"], campaign_id="campaign",
                builder_return_report_id=self.campaign["builder_runs"][-1]["return_report_id"],
                candidate_snapshot_id=frozen.provenance["candidate_snapshot_id"],
                candidate_snapshot_root=frozen.root, invocation_id=invocation_id)
        self.assertEqual(result["status"], "delivered")
        self.assertIn(result["review_status"], {"pass", "pass_with_caveats", "correction_required", "insufficient_evidence", "blocked"})
        evidence_path = os.environ.get("FAWKES_WSL_ROUTE_EVIDENCE_PATH")
        if evidence_path:
            evidence = {"schema_version": 1, "route_run_id": route_run_id,
                "invocation_id": invocation_id, "package_id": prepared["package_id"],
                "candidate_snapshot_id": frozen.provenance["candidate_snapshot_id"],
                "result_record_sha256": result["record_sha256"], "status": result["status"],
                "review_status_present": bool(result.get("review_status")),
                "creates_authority": result["creates_authority"]}
            Path(evidence_path).write_text(json.dumps(evidence, sort_keys=True) + "\n")


if __name__ == "__main__": unittest.main()

#!/usr/bin/env python3
"""Independent Tier 2 Assurance for the unpromoted CODEX write candidate."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.codex_write_builder_adapter import (
    WRITE_ADAPTER_ID, WRITE_ADAPTER_VERSION, WRITE_QUALIFICATION_CONTRACT_VERSION,
)
from src.runtime.disposable_verifier import DisposableVerifierWorkspace, SNAPSHOT_POLICY_VERSION


CAMPAIGN_VERSION = "codex-write-independent-assurance-v16-disposable-memory-database"
RESULT_SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "campaign_version", "candidate_snapshot_id", "verdict",
        "fixed_before_execution", "independently_derived", "hard_invariants", "real_route",
        "mutation_backed", "limitations", "promotion_recommended"],
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "campaign_version": {"type": "string", "const": CAMPAIGN_VERSION},
        "candidate_snapshot_id": {"type": "string"},
        "verdict": {"enum": ["pass", "fail", "partial", "inconclusive"]},
        "fixed_before_execution": {"type": "boolean"},
        "independently_derived": {"type": "boolean"},
        "hard_invariants": {"type": "object", "additionalProperties": False,
            "required": ["declared", "passed", "failed", "applicable_cases", "passed_cases"],
            "properties": {key: {"type": "integer"} for key in
                ("declared", "passed", "failed", "applicable_cases", "passed_cases")}},
        "real_route": {"type": "object", "additionalProperties": False,
            "required": ["attempted", "passed", "evidence_sha256"],
            "properties": {"attempted": {"type": "boolean"}, "passed": {"type": "boolean"},
                "evidence_sha256": {"type": "string"}}},
        "mutation_backed": {"type": "object", "additionalProperties": False,
            "required": ["cases", "passed", "failed"], "properties": {
                "cases": {"type": "integer"}, "passed": {"type": "integer"},
                "failed": {"type": "integer"}}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "promotion_recommended": {"type": "boolean"},
    }}


def _environment(**extra):
    allowed = ("PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "TERM", "SSL_CERT_FILE", "SSL_CERT_DIR")
    return {**{key: os.environ[key] for key in allowed if key in os.environ},
            "PYTHONDONTWRITEBYTECODE": "1", **extra}


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    with DisposableVerifierWorkspace(ROOT, parent="/tmp") as fixture:
        evidence_dir = fixture.root / "assurance-input"; evidence_dir.mkdir()
        portable_command = [str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/run_windows_snapshot_identity_acceptance.py")]
        portable = subprocess.run(portable_command, cwd=fixture.root, text=True, capture_output=True,
            env=_environment(), timeout=180, check=False)
        portable_evidence = {"policy_version": SNAPSHOT_POLICY_VERSION,
            "exit_status": portable.returncode,
            "stdout_sha256": _sha((portable.stdout or "").encode()),
            "stderr_sha256": _sha((portable.stderr or "").encode()),
            "real_windows_recomputation": True, "one_byte_tamper_required": True}
        (evidence_dir / "portable-snapshot-v2.json").write_text(
            json.dumps(portable_evidence, indent=2) + "\n", encoding="utf-8")
        real_command = [str(ROOT / ".venv/bin/python"), "-m", "unittest",
            "tests.test_autonomy_production_transports.AutonomyProductionTransportTests.test_real_codex_write_route_in_exact_disposable_candidate", "-v"]
        real = subprocess.run(real_command, cwd=fixture.root, text=True, capture_output=True,
            env=_environment(FAWKES_CODEX_WRITE_QUALIFICATION="1"), timeout=600, check=False)
        real_evidence = {"command": real_command, "exit_status": real.returncode,
            "stdout_sha256": _sha((real.stdout or "").encode()),
            "stderr_sha256": _sha((real.stderr or "").encode()),
            "real_authenticated_codex_route": True, "workspace": "nested_disposable_exact_candidate",
            "credentials_captured": False, "candidate_snapshot_id": fixture.provenance["candidate_snapshot_id"]}
        real_path = evidence_dir / "real-write-route.json"
        real_path.write_text(json.dumps(real_evidence, indent=2) + "\n", encoding="utf-8")
        schema = fixture.root / "assurance-result-schema.json"
        result_path = fixture.root / "assurance-result.json"
        schema.write_text(json.dumps(RESULT_SCHEMA, indent=2) + "\n", encoding="utf-8")
        prompt = f"""You are an independent Tier 2 Phoenix Assurance verifier in a disposable exact candidate.
You are separate from the builder context. The real Fawkes repository is read-only to this campaign; mutate only disposable fixtures under assurance-output/.
Candidate: {fixture.provenance['candidate_snapshot_id']}
Adapter: {WRITE_ADAPTER_ID} {WRITE_ADAPTER_VERSION}
Contract: {WRITE_QUALIFICATION_CONTRACT_VERSION}
Campaign: {CAMPAIGN_VERSION}
Snapshot identity policy: {SNAPSHOT_POLICY_VERSION}

Read the exact write adapter, read-only adapter, Worker Exchange, campaign coordinator, canonical Assurance contract, and focused tests.
Before executing tests, freeze your independently derived hard cases in assurance-output/fixed-campaign.json.
Independently derive mutation-backed cases for bindings, scope escape, wrong workspace/recipient/Phoenix/task/campaign/iteration,
expiry/revocation/replay, malformed return, timeout/interruption/nonzero exit, exact diff, dirty snapshot preservation,
recovery requirement, source/package mismatch, state typing, credential exclusion, no self-promotion,
and enforced PYTHONDONTWRITEBYTECODE without weakening mutation accounting. Independently verify
that newly created Python bytecode is exactly recorded and removed, meaningful non-cache mutations
remain visible, cleanup cannot mask source changes, and cache absence is verified before acceptance.
Derive cases for disposable-only construction, exact candidate identity, authorized and unauthorized
additions, deletion rejection, target-only drift, unrelated concurrent Archive creation, concurrent
target mutation, staged apply, post-apply digest verification, interruption, partial-apply rollback,
durable application evidence, stale/replayed candidates, and recovery restoration.
Verify that the schema itself binds exact package, source, task, and recipient fields and that
model-generated role paraphrases cannot cross the return lineage boundary.
Verify unknown claim IDs fail before application and any later Exchange evidence-recording failure
restores every applied target with durable rollback evidence rather than leaving ambiguous bytes.
Inject apply-path replacement failures independently from rollback and verify restoration uses the
recovery primitive; if restoration itself fails, require a durable recovery-required record.
Require rollback failure to remain explicitly recovery_required and never be typed as rolled back.
Run deterministic tests locally with {ROOT / '.venv/bin/python'} while cwd remains this disposable candidate.
Inspect assurance-input/real-write-route.json; a nonzero exit makes the required real route fail.
Inspect assurance-input/portable-snapshot-v2.json; a nonzero exit fails exact cross-platform
candidate identity and one-byte tamper-detection requirements.
Do not merely repeat builder conclusions and do not edit candidate source. One hard failure means fail.
Same model/provider family is a disclosed common-mode limitation, not provider diversity.
Return only the requested schema. Assurance may recommend promotion but cannot promote.
"""
        command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--strict-config",
            "--skip-git-repo-check", "--sandbox", "workspace-write", "--cd", str(fixture.root),
            "--output-schema", str(schema), "--output-last-message", str(result_path), "-"]
        verifier = subprocess.run(command, input=prompt, text=True, capture_output=True,
            env=_environment(), timeout=900, check=False)
        if verifier.returncode != 0 or not result_path.exists():
            raise RuntimeError(f"independent write verifier failed closed: {verifier.returncode}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        fixed = fixture.root / "assurance-output/fixed-campaign.json"
        if not fixed.exists() or result.get("candidate_snapshot_id") != fixture.provenance["candidate_snapshot_id"]:
            raise RuntimeError("independent write campaign provenance/freeze requirement failed")
        fixture.verify_source_unchanged()
        qualified = (portable.returncode == 0 and real.returncode == 0 and result["verdict"] == "pass"
            and result["hard_invariants"]["failed"] == 0
            and result["hard_invariants"]["applicable_cases"] == result["hard_invariants"]["passed_cases"])
        output = {"schema_version": 1, "record_type": "codex_write_independent_assurance",
            "campaign_version": CAMPAIGN_VERSION, "candidate_snapshot": fixture.provenance,
            "fixed_campaign_sha256": _sha(fixed.read_bytes()), "real_route": real_evidence,
            "portable_snapshot_v2": portable_evidence,
            "verdict": result, "qualified": qualified, "promoted": False,
            "real_repository_unchanged": True, "disposable_cleanup": True}
    print(json.dumps(output, indent=2))
    return 0 if output["qualified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

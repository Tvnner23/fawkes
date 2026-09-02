#!/usr/bin/env python3
"""Tier 2 independent Assurance for the Windows exact-review candidate."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime.disposable_verifier import DisposableVerifierWorkspace, SNAPSHOT_POLICY_VERSION
from src.runtime.windows_codex_reviewer import (
    WINDOWS_ADAPTER_ID, WINDOWS_ADAPTER_VERSION, WINDOWS_REVIEW_CONTRACT_VERSION,
)

CAMPAIGN_VERSION = "windows-codex-exact-review-independent-assurance-v3-portable-snapshot-v2"
RESULT_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": ["schema_version", "campaign_version", "candidate_snapshot_id", "verdict",
        "fixed_before_execution", "independently_derived", "hard_invariants", "mutation_backed",
        "limitations", "promotion_recommended"],
    "properties": {"schema_version": {"type": "integer", "const": 1},
        "campaign_version": {"type": "string", "const": CAMPAIGN_VERSION},
        "candidate_snapshot_id": {"type": "string"},
        "verdict": {"enum": ["pass", "fail", "partial", "inconclusive"]},
        "fixed_before_execution": {"type": "boolean"}, "independently_derived": {"type": "boolean"},
        "hard_invariants": {"type": "object", "additionalProperties": False,
            "required": ["declared", "passed", "failed", "applicable_cases", "passed_cases"],
            "properties": {key: {"type": "integer"} for key in
                ("declared", "passed", "failed", "applicable_cases", "passed_cases")}},
        "mutation_backed": {"type": "object", "additionalProperties": False,
            "required": ["cases", "passed", "failed"], "properties": {
                "cases": {"type": "integer"}, "passed": {"type": "integer"}, "failed": {"type": "integer"}}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "promotion_recommended": {"type": "boolean"}}}


def env(**extra):
    allowed = ("PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "TERM", "SSL_CERT_FILE", "SSL_CERT_DIR",
               "WSL_INTEROP", "WSL_DISTRO_NAME")
    return {**{key: os.environ[key] for key in allowed if key in os.environ}, **extra}


def sha(value): return hashlib.sha256(value).hexdigest()


def main():
    with DisposableVerifierWorkspace(ROOT, parent="/tmp") as fixture:
        evidence = fixture.root / "assurance-input"; evidence.mkdir()
        portable_command = [str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/run_windows_snapshot_identity_acceptance.py")]
        portable = subprocess.run(portable_command, cwd=fixture.root, text=True, capture_output=True,
            env=env(), timeout=180, check=False)
        portable_record = {"policy_version": SNAPSHOT_POLICY_VERSION,
            "exit_status": portable.returncode,
            "stdout_sha256": sha((portable.stdout or "").encode()),
            "stderr_sha256": sha((portable.stderr or "").encode()),
            "real_windows_recomputation": True, "one_byte_tamper_required": True}
        (evidence / "portable-snapshot-v2.json").write_text(
            json.dumps(portable_record, indent=2) + "\n", encoding="utf-8")
        real_command = [str(ROOT / ".venv/bin/python"), "-m", "unittest",
            "tests.test_autonomy_production_transports.AutonomyProductionTransportTests.test_real_authenticated_windows_exact_evidence_review_route", "-v"]
        real = subprocess.run(real_command, cwd=fixture.root, text=True, capture_output=True,
            env=env(FAWKES_WINDOWS_CODEX_QUALIFICATION="1"), timeout=600, check=False)
        real_record = {"exit_status": real.returncode, "stdout_sha256": sha((real.stdout or "").encode()),
            "stderr_sha256": sha((real.stderr or "").encode()), "real_authenticated_windows_route": True,
            "candidate_snapshot_id": fixture.provenance["candidate_snapshot_id"], "credentials_captured": False}
        (evidence / "real-route.json").write_text(json.dumps(real_record, indent=2) + "\n", encoding="utf-8")
        schema = fixture.root / "assurance-schema.json"; result_path = fixture.root / "assurance-result.json"
        schema.write_text(json.dumps(RESULT_SCHEMA), encoding="utf-8")
        prompt = f"""You are a fresh independent Tier 2 Phoenix Assurance verifier in an exact disposable candidate.
Candidate: {fixture.provenance['candidate_snapshot_id']}
Adapter: {WINDOWS_ADAPTER_ID} {WINDOWS_ADAPTER_VERSION}
Contract: {WINDOWS_REVIEW_CONTRACT_VERSION}
Campaign: {CAMPAIGN_VERSION}
Snapshot identity policy: {SNAPSHOT_POLICY_VERSION}
The authoritative repository is read-only; mutate only assurance-output fixtures.
Read the exact Windows adapter, Worker Exchange, campaign coordinator, Assurance contract, and focused tests.
Before executing tests, independently derive and freeze a fixed campaign at assurance-output/fixed-campaign.json.
Include mutation-backed cases for recipient/environment/Phoenix/campaign/task/builder/digest/snapshot linkage;
exact UTF-8 artifact bytes, mutation manifests, test evidence, stale/wrong candidate rejection, logical request idempotency,
attempt accounting, summary substitution, unsupported claims, disagreements, malformed/partial returns, authority creation,
expiry/revocation/replay, timeout/cancellation/nonzero process, credential exclusion, and read-only/no-promotion semantics.
Run deterministic tests locally. Inspect assurance-input/real-route.json: nonzero exit fails the real-route invariant.
Inspect assurance-input/portable-snapshot-v2.json: nonzero exit fails exact cross-platform
snapshot identity and one-byte tamper detection.
Do not copy builder conclusions. One applicable hard failure means fail. Do not edit candidate source.
Same provider/model family is a disclosed common-mode limitation, not provider diversity.
Return only the schema; Assurance may recommend promotion but cannot promote.
"""
        command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--strict-config",
            "--skip-git-repo-check", "--sandbox", "workspace-write", "--cd", str(fixture.root),
            "--output-schema", str(schema), "--output-last-message", str(result_path), "-"]
        verifier = subprocess.run(command, input=prompt, text=True, capture_output=True,
            env=env(), timeout=900, check=False)
        if verifier.returncode != 0 or not result_path.exists():
            raise RuntimeError(f"independent Windows-review verifier failed closed: {verifier.returncode}")
        verdict = json.loads(result_path.read_text(encoding="utf-8"))
        fixed = fixture.root / "assurance-output/fixed-campaign.json"
        if not fixed.exists() or verdict.get("candidate_snapshot_id") != fixture.provenance["candidate_snapshot_id"]:
            raise RuntimeError("independent campaign provenance/freeze failed")
        fixture.verify_source_unchanged()
        qualified = (portable.returncode == 0 and real.returncode == 0 and verdict["verdict"] == "pass"
            and verdict["hard_invariants"]["failed"] == 0
            and verdict["hard_invariants"]["applicable_cases"] == verdict["hard_invariants"]["passed_cases"])
        snapshot = {key: fixture.provenance[key] for key in ("candidate_snapshot_id",
            "source_root_sha256", "disposable_root_sha256", "file_count", "total_byte_length",
            "record_sha256")}
        output = {"schema_version": 1, "record_type": "windows_codex_review_independent_assurance",
            "campaign_version": CAMPAIGN_VERSION, "candidate_snapshot": snapshot,
            "fixed_campaign_sha256": sha(fixed.read_bytes()), "real_route": real_record,
            "portable_snapshot_v2": portable_record,
            "verdict": verdict, "qualified": qualified, "promoted": False,
            "real_repository_unchanged": True, "disposable_cleanup": True}
    print(json.dumps(output, indent=2)); return 0 if output["qualified"] else 2


if __name__ == "__main__": raise SystemExit(main())

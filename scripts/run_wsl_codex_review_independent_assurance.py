#!/usr/bin/env python3
"""Independent qualification for the exact WSL formal-review candidate."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.runtime.disposable_verifier import DisposableVerifierWorkspace
from src.runtime.wsl_codex_reviewer import WSL_QUALIFICATION_CONTRACT

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "wsl-codex-formal-review-independent-assurance-v1"


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    with tempfile.TemporaryDirectory(prefix="fawkes-wsl-assurance-") as outer, \
            DisposableVerifierWorkspace(ROOT) as fixture:
        evidence = Path(outer) / "assurance-input"; evidence.mkdir()
        python = str(ROOT / ".venv/bin/python")
        command = [python, "-B", "-m", "unittest", "tests.test_wsl_codex_reviewer", "-v"]
        deterministic = subprocess.run(command, cwd=fixture.root, text=True, capture_output=True,
                                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=180)
        real_command = [python, "-B", "-m", "unittest",
            "tests.test_wsl_codex_reviewer.WslFormalReviewerTests.test_real_authenticated_wsl_formal_review_route", "-v"]
        route_run_id = "wsl-assurance-route-" + uuid.uuid4().hex
        route_evidence_path = evidence / "real-route-bound.json"
        real = subprocess.run(real_command, cwd=fixture.root, text=True, capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "FAWKES_WSL_CODEX_QUALIFICATION": "1",
                 "FAWKES_WSL_ROUTE_RUN_ID": route_run_id,
                 "FAWKES_WSL_ROUTE_EVIDENCE_PATH": str(route_evidence_path)},
            timeout=480)
        bound_route = (json.loads(route_evidence_path.read_text())
                       if route_evidence_path.exists() else {})
        route_bound = (bound_route.get("route_run_id") == route_run_id
            and bound_route.get("invocation_id") == route_run_id + "-invocation"
            and bound_route.get("status") == "delivered"
            and bound_route.get("review_status_present") is True
            and bound_route.get("creates_authority") is False)
        real_record = {"command": real_command, "exit_status": real.returncode,
            "stdout_sha256": sha(real.stdout.encode()), "stderr_sha256": sha(real.stderr.encode()),
            "output_bodies_recorded": False, "route_run_id": route_run_id,
            "bound_route_evidence_sha256": (sha(route_evidence_path.read_bytes())
                if route_evidence_path.exists() else None),
            "real_authenticated_route": real.returncode == 0 and route_bound}
        (evidence / "real-route.json").write_text(json.dumps(real_record, indent=2) + "\n", encoding="utf-8")
        deterministic_record = {"command": command, "exit_status": deterministic.returncode,
            "stdout_sha256": sha(deterministic.stdout.encode()), "stderr_sha256": sha(deterministic.stderr.encode()),
            "output_bodies_recorded": False}
        (evidence / "deterministic.json").write_text(json.dumps(deterministic_record, indent=2) + "\n", encoding="utf-8")
        schema = Path(outer) / "assurance-schema.json"
        schema.write_text(json.dumps({"type": "object", "additionalProperties": False,
            "required": ["campaign_version", "candidate_snapshot_id", "hard_invariants_passed",
                         "hard_invariants_total", "applicable_cases_passed", "applicable_cases_total",
                         "real_route_passed", "verdict", "limitations"],
            "properties": {"campaign_version": {"type": "string"}, "candidate_snapshot_id": {"type": "string"},
                "hard_invariants_passed": {"type": "integer"}, "hard_invariants_total": {"type": "integer"},
                "applicable_cases_passed": {"type": "integer"}, "applicable_cases_total": {"type": "integer"},
                "real_route_passed": {"type": "boolean"}, "verdict": {"enum": ["pass", "fail"]},
                "limitations": {"type": "array", "items": {"type": "string"}}}}), encoding="utf-8")
        output = Path(outer) / "assurance-result.json"
        prompt = f"""You are an independent Phoenix Assurance verifier in a fresh disposable execution context.
Independently inspect the exact candidate at {fixture.root}, its contract in
src/runtime/wsl_codex_reviewer.py, tests/test_wsl_codex_reviewer.py, and body-free evidence at {evidence}.
Do not rely on builder conclusions. Derive and execute held-out/adversarial checks where safely possible in /tmp.
This entire candidate is disposable and writable for Assurance mutation tests; the authoritative repository is not.
Recompute the candidate identity before mutating it and require it to equal the declared identity.
Verify all 16 declared hard invariants, including exact frozen identity/evidence/lineage, wrong binding,
read-only and no inherited write authority, zero authority, replay/stale/malformed/timeout handling, and all
structured review states. A real-route exit other than zero blocks PASS. Preserve limitations truthfully.
The WSL_QUALIFIED_SNAPSHOT_ID is provenance for the adapter qualification fixture, not a required
identity for later production review candidates. Prove instead that each dynamically frozen candidate
is exactly bound throughout its own request and cannot be substituted by that fixture or a neighbor.
The body-free real-route record includes a unique route_run_id and digest of a separately retained,
schema-bound route result. Require real_authenticated_route=true; do not infer route absence merely
because private model response bodies are intentionally excluded.
Return only the schema with campaign_version={CAMPAIGN!r} and
candidate_snapshot_id={fixture.provenance['candidate_snapshot_id']!r}."""
        verifier_command = ["codex", "--ask-for-approval", "never", "exec", "--ephemeral",
            "--ignore-user-config", "--strict-config", "--sandbox", "workspace-write", "--cd", str(fixture.root),
            "--output-schema", str(schema), "--output-last-message", str(output), "-"]
        verifier = subprocess.run(verifier_command, input=prompt, text=True, capture_output=True,
                                  env=os.environ, timeout=900)
        result = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
        qualified = (deterministic.returncode == real.returncode == verifier.returncode == 0
            and route_bound
            and result.get("verdict") == "pass"
            and result.get("hard_invariants_passed") == len(WSL_QUALIFICATION_CONTRACT["hard_invariants"])
            and result.get("hard_invariants_total") == len(WSL_QUALIFICATION_CONTRACT["hard_invariants"])
            and result.get("real_route_passed") is True
            and result.get("applicable_cases_passed") == result.get("applicable_cases_total"))
        record = {"schema_version": 1, "record_type": "wsl_codex_review_independent_assurance",
            "campaign_version": CAMPAIGN, "candidate_snapshot_id": fixture.provenance["candidate_snapshot_id"],
            "candidate_record_sha256": fixture.provenance["record_sha256"],
            "fixed_contract_sha256": sha(json.dumps(WSL_QUALIFICATION_CONTRACT, sort_keys=True).encode()),
            "deterministic": deterministic_record, "real_route": real_record,
            "verifier_exit_status": verifier.returncode, "independent_result": result,
            "qualified": qualified, "promoted": False}
        print(json.dumps(record, indent=2))
        return 0 if qualified else 2


if __name__ == "__main__": raise SystemExit(main())

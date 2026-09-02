#!/usr/bin/env python3
"""Focused independent Assurance for the fixed WSL default-reviewer binding."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.runtime.disposable_verifier import DisposableVerifierWorkspace

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "wsl-default-formal-reviewer-binding-assurance-v1"
INVARIANTS = (
    "promoted_exact_wsl_candidate_is_default", "builder_and_reviewer_are_distinct",
    "formal_review_uses_exact_frozen_candidate", "reviewer_cannot_inherit_write_authority",
    "wrong_reviewer_binding_fails_closed", "windows_transport_remains_promoted_fallback",
    "maximum_three_builder_iterations", "fawkes_authority_does_not_expand",
)


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    with tempfile.TemporaryDirectory(prefix="fawkes-wsl-binding-") as outer, \
            DisposableVerifierWorkspace(ROOT) as fixture:
        outer = Path(outer); python = str(ROOT / ".venv/bin/python")
        focused = [python, "-B", "-m", "unittest", "tests.test_codex_development_campaign",
                   "tests.test_wsl_codex_reviewer", "tests.test_autonomy_production_transports", "-q"]
        focused_run = subprocess.run(focused, cwd=fixture.root, text=True, capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=240)
        real = [python, "-B", "-m", "unittest",
            "tests.test_wsl_codex_reviewer.WslFormalReviewerTests.test_real_campaign_default_wsl_review_reaches_terminal_decision", "-v"]
        real_run = subprocess.run(real, cwd=fixture.root, text=True, capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "FAWKES_WSL_CAMPAIGN_ACCEPTANCE": "1"}, timeout=600)
        evidence = outer / "evidence.json"
        evidence.write_text(json.dumps({"focused_exit": focused_run.returncode,
            "focused_stdout_sha256": sha(focused_run.stdout.encode()),
            "focused_stderr_sha256": sha(focused_run.stderr.encode()),
            "real_path_exit": real_run.returncode, "real_stdout_sha256": sha(real_run.stdout.encode()),
            "real_stderr_sha256": sha(real_run.stderr.encode()), "output_bodies_recorded": False}, indent=2),
            encoding="utf-8")
        schema = outer / "schema.json"; output = outer / "result.json"
        schema.write_text(json.dumps({"type": "object", "additionalProperties": False,
            "required": ["campaign", "snapshot", "passed", "total", "verdict", "limitations"],
            "properties": {"campaign": {"type": "string"}, "snapshot": {"type": "string"},
                "passed": {"type": "integer"}, "total": {"type": "integer"},
                "verdict": {"enum": ["pass", "fail"]},
                "limitations": {"type": "array", "items": {"type": "string"}}}}), encoding="utf-8")
        prompt = f"""Independently verify this exact disposable Fawkes candidate and focused evidence at {evidence}.
Inspect src/runtime/codex_development_campaign.py, src/runtime/wsl_codex_reviewer.py,
src/runtime/windows_codex_reviewer.py, and their focused tests. Derive adversarial checks for these invariants:
{json.dumps(INVARIANTS)}
Require the exact promoted WSL identity as the fixed normal reviewer; frozen evidence; no write/approval/promotion
authority; wrong binding rejection; Windows still independently promoted and only explicit fallback; limit 3;
and the real campaign-path test exit zero. Do not infer PASS from prose. Return only the schema with
campaign={CAMPAIGN!r} and snapshot={fixture.provenance['candidate_snapshot_id']!r}."""
        command = ["codex", "--ask-for-approval", "never", "exec", "--ephemeral", "--ignore-user-config",
            "--strict-config", "--sandbox", "workspace-write", "--cd", str(fixture.root),
            "--output-schema", str(schema), "--output-last-message", str(output), "-"]
        verified = subprocess.run(command, input=prompt, text=True, capture_output=True, env=os.environ, timeout=900)
        result = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
        passed = (focused_run.returncode == real_run.returncode == verified.returncode == 0
                  and result.get("verdict") == "pass" and result.get("passed") == len(INVARIANTS)
                  and result.get("total") == len(INVARIANTS))
        record = {"campaign": CAMPAIGN, "candidate_snapshot_id": fixture.provenance["candidate_snapshot_id"],
            "candidate_record_sha256": fixture.provenance["record_sha256"],
            "invariants": f"{result.get('passed', 0)}/{len(INVARIANTS)}", "real_path": real_run.returncode == 0,
            "independent_result": result, "qualified": passed, "promotion_preauthorized": True}
        print(json.dumps(record, indent=2)); return 0 if passed else 2


if __name__ == "__main__": raise SystemExit(main())

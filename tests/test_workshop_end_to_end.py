"""Composed synthetic Workshop flow with actual isolated candidate execution.

The candidate is a tiny fixture, not a production Fawkes change. Tests establish
execution-to-report-to-review fidelity, not real independent Assurance or Alpha
daily-use acceptance. No provider, live state, or campaign is used.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from src.memory.workshop import WorkshopStore
from tests import test_workshop as fixtures


class WorkshopComposedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.WorkshopTests(methodName="test_full_flow_is_versioned_attributed_and_inert")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def execute_and_record(self, candidate_id, *, corrected):
        fixture = self.fixture
        candidate = fixture.root / "isolated-candidates" / candidate_id
        candidate.mkdir(parents=True)
        # Both versions really run. The old one preserves input order; the
        # corrected fixture orders equal-ranked evidence by its exact identity.
        expression = "sorted(values)" if corrected else "list(values)"
        source = (
            "import json\n"
            f"def rank(values): return {expression}\n"
            "actual=rank(['source-b','source-a'])\n"
            "passed=actual==['source-a','source-b']\n"
            "print(json.dumps({'actual':actual,'passed':passed}))\n"
            "raise SystemExit(0 if passed else 1)\n"
        )
        path = candidate / "candidate.py"
        path.write_text(source)
        path.chmod(0o444)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        started = datetime.now(timezone.utc).isoformat()
        completed = subprocess.run(
            [sys.executable, "-I", "-B", str(path)], cwd=candidate,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=10,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0 if corrected else 1)
        self.assertIs(result["passed"], corrected)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        raw_report = fixture.report(payload={
            "candidate_id": candidate_id, "candidate_sha256": digest,
            "exit_status": completed.returncode, "result": result,
            "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
            "scope": "actual synthetic fixture subprocess only; not production acceptance",
        })
        contract = fixture.record["acceptance_contracts"][-1]
        payload = {
            "proposal_id": fixture.record["proposal_id"],
            "contract_version": contract["contract_version"],
            "contract_sha256": contract["contract_sha256"],
            "candidate": {"candidate_id": candidate_id, "revision": candidate_id,
                "sha256": digest, "instance_id": "fixture-phoenix", "reality_scope": "isolated"},
            "started_at": started, "isolated": True, "ordinary_history_mutated": False,
            "results": [
                {"criterion_id": "exact-source", "verdict": "pass" if result["passed"] else "fail",
                 "observed": "Actual subprocess ordering: " + json.dumps(result["actual"]),
                 "evidence": [fixture.ref(raw_report)]},
                {"criterion_id": "no-live-write", "verdict": "pass",
                 "observed": "The inspected fixture code only sorts fixed synthetic IDs and writes stdout.",
                 "evidence": [fixture.ref(raw_report)]},
            ],
            "tests": ["actual isolated exact-source ordering"],
            "sandbox_results": ["Fresh temporary cwd; isolated Python; no provider credentials; immutable fixture source."],
            "cost": {"provider_calls": 0, "source": "actual local test subprocess"},
            "limitations": ["A synthetic algorithm fixture, not production retrieval qualification or independent review."],
        }
        report = fixture.report("workshop-evaluation-v1", payload)
        fixture.append("record_evaluation", {"report_reference": fixture.ref(report)})
        return fixture.ref(report)

    def test_actual_failed_then_corrected_execution_remains_inert_and_historical(self):
        fixture = self.fixture
        fixture.declared(tier=2)
        first = self.execute_and_record("actual-fixture-bad", corrected=False)
        first_revision = fixture.record["revision"]
        self.assertEqual(fixture.record["verdict"], "fail")
        first_sha = fixture.record["record_sha256"]
        second = self.execute_and_record("actual-fixture-corrected", corrected=True)
        self.assertNotEqual(first, second)
        self.assertEqual([item["verdict"] for item in fixture.record["evaluations"]], ["fail", "pass"])
        # Successful builder execution is still not independent Tier2 Assurance.
        self.assertEqual(fixture.record["verdict"], "inconclusive")
        fixture.append("submit", {})
        with patch("src.runtime.codex_development_campaign.CodexDevelopmentCampaign.create",
                   side_effect=AssertionError("Workshop review must not create a campaign")), \
             patch("openai.OpenAI", side_effect=AssertionError("Workshop review must not call a provider")):
            reviewed = fixture.store.review(
                fixture.record["proposal_id"], expected_revision=fixture.record["revision"],
                decision="approve", note="Only a future separately authorized action; independent evidence still needed.",
                rider_principal_id="fixture-rider", authenticated_rider=True,
            )
        self.assertEqual(reviewed["status"], "approved_for_future_action")
        self.assertEqual(reviewed["verdict"], "inconclusive")
        self.assertIs(reviewed["reviews"][-1]["creates_authority"], False)
        restarted = WorkshopStore("fixture-phoenix", root=fixture.root)
        historical = restarted.get(reviewed["proposal_id"], revision=first_revision)
        self.assertEqual(historical["record_sha256"], first_sha)
        self.assertEqual(historical["verdict"], "fail")
        self.assertEqual(restarted.get(reviewed["proposal_id"])["record_sha256"], reviewed["record_sha256"])
        for forbidden in ("archive", "conversations", "database/development_campaigns"):
            self.assertFalse((fixture.root / forbidden).exists())


if __name__ == "__main__":
    unittest.main()

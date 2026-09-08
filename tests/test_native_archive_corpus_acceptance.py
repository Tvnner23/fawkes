import copy
import json
import unittest
from pathlib import Path

from src.runtime.native_archive_corpus_acceptance import run_corpus


ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "native_archive_acceptance_corpus.json"
EXPECTED = ROOT / "tests" / "fixtures" / "native_archive_acceptance_expected.json"


class NativeArchiveCorpusAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(CORPUS.read_text())
        cls.expected = json.loads(EXPECTED.read_text())
        cls.result = run_corpus(cls.corpus, cls.expected)

    def test_fixture_is_synthetic_scoped_and_truth_is_separate(self):
        self.assertIn("synthetic disposable", self.corpus["fixture_purpose"])
        self.assertEqual(self.corpus["instance_id"], "acceptance-phoenix")
        self.assertTrue(self.expected["annotations_are_not_runtime_input"])
        self.assertNotIn("requires_clarification", json.dumps(self.corpus))
        self.assertNotIn("expected_choice_ids", json.dumps(self.corpus))
        self.assertTrue(self.result["synthetic_disposable_data"])
        self.assertFalse(self.result["real_history_accessed"])

    def test_predeclared_thresholds_pass_with_raw_metrics(self):
        self.assertTrue(self.result["passed"], json.dumps(self.result["metrics"], indent=2))
        self.assertTrue(all(self.result["threshold_checks"].values()))
        for metric in self.result["metrics"].values():
            self.assertIn("rate", metric)

    def test_security_projection_and_authority_invariants(self):
        by_id = {item["case_id"]: item for item in self.result["case_results"]}
        preference = by_id["source_original_preference"]
        self.assertEqual(preference["selected_evidence_ids"], ["original"])
        self.assertEqual(preference["context_redundancy_reduction"], 1)
        projection = by_id["duplicate_and_contradiction_projection"]
        self.assertEqual(projection["duplicate_group_count"], 1)
        self.assertEqual(projection["contradiction_group_ids"], ["router-claim"])
        self.assertEqual(projection["projected_evidence_ids"], ["claim-a", "claim-b"])
        stale = by_id["stale_projection"]
        self.assertEqual(stale["status"], "stale")
        self.assertFalse(stale["projection_applied"])
        self.assertEqual(self.result["metrics"]["fail_closed_security"]["rate"], 1.0)

    def test_result_is_deterministic_machine_readable_and_body_free(self):
        repeated = run_corpus(copy.deepcopy(self.corpus), copy.deepcopy(self.expected))
        self.assertEqual(self.result, repeated)
        encoded = json.dumps(self.result, sort_keys=True)
        self.assertNotIn("The router uses wired backhaul", encoded)
        self.assertNotIn("synthetic acceptance body", encoded)
        self.assertIn("acceptance passed", self.result["summary"])
        self.assertEqual(self.result["metrics"]["determinism"]["rate"], 1.0)


if __name__ == "__main__":
    unittest.main()

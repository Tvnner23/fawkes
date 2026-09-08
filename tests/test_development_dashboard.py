import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.development_dashboard as dashboard
import src.memory.development_store as development_store


class DevelopmentDashboardTests(unittest.TestCase):
    def _write(self, directory, name, payload):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_dashboard_projects_existing_stores_without_copying_or_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposals = root / "proposals"
            review = root / "review"
            feedback = root / "feedback"
            self._write(proposals, "p1.json", {"proposal_id": "p1", "instance_id": "fawkes-1", "status": "proposed"})
            self._write(proposals, "p2.json", {"proposal_id": "p2", "instance_id": "sibling-2", "status": "proposed"})
            self._write(review, "r1.json", {"review_id": "r1", "instance_id": "fawkes-1", "status": "needs_review"})
            self._write(feedback, "f1.json", {"feedback_id": "f1", "instance_id": "fawkes-1"})
            observed = [
                {"observation_id": "o1", "category": "system_defect"},
                {"observation_id": "o2", "category": "base_phoenix_candidate"},
                {"observation_id": "o3", "category": "correction_signal"},
            ]
            with patch.object(dashboard, "DEVELOPMENT_DIR", proposals), patch.object(
                dashboard, "DEV_REVIEW_DIR", review
            ), patch.object(dashboard, "FEEDBACK_DIR", feedback), patch.object(
                dashboard, "list_development_observations", return_value=observed
            ), patch.object(
                dashboard,
                "development_progression",
                return_value=[{"event_id": "event-1", "instance_id": "fawkes-1"}],
            ):
                result = dashboard.build_development_dashboard(instance_id="fawkes-1")

        self.assertEqual([item["proposal_id"] for item in result["development_proposals"]], ["p1"])
        self.assertEqual(result["system_defects"][0]["observation_id"], "o1")
        self.assertEqual(result["base_phoenix_candidates"][0]["observation_id"], "o2")
        self.assertEqual(result["corrections"][0]["observation_id"], "o3")
        self.assertEqual(result["growth_assessment_status"], "deferred")
        self.assertIsNone(result["growth_assessment"])
        self.assertEqual(result["progression"][0]["event_id"], "event-1")
        projected = [
            item for item in result["human_review_items"]
            if item.get("source") == "development_proposal"
        ]
        self.assertEqual(projected[0]["candidate_id"], "p1")
        self.assertEqual(result["presentation_contract_version"], 1)
        self.assertEqual(result["presentation_development"], [])
        self.assertNotIn("personality_score", result)

    def test_legacy_unscoped_records_require_explicit_migration_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "legacy.json", {"proposal_id": "legacy", "status": "proposed"})
            strict = dashboard._records(root, instance_id="fawkes-1")
            bridged = dashboard._records(root, instance_id="fawkes-1", include_legacy_unscoped=True)

        self.assertEqual(strict, [])
        self.assertEqual(bridged[0]["proposal_id"], "legacy")

    def test_human_review_records_decision_without_applying_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "p1.json", {
                "proposal_id": "p1", "instance_id": "fawkes-1", "status": "proposed",
                "proposed_change": "Consider a different response pattern.",
            })
            with patch.object(development_store, "DEVELOPMENT_DIR", root):
                result = development_store.review_development_proposal(
                    "p1", instance_id="fawkes-1", decision="approve"
                )
        self.assertEqual(result["status"], "approved_for_future_action")
        self.assertEqual(
            result["review"]["effect"],
            "recorded_only_no_automatic_personality_or_code_change",
        )


if __name__ == "__main__":
    unittest.main()

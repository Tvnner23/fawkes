from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from src.runtime.autonomy_supervision import (
    PROGRESS_INTERVAL_SECONDS, RiderActivityStore, RiderNotificationStore,
    TannerAttentionTransportRegistry,
    campaign_activity_projection, notification_eligibility,
    retain_needs_tanner_notification,
)


class AutonomySupervisionTests(unittest.TestCase):
    def record(self, *, status="builder_in_progress", needs=None):
        return {"campaign_id": "campaign-one", "objective": "bounded objective",
            "status": status, "iteration": 1, "maximum_iterations": 3,
            "builder": {"worker_id": "worker"},
            "reviewer_requirement": {"worker_id": "reviewer"},
            "needs_tanner": needs, "cancelled": False,
            "recovery_references": [{"reference_type": "recovery", "reference_id": "base"}],
            "builder_runs": [{"iteration": 1, "status": "completed", "task_scope_id": "task",
                "return_report_id": "builder-report", "verification_status": "verified",
                "failure": None, "transport_result_reference": {"record_sha256": "a"},
                "validation_evidence": [{"exit_status": 0}]}],
            "reviews": [{"iteration": 1, "status": "correction_required",
                "reviewer": {"worker_id": "reviewer"}, "review_report_id": "review-report",
                "acceptance_condition_ids_satisfied": [],
                "violated_acceptance_condition_ids": ["condition"],
                "defects": [{"defect_id": "defect"}]}],
            "events": [
                {"event_id": "e1", "kind": "builder_return_retained",
                 "created_at": "2026-09-01T00:00:00+00:00", "detail": {"iteration": 1}},
                {"event_id": "e2", "kind": "independent_review_retained",
                 "created_at": "2026-09-01T00:01:00+00:00", "detail": {"iteration": 1}},
                {"event_id": "e3", "kind": "bounded_correction_started",
                 "created_at": "2026-09-01T00:02:00+00:00", "detail": {"iteration": 2}},
            ]}

    def test_live_projection_orders_and_distinguishes_worker_events(self):
        view = campaign_activity_projection(self.record())
        self.assertEqual([item["event_id"] for item in view["activity"]], ["e1", "e2", "e3"])
        self.assertEqual(view["activity"][0]["worker"]["worker_id"], "worker")
        self.assertEqual(view["activity"][1]["worker"]["worker_id"], "reviewer")
        self.assertFalse(view["hidden_chain_of_thought_exposed"])
        self.assertFalse(view["creates_authority"])

    def test_needs_tanner_is_immediate_and_quiet_hour_bypass(self):
        now = datetime(2026, 9, 1, tzinfo=timezone.utc)
        record = self.record(status="tanner_escalation", needs={"reason": "blocked"})
        intent = notification_eligibility(record, now=now, rider_last_active_at=now)
        self.assertEqual(intent["kind"], "needs_tanner")
        self.assertTrue(intent["bypasses_quiet_hours"])

    def test_progress_requires_three_hours_inactivity_and_quiet_configuration(self):
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        self.assertIsNone(notification_eligibility(self.record(), now=now,
            rider_last_active_at=now - timedelta(seconds=PROGRESS_INTERVAL_SECONDS - 1)))
        unconfigured = notification_eligibility(self.record(), now=now,
            rider_last_active_at=now - timedelta(seconds=PROGRESS_INTERVAL_SECONDS))
        self.assertFalse(unconfigured["eligible"])
        self.assertEqual(unconfigured["reason"], "quiet_hours_unconfigured")
        quiet = {"is_quiet": lambda moment: True, "ended_with_suppressed": False}
        suppressed = notification_eligibility(self.record(), now=now,
            rider_last_active_at=now - timedelta(hours=4), quiet_hours=quiet)
        self.assertTrue(suppressed["suppressed"])

    def test_morning_summary_and_logical_dedup_are_separate_from_attempts(self):
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        quiet = {"is_quiet": lambda moment: False, "ended_with_suppressed": True}
        self.assertEqual(notification_eligibility(self.record(), now=now,
            rider_last_active_at=now - timedelta(hours=4), quiet_hours=quiet)["kind"], "morning_summary")
        with tempfile.TemporaryDirectory() as directory:
            store = RiderNotificationStore("phoenix", root=directory)
            first, created = store.create_once(kind="needs_tanner", campaign_id="campaign-one",
                state_key="blocked", message="Fawkes: campaign needs Tanner; inspect private Development.",
                evidence_refs=[{"reference_id": "campaign-one"}])
            repeated, created_again = store.create_once(kind="needs_tanner", campaign_id="campaign-one",
                state_key="blocked", message="ignored duplicate", evidence_refs=[])
            self.assertTrue(created); self.assertFalse(created_again)
            self.assertEqual(first["notification_id"], repeated["notification_id"])
            failed = store.deliver(first, lambda message: (_ for _ in ()).throw(RuntimeError("offline")))
            self.assertFalse(failed["delivered"])
            self.assertEqual(failed["attempts"][0]["status"], "failed")
            self.assertFalse(failed["creates_authority"])

    def test_authenticated_rider_activity_is_integrity_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RiderActivityStore("phoenix", root=directory)
            with self.assertRaises(PermissionError): store.touch(authenticated_rider=False)
            written = store.touch(authenticated_rider=True)
            self.assertEqual(store.load()["last_active_at"], written["last_active_at"])

    def test_needs_tanner_body_is_sanitized_and_deduplicated(self):
        attention_id = "attention-" + "b" * 64
        record = self.record(status="tanner_escalation", needs={
            "reason": "scope decision required", "attention_id": attention_id})
        record.update({"instance_id": "phoenix", "record_sha256": "a" * 64})
        with tempfile.TemporaryDirectory() as directory:
            first = retain_needs_tanner_notification(record, root=directory)
            second = retain_needs_tanner_notification(record, root=directory)
            self.assertEqual(first["notification_id"], second["notification_id"])
            self.assertNotIn("builder-report", first["message"])
            self.assertNotIn("review-report", first["message"])
            self.assertIn(attention_id, first["message"])
            self.assertFalse(first["creates_authority"])

    def test_registered_transport_fanout_is_extensible_deduplicated_and_tanner_only(self):
        received = []
        registry = TannerAttentionTransportRegistry().register(
            "fake_attention", lambda message: received.append(message) or
            {"provider": "fake", "provider_status": "delivered"}, endpoint_authorized=True)
        with self.assertRaises(PermissionError):
            registry.register("emily_private", lambda message: None,
                              endpoint_authorized=True, recipient_identity="emily")
        with tempfile.TemporaryDirectory() as directory:
            store = RiderNotificationStore("phoenix", root=directory)
            logical, _ = store.create_once(kind="needs_tanner", campaign_id="campaign-one",
                state_key="exact-blocker", message="Fawkes needs Tanner. Open exact request.",
                evidence_refs=[])
            first = registry.dispatch(logical, store)
            second = registry.dispatch(first["notification"], store)
        self.assertEqual(received, ["Fawkes needs Tanner. Open exact request."])
        self.assertEqual(len(second["notification"]["attempts"]), 1)
        self.assertFalse(second["creates_authority"])

    def test_ambiguous_accepted_attempt_is_not_blindly_replayed(self):
        sent = []
        with tempfile.TemporaryDirectory() as directory:
            store = RiderNotificationStore("phoenix", root=directory)
            logical, _ = store.create_once(kind="needs_tanner", campaign_id="campaign-one",
                state_key="exact-blocker", message="Fawkes needs Tanner.", evidence_refs=[])
            logical["attempts"] = [{"attempt_id": "attempt-existing",
                "transport": "discord_webhook", "status": "accepted_receipt_ambiguous"}]
            result = store.deliver(logical, lambda message: sent.append(message),
                                   transport_name="discord_webhook")
        self.assertEqual(sent, [])
        self.assertEqual(result["attempts"], logical["attempts"])


if __name__ == "__main__":
    unittest.main()

"""Canonical read-only reporting and real JavaScript render regressions."""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.app.server import _console_campaigns, _console_jobs, _console_roadmap, _console_update_text
from src.runtime.autonomy_supervision import campaign_console_reporting, console_timestamp
from src.runtime.codex_development_campaign import CodexDevelopmentCampaign


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-11T03:10:00+00:00"


def event(kind, stamp, iteration=1, **detail):
    return {"event_id": f"{kind}-{iteration}", "kind": kind, "created_at": stamp,
            "detail": {"iteration": iteration, **detail}}


def record(status="awaiting_independent_review"):
    return {"campaign_id": "sourced-job", "objective": "Improve a bounded component",
        "record_sha256": "a" * 64, "status": status, "iteration": 1, "maximum_iterations": 3,
        "builder": {"worker_id": "worker-one"}, "reviewer_requirement": {"worker_id": "reviewer-one"},
        "needs_tanner": None, "cancelled": False, "recovery_references": [], "source_sections": [],
        "acceptance_condition_ids": ["condition-one"], "acceptance_satisfied": [],
        "builder_runs": [{"iteration": 1, "status": "completed", "task_scope_id": "task-one",
            "return_report_id": "returned-one", "verification_status": "unverified",
            "completed_at": "2026-09-11T03:02:05+00:00",
            "validation_evidence": [{"exit_status": 0}, {"exit_status": 0}]}],
        "reviews": [], "events": [
            event("campaign_created", "2026-09-11T03:00:00+00:00"),
            event("builder_invocation_started", "2026-09-11T03:01:00+00:00", task_scope_id="task-one"),
            event("builder_return_retained", "2026-09-11T03:02:06+00:00")],
    }


def projected(value, managed=()):
    owner = object.__new__(CodexDevelopmentCampaign)
    owner.store = SimpleNamespace(load=lambda _identity: value)
    owner.exchange = SimpleNamespace(_load=lambda *_: (_ for _ in ()).throw(KeyError("No report in fixture")))
    owner.managed_worker_activity_projection = lambda _identity: list(managed)
    with patch("src.runtime.autonomy_supervision.campaign_console_reporting",
               side_effect=lambda source, observations: campaign_console_reporting(source, observations, observed_at=NOW)):
        wrapper = owner.presentation(value["campaign_id"])
    return _console_campaigns({"campaigns": [wrapper]})[0]


class ConsoleJobTimingTests(unittest.TestCase):
    def test_retained_worker_is_waiting_and_projection_does_not_rewrite_record(self):
        source = record()
        before = copy.deepcopy(source)
        campaign = projected(source)
        self.assertEqual(source, before)
        job = _console_jobs([campaign], [])[0]
        self.assertEqual(job["state"], "waiting")
        self.assertFalse(job["successful"])
        self.assertIn("completed", job["accomplished"])
        self.assertIn("2/2", job["accomplished"])
        self.assertIn("still required", job["current_step"])
        self.assertIn("Independent review", job["next"])
        intervals = campaign["console_reporting"]["intervals"]
        self.assertEqual(intervals[0]["duration_seconds"], 65)
        self.assertTrue(all(not item["active_verified"] for item in intervals))
        self.assertEqual(next(item for item in intervals if item["stage"] == "review")["duration_seconds"], None)

    def test_success_failed_closed_escalated_and_unknown_export_the_same_facts(self):
        for status, state in [("succeeded", "done"), ("failed_safe", "failed"),
                ("cancelled", "closed"), ("expired", "closed"), ("denied", "closed"),
                ("tanner_escalation", "needs_you"), ("integrity_unavailable", "unknown")]:
            with self.subTest(status=status):
                source = record(status)
                source["needs_tanner"] = {"decision_needed": "Inspect the exact retained failure"}
                if status == "succeeded":
                    source["reviews"] = [{"iteration": 1, "status": "pass", "reviewer": {},
                        "defects": [], "acceptance_condition_ids_satisfied": ["condition-one"]}]
                    source["application_evidence"] = {"status": "applied_verified_after_review", "applied_paths": ["src/example.py"]}
                    source["git_commit_evidence"] = {"status": "committed", "head": "b" * 40}
                job = _console_jobs([projected(source)], [])[0]
                self.assertEqual(job["state"], state)
                self.assertEqual(job["successful"], status == "succeeded")
                if status == "succeeded":
                    for fact in ("Independent review: pass", "applied_verified_after_review", "Git: committed"):
                        self.assertIn(fact, job["accomplished"])
                output = _console_update_text({"jobs": [job], "creates_authority": False},
                    created_at=NOW, snapshot_id="fixture")
                for field in ("objective", "current_step", "accomplished", "gained", "next"):
                    self.assertIn(job[field], output)
                self.assertIn(state.upper().replace("_", " ") + ":", output)
                self.assertNotIn("Suggested next job", output)
                self.assertNotIn("remain not started", output)
                self.assertIn("no parent completion inferred", output)

    def test_public_result_and_parent_identity_stay_separate(self):
        source = record()
        source["parent_campaign_id"] = "parent-still-open"
        managed = [{"invocation_id": "task-one-appserver", "worker_id": "worker-one",
            "state": "completed", "updated_at": "2026-09-11T03:02:05+00:00", "events": [{
                "event_id": "public-final", "kind": "result", "state": "completed",
                "created_at": "2026-09-11T03:02:05+00:00", "public_message": "Added the requested bounded index."}]}]
        job = _console_jobs([projected(source, managed)], [])[0]
        self.assertEqual(job["public_result"], "Added the requested bounded index.")
        self.assertEqual(job["parent_campaign_id"], "parent-still-open")
        self.assertFalse(job["successful"])
        self.assertEqual(job["state"], "waiting")

    def test_active_requires_exact_fresh_running_observation(self):
        source = record("builder_in_progress")
        source["builder_runs"] = []
        source["events"] = source["events"][:2]
        source["active_builder_task_scope_id"] = "task-one"
        managed = {"invocation_id": "task-one-appserver", "worker_id": "worker-one",
            "state": "running", "updated_at": "2026-09-11T03:09:59+00:00", "events": []}
        result = campaign_console_reporting(source, [managed], observed_at=NOW)["intervals"][0]
        self.assertTrue(result["active_verified"])
        self.assertEqual(result["duration_seconds"], 540)
        self.assertEqual(_console_jobs([projected(source, [managed])], [])[0]["state"], "working")
        quiet = campaign_console_reporting(source, [{**managed, "updated_at": "2026-09-11T03:01:00+00:00"}], observed_at=NOW)
        self.assertTrue(quiet["intervals"][0]["active_verified"], "quiet process-verified work is not stale prose")
        for change in ({"state": "waiting"}, {"state": "disconnected"}, {"state": "completed"},
                       {"invocation_id": "neighbor"}, {"worker_id": "neighbor"},
                       {"updated_at": "2026-09-11T03:10:01+00:00"}):
            result = campaign_console_reporting(source, [{**managed, **change}], observed_at=NOW)["intervals"][0]
            self.assertFalse(result["active_verified"])
            self.assertIsNone(result["duration_seconds"])

    def test_bad_partial_reversed_and_future_boundaries_fail_closed(self):
        for stamp in (None, "not a time", "2026-09-11", "2026-09-11T03:00:00",
                      "2026-02-30T03:00:00+00:00", "2026-09-11T03:00:59+00:00", "2026-09-11T04:00:00+00:00"):
            source = record()
            source["builder_runs"][0]["completed_at"] = stamp
            result = campaign_console_reporting(source, observed_at=NOW)["intervals"][0]
            self.assertIsNone(result["duration_seconds"], stamp)
        self.assertIsNone(console_timestamp("2026-09-11T25:00:00Z"))
        source = record()
        source["events"][1]["created_at"] = "invalid start"
        self.assertIsNone(campaign_console_reporting(source, observed_at=NOW)["intervals"][0]["duration_seconds"])

    def test_correction_attempts_queue_dispatch_and_transport_close_are_distinct(self):
        source = record("awaiting_independent_review")
        source["iteration"] = 2
        source["events"] += [
            event("logical_review_request_prepared", "2026-09-11T03:03:06+00:00"),
            event("provider_action_reserved", "2026-09-11T03:03:10+00:00", operation_type="reviewer"),
            event("builder_invocation_started", "2026-09-11T03:05:00+00:00", 2, task_scope_id="task-two"),
            event("builder_return_retained", "2026-09-11T03:07:01+00:00", 2)]
        source["builder_runs"].append({"iteration": 2, "status": "completed", "completed_at": "2026-09-11T03:07:00+00:00"})
        source["review_transport_attempts"] = [{"iteration": 1, "actual_process_invocation": True,
            "created_at": "2026-09-11T03:04:00+00:00", "status": "completed"}]
        result = campaign_console_reporting(source, observed_at=NOW)
        workers = [item for item in result["intervals"] if item["stage"] == "worker"]
        self.assertEqual([item["duration_seconds"] for item in workers], [65, 120])
        self.assertEqual([item["attempt"] for item in workers], [1, 2])
        queue = next(item for item in result["intervals"] if item["stage"] == "review_queue")
        self.assertEqual(queue["duration_seconds"], 60)
        review = next(item for item in result["intervals"] if item["stage"] == "review")
        self.assertIsNone(review["started_at"])
        self.assertIsNone(review["duration_seconds"])
        self.assertFalse(review["active_verified"])
        self.assertEqual(result, campaign_console_reporting(source, observed_at=NOW))
        source["events"][-2]["created_at"] = "2026-09-11T03:01:30+00:00"
        overlapping = campaign_console_reporting(source, observed_at=NOW)
        self.assertIsNone(next(item for item in overlapping["intervals"] if item["stage"] == "worker")["duration_seconds"])

    def test_public_recap_exact_lineage_not_stale_next_authority(self):
        source = record("succeeded")
        source["builder_runs"][0]["package_id"] = "package-one"
        package = {"package_id": "package-one", "task_scope_id": "task-one",
            "source_report_id": "source-one", "source_report_sha256": "c" * 64,
            "record_sha256": "d" * 64, "recipient": {"worker_id": "worker-one"}}
        report = {"report_id": "returned-one", "task_scope_id": "task-one", "record_sha256": "e" * 64,
            "sender": {"worker_id": "worker-one"}, "created_at": NOW,
            "in_reply_to": {"package_id": "package-one", "source_report_id": "source-one",
                "source_report_sha256": "c" * 64, "source_package_sha256": "d" * 64},
            "sections": [{"section_id": key, "content": text,
                "content_sha256": hashlib.sha256(text.encode()).hexdigest()}
                for key, text in (("accomplished", "Created the contributor index."),
                    ("gained", "Contributors can find the correct owner."),
                    ("next", "Historical review was still pending."), ("unrelated", "DO NOT DISPLAY"))]}
        owner = object.__new__(CodexDevelopmentCampaign)
        owner.exchange = SimpleNamespace(_load=lambda kind, _: report if kind == "reports" else package)
        recap = owner._console_return_recap(source)
        self.assertEqual(recap["accomplished"], "Created the contributor index.")
        self.assertNotIn("unrelated", recap)
        campaign = projected(source)
        campaign["console_reporting"]["return_recap"] = recap
        job = _console_jobs([campaign], [])[0]
        self.assertIn(recap["accomplished"], job["accomplished"])
        self.assertIn(recap["gained"], job["gained"])
        self.assertNotIn("pending", job["next"])
        self.assertEqual(job["return_recap"]["next"], recap["next"])
        unicode_report = copy.deepcopy(report)
        section = unicode_report["sections"][0]
        section["content"] = "🦅" * 901
        section["content_sha256"] = hashlib.sha256(section["content"].encode()).hexdigest()
        owner.exchange = SimpleNamespace(_load=lambda kind, _: unicode_report if kind == "reports" else package)
        bounded = owner._console_return_recap(source)
        self.assertLess(len(bounded["accomplished"].encode()), 1000)
        self.assertTrue(bounded["accomplished"].endswith("[excerpt]"))
        from src.app.server import _console_reporting
        self.assertEqual(_console_reporting({**campaign["console_reporting"], "return_recap": bounded})["return_recap"], bounded)
        for mutate in (lambda r: r["in_reply_to"].update(package_id="wrong"),
                lambda r: r.update(task_scope_id="wrong"),
                lambda r: r["sender"].update(worker_id="wrong"),
                lambda r: r["sections"][0].update(content="changed"),
                lambda r: r["sections"].append(r["sections"][0])):
            broken = copy.deepcopy(report); mutate(broken)
            owner.exchange = SimpleNamespace(_load=lambda kind, _: broken if kind == "reports" else package)
            self.assertEqual(owner._console_return_recap(source), {"status": "unavailable"})


class ConsoleJavaScriptQualificationTests(unittest.TestCase):
    def run_harness(self, path, payload=None):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node executable is absent")
        result = subprocess.run([node, str(ROOT / path)], cwd=ROOT, text=True,
            input=json.dumps(payload) if payload is not None else "", capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_projection_harness(self):
        self.assertIn("dev-console-projection-ok", self.run_harness("tests/js/dev_console_projection_harness.js"))

    def test_touch_harness(self):
        self.run_harness("tests/js/console_touch_harness.js")

    def test_combined_timing_harness(self):
        campaign = projected(record())
        roadmap = _console_roadmap(ROOT, source_revision="a" * 40)
        self.assertIn("console-combined-timing-ok", self.run_harness("tests/js/console_combined_timing_harness.js",
            {"roadmap": roadmap, "campaigns": [campaign], "jobs": _console_jobs([campaign], [])}))


if __name__ == "__main__":
    unittest.main()

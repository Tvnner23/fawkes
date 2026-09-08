"""Read-only contract tests for the portable development-console projection."""

from __future__ import annotations

from email.message import Message
from io import BytesIO
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import urllib.request
import unittest
from unittest.mock import Mock, patch

from src.app.server import (
    BrowserSessionStore, ConsoleUpdateStore, FawkesAppHandler, FawkesAppServer,
    _console_jobs,
)
from src.runtime.chat_service import (
    ChatServiceError,
    FawkesChatService,
    build_development_console_repository_projection,
)
from src.runtime.development_attention import DevelopmentAttentionStore


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "src" / "app" / "static" / "dev-console"
HTML_PATH = STATIC_ROOT / "index.html"
CSS_PATH = STATIC_ROOT / "console.css"
JAVASCRIPT_PATH = STATIC_ROOT / "console.js"
NODE_HARNESS = ROOT / "tests" / "js" / "dev_console_projection_harness.js"


def _repository_fixture():
    head = "1" * 40
    return {
        "branch": "fixture/console",
        "head": head,
        "comparison_base": "3" * 40,
        "selection_basis": "head_commit_paths",
        "status_summary": {
            "dirty_paths": 0, "tracked_changes": 0, "untracked_paths": 0,
            "staged_paths": 0, "deleted_paths": 0,
        },
        "files": [{
            "path": "src/app/server.py", "mode": "100644", "object_type": "blob",
            "object_id": "2" * 40, "head_change": "M", "worktree_state": "clean",
            "revision": head, "review_status": "not_projected",
            "diff_excerpt": "@@ -1 +1 @@\n-old\n+new\n",
        }],
        "creates_authority": False,
        "creates_continuing_authority": False,
    }


class _StaticHandler:
    """Minimal HTTP output surface for exercising the exact static allowlist."""

    def __init__(self):
        self.statuses = []
        self.headers = []
        self.wfile = BytesIO()
        self.server = SimpleNamespace(chat_service=Mock())

    def send_response(self, status):
        self.statuses.append(status)

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        return None

    def _json(self, status, payload):
        self.statuses.append(status)
        self.headers.append(("Content-Type", "application/json; charset=utf-8"))
        self.wfile.write(json.dumps(payload).encode("utf-8"))


class DevConsoleStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.javascript = JAVASCRIPT_PATH.read_text(encoding="utf-8")

    def test_console_has_five_bounded_pages_and_defaults_to_summary(self):
        self.assertIn('id="dev-console" data-idle-seconds="60"', self.html)
        pages = re.findall(r'class="console-page" data-page="(\d)"([^>]*)', self.html)
        self.assertEqual([value for value, _ in pages], ["0", "1", "2", "3", "4"])
        self.assertNotIn("hidden", pages[0][1])
        self.assertTrue(all("hidden" in attributes for _, attributes in pages[1:]))
        for heading in (
            "Activity Summary",
            "Campaign Status",
            "Repository View",
            "Architecture View",
        ):
            self.assertIn(heading, self.html)
        for label in ("Summary", "Campaign", "Repo", "System map"):
            self.assertRegex(
                self.html,
                rf'data-page-target="[0-3]"[^>]*>{re.escape(label)}</button>',
            )
        self.assertIn('id="preview-context"', self.html)
        self.assertIn('id="connection-state"', self.html)
        self.assertIn('id="campaign-state"', self.html)
        self.assertIn('id="attention-state"', self.html)

    def test_primary_copy_distinguishes_connection_campaign_and_component_truth(self):
        self.assertNotIn(">LIVE<", self.html)
        for phrase in (
            "CONNECTED",
            "EXECUTION NOT OBSERVED",
            "NO ACTIONABLE REQUEST",
            "This does not mean Fawkes has no history",
            "Reference maturity is not runtime health",
            "Independent review recorded",
            "Stopped safely",
        ):
            self.assertIn(phrase, self.javascript)

    def test_each_non_activity_page_has_a_dedicated_primary_interface(self):
        self.assertIn('id="campaign-graph" class="campaign-graph gesture-surface"', self.html)
        self.assertIn('id="campaign-selector"', self.html)
        self.assertIn('id="repository-tree" class="repository-tree gesture-surface"', self.html)
        self.assertIn('id="repository-detail-view" class="repository-detail-view gesture-surface"', self.html)
        self.assertIn('id="repository-back"', self.html)
        self.assertIn('id="architecture-map" class="architecture-map gesture-surface"', self.html)
        self.assertEqual(self.html.count('id="activity-feed" class="job-list"'), 1)
        self.assertNotIn('id="campaign-list" class="card-list"', self.html)
        self.assertNotIn('id="repository-content" class="card-list"', self.html)
        self.assertNotIn('id="architecture-content" class="card-list"', self.html)
        for marker in (
            "campaignGraphStages", "renderCampaignDashboard",
            "renderRepositoryDashboard", "renderArchitectureDashboard",
        ):
            self.assertIn(marker, self.javascript)

    def test_square_viewport_fixed_navigation_and_reliable_touch_targets(self):
        self.assertIn("width: min(100dvw, 720px)", self.css)
        self.assertIn("height: min(100dvh, 720px)", self.css)
        self.assertRegex(self.css, r"\.console-header\s*\{[^}]*position:\s*relative")
        self.assertRegex(self.css, r"\.page-nav button\s*\{[^}]*min-width:\s*44px;[^}]*min-height:\s*44px")
        # A small-viewport override must never shrink an interactive target.
        target_sizes = [int(value) for value in re.findall(r"min-(?:width|height):\s*(\d+)px", self.css)]
        self.assertTrue(target_sizes)
        self.assertGreaterEqual(min(target_sizes), 44)
        self.assertIn("overflow-y: auto", self.css)
        self.assertIn("overflow-x: auto", self.css)
        self.assertIn("touch-action: pan-x", self.css)

    def test_campaign_repository_and_architecture_visual_contracts_are_distinct(self):
        self.assertIn('marker-end": "url(#campaign-arrow)"', self.javascript)
        self.assertIn("established-edge", self.javascript)
        self.assertIn("Recorded correction loop", self.javascript)
        self.assertIn('repositoryDetailOpen = true', self.javascript)
        self.assertIn('repositoryDetailOpen = false', self.javascript)
        self.assertIn("Working-tree paths", self.javascript)
        for component in (
            "Phoenix identity", "Archive and evidence", "Memory", "Library",
            "Clients and console", "Development campaign", "Native Attention",
            "Workers and Reviewers", "Application and Git", "Physical embodiment",
        ):
            self.assertIn(component, self.javascript)
        self.assertIn("Canonical app server (not this localhost candidate preview)", self.javascript)

    def test_markup_and_script_have_no_inline_or_duplicate_decision_controls(self):
        self.assertNotRegex(self.html, r"\son[a-z]+\s*=")
        self.assertNotRegex(self.html, r"\sstyle\s*=")
        combined = self.html + "\n" + self.javascript
        for forbidden in (
            "approve_once",
            "Approve Once",
            "/decision",
            "Authorization",
            "sessionStorage",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertNotIn("innerHTML", self.javascript)
        self.assertIn("textContent", self.javascript)
        self.assertIn("X-Fawkes-CSRF-Token", self.javascript)
        self.assertIn("idempotency_key", self.javascript)
        self.assertIn('key: pendingUpdateKey, campaign_id: pendingUpdateCampaign', self.javascript)
        self.assertNotRegex(self.javascript, r'setItem\([^\n]*(credential|csrf|token)')

    def test_script_uses_only_compact_authenticated_read_only_projection(self):
        expected = {"/api/development/dev-console", "/api/development/console-updates",
                    "/api/session/console-csrf"}
        routes = set(re.findall(r"['\"](/api/[^'\"]+)['\"]", self.javascript))
        self.assertEqual(routes, expected)
        self.assertIn("credentials", self.javascript)
        self.assertIn("same-origin", self.javascript)
        self.assertNotIn("/api/development/dashboard", self.javascript)
        self.assertNotIn("/evidence", self.javascript)

    def test_script_wires_accessible_details_and_non_authorizing_inputs(self):
        for event_name in ("pointerdown", "pointerup", "keydown", "wheel", "auxclick"):
            self.assertIn(event_name, self.javascript)
        self.assertIn('element(documentRef, "details"', self.javascript)
        self.assertIn('element(documentRef, "summary"', self.javascript)
        self.assertRegex(self.javascript, r"button\s*!==\s*1")
        self.assertIn("ArrowLeft", self.javascript)
        self.assertIn("ArrowRight", self.javascript)
        # Horizontal code scrolling is explicitly excluded from page swipes.
        self.assertIn("code-scroll", self.javascript)
        self.assertRegex(
            self.javascript,
            r'state\s*===\s*"live"[\s\S]*actionable:\s*false,\s*detail_url:\s*""',
        )

    def test_static_routes_are_exact_no_store_and_do_not_touch_campaign_service(self):
        expected = {
            "/dev-console": ("text/html; charset=utf-8", b"Fawkes Developer Console"),
            "/dev-console/": ("text/html; charset=utf-8", b"Fawkes Developer Console"),
            "/dev-console/index.html": ("text/html; charset=utf-8", b"Fawkes Developer Console"),
            "/dev-console/console.js": ("text/javascript; charset=utf-8", b"FawkesDevConsole"),
            "/dev-console/console.css": ("text/css; charset=utf-8", b"#dev-console"),
        }
        for route, (content_type, marker) in expected.items():
            with self.subTest(route=route):
                handler = _StaticHandler()
                FawkesAppHandler._serve_static(handler, route)
                headers = dict(handler.headers)
                self.assertEqual(handler.statuses, [200])
                self.assertEqual(headers["Content-Type"], content_type)
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
                self.assertIn(marker, handler.wfile.getvalue())
                if content_type.startswith("text/html"):
                    self.assertNotIn(b"__FAWKES_BUILD_ID__", handler.wfile.getvalue())
                handler.server.chat_service.assert_not_called()

        handler = _StaticHandler()
        FawkesAppHandler._serve_static(handler, "/dev-console/../app.js")
        self.assertEqual(handler.statuses, [404])


class DevConsoleReadOnlyHTTPTests(unittest.TestCase):
    def test_roadmap_every_item_binds_its_actual_document(self):
        from src.app.server import _console_roadmap
        roadmap = _console_roadmap(ROOT, source_revision="a" * 40)
        for item in [*roadmap["phases"], *roadmap["tracks"]]:
            body = (ROOT / item["source"]).read_bytes()
            self.assertEqual(item["source_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(item["source_bytes"], len(body))
            self.assertEqual(item["source_revision"], "a" * 40)
            if item["source_status"] != "canonical":
                self.assertNotEqual(item["source_sha256"], roadmap["source_sha256"])
                self.assertEqual(item["source_excerpt"].encode(), body)
                self.assertIn("not the complete original instruction", item["source_excerpt"])
        home = next(i for i in roadmap["tracks"] if i["id"] == "track-dedicated-home")
        social = next(i for i in roadmap["tracks"] if i["id"] == "track-social")
        self.assertEqual(home["source_status"], "recorded_requirement")
        self.assertEqual(social["source_status"], "proposed")

    def test_roadmap_missing_source_is_unavailable_not_wrongly_authenticated(self):
        from src.app.server import _console_roadmap
        original = Path.open
        def missing(path, *args, **kwargs):
            if path.name == "roadmap-addendum.txt": raise FileNotFoundError(path)
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", missing):
            with self.assertRaises(FileNotFoundError):
                _console_roadmap(ROOT, source_revision="a" * 40)

    def test_roadmap_source_change_changes_only_its_own_binding(self):
        from src.app.server import _console_roadmap
        original = Path.open
        changed = b"Recorded synthetic source change; no authority.\n"
        def altered(path, *args, **kwargs):
            if path.name == "roadmap-addendum.txt": return BytesIO(changed)
            return original(path, *args, **kwargs)
        before = _console_roadmap(ROOT, source_revision="a" * 40)
        with patch.object(Path, "open", altered):
            after = _console_roadmap(ROOT, source_revision="a" * 40)
        self.assertEqual(before["phases"], after["phases"])
        for item in after["tracks"]:
            if item["source_status"] != "canonical":
                self.assertEqual(item["source_sha256"], hashlib.sha256(changed).hexdigest())
                self.assertEqual(item["source_excerpt"].encode(), changed)

    def test_canonical_tanner_escalation_needs_human_without_native_request(self):
        campaign={"campaign_id":"human-blocked","status":"tanner_escalation",
            "needs_tanner":{"decision_needed":"Choose a supported builder before continuing."}}
        job=_console_jobs([campaign],[])[0]
        self.assertEqual(job["state"],"needs_you")
        self.assertEqual(job["next"],campaign["needs_tanner"]["decision_needed"])
        self.assertFalse(job["successful"])
        self.assertFalse(job["creates_authority"])

    def test_roadmap_completed_milestone_is_not_overridden_by_phase_number(self):
        from src.app.server import _console_roadmap
        repository=Path(__file__).resolve().parents[1]
        roadmap=_console_roadmap(repository,source_revision="fixture-revision")
        self.assertEqual(roadmap["phases"][8]["maturity"],"implemented")
        self.assertEqual(roadmap["phases"][8]["runtime_state"],"unknown")
        self.assertTrue(any(item["maturity"]=="planned" for item in roadmap["tracks"]))

    def test_only_current_actionable_attention_marks_a_job_needs_you(self):
        campaign = {"campaign_id": "campaign-closed", "objective": "Preserve a failed review",
            "status": "failed_safe", "current_stage": "review", "builder": None,
            "needs_tanner": {"decision_needed": "historical text"}, "activity": [],
            "managed_worker_activity": []}
        closed = _console_jobs([campaign], [])[0]
        # Terminal failure must no longer share the successful Done label.
        self.assertEqual(closed["state"], "failed")
        self.assertFalse(closed["successful"])
        self.assertIn("No verified capability gain", closed["gained"])
        self.assertNotEqual(closed["next"], "historical text")
        actionable = _console_jobs([campaign], [{"campaign_id": "campaign-closed",
                                                  "actionable": True}])[0]
        self.assertEqual(actionable["state"], "needs_you")
        self.assertFalse(actionable["creates_authority"])

    def _handler(self, path, *, authorized):
        service = Mock()
        handler = object.__new__(FawkesAppHandler)
        handler.server = SimpleNamespace(chat_service=service)
        handler.path = path
        handler.headers = Message()
        handler._require_auth = Mock(return_value=authorized)
        handler._json = Mock()
        return handler, service

    def test_compact_projection_requires_existing_authentication(self):
        handler, service = self._handler("/api/development/dev-console", authorized=False)
        handler.do_GET()
        handler._require_auth.assert_called_once_with(record_rider_activity=False)
        self.assertEqual(service.mock_calls, [])
        handler._json.assert_not_called()

    def test_compact_projection_uses_passive_attention_projection_without_rider_activity(self):
        handler, service = self._handler("/api/development/dev-console", authorized=True)
        service.list_codex_development_campaigns.return_value = {"campaigns": []}
        service.development_attention_projection.return_value = {
            "attention": [], "creates_authority": False,
        }
        service.production_component_status.return_value = {
            "components": {}, "latest_failure_receipts": [], "creates_authority": False,
        }
        service.development_console_repository_projection.return_value = _repository_fixture()
        handler.do_GET()
        handler._require_auth.assert_called_once_with(record_rider_activity=False)
        service.list_codex_development_campaigns.assert_called_once_with()
        service.development_attention_projection.assert_called_once_with(pending_only=True)
        service.production_component_status.assert_called_once_with()
        service.development_console_repository_projection.assert_called_once_with()
        self.assertEqual(
            [call[0] for call in service.mock_calls],
            [
                "list_codex_development_campaigns",
                "development_attention_projection",
                "production_component_status",
                "development_console_repository_projection",
            ],
        )
        handler._json.assert_called_once()
        self.assertEqual(handler._json.call_args.args[0], 200)

    def test_authenticated_http_poll_is_observational_for_attention_and_rider_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            sessions = Path(directory) / "sessions"
            environment = {
                "FAWKES_RUNTIME_STATE_ROOT": str(runtime),
                "FAWKES_DEVELOPMENT_ROOT": str(ROOT),
                "FAWKES_APP_SESSION_ROOT": str(sessions),
            }
            with patch.dict(os.environ, environment, clear=False):
                store = DevelopmentAttentionStore()
                event = store.create(
                    campaign_id="console-observer-http", invocation_id="fixture-invocation",
                    worker={"worker_id": "fixture-worker"},
                    kind="native_codex_approval_required", blocked_action="fixture action",
                    why_required="test passive display", requested_authority="fixture only",
                    expires_in_seconds=0, expiration_reason="fixture deadline",
                    expiration_effect="no continuation", can_request_again=True,
                    work_lost=False,
                )
                store.transactions.mkdir(parents=True, exist_ok=True)
                transaction = store.transactions / "incomplete.json"
                transaction.write_text(json.dumps({"schema_version": 1,
                    "record_type": "development_attention_transaction",
                    "transaction_id": "incomplete", "writes": [{
                        "relative_path": f"events/{event['attention_id']}.json",
                        "value": {"attention_id": event["attention_id"]},
                    }]}), encoding="utf-8")

                def snapshot(path):
                    if not path.exists():
                        return {}
                    return {item.relative_to(path).as_posix(): hashlib.sha256(
                        item.read_bytes()).hexdigest() for item in path.rglob("*")
                            if item.is_file()}

                class FixtureService:
                    instance_id = "console-observer-fixture"

                    def list_codex_development_campaigns(self):
                        return {"campaigns": []}

                    def development_attention_projection(self, *, pending_only=False):
                        return FawkesChatService.development_attention_projection(
                            self, pending_only=pending_only)

                    def production_component_status(self):
                        return {"components": {}, "creates_authority": False}

                    def development_console_repository_projection(self):
                        return _repository_fixture()

                attention_before = snapshot(runtime / "development_attention")
                rider_root = ROOT / "database" / "rider_activity"
                rider_before = snapshot(rider_root)
                server = FawkesAppServer(("127.0.0.1", 0), chat_service=FixtureService(),
                    app_token="fixture-token", app_session_store=BrowserSessionStore(sessions))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/development/dev-console",
                        headers={"Authorization": "Bearer fixture-token", "Accept": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=10) as response:
                        payload = json.loads(response.read())
                        self.assertEqual(response.status, 200)
                finally:
                    server.shutdown(); server.server_close(); thread.join(timeout=5)
                self.assertFalse(payload["creates_authority"])
                self.assertFalse(payload["creates_continuing_authority"])
                self.assertEqual(payload["attention"], [])
                self.assertEqual(snapshot(runtime / "development_attention"), attention_before)
                self.assertEqual(snapshot(rider_root), rider_before)

    def test_server_projection_is_exact_body_free_and_drops_overbroad_records(self):
        handler, service = self._handler("/api/development/dev-console", authorized=True)
        secret_markers = (
            "SOURCE-BODY-MUST-NOT-CROSS",
            "RAW-PROMPT-MUST-NOT-CROSS",
            "FAILURE-RECEIPT-MUST-NOT-CROSS",
            "PRIVATE-REASONING-MUST-NOT-CROSS",
        )
        service.list_codex_development_campaigns.return_value = {
            "campaigns": [{
                "campaign_id": "outer-campaign-id-is-not-authoritative-here",
                "objective": "Ignored outer wrapper objective",
                "acceptance_satisfied": ["condition-1"],
                "operational_learning_observations": {
                    "builder_invocations": 1,
                    "logical_reviews": 1,
                    "review_transport_attempts": 1,
                    "reviewer_process_invocations": 1,
                    "correction_count": 0,
                    "reviewer_defect_count": 0,
                    "source_section_count": 2,
                    "private": secret_markers[3],
                },
                "live_activity": {
                    "campaign_id": "campaign-compact",
                    "objective": "Finish the authenticated console fixture",
                    "status": "needs_tanner",
                    "current_stage": "awaiting_attention",
                    "iteration": 1,
                    "maximum_iterations": 2,
                    "cancelled": False,
                    "builder": {
                        "worker_id": "worker-1", "role": "worker",
                        "functional_role": "builder", "environment_id": "wsl-development",
                        "target": "wsl",
                        "transport_binding": "codex-app-server",
                        "execution_mode_required": "workspace-write",
                        "prompt": secret_markers[1],
                    },
                    "reviewer": {
                        "worker_id": "reviewer-1", "role": "reviewer",
                        "functional_role": "independent_review", "environment_id": "wsl-review",
                        "target": "wsl",
                        "transport_binding": "codex-app-server",
                        "execution_mode_required": "read-only",
                        "provider_response": secret_markers[3],
                    },
                    "needs_tanner": {
                        "attention_id": "attention-" + "a" * 64,
                        "reason": "Protected action requested",
                        "decision_needed": "Approve Once or Deny",
                        "expires_at": "2026-09-07T12:00:00+00:00",
                        "source_body": secret_markers[0],
                    },
                    "recovery_references": [{
                        "reference_type": "campaign_record",
                        "reference_id": "campaign-record-1",
                        "record_sha256": "b" * 64,
                        "source_body": secret_markers[0],
                    }],
                    "activity": [{
                        "event_id": "event-1", "kind": "independent_review_retained",
                        "created_at": "2026-09-07T10:00:00+00:00",
                        "detail": {"iteration": 1, "prompt": secret_markers[1]},
                        "worker": {
                            "worker_id": "reviewer-1", "role": "reviewer",
                            "functional_role": "independent_review", "environment_id": "wsl-review",
                            "target": "wsl",
                            "transport_binding": "codex-app-server",
                            "execution_mode_required": "read-only",
                            "response_body": secret_markers[3],
                        },
                        "summary": {
                            "status": "accepted", "task_scope_id": "scope-1",
                            "return_report_id": "return-report-1",
                            "review_report_id": "review-report-1",
                            "verification_status": "verified",
                            "transport_result_reference": "transport-result-1",
                            "acceptance_condition_ids_satisfied": ["condition-1"],
                            "violated_acceptance_condition_ids": [],
                            "defects": [],
                            "validation_evidence": [{"source_body": secret_markers[0]}],
                            "failure": {"code": "none", "trace": secret_markers[3]},
                            "source_body": secret_markers[0],
                        },
                    }],
                    "source_body": secret_markers[0],
                    "raw_prompt": secret_markers[1],
                },
            }],
        }
        service.development_attention_projection.return_value = {
            "attention": [{
                "attention_id": "attention-" + "a" * 64,
                "campaign_id": "campaign-compact",
                "invocation_id": "invocation-1",
                "state": "needs_tanner",
                "blocked_action": "Run protected action",
                "why_required": "Tanner decision required",
                "expires_at": "2026-09-07T12:00:00+00:00",
                "consumer_state": "durably_resumable",
                "actionable": True,
                "detail_url": "https://localhost:8791/?view=developer&section=attention&attention=attention-" + "a" * 64,
                "notification_body": secret_markers[0],
                "provider_prompt": secret_markers[1],
            }],
            "source_body": secret_markers[0],
            "creates_authority": False,
        }
        service.production_component_status.return_value = {
            "components": {
                "app_server": {"state": "READY", "details": secret_markers[0]},
                "reviewer_launcher": {"state": "IDLE", "pid": 12345},
            },
            "latest_failure_receipts": [{
                "code": "provider_failure", "technical": secret_markers[2],
            }],
            "creates_authority": False,
        }
        repository = _repository_fixture()
        repository["secret"] = secret_markers[0]
        repository["files"][0]["source_body"] = secret_markers[0]
        repository["files"][0]["diff_excerpt"] = (
            "+authorization: Bearer " + secret_markers[0] + "\n+ordinary=true\n")
        service.development_console_repository_projection.return_value = repository

        with unittest.mock.patch("src.app.server.build_identity", return_value={
            "mode": "development_checkout",
            "release_id": "development-" + "c" * 64,
            "manifest_sha256": "d" * 64,
            "secret": secret_markers[0],
        }):
            handler.do_GET()

        handler._json.assert_called_once()
        status, projection = handler._json.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual(
            set(projection),
            {
                "schema_version", "observed_at", "build", "campaigns", "attention",
                "components", "repository", "roadmap", "jobs", "creates_authority",
                "creates_continuing_authority", "managed_activity_window",
                "current_campaign_id", "selection_basis",
            },
        )
        self.assertEqual(projection["schema_version"], "fawkes.dev_console.read_only.v1")
        self.assertIs(projection["creates_authority"], False)
        self.assertIs(projection["creates_continuing_authority"], False)
        observed = datetime.fromisoformat(projection["observed_at"])
        self.assertEqual(observed.utcoffset(), timezone.utc.utcoffset(observed))
        self.assertEqual(projection["build"], {
            "mode": "development_checkout",
            "release_id": "development-" + "c" * 64,
            "manifest_sha256": "d" * 64,
        })
        self.assertEqual(set(projection["campaigns"][0]), {
            "campaign_id", "objective", "status", "current_stage", "iteration", "maximum_iterations",
            "cancelled", "builder", "reviewer", "needs_tanner", "recovery_references",
            "activity", "satisfied_condition_count",
            "operational_learning_observations", "managed_worker_activity", "console_reporting",
            "created_at", "updated_at",
        })
        self.assertEqual(set(projection["campaigns"][0]["builder"]), {
            "worker_id", "role", "functional_role", "environment_id",
        })
        self.assertEqual(set(projection["campaigns"][0]["reviewer"]), {
            "worker_id", "role", "functional_role", "environment_id",
        })
        self.assertEqual(set(projection["campaigns"][0]["needs_tanner"]), {
            "attention_id", "reason", "decision_needed", "expires_at",
        })
        self.assertEqual(set(projection["campaigns"][0]["recovery_references"][0]), {
            "reference_type", "reference_id", "record_sha256",
        })
        event = projection["campaigns"][0]["activity"][0]
        self.assertEqual(set(event), {
            "event_id", "kind", "created_at", "iteration", "worker", "summary",
        })
        self.assertEqual(set(event["summary"]), {
            "status", "task_scope_id", "return_report_id", "review_report_id",
            "verification_status", "satisfied_condition_count", "violated_condition_count",
            "defect_count", "validation_evidence_count", "failure_code",
        })
        self.assertEqual(set(projection["attention"][0]), {
            "attention_id", "campaign_id", "invocation_id", "state", "blocked_action",
            "why_required", "expires_at", "consumer_state", "actionable", "detail_url",
        })
        self.assertEqual(projection["components"], [
            {"name": "app_server", "state": "READY"},
            {"name": "reviewer_launcher", "state": "unobserved_configured"},
        ])
        self.assertEqual(projection["repository"]["branch"], "fixture/console")
        self.assertEqual(projection["repository"]["files"][0]["path"], "src/app/server.py")
        self.assertNotIn(secret_markers[0],
                         projection["repository"]["files"][0]["diff_excerpt"])
        self.assertIn("<redacted-sensitive-line>",
                      projection["repository"]["files"][0]["diff_excerpt"])
        self.assertIn("ordinary=true", projection["repository"]["files"][0]["diff_excerpt"])
        self.assertFalse(projection["repository"]["creates_authority"])
        self.assertEqual([item["id"] for item in projection["roadmap"]["phases"]],
                         [f"phase-{number}" for number in range(40)])
        self.assertTrue(projection["roadmap"]["coverage_complete"])
        self.assertTrue(all(item["summary"] for item in projection["roadmap"]["phases"]))
        self.assertTrue(any(item["id"] == "track-dedicated-home"
                            for item in projection["roadmap"]["tracks"]))
        self.assertEqual(projection["roadmap"]["phases"][17]["prerequisites"], [])
        self.assertEqual(projection["roadmap"]["tracks"][0]["prerequisites"],
                         ["phase-0", "phase-1"])
        self.assertEqual(projection["jobs"][0]["objective"],
                         "Finish the authenticated console fixture")
        serialized = json.dumps(projection, sort_keys=True)
        for marker in secret_markers:
            self.assertNotIn(marker, serialized)
        for forbidden_key in (
            "source_body", "raw_prompt", "provider_prompt", "provider_response",
            "latest_failure_receipts", "technical", "trace", "notification_body", "pid",
        ):
            self.assertNotIn(f'"{forbidden_key}"', serialized)

    def test_malformed_compact_sources_fail_closed_without_partial_projection(self):
        for malformed_method, malformed_value in (
            ("list_codex_development_campaigns", {"campaigns": "not-a-list"}),
            ("development_attention_projection", {"attention": "not-a-list"}),
            ("production_component_status", {"components": "not-an-object"}),
            ("development_console_repository_projection", {"files": "not-an-array"}),
        ):
            with self.subTest(source=malformed_method):
                handler, service = self._handler("/api/development/dev-console", authorized=True)
                service.list_codex_development_campaigns.return_value = {"campaigns": []}
                service.development_attention_projection.return_value = {"attention": []}
                service.production_component_status.return_value = {"components": {}}
                service.development_console_repository_projection.return_value = _repository_fixture()
                getattr(service, malformed_method).return_value = malformed_value
                handler.do_GET()
                handler._json.assert_called_once_with(503, {
                    "error": {
                        "code": "dev_console_projection_unavailable",
                        "message": "The read-only developer-console projection is unavailable right now.",
                    },
                })

    def test_compact_projection_rejects_overlong_allowlisted_text(self):
        handler, service = self._handler("/api/development/dev-console", authorized=True)
        service.list_codex_development_campaigns.return_value = {
            "campaigns": [{
                "live_activity": {
                    "campaign_id": "campaign-" + "x" * 2_048,
                    "status": "running", "current_stage": "running",
                    "iteration": 0, "maximum_iterations": 1, "cancelled": False,
                    "builder": None, "reviewer": None, "needs_tanner": None,
                    "recovery_references": [], "activity": [],
                },
            }],
        }
        service.development_attention_projection.return_value = {"attention": []}
        service.production_component_status.return_value = {"components": {}}
        service.development_console_repository_projection.return_value = _repository_fixture()
        handler.do_GET()
        handler._json.assert_called_once_with(503, {
            "error": {
                "code": "dev_console_projection_unavailable",
                "message": "The read-only developer-console projection is unavailable right now.",
            },
        })

    def test_compact_projection_enforces_total_serialized_byte_bound(self):
        handler, service = self._handler("/api/development/dev-console", authorized=True)
        service.list_codex_development_campaigns.return_value = {"campaigns": []}
        service.development_attention_projection.return_value = {"attention": []}
        service.production_component_status.return_value = {"components": {}}
        service.development_console_repository_projection.return_value = _repository_fixture()
        with unittest.mock.patch("src.app.server.DEV_CONSOLE_MAX_RESPONSE_BYTES", 1):
            handler.do_GET()
        handler._json.assert_called_once_with(503, {
            "error": {
                "code": "dev_console_projection_unavailable",
                "message": "The read-only developer-console projection is unavailable right now.",
            },
        })

    def test_loading_console_static_content_invokes_no_canonical_operation(self):
        handler = _StaticHandler()
        FawkesAppHandler._serve_static(handler, "/dev-console/")
        self.assertEqual(handler.statuses, [200])
        self.assertEqual(handler.server.chat_service.mock_calls, [])

    def test_repository_projection_is_head_bound_bounded_and_not_a_filesystem_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            repository.mkdir()
            environment = {**os.environ,
                "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test",
                "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test",
            }
            subprocess.run(["git", "init", "-q", "-b", "fixture/console"], cwd=repository,
                check=True, env=environment)
            (repository / "src").mkdir()
            (repository / "src" / "console.py").write_text("before\n", encoding="utf-8")
            (repository / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "src/console.py", "README.md"], cwd=repository,
                check=True, env=environment)
            subprocess.run(["git", "commit", "-q", "-m", "Fixture projection"], cwd=repository,
                check=True, env=environment)
            (repository / "src" / "console.py").write_text("after\n", encoding="utf-8")
            (repository / "private-untracked.txt").write_text(
                "must not become a browseable file", encoding="utf-8")
            index_path = repository / ".git" / "index"
            index_before = (index_path.read_bytes(), index_path.stat().st_mtime_ns)

            projection = build_development_console_repository_projection(repository)

            self.assertEqual(
                (index_path.read_bytes(), index_path.stat().st_mtime_ns),
                index_before,
            )
            self.assertEqual(projection["branch"], "fixture/console")
            self.assertRegex(projection["head"], r"^[a-f0-9]{40,64}$")
            self.assertTrue(projection["comparison_base"] == "root" or re.fullmatch(
                r"[a-f0-9]{40,64}", projection["comparison_base"]))
            self.assertEqual(projection["selection_basis"], "head_commit_paths")
            self.assertEqual(projection["status_summary"]["dirty_paths"], 2)
            self.assertEqual(projection["status_summary"]["untracked_paths"], 1)
            paths = [item["path"] for item in projection["files"]]
            self.assertEqual(paths, ["README.md", "src/console.py"])
            self.assertNotIn("private-untracked.txt", json.dumps(projection))
            self.assertTrue(all(item["revision"] == projection["head"]
                for item in projection["files"]))
            self.assertTrue(all(len(item["diff_excerpt"].encode("utf-8")) <= 2_048
                for item in projection["files"]))
            self.assertFalse(projection["creates_authority"])
            self.assertFalse(projection["creates_continuing_authority"])

    def test_repository_projection_ignores_git_environment_redirection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = {**os.environ,
                "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test",
                "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test"}
            repositories = []
            for name, branch in (("intended", "fixture/intended"), ("redirect", "fixture/redirect")):
                repository = root / name
                repository.mkdir()
                subprocess.run(["git", "init", "-q", "-b", branch], cwd=repository,
                    check=True, env=environment)
                (repository / f"{name}.txt").write_text(name + "\n", encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=repository, check=True, env=environment)
                subprocess.run(["git", "commit", "-q", "-m", name], cwd=repository,
                    check=True, env=environment)
                repositories.append(repository)
            intended, redirect = repositories
            with patch.dict(os.environ, {
                    "GIT_DIR": str(redirect / ".git"),
                    "GIT_WORK_TREE": str(redirect),
                    "GIT_INDEX_FILE": str(redirect / ".git" / "index"),
                    "GIT_CONFIG_GLOBAL": str(root / "attacker-config"),
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "core.worktree",
                    "GIT_CONFIG_VALUE_0": str(redirect),
            }, clear=False):
                projection = build_development_console_repository_projection(intended)
            self.assertEqual(projection["branch"], "fixture/intended")
            self.assertEqual([item["path"] for item in projection["files"]], ["intended.txt"])
            self.assertNotIn("redirect", json.dumps(projection))

    def test_repository_projection_rejects_local_worktree_redirection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            redirect = root / "redirect"
            repository.mkdir()
            redirect.mkdir()
            environment = {**os.environ,
                "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test",
                "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test"}
            subprocess.run(["git", "init", "-q", "-b", "fixture/local-config"],
                cwd=repository, check=True, env=environment)
            (repository / "intended.txt").write_text("intended\n", encoding="utf-8")
            subprocess.run(["git", "add", "intended.txt"], cwd=repository,
                check=True, env=environment)
            subprocess.run(["git", "commit", "-q", "-m", "intended"],
                cwd=repository, check=True, env=environment)
            (redirect / "redirect.txt").write_text("redirect\n", encoding="utf-8")
            subprocess.run(["git", "config", "core.worktree", str(redirect)],
                cwd=repository, check=True, env=environment)

            with self.assertRaisesRegex(ChatServiceError, "bounded repository projection"):
                build_development_console_repository_projection(repository)

    def test_repository_projection_rejects_local_clean_filters_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            environment = {**os.environ,
                "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test",
                "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test"}
            subprocess.run(["git", "init", "-q", "-b", "fixture/filter"],
                cwd=repository, check=True, env=environment)
            path = repository / "tracked.txt"
            path.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repository,
                check=True, env=environment)
            subprocess.run(["git", "commit", "-q", "-m", "before"],
                cwd=repository, check=True, env=environment)
            sentinel = root / "filter-ran"
            helper = root / "filter.py"
            helper.write_text(
                "#!/usr/bin/env python3\nimport pathlib, sys\n"
                f"pathlib.Path({str(sentinel)!r}).write_text('ran')\n"
                "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
                encoding="utf-8",
            )
            helper.chmod(0o700)
            (repository / ".gitattributes").write_text(
                "*.txt filter=consolefixture\n", encoding="utf-8")
            subprocess.run(["git", "config", "filter.consolefixture.clean", str(helper)],
                cwd=repository, check=True, env=environment)
            path.write_text("after\n", encoding="utf-8")

            with self.assertRaisesRegex(ChatServiceError, "bounded repository projection"):
                build_development_console_repository_projection(repository)
            self.assertFalse(sentinel.exists())

            subprocess.run(["git", "config", "--remove-section", "filter.consolefixture"],
                cwd=repository, check=True, env=environment)
            with self.assertRaisesRegex(ChatServiceError, "bounded repository projection"):
                build_development_console_repository_projection(repository)
            self.assertFalse(sentinel.exists())

    def test_repository_projection_bounds_git_output_before_returning_it(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            repository.mkdir()
            environment = {**os.environ,
                "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test",
                "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test"}
            subprocess.run(["git", "init", "-q", "-b", "fixture/bounded"], cwd=repository,
                check=True, env=environment)
            (repository / "large.txt").write_text("x" * 50_000 + "\n", encoding="utf-8")
            subprocess.run(["git", "add", "large.txt"], cwd=repository, check=True, env=environment)
            subprocess.run(["git", "commit", "-q", "-m", "large"], cwd=repository,
                check=True, env=environment)
            with patch("src.runtime.chat_service.DEVELOPMENT_CONSOLE_GIT_MAX_STDOUT_BYTES", 4_096):
                with self.assertRaisesRegex(ChatServiceError, "bounded repository projection"):
                    build_development_console_repository_projection(repository)

    def test_repository_projection_redacts_committed_secret_diff_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            repository.mkdir()
            environment = {**os.environ,
                "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test",
                "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test"}
            subprocess.run(["git", "init", "-q", "-b", "fixture/redaction"], cwd=repository,
                check=True, env=environment)
            path = repository / "settings.txt"
            path.write_text("safe=true\n", encoding="utf-8")
            subprocess.run(["git", "add", "settings.txt"], cwd=repository,
                check=True, env=environment)
            subprocess.run(["git", "commit", "-q", "-m", "safe"], cwd=repository,
                check=True, env=environment)
            secret = "sk-" + "A" * 32
            private_begin = "-----BEGIN " + "PRIVATE KEY-----"
            private_end = "-----END " + "PRIVATE KEY-----"
            path.write_text(
                f"api_key={secret}\n{private_begin}\nprivate-body\n"
                f"{private_end}\nordinary=true\n", encoding="utf-8")
            subprocess.run(["git", "add", "settings.txt"], cwd=repository,
                check=True, env=environment)
            subprocess.run(["git", "commit", "-q", "-m", "sensitive fixture"], cwd=repository,
                check=True, env=environment)
            projection = build_development_console_repository_projection(repository)
            excerpt = projection["files"][0]["diff_excerpt"]
            self.assertNotIn(secret, excerpt)
            self.assertNotIn("private-body", excerpt)
            self.assertIn("<redacted-sensitive-line>", excerpt)
            self.assertIn("ordinary=true", excerpt)


class DevConsoleDOMContractTests(unittest.TestCase):
    def test_deterministic_node_projection_and_navigation_fixture(self):
        completed = subprocess.run(
            ["node", str(NODE_HARNESS)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "dev-console-projection-ok")


class ConsoleUpdateStoreTests(unittest.TestCase):
    def _projection(self):
        return {
            "observed_at": "2026-09-10T01:00:00+00:00",
            "build": {"mode": "development_checkout", "release_id": "development-fixture"},
            "jobs": [{"job_id": "campaign-one", "objective": "Finish the Pi console",
                "state": "working", "current_step": "Independent review",
                "last_activity_at": "2026-09-10T00:59:00+00:00",
                "successful": False, "historical": False,
                "worker": {"worker_id": "managed-worker"}}],
            "attention": [],
            "repository": {"branch": "fixture/console", "head": "1" * 40,
                "status_summary": {"dirty_paths": 2}},
            "creates_authority": False,
            "creates_continuing_authority": False,
        }

    def test_immutable_idempotent_snapshot_round_trip_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConsoleUpdateStore(Path(directory) / "updates")
            first = store.save(idempotency_key="browser-fixture-key-0001",
                               projection=self._projection())
            retry = store.save(idempotency_key="browser-fixture-key-0001",
                               projection={**self._projection(), "jobs": []})
            self.assertEqual(retry, first)
            self.assertIn("Finish the Pi console", first["content"])
            self.assertIn("WORKING", first["content"])
            self.assertEqual(store.get(first["snapshot_id"]), first)
            self.assertEqual(store.list()["updates"][0]["snapshot_id"], first["snapshot_id"])
            self.assertEqual((store.root.stat().st_mode & 0o777), 0o700)
            record = store.root / "records" / f"{first['snapshot_id']}.json"
            self.assertEqual((record.stat().st_mode & 0o777), 0o600)

    def test_interrupted_mapping_write_recovers_same_snapshot_and_heals_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "updates"
            store = ConsoleUpdateStore(root)
            original = ConsoleUpdateStore._write_atomic

            def interrupt_mapping(path, body):
                if path.parent.name == "idempotency" and path.suffix == ".txt":
                    raise RuntimeError("synthetic interruption before mapping publication")
                return original(path, body)

            with patch.object(ConsoleUpdateStore, "_write_atomic",
                              side_effect=interrupt_mapping):
                with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                    store.save(idempotency_key="browser-fixture-crash-key-0001",
                               projection=self._projection())
            retained = list((root / "records").glob("console-update-*.json"))
            self.assertEqual(len(retained), 1)
            recovered = ConsoleUpdateStore(root).save(
                idempotency_key="browser-fixture-crash-key-0001",
                projection={**self._projection(), "jobs": []})
            self.assertEqual(recovered["snapshot_id"], retained[0].stem)
            self.assertIn("Finish the Pi console", recovered["content"])
            self.assertEqual(len(list((root / "records").glob("console-update-*.json"))), 1)
            self.assertTrue(list((root / "idempotency").glob("*.txt")))

    def test_two_processes_publish_one_idempotent_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "updates"
            script = (
                "import json,sys; from pathlib import Path; "
                "from src.app.server import ConsoleUpdateStore; "
                "value=ConsoleUpdateStore(Path(sys.argv[1])).save("
                "idempotency_key=sys.argv[2],projection=json.loads(sys.argv[3])); "
                "print(value['snapshot_id'])"
            )
            projection = json.dumps(self._projection(), sort_keys=True)
            command = [sys.executable, "-c", script, str(root),
                       "browser-fixture-process-key-0001", projection]
            processes = [subprocess.Popen(command, cwd=ROOT, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
            results = [process.communicate(timeout=20) for process in processes]
            self.assertEqual([process.returncode for process in processes], [0, 0], results)
            snapshot_ids = [stdout.strip() for stdout, _ in results]
            self.assertEqual(snapshot_ids[0], snapshot_ids[1])
            self.assertEqual(len(list((root / "records").glob("console-update-*.json"))), 1)
            self.assertEqual(len(list((root / "idempotency").glob("*.txt"))), 1)

    def test_atomic_publication_fsyncs_record_and_mapping_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConsoleUpdateStore(Path(directory) / "updates")
            original = ConsoleUpdateStore._fsync_directory
            observed = []

            def record_directory(path):
                observed.append(Path(path).name)
                return original(path)

            with patch.object(ConsoleUpdateStore, "_fsync_directory",
                              side_effect=record_directory):
                store.save(idempotency_key="browser-fixture-fsync-key-0001",
                           projection=self._projection())
            self.assertIn("records", observed)
            self.assertIn("idempotency", observed)

    def test_invalid_key_missing_id_and_tampered_content_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConsoleUpdateStore(Path(directory) / "updates")
            with self.assertRaises(ValueError):
                store.save(idempotency_key="short", projection=self._projection())
            with self.assertRaises(KeyError):
                store.get("../neighbor")
            record = store.save(idempotency_key="browser-fixture-key-0002",
                                projection=self._projection())
            path = store.root / "records" / f"{record['snapshot_id']}.json"
            body = json.loads(path.read_text(encoding="utf-8"))
            body["content"] += "tampered"
            path.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.get(record["snapshot_id"])

    def test_post_requires_auth_csrf_and_server_generated_content(self):
        handler = object.__new__(FawkesAppHandler)
        handler.path = "/api/development/console-updates"
        handler._require_auth = Mock(return_value=True)
        handler._require_attention_decision_auth = Mock(return_value=True)
        handler._read_json = Mock(return_value={"idempotency_key": "browser-fixture-key-0003"})
        handler._json = Mock()
        store = Mock()
        store.save.return_value = {"snapshot_id": "console-update-" + "a" * 64,
                                   "content": "exact"}
        handler.server = SimpleNamespace(chat_service=Mock(), console_update_store=store)
        with patch("src.app.server.developer_console_projection",
                   return_value=self._projection()) as projection:
            handler.do_POST()
        handler._require_auth.assert_called_once_with(record_rider_activity=False)
        handler._require_attention_decision_auth.assert_called_once_with()
        projection.assert_called_once_with(handler.server.chat_service)
        store.save.assert_called_once_with(idempotency_key="browser-fixture-key-0003",
                                           projection=self._projection(), campaign_id=None)
        self.assertEqual(handler._json.call_args.args[0], 201)


if __name__ == "__main__":
    unittest.main()

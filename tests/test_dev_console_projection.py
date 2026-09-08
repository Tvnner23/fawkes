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
import tempfile
import threading
from types import SimpleNamespace
import urllib.request
import unittest
from unittest.mock import Mock, patch

from src.app.server import BrowserSessionStore, FawkesAppHandler, FawkesAppServer
from src.runtime.chat_service import FawkesChatService
from src.runtime.development_attention import DevelopmentAttentionStore


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "src" / "app" / "static" / "dev-console"
HTML_PATH = STATIC_ROOT / "index.html"
CSS_PATH = STATIC_ROOT / "console.css"
JAVASCRIPT_PATH = STATIC_ROOT / "console.js"
NODE_HARNESS = ROOT / "tests" / "js" / "dev_console_projection_harness.js"


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

    def test_console_has_four_bounded_pages_and_defaults_to_summary(self):
        self.assertIn('id="dev-console" data-idle-seconds="60"', self.html)
        pages = re.findall(r'class="console-page" data-page="(\d)"([^>]*)', self.html)
        self.assertEqual([value for value, _ in pages], ["0", "1", "2", "3"])
        self.assertNotIn("hidden", pages[0][1])
        self.assertTrue(all("hidden" in attributes for _, attributes in pages[1:]))
        for heading in (
            "Activity Summary",
            "Campaign Status",
            "Repository View",
            "Architecture View",
        ):
            self.assertIn(heading, self.html)

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

    def test_markup_and_script_have_no_inline_or_duplicate_decision_controls(self):
        self.assertNotRegex(self.html, r"\son[a-z]+\s*=")
        combined = self.html + "\n" + self.javascript
        for forbidden in (
            "approve_once",
            "Approve Once",
            "/decision",
            "X-Fawkes-CSRF-Token",
            "Authorization",
            "localStorage",
            "sessionStorage",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertNotRegex(self.javascript, r"\bfetch\s*\([^)]*,\s*\{[^}]*method\s*:")
        self.assertNotIn("innerHTML", self.javascript)
        self.assertIn("textContent", self.javascript)

    def test_script_uses_only_compact_authenticated_read_only_projection(self):
        expected = {"/api/development/dev-console"}
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
        handler.do_GET()
        handler._require_auth.assert_called_once_with(record_rider_activity=False)
        service.list_codex_development_campaigns.assert_called_once_with()
        service.development_attention_projection.assert_called_once_with(pending_only=True)
        service.production_component_status.assert_called_once_with()
        self.assertEqual(
            [call[0] for call in service.mock_calls],
            [
                "list_codex_development_campaigns",
                "development_attention_projection",
                "production_component_status",
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
                "objective": secret_markers[1],
                "live_activity": {
                    "campaign_id": "campaign-compact",
                    "objective": secret_markers[0],
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
                "components", "creates_authority", "creates_continuing_authority",
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
            "campaign_id", "status", "current_stage", "iteration", "maximum_iterations",
            "cancelled", "builder", "reviewer", "needs_tanner", "recovery_references",
            "activity",
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
        serialized = json.dumps(projection, sort_keys=True)
        for marker in secret_markers:
            self.assertNotIn(marker, serialized)
        for forbidden_key in (
            "objective", "source_body", "raw_prompt", "provider_prompt", "provider_response",
            "latest_failure_receipts", "technical", "trace", "notification_body", "pid",
        ):
            self.assertNotIn(f'"{forbidden_key}"', serialized)

    def test_malformed_compact_sources_fail_closed_without_partial_projection(self):
        for malformed_method, malformed_value in (
            ("list_codex_development_campaigns", {"campaigns": "not-a-list"}),
            ("development_attention_projection", {"attention": "not-a-list"}),
            ("production_component_status", {"components": "not-an-object"}),
        ):
            with self.subTest(source=malformed_method):
                handler, service = self._handler("/api/development/dev-console", authorized=True)
                service.list_codex_development_campaigns.return_value = {"campaigns": []}
                service.development_attention_projection.return_value = {"attention": []}
                service.production_component_status.return_value = {"components": {}}
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


if __name__ == "__main__":
    unittest.main()

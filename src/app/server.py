"""Dependency-free authenticated HTTP home for Fawkes Chat."""

import argparse
import hmac
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from src.runtime.chat_service import ChatServiceError, FawkesChatService
from src.runtime.autonomy_supervision import RiderActivityStore


STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 22 * 1024 * 1024


def default_bind_host(*, app_token, configured_host=None):
    """Expose the app only when authentication has been configured."""
    return configured_host or ("0.0.0.0" if app_token else "127.0.0.1")


def bind_requires_token(host):
    return host not in {"127.0.0.1", "localhost", "::1"}


class FawkesAppHandler(BaseHTTPRequestHandler):
    server_version = "FawkesApp/1"

    def log_message(self, format, *args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        expected = self.server.app_token
        if not expected:
            return True
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        return supplied.startswith(prefix) and hmac.compare_digest(
            supplied[len(prefix):], expected
        )

    def _require_auth(self):
        if self._authorized():
            instance_id = getattr(self.server.chat_service, "instance_id", None)
            if instance_id:
                RiderActivityStore(
                    instance_id,
                    root=Path(__file__).resolve().parents[2] / "database" / "rider_activity",
                ).touch(authenticated_rider=True)
            return True
        self._json(401, {"error": {"code": "unauthorized", "message": "Access token required."}})
        return False

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ChatServiceError("Invalid request.", code="invalid_request") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ChatServiceError("Invalid request size.", code="invalid_request")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ChatServiceError("Invalid request.", code="invalid_request") from exc
        if not isinstance(value, dict):
            raise ChatServiceError("Invalid request.", code="invalid_request")
        return value

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/chat":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.history())
            except ChatServiceError as exc:
                self._json(400, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "chat_unavailable", "message": "Fawkes is unavailable right now."}})
            return
        inspector_prefix = "/api/chat/messages/"
        inspector_suffix = "/context-inspector"
        if path.startswith(inspector_prefix) and path.endswith(inspector_suffix):
            if not self._require_auth():
                return
            message_id = path[len(inspector_prefix):-len(inspector_suffix)].strip("/")
            try:
                self._json(200, self.server.chat_service.context_inspector(message_id))
            except ChatServiceError as exc:
                status = 404 if exc.code == "context_inspection_not_found" else 409 if exc.code == "context_inspection_invalid" else 400
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "context_inspection_unavailable", "message": "Context inspection is unavailable right now."}})
            return
        if path == "/api/capabilities":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.capabilities())
            except Exception:
                self._json(503, {"error": {"code": "capabilities_unavailable", "message": "Capability discovery is unavailable right now."}})
            return
        if path == "/api/preferences/sounds":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.sound_settings())
            except Exception:
                self._json(503, {"error": {"code": "sound_preferences_unavailable", "message": "Sound settings are unavailable right now."}})
            return
        if path == "/api/presence":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.presence_profile())
            except Exception:
                self._json(503, {"error": {"code": "presence_unavailable", "message": "Phoenix Presence is unavailable right now; Chat remains available."}})
            return
        if path == "/api/library":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.library_catalog())
            except Exception: self._json(503, {"error": {"code": "library_unavailable", "message": "Library is unavailable right now."}})
            return
        history_evidence_prefix = "/api/history/evidence/"
        if path.startswith(history_evidence_prefix):
            if not self._require_auth(): return
            parts = path[len(history_evidence_prefix):].strip("/").split("/", 1)
            if len(parts) != 2:
                self._json(400, {"error": {"code": "invalid_history_evidence", "message": "History evidence domain and identity are required."}}); return
            try: self._json(200, self.server.chat_service.historical_evidence(unquote(parts[0]), unquote(parts[1])))
            except ChatServiceError as exc:
                self._json(404 if exc.code == "history_evidence_not_found" else 400,
                           {"error": {"code": exc.code, "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "history_unavailable", "message": "Historical evidence is unavailable right now."}})
            return
        if path == "/api/development/observations":
            if not self._require_auth():
                return
            query = parse_qs(parsed.query)
            try:
                self._json(200, {"observations": self.server.chat_service.list_observations(
                    category=query.get("category", [None])[0],
                    status=query.get("status", [None])[0],
                )})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path == "/api/development/dashboard":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.development_dashboard())
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development information is unavailable right now."}})
            return
        if path == "/api/development/codex-campaigns":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.list_codex_development_campaigns())
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Campaign activity is unavailable right now."}})
            return
        campaign_prefix = "/api/development/codex-campaigns/"
        if path.startswith(campaign_prefix) and path.count("/") == 4:
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):])
            try:
                self._json(200, self.server.chat_service.codex_development_campaign(campaign_id))
            except KeyError:
                self._json(404, {"error": {"code": "campaign_not_found", "message": "Development campaign not found."}})
            except (ValueError, PermissionError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development campaign status is unavailable right now."}})
            return
        if path.startswith(campaign_prefix) and path.endswith("/evidence"):
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):-len("/evidence")].strip("/"))
            try:
                self._json(200, self.server.chat_service.codex_development_campaign_evidence(campaign_id))
            except KeyError:
                self._json(404, {"error": {"code": "campaign_not_found", "message": "Development campaign not found."}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_evidence_unavailable", "message": "Exact campaign evidence is unavailable right now."}})
            return
        if path == "/api/development/runtime-status":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.production_component_status())
            except Exception:
                self._json(503, {"error": {"code": "runtime_status_unavailable", "message": "Fawkes component status is unavailable right now."}})
            return
        if path == "/api/development/attention":
            if not self._require_auth():
                return
            try:
                query = parse_qs(parsed.query)
                self._json(200, self.server.chat_service.development_attention(
                    pending_only=query.get("pending", ["false"])[0].lower() == "true"))
            except Exception:
                self._json(503, {"error": {"code": "attention_unavailable", "message": "Development attention state is unavailable right now."}})
            return
        if path == "/api/development/test-center":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.acceptance_center().snapshot())
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        prefix = "/api/development/observations/"
        if path.startswith(prefix) and path.count("/") == 4:
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.inspect_observation(path[len(prefix):]))
            except ChatServiceError as exc:
                self._json(404, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        observation_prefix = "/api/development/observations/"
        proposal_prefix = "/api/development/proposals/"
        test_prefix = "/api/development/test-center/tests/"
        run_prefix = "/api/development/test-center/runs/"
        feedback_prefix = "/api/chat/messages/"
        feedback_suffix = "/context-feedback"
        if path == "/api/development/codex-handoffs":
            if not self._require_auth():
                return
            try:
                self._json(201, self.server.chat_service.codex_development_handoff(
                    self._read_json(), authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "codex_handoff_denied", "message": str(exc)}})
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_codex_handoff", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "codex_handoff_unavailable",
                    "message": "The Codex Development handoff is unavailable right now."}})
            return
        if path == "/api/development/runtime-control":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.control_production_component(
                    self._read_json(), authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "runtime_control_denied", "message": str(exc)}})
            except (ValueError, RuntimeError) as exc:
                self._json(400, {"error": {"code": "runtime_control_failed", "message": str(exc)}})
            return
        if path == "/api/development/codex-campaigns":
            if not self._require_auth():
                return
            try:
                self._json(201, self.server.chat_service.create_codex_development_campaign(
                    self._read_json(), authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "campaign_denied", "message": str(exc)}})
            except (ValueError, RuntimeError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_unavailable",
                    "message": "The bounded Codex Development campaign is unavailable right now."}})
            return
        campaign_prefix = "/api/development/codex-campaigns/"
        if path.startswith(campaign_prefix) and path.endswith("/cancel"):
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):-len("/cancel")].strip("/"))
            try:
                self._read_json()
                self._json(200, self.server.chat_service.cancel_codex_development_campaign(
                    campaign_id, authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "campaign_cancel_denied", "message": str(exc)}})
            except (KeyError, ValueError, RuntimeError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign_cancel", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_unavailable",
                    "message": "The bounded Codex Development campaign is unavailable right now."}})
            return
        if path.startswith(campaign_prefix) and path.endswith("/review"):
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):-len("/review")].strip("/"))
            try:
                self._read_json()
                self._json(200, self.server.chat_service.review_codex_development_campaign(
                    campaign_id, authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "campaign_review_denied", "message": str(exc)}})
            except (KeyError, ValueError, RuntimeError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign_review", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_review_unavailable",
                    "message": "The formal campaign review is unavailable right now."}})
            return
        if path.startswith(campaign_prefix) and "/attention/" in path and path.endswith("/decision"):
            if not self._require_auth():
                return
            remainder = path[len(campaign_prefix):-len("/decision")].strip("/")
            campaign_id, marker, attention_id = remainder.partition("/attention/")
            if not marker:
                self._json(400, {"error": {"code": "invalid_attention_decision", "message": "Attention identity is required."}}); return
            try:
                payload = self._read_json()
                self._json(200, self.server.chat_service.decide_development_attention(
                    unquote(campaign_id), unquote(attention_id), payload.get("choice"),
                    authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "attention_decision_denied", "message": str(exc)}})
            except (KeyError, ValueError, RuntimeError) as exc:
                self._json(400, {"error": {"code": "invalid_attention_decision", "message": str(exc)}})
            return
        if path.startswith(feedback_prefix) and path.endswith(feedback_suffix):
            if not self._require_auth():
                return
            message_id = path[len(feedback_prefix):-len(feedback_suffix)].strip("/")
            try:
                self._json(201, {"feedback": self.server.chat_service.context_feedback(
                    message_id, self._read_json())})
            except ChatServiceError as exc:
                status = 404 if exc.code == "context_inspection_not_found" else 409 if exc.code == "context_inspection_invalid" else 400
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "context_feedback_unavailable",
                    "message": "Context feedback could not be recorded right now."}})
            return
        if path == "/api/preferences/presence":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.update_presence_preferences(self._read_json()))
            except (ValueError, ChatServiceError) as exc: self._json(400, {"error": {"code": "invalid_presence_preferences", "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "presence_unavailable", "message": "Phoenix Presence settings are unavailable right now."}})
            return
        if path == "/api/preferences/sounds":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.update_sound_settings(self._read_json()))
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_sound_preferences", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "sound_preferences_unavailable", "message": "Sound settings are unavailable right now."}})
            return
        if path == "/api/library/search":
            if not self._require_auth(): return
            try:
                payload = self._read_json(); self._json(200, self.server.chat_service.library_search(payload.get("query")))
            except (ValueError, ChatServiceError) as exc: self._json(400, {"error": {"code": "invalid_library_query", "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "library_unavailable", "message": "Library search is unavailable right now."}})
            return
        if path == "/api/history/search":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.historical_search(self._read_json()))
            except ChatServiceError as exc: self._json(400, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "history_unavailable", "message": "Historical search is unavailable right now."}})
            return
        if path == "/api/history/validate":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.historical_corpus_validation(self._read_json()))
            except ChatServiceError as exc: self._json(400, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "history_validation_unavailable", "message": "Historical corpus validation is unavailable right now."}})
            return
        library_extract_prefix = "/api/library/sources/"
        if path.startswith(library_extract_prefix) and path.endswith("/extract"):
            if not self._require_auth(): return
            source_id = unquote(path[len(library_extract_prefix):-len("/extract")].strip("/"))
            try:
                self._read_json()
                self._json(200, self.server.chat_service.library_extract(source_id))
            except ChatServiceError as exc:
                status = 404 if exc.code == "library_source_not_found" else 400
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "library_extraction_unavailable", "message": "Library extraction is unavailable right now."}})
            return
        if path == "/api/development/test-center/run-all":
            if not self._require_auth():
                return
            try:
                payload = self._read_json()
                self._json(202, self.server.chat_service.acceptance_center().start_all(platform=payload.get("platform")))
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_acceptance_request", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        if path.startswith(test_prefix) and path.endswith("/run"):
            if not self._require_auth():
                return
            test_id = path[len(test_prefix):-len("/run")].strip("/")
            try:
                payload = self._read_json()
                self._json(202, self.server.chat_service.acceptance_center().start(test_id, platform=payload.get("platform")))
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_acceptance_request", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        if path.startswith(run_prefix) and path.endswith("/complete"):
            if not self._require_auth():
                return
            run_id = path[len(run_prefix):-len("/complete")].strip("/")
            try:
                payload = self._read_json()
                result = self.server.chat_service.acceptance_center().complete(
                    run_id, result=payload.get("result"), actual=payload.get("actual", ""),
                    duration_ms=payload.get("duration_ms", 0), failure_stage=payload.get("failure_stage"),
                    technical=payload.get("technical_details"), source="client",
                )
                self._json(200, result)
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_acceptance_result", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        if path.startswith(proposal_prefix) and path.endswith("/review"):
            if not self._require_auth():
                return
            proposal_id = path[len(proposal_prefix):-len("/review")].strip("/")
            try:
                self._json(200, {"proposal": self.server.chat_service.review_development_proposal(proposal_id, self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_review", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development review is unavailable right now."}})
            return
        if path == "/api/research":
            if not self._require_auth():
                return
            try:
                self._json(201, self.server.chat_service.research(self._read_json()))
            except ChatServiceError as exc:
                status = 400 if exc.code.startswith("invalid_") else 503
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "research_unavailable", "message": "Web research is unavailable right now."}})
            return
        if path == "/api/development/observations":
            if not self._require_auth():
                return
            try:
                self._json(201, {"observation": self.server.chat_service.create_observation(self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_observation", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path.startswith(observation_prefix) and path.endswith("/evidence"):
            if not self._require_auth():
                return
            observation_id = path[len(observation_prefix):-len("/evidence")].strip("/")
            try:
                self._json(200, {"observation": self.server.chat_service.add_observation_evidence(observation_id, self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_observation_evidence", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path.startswith(observation_prefix) and path.endswith("/revisions"):
            if not self._require_auth():
                return
            observation_id = path[len(observation_prefix):-len("/revisions")].strip("/")
            try:
                self._json(200, {"observation": self.server.chat_service.revise_observation(observation_id, self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_observation_revision", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path != "/api/chat/messages":
            self._json(404, {"error": {"code": "not_found", "message": "Not found."}})
            return
        if not self._require_auth():
            return
        try:
            payload = self._read_json()
            result = self.server.chat_service.send(
                payload.get("message"),
                conversation_id=payload.get("conversation_id"),
                attachments=payload.get("attachments"),
                retrieval_clarification=payload.get("retrieval_clarification"),
            )
            self._json(201, result)
        except ChatServiceError as exc:
            status = 400 if exc.code.startswith("invalid_") else 503
            self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
        except Exception:
            self._json(503, {"error": {"code": "chat_unavailable", "message": "Fawkes is unavailable right now."}})

    def _serve_static(self, path):
        names = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/presence-contract.js": ("presence-contract.js", "text/javascript; charset=utf-8"),
            "/presence-controller.js": ("presence-controller.js", "text/javascript; charset=utf-8"),
            "/presence-renderer-three.js": ("presence-renderer-three.js", "text/javascript; charset=utf-8"),
            "/presence-fallback.js": ("presence-fallback.js", "text/javascript; charset=utf-8"),
            "/presence-bootstrap.js": ("presence-bootstrap.js", "text/javascript; charset=utf-8"),
            "/presence-three.bundle.js": ("presence-three.bundle.js", "text/javascript; charset=utf-8"),
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
        }
        if path.startswith("/assets/presence/"):
            filename = path.removeprefix("/assets/presence/")
            try:
                target = self.server.chat_service.presence_asset_path(filename)
                if target is not None:
                    body = target.read_bytes(); self.send_response(200)
                    self.send_header("Content-Type", "model/gltf-binary")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers(); self.wfile.write(body); return
            except Exception:
                pass
            self._json(404, {"error": {"code": "presence_asset_unavailable", "message": "That Phoenix embodiment asset is not installed."}}); return
        if path.startswith("/assets/sounds/"):
            filename = path.removeprefix("/assets/sounds/")
            from src.capabilities.event_audio import SOUND_EVENTS, ASSET_ROOT
            allowed = {item.asset_filename for item in SOUND_EVENTS if item.asset_filename}
            if filename in allowed and (ASSET_ROOT / filename).is_file():
                body = (ASSET_ROOT / filename).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers(); self.wfile.write(body); return
            self._json(404, {"error": {"code": "sound_asset_unavailable", "message": "That approved sound asset is not installed."}}); return
        item = names.get(path)
        if item is None:
            self._json(404, {"error": {"code": "not_found", "message": "Not found."}})
            return
        body = (STATIC_DIR / item[0]).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", item[1])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:")
        self.end_headers()
        self.wfile.write(body)


class FawkesAppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, *, chat_service, app_token):
        super().__init__(address, FawkesAppHandler)
        self.chat_service = chat_service
        self.app_token = app_token


def main():
    parser = argparse.ArgumentParser(description="Serve the Fawkes mobile Chat app")
    token = os.getenv("FAWKES_APP_TOKEN", "")
    default_host = default_bind_host(
        app_token=token,
        configured_host=os.getenv("FAWKES_APP_HOST"),
    )
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=int(os.getenv("FAWKES_APP_PORT", "8787")))
    args = parser.parse_args()
    if bind_requires_token(args.host) and not token:
        parser.error("FAWKES_APP_TOKEN is required when binding beyond this computer")
    service = FawkesChatService()
    server = FawkesAppServer((args.host, args.port), chat_service=service, app_token=token)
    if args.host in {"127.0.0.1", "localhost", "::1"}:
        print(f"Fawkes Chat is local-only at http://127.0.0.1:{args.port}")
        print("Set FAWKES_APP_TOKEN and bind --host 0.0.0.0 for phone access.")
    else:
        print(f"Fawkes Chat is listening on all interfaces at port {args.port}.")
        addresses = set()
        try:
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                address = item[4][0]
                if not address.startswith("127."):
                    addresses.add(address)
        except OSError:
            pass
        for address in sorted(addresses):
            print(f"Candidate phone URL: http://{address}:{args.port}")
        print("A WSL/container address may require host forwarding and a firewall rule.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

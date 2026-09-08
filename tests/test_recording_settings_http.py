"""Authenticated real-loopback recording preferences; synthetic store only."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from src.app.server import BrowserSessionStore, FawkesAppServer
from src.runtime.personal_recording import RecordingPolicyDurabilityError, RecordingPolicyStore


class PolicyService:
    instance_id = "recording-http-fixture"

    def __init__(self, root):
        self.store = RecordingPolicyStore(self.instance_id, root=root)
        self.updates = 0
        self.sent = []

    def get_recording_policy(self):
        return self.store.load().public()

    def update_recording_policy(self, changes, *, expected_revision):
        self.updates += 1
        return self.store.update(changes, expected_revision=expected_revision).public()

    def send(self, message, **options):
        self.sent.append(options)
        return {"recording": self.store.latch(mode=options.get("recording_mode")).public()}


class RecordingSettingsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fawkes-recording-http-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "FAWKES_RUNTIME_STATE_ROOT": str(self.root),
            "FAWKES_DEVELOPMENT_ROOT": str(self.root),
            "FAWKES_CONSOLE_UPDATE_ROOT": str(self.root / "console-updates"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = PolicyService(self.root)
        self.sessions = BrowserSessionStore(self.root / "sessions")
        self.server = FawkesAppServer(("127.0.0.1", 0), chat_service=self.service,
            app_token="recording-fixture-token", app_session_store=self.sessions)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.cookie, self.csrf = self.sessions.create_bound()

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, *, path="/api/preferences/recording", payload=None,
                authenticated=True, csrf=True, bearer=False, origin=None):
        headers = {}
        if authenticated:
            headers["Authorization" if bearer else "Cookie"] = (
                "Bearer recording-fixture-token" if bearer else "fawkes_app_session=" + self.cookie)
        if csrf:
            headers["X-Fawkes-CSRF-Token"] = self.csrf
        if origin:
            headers["Origin"] = origin
        body = None if payload is None else json.dumps(payload).encode()
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.origin + path, data=body, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response), response.headers

    def update(self, changes, revision=0, **options):
        return self.request(payload={"changes": changes, "expected_revision": revision}, **options)

    def test_read_and_write_require_authentication_and_bound_csrf(self):
        self.assertEqual(self.request(authenticated=False)[0], 401)
        self.assertEqual(self.update({"mode": "private"}, authenticated=False)[0], 401)
        status, value, headers = self.request(bearer=True)
        self.assertEqual((status, value["revision"], headers["Cache-Control"]), (200, 0, "no-store"))
        self.assertEqual(self.update({"mode": "private"}, csrf=False)[0], 403)
        self.assertEqual(self.update({"mode": "private"}, bearer=True)[0], 403)
        self.assertEqual(self.update({"mode": "private"}, origin="https://foreign.invalid")[0], 403)
        self.assertEqual(self.service.updates, 0)
        self.assertEqual(self.update({"mode": "private"}, origin=self.origin)[0], 200)
        self.assertEqual(self.service.store.load().mode, "private")

    def test_exact_revision_conflict_preserves_actual_policy(self):
        self.assertEqual(self.update({"mode": "private"})[0], 200)
        status, value, _ = self.update({"mode": "retained"})
        self.assertEqual(status, 409)
        self.assertEqual(value["error"]["code"], "recording_policy_conflict")
        status, actual, _ = self.request()
        self.assertEqual((actual["revision"], actual["mode"]), (1, "private"))

    def test_invalid_fields_and_unavailable_sensor_do_not_reach_writer(self):
        for changes, revision in [
            ({"mode": "automatic"}, 0), ({"mode": "private"}, True),
            ({"categories": {"sensor_retention": True}}, 0),
            ({"categories": {"memory_learning": "false"}}, 0),
            ({"unexpected": True}, 0),
        ]:
            with self.subTest(changes=changes, revision=revision):
                self.assertEqual(self.update(changes, revision)[0], 400)
        self.assertEqual(self.service.updates, 0)
        self.assertEqual(self.service.store.load().revision, 0)

    def test_archive_and_memory_choices_remain_independent(self):
        status, value, _ = self.update({"categories": {"memory_learning": False}})
        self.assertEqual(status, 200)
        self.assertTrue(value["categories"]["archive_recording"])
        self.assertFalse(value["categories"]["memory_learning"])
        self.assertEqual(len(value["categories"]), 7)

    def test_corrupt_policy_is_unavailable_without_claiming_defaults(self):
        self.update({"mode": "private"})
        self.service.store.path.write_text("{broken")
        status, value, _ = self.request()
        self.assertEqual(status, 503)
        self.assertEqual(value["error"]["code"], "recording_policy_unavailable")
        status, value, _ = self.update({"mode": "retained"}, 1)
        self.assertEqual(status, 503)
        self.assertEqual(self.service.store.path.read_text(), "{broken")

    def test_postpublication_durability_error_reports_uncertainty(self):
        publish = self.service.store._publish
        def uncertain(directory, policy):
            publish(directory, policy)
            raise RecordingPolicyDurabilityError("synthetic directory fsync failure")
        with patch.object(self.service.store, "_publish", side_effect=uncertain):
            status, value, _ = self.update({"mode": "private"})
        self.assertEqual(status, 503)
        self.assertEqual(value["error"]["code"], "recording_policy_commit_unconfirmed")
        self.assertEqual(self.service.updates, 1)
        status, value, _ = self.request()
        self.assertEqual((value["revision"], value["mode"]), (1, "private"))

    def test_chat_forwards_private_mode_and_cannot_override_configured_private(self):
        status, value, _ = self.request(path="/api/chat/messages",
            payload={"message": "synthetic", "recording_mode": "private"}, bearer=True)
        self.assertEqual((status, value["recording"]["mode"]), (201, "private"))
        self.update({"mode": "private"})
        status, value, _ = self.request(path="/api/chat/messages",
            payload={"message": "synthetic", "recording_mode": "retained"}, bearer=True)
        self.assertEqual((status, value["recording"]["mode"]), (201, "private"))
        status, _, _ = self.request(path="/api/chat/messages",
            payload={"message": "synthetic", "recording_mode": "bad"}, bearer=True)
        self.assertEqual(status, 400)
        self.assertEqual(len(self.service.sent), 2)


if __name__ == "__main__":
    unittest.main()

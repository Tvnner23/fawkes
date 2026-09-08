import os
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request
import urllib.error
import json
from pathlib import Path

from src.app.server import FawkesAppServer
from src.capabilities.phoenix_presence import PresenceProfileStore, WORKSHOP_STATIC_CONTRACT_VERSION
from tests.presence_glb_fixture import synthetic_presence_glb, synthetic_workshop_glb


class PresenceService:
    instance_id = "presence-http-phoenix"
    def __init__(self, root): self.root = root
    def store(self): return PresenceProfileStore(self.instance_id, root=self.root / "profiles", asset_root=self.root / "assets")
    def presence_profile(self): return self.store().public()
    def presence_asset_path(self, filename):
        store = self.store(); profile = store.load(); asset = profile.get("asset")
        if not asset or asset.get("filename") != filename: return None
        target = store.asset_root / filename
        return target if target.is_file() else None


class PresenceHTTPToClientAcceptanceTests(unittest.TestCase):
    def test_request_inbox_observation_is_authenticated_and_not_rider_activity(self):
        if os.getenv("FAWKES_HTTP_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_HTTP_ACCEPTANCE=1 where loopback sockets are permitted")
        with tempfile.TemporaryDirectory() as tmp:
            service = PresenceService(Path(tmp))
            service.development_dashboard = lambda: {"human_review_items": []}
            service.development_attention_projection = lambda **kw: {"attention": []}
            token = "synthetic-observation-token"
            server = FawkesAppServer(("127.0.0.1", 0), chat_service=service, app_token=token)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                with mock.patch("src.app.server.RiderActivityStore") as activity:
                    for endpoint in ("dashboard", "attention"):
                        url = f"http://127.0.0.1:{server.server_port}/api/development/{endpoint}?observation=true"
                        with self.assertRaises(urllib.error.HTTPError) as denied:
                            urllib.request.urlopen(url, timeout=5)
                        self.assertEqual(denied.exception.code, 401)
                        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                        with urllib.request.urlopen(request, timeout=5) as response:
                            self.assertEqual(response.status, 200)
                    activity.assert_not_called()
                    asset_url = f"http://127.0.0.1:{server.server_port}/presence-resident.js"
                    with urllib.request.urlopen(asset_url, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn("text/javascript", response.headers["Content-Type"])
                        self.assertIn(b"export function mountResident", response.read())
                    url = f"http://127.0.0.1:{server.server_port}/api/development/dashboard"
                    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}), timeout=5) as response:
                        self.assertEqual(response.status, 200)
                    activity.return_value.touch.assert_called_once_with(authenticated_rider=True)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_authenticated_profile_renders_truthful_fallback_on_mobile_and_desktop(self):
        if os.getenv("FAWKES_HTTP_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_HTTP_ACCEPTANCE=1 where loopback sockets are permitted")
        with tempfile.TemporaryDirectory() as tmp:
            token = "ephemeral-presence-acceptance-token"
            service = PresenceService(Path(tmp))
            server = FawkesAppServer(("127.0.0.1", 0), chat_service=service, app_token=token)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                base = {**os.environ, "FAWKES_TEST_BASE_URL": f"http://127.0.0.1:{server.server_port}", "FAWKES_TEST_TOKEN": token}
                results = [subprocess.run(["node", "tests/js/app_http_presence_harness.mjs"],
                    cwd=os.path.dirname(os.path.dirname(__file__)), env={**base, "FAWKES_TEST_VIEWPORT": viewport},
                    text=True, capture_output=True, timeout=20) for viewport in ("mobile", "desktop")]
                source = Path(tmp) / "synthetic-fixture-not-fawkes.glb"; source.write_bytes(synthetic_presence_glb())
                registered = service.store().install_development_asset(source, asset_id="synthetic.test.fixture", revision=1,
                    rights={"license": "synthetic-test-only", "creator": "automated-test"}, actor_principal_id="developer:test")
                asset_url = f"http://127.0.0.1:{server.server_port}/assets/presence/{registered['asset']['filename']}"
                served = urllib.request.urlopen(asset_url, timeout=10)
                served_body = served.read(); served_mime = served.headers.get_content_type()
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
        for result in results:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"health":"unavailable"', result.stdout)
            self.assertIn('"renderer":"fallback"', result.stdout)
            self.assertIn('"visible":true', result.stdout)
            self.assertIn('"thinking":true', result.stdout)
            self.assertIn('"invoked":true', result.stdout)
            self.assertIn('"chat_focused":true', result.stdout)
            self.assertIn('"three_dimensional_verified":false', result.stdout)
        self.assertEqual(served_mime, "model/gltf-binary")
        self.assertEqual(served_body, synthetic_presence_glb())

    def test_authenticated_profile_serves_static_workshop_manifestation_truthfully(self):
        if os.getenv("FAWKES_HTTP_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_HTTP_ACCEPTANCE=1 where loopback sockets are permitted")
        with tempfile.TemporaryDirectory() as tmp:
            token = "ephemeral-presence-workshop-token"
            service = PresenceService(Path(tmp))
            source = Path(tmp) / "synthetic-workshop-not-fawkes.glb"; source.write_bytes(synthetic_workshop_glb())
            registered = service.store().install_development_asset(source, asset_id="synthetic.workshop.fixture", revision=1,
                rights={"license": "synthetic-test-only", "creator": "automated-test"},
                actor_principal_id="developer:test", contract_version=WORKSHOP_STATIC_CONTRACT_VERSION)
            server = FawkesAppServer(("127.0.0.1", 0), chat_service=service, app_token=token)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/presence",
                    headers={"Authorization": f"Bearer {token}"})
                profile = json.load(urllib.request.urlopen(request, timeout=10))
                denied = None
                try: urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/presence", timeout=10)
                except urllib.error.HTTPError as exc:
                    denied = exc.code; exc.close()
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
        self.assertEqual(denied, 401)
        self.assertEqual(profile["health"]["status"], "live")
        self.assertEqual(profile["asset"]["asset_id"], registered["asset"]["asset_id"])
        self.assertEqual(profile["asset"]["rig_contract_version"], WORKSHOP_STATIC_CONTRACT_VERSION)
        self.assertFalse(profile["asset"]["inspection"]["production_contract_complete"])


if __name__ == "__main__": unittest.main()

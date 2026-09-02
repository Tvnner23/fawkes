import subprocess
import os
import tempfile
import unittest
from pathlib import Path
from tests.presence_glb_fixture import synthetic_presence_glb, synthetic_workshop_glb


ROOT = Path(__file__).resolve().parent.parent


class PresenceClientTests(unittest.TestCase):
    def test_modular_client_fallback_lifecycle_interaction_and_off(self):
        result = subprocess.run(["node", "tests/js/presence_controller_harness.mjs"], cwd=ROOT,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for expected in ('"fallback_visible":true', '"thinking":true',
                         '"duplicate_suppressed":true', '"keyboard_invoked":true',
                         '"presence_off":true'):
            self.assertIn(expected, result.stdout)

    def test_three_renderer_is_isolated_and_locally_bundled(self):
        app = (ROOT / "src/app/static/app.js").read_text()
        adapter = (ROOT / "src/app/static/presence-renderer-three.js").read_text()
        bundle = ROOT / "src/app/static/presence-three.bundle.js"
        self.assertNotIn("THREE.", app)
        self.assertNotIn("GLTFLoader", app)
        self.assertIn("FawkesThreeRuntime", adapter)
        self.assertIn("profile.asset.rig_contract_version", adapter)
        self.assertIn("presence-workshop-static-1", (ROOT / "src/app/presence-three-entry.js").read_text())
        self.assertIn("Box3().setFromObject", (ROOT / "src/app/presence-three-entry.js").read_text())
        self.assertTrue(bundle.is_file())
        self.assertGreater(bundle.stat().st_size, 100_000)

    def test_synthetic_glb_loads_actions_animation_and_independent_palette_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "synthetic-contract-fixture-not-fawkes.glb"
            fixture.write_bytes(synthetic_presence_glb())
            result = subprocess.run(["node", "tests/js/presence_glb_pipeline_harness.mjs"], cwd=ROOT,
                env={**os.environ, "FAWKES_TEST_GLB": str(fixture)}, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for expected in ('"fixture_only":true', '"mesh_loaded":true', '"actions_loaded":true',
                         '"animated":true', '"plumage_primary"', '"expression_crest"',
                         '"expression_feather_tips"', '"flame_accent"',
                         '"color":"#112233"', '"color":"#778899"',
                         '"color":"#aabbcc"', '"emissive":"#ff3300"'):
            self.assertIn(expected, result.stdout)

    def test_static_workshop_glb_loads_with_bounds_without_animation_or_palette_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "synthetic-workshop-not-fawkes.glb"
            fixture.write_bytes(synthetic_workshop_glb())
            result = subprocess.run(["node", "tests/js/presence_workshop_glb_pipeline_harness.mjs"], cwd=ROOT,
                env={**os.environ, "FAWKES_TEST_GLB": str(fixture)}, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for expected in ('"workshop_only":true', '"mesh_loaded":true', '"animations":[]',
                         '"palette_channels_applied":[]', '"runtime_parse":true'):
            self.assertIn(expected, result.stdout)

    def test_presence_surface_and_modules_are_served_without_replacing_chat(self):
        html = (ROOT / "src/app/static/index.html").read_text()
        self.assertIn('id="phoenix-presence"', html)
        self.assertIn('type="module" src="/presence-bootstrap.js"', html)
        self.assertIn('id="chat-view"', html)
        self.assertIn('id="composer"', html)


if __name__ == "__main__": unittest.main()

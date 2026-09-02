import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.runtime.production_control import control_component


ROOT = Path(__file__).resolve().parents[1]


class DevelopmentSummonTests(unittest.TestCase):
    def test_existing_authenticated_development_view_has_required_actions(self):
        html = (ROOT / "src/app/static/index.html").read_text()
        javascript = (ROOT / "src/app/static/app.js").read_text()
        for label in ("Start Development Task", "Live Activity", "Fawkes Status / Failures"):
            self.assertIn(label, html)
        self.assertIn("Review Current Candidate", javascript)
        self.assertIn("Exact diff / tests / evidence", javascript)
        self.assertIn("awaiting_independent_review", javascript)
        self.assertIn("/api/development/runtime-control", javascript)

    def test_shortcut_opens_development_without_terminal(self):
        source = (ROOT / "deploy/windows/Install-FawkesDevelopmentShortcut.ps1").read_text()
        self.assertIn("http://localhost:8787/?view=developer", source)
        self.assertIn("Fawkes Development.url", source)
        self.assertNotIn("powershell.exe", source.lower())
        self.assertNotIn("wsl.exe", source.lower())

    @patch("src.runtime.production_control.subprocess.run")
    def test_runtime_control_is_fixed_allowlist_and_zero_development_authority(self, run):
        run.return_value = Mock(returncode=0, stdout="", stderr="")
        result = control_component("discord_bridge", "restart")
        self.assertFalse(result["creates_development_authority"])
        self.assertEqual(run.call_args.args[0], ["/usr/bin/sudo", "-n", "/usr/bin/systemctl",
                                                 "restart", "fawkes-discord.service"])
        with self.assertRaises(ValueError):
            control_component("arbitrary", "restart")
        with self.assertRaises(ValueError):
            control_component("stack", "enable")

    def test_login_projection_is_ready_and_idle_without_model_invocation(self):
        source = (ROOT / "src/runtime/chat_service.py").read_text()
        self.assertIn('"development_coordinator": {"state": "READY"}', source)
        self.assertIn('"worker_launcher": {"state": "IDLE"}', source)
        self.assertIn('"reviewer_launcher": {"state": "IDLE"}', source)

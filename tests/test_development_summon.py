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

    def test_windows_attention_is_persistent_fawkes_toast_with_exact_deep_link(self):
        runner = (ROOT / "deploy/windows/FawkesAttention.ps1").read_text()
        installer = (ROOT / "deploy/windows/Install-FawkesAttentionTask.ps1").read_text()
        self.assertIn("ToastNotificationManager", runner)
        self.assertIn("ProjectFawkes.Attention", runner)
        self.assertIn("activationType='protocol'", runner)
        self.assertIn("fawkes-attention://open?attention=", runner)
        self.assertIn("--pending-attention", runner)
        self.assertIn("Remove-ResolvedFawkesToasts", runner)
        self.assertIn("Start-Sleep -Seconds 3", runner)
        self.assertIn("Sort-Object created_at -Descending", runner)
        self.assertNotIn("NotifyIcon", runner)
        self.assertNotIn("ShowBalloonTip", runner)
        self.assertIn("Fawkes Attention.lnk", installer)
        self.assertIn("ProjectFawkes.Attention", installer)
        self.assertIn("FawkesAttentionLauncher.exe", installer)
        self.assertIn("HKCU:\\Software\\Classes\\fawkes-attention", installer)
        self.assertIn("^attention-(?:[a-f0-9]{64}|test)$", installer)

    def test_attention_deep_link_renders_plain_language_bounded_choices(self):
        javascript = (ROOT / "src/app/static/app.js").read_text()
        self.assertIn("Tanner: Fawkes is paused and needs your decision", javascript)
        self.assertIn("['approve_once','Approve Once'", javascript)
        self.assertIn("['deny','Deny'", javascript)
        self.assertIn("['cancel_campaign','Cancel Campaign'", javascript)
        self.assertIn("humanTarget=qualificationLabel||'this Fawkes request'", javascript)
        self.assertNotIn("`Approve Once — ${record.campaign_id}`", javascript)
        self.assertNotIn("`Deny — ${record.campaign_id}`", javascript)
        self.assertNotIn("`Cancel Campaign — ${record.campaign_id}`", javascript)
        self.assertIn("startup.get('attention')", javascript)
        self.assertIn("scrollIntoView", javascript)
        self.assertIn("BUILD MISMATCH", javascript)
        self.assertIn("/api/development/attention/", javascript)
        self.assertIn('data-section="attention"', (ROOT / "src/app/static/index.html").read_text())

    def test_phoenix_board_is_read_only_bounded_projection(self):
        javascript = (ROOT / "src/app/static/app.js").read_text()
        self.assertIn("Worker Pulse / Phoenix Board", javascript)
        self.assertIn("renderPhoenixBoard(campaigns, attentionItems)", javascript)
        self.assertIn("PHOENIX_BOARD_CAMPAIGN_LIMIT = 6", javascript)
        self.assertIn("PHOENIX_BOARD_ACTIVITY_LIMIT = 3", javascript)
        self.assertIn("campaigns.slice(0, PHOENIX_BOARD_CAMPAIGN_LIMIT)", javascript)
        self.assertIn("activity.slice(-PHOENIX_BOARD_ACTIVITY_LIMIT)", javascript)
        self.assertIn("Provider / model usage: Unavailable in canonical projection", javascript)
        board = javascript[javascript.index("function renderPhoenixBoard"):javascript.index("function renderDeveloperSection")]
        self.assertNotIn("request(", board)
        self.assertNotIn("addEventListener", board)
        self.assertNotIn("JSON.stringify", board)

    def test_phoenix_board_allowlists_safe_projection_fields_and_keeps_decisions_immutable(self):
        javascript = (ROOT / "src/app/static/app.js").read_text()
        board = javascript[javascript.index("function renderPhoenixBoard"):javascript.index("function renderDeveloperSection")]
        for forbidden in ("hidden_reasoning", "credentials", "private_body",
                          "memory", "archive", "raw_transcript", "reference_arrays"):
            self.assertNotIn(forbidden, board.lower())
        self.assertIn("exact_worker_bodies_remain_in_worker_exchange", board)
        self.assertIn("hidden_chain_of_thought_exposed === false", board)
        self.assertIn("const immutableIdentity={attention_id:attention.attention_id", javascript)
        self.assertIn("body:JSON.stringify({choice,identity:immutableIdentity})", javascript)

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
